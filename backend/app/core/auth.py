import os
from dotenv import load_dotenv
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

load_dotenv()

security = HTTPBearer()

# Clerk configuration
CLERK_JWT_ISSUER = os.getenv("CLERK_JWT_ISSUER")
if not CLERK_JWT_ISSUER:
    raise ValueError("CLERK_JWT_ISSUER environment variable is required")

# Construct JWKS URL from issuer
JWKS_URL = f"{CLERK_JWT_ISSUER}/.well-known/jwks.json"
jwks_client = PyJWKClient(JWKS_URL)


class CurrentUser:
    def __init__(self, user_id: str, email: Optional[str] = None):
        self.user_id = user_id
        self.email = email


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

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        return CurrentUser(user_id=user_id, email=email)

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
