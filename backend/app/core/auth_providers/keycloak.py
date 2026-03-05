import os
from dotenv import load_dotenv
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from app.core.models import CurrentUser

load_dotenv()

security = HTTPBearer()

KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")
KEYCLOAK_REALM_URL = os.getenv("KEYCLOAK_REALM_URL")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID")

KEYCLOAK_BASE_ISSUER = KEYCLOAK_ISSUER or KEYCLOAK_REALM_URL

if not KEYCLOAK_BASE_ISSUER:
    raise ValueError(
        "KEYCLOAK_ISSUER or KEYCLOAK_REALM_URL environment variable is required"
    )

if not KEYCLOAK_CLIENT_ID:
    raise ValueError("KEYCLOAK_CLIENT_ID environment variable is required")

JWKS_URL = f"{KEYCLOAK_BASE_ISSUER}/protocol/openid-connect/certs"
jwks_client = PyJWKClient(JWKS_URL)


def _extract_org_slug_from_orgs(orgs: Optional[list[str]]) -> Optional[str]:
    if not orgs:
        return None
    for org_path in orgs:
        if not org_path or not isinstance(org_path, str):
            continue
        parts = [segment for segment in org_path.split("/") if segment]
        if parts:
            return parts[-1]
    return None


def _client_id_matches(payload: dict, client_id: str) -> bool:
    aud = payload.get("aud")
    azp = payload.get("azp")

    if isinstance(aud, list):
        if client_id in aud:
            return True
    elif isinstance(aud, str):
        if aud == client_id:
            return True

    if isinstance(azp, str) and azp == client_id:
        return True

    return False


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> CurrentUser:
    """Verify Keycloak JWT token and return user info."""
    token = credentials.credentials

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=KEYCLOAK_BASE_ISSUER,
            options={"verify_exp": True},
            leeway=30,
        )

        if not _client_id_matches(payload, KEYCLOAK_CLIENT_ID):
            raise HTTPException(status_code=401, detail="Invalid token: audience")

        user_id = payload.get("sub")
        email = payload.get("email")

        name = None
        first_name = payload.get("first_name")
        last_name = payload.get("last_name")
        full_name = payload.get("full_name")
        preferred_username = payload.get("preferred_username")

        if full_name:
            name = full_name
        elif first_name or last_name:
            name_parts = []
            if first_name:
                name_parts.append(first_name)
            if last_name:
                name_parts.append(last_name)
            name = " ".join(name_parts) if name_parts else None
        elif preferred_username:
            name = preferred_username
        elif email:
            name = email.split("@")[0]

        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID")

        organization_id = payload.get("org_id")
        organization_slug = payload.get("org_slug")
        organization_role = payload.get("org_role")

        org_claim = payload.get("o")
        if org_claim and isinstance(org_claim, dict):
            organization_id = organization_id or org_claim.get("id")
            organization_slug = (
                organization_slug or org_claim.get("slg") or org_claim.get("slug")
            )
            organization_role = (
                organization_role or org_claim.get("rol") or org_claim.get("role")
            )

        if not organization_slug:
            organization_slug = _extract_org_slug_from_orgs(payload.get("orgs"))

        if not organization_id and not organization_slug:
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
