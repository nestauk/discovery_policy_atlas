import os
from dotenv import load_dotenv
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from cachetools import TTLCache
from app.core.models import CurrentUser
import httpx

load_dotenv()

security = HTTPBearer()

# Clerk configuration
CLERK_JWT_ISSUER = os.getenv("CLERK_JWT_ISSUER")
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
if not CLERK_JWT_ISSUER:
    raise ValueError("CLERK_JWT_ISSUER environment variable is required")
if not CLERK_SECRET_KEY:
    raise ValueError("CLERK_SECRET_KEY environment variable is required")

# Construct JWKS URL from issuer
JWKS_URL = f"{CLERK_JWT_ISSUER}/.well-known/jwks.json"
jwks_client = PyJWKClient(JWKS_URL)

# Simple in-memory cache for user details (fallback if not in JWT)
# TTLCache provides automatic expiry + LRU eviction when maxsize is reached
_user_cache: TTLCache[str, tuple[Optional[str], Optional[str]]] = TTLCache(
    maxsize=1000, ttl=3600
)


async def fetch_user_from_clerk_cached(
    user_id: str
) -> tuple[Optional[str], Optional[str]]:
    """Fetch user details from Clerk API with caching."""
    # Check cache first - TTLCache handles expiry automatically
    if user_id in _user_cache:
        return _user_cache[user_id]

    # Fetch from API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.clerk.com/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {CLERK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 200:
                user_data = response.json()

                # Extract email
                email_addresses = user_data.get("email_addresses", [])
                email = None
                if email_addresses:
                    primary_email = next(
                        (
                            addr
                            for addr in email_addresses
                            if addr.get("primary", False)
                        ),
                        email_addresses[0] if email_addresses else None,
                    )
                    if primary_email:
                        email = primary_email.get("email_address")

                # Extract name
                first_name = user_data.get("first_name")
                last_name = user_data.get("last_name")

                name = None
                if first_name or last_name:
                    name_parts = [n for n in [first_name, last_name] if n]
                    name = " ".join(name_parts) if name_parts else None
                elif email:
                    name = email.split("@")[0]

                # Cache the result - TTLCache handles timestamp internally
                _user_cache[user_id] = (email, name)
                return email, name
            else:
                return None, None

    except Exception:
        return None, None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CurrentUser:
    """Verify Clerk JWT token and return user info"""
    token = credentials.credentials

    try:
        # Get the signing key
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and verify the token
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=CLERK_JWT_ISSUER,
            options={"verify_exp": True},
            leeway=30,  # Allow 30 seconds of clock skew
        )

        # Extract user info
        user_id = payload.get("sub")
        email = payload.get("email")

        # Extract name information from JWT claims
        # Try different name fields that Clerk might include
        name = None
        first_name = payload.get("first_name")
        last_name = payload.get("last_name")
        full_name = payload.get("full_name")

        if full_name:
            name = full_name
        elif first_name or last_name:
            # Combine first and last name, handling None values
            name_parts = []
            if first_name:
                name_parts.append(first_name)
            if last_name:
                name_parts.append(last_name)
            name = " ".join(name_parts) if name_parts else None
        elif email:
            # Fallback to email if no name is available
            name = email.split("@")[0]  # Use email prefix as display name

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        # If we don't have email or name from JWT, fetch from Clerk API (cached)
        if not email or not name:
            api_email, api_name = await fetch_user_from_clerk_cached(user_id)
            if not email and api_email:
                email = api_email
            if not name and api_name:
                name = api_name

        # Extract organization info from JWT (Clerk Organizations)
        # Clerk may put org info in 'o' claim as nested object, or as top-level org_id/org_slug/org_role
        organization_id = payload.get("org_id")
        organization_slug = payload.get("org_slug")
        organization_role = payload.get("org_role")

        # Check for nested 'o' claim (Clerk's default org structure)
        org_claim = payload.get("o")
        if org_claim and isinstance(org_claim, dict):
            organization_id = organization_id or org_claim.get("id")
            organization_slug = (
                organization_slug or org_claim.get("slg") or org_claim.get("slug")
            )
            organization_role = (
                organization_role or org_claim.get("rol") or org_claim.get("role")
            )

        # Only warn if org is missing (don't log every successful request)
        if not organization_id:
            print(
                f"WARNING: No org_id in JWT for user {user_id}. User may not have an active organization."
            )

        return CurrentUser(
            user_id=user_id,
            email=email,
            name=name,
            organization_id=organization_id,
            organization_slug=organization_slug,
            organization_role=organization_role,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
