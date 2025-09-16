import os
from dotenv import load_dotenv
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
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


class CurrentUser:
    def __init__(
        self, user_id: str, email: Optional[str] = None, name: Optional[str] = None
    ):
        self.user_id = user_id
        self.email = email
        self.name = name


async def fetch_user_from_clerk(user_id: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch user details from Clerk API"""
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
                    # Get the primary email or first email
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
                    name_parts = []
                    if first_name:
                        name_parts.append(first_name)
                    if last_name:
                        name_parts.append(last_name)
                    name = " ".join(name_parts) if name_parts else None
                elif email:
                    # Fallback to email prefix
                    name = email.split("@")[0]

                return email, name
            else:
                print(f"Failed to fetch user from Clerk API: {response.status_code}")
                return None, None

    except Exception as e:
        print(f"Error fetching user from Clerk API: {e}")
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

        # If we don't have email or name from JWT, fetch from Clerk API
        if not email or not name:
            print(
                f"JWT missing user details, fetching from Clerk API for user: {user_id}"
            )
            api_email, api_name = await fetch_user_from_clerk(user_id)
            if not email and api_email:
                email = api_email
            if not name and api_name:
                name = api_name

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        return CurrentUser(user_id=user_id, email=email, name=name)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
