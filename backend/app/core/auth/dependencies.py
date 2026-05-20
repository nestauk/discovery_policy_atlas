"""FastAPI dependency that turns a bearer token into a ``CurrentUser``."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth.base import AuthError, AuthProvider, CurrentUser
from app.core.auth.factory import get_auth_provider

_security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    provider: AuthProvider = Depends(get_auth_provider),
) -> CurrentUser:
    """Verify the bearer token and return the authenticated user.

    The provider produces ``ProviderClaims``; this dependency layers any
    app-side enrichment (currently a Clerk REST fallback for missing
    email/name) before assembling the ``CurrentUser`` consumed by routes.

    Args:
        credentials: Bearer token credentials extracted from the
            ``Authorization`` header.
        provider: The active auth provider, resolved from settings.

    Returns:
        The authenticated ``CurrentUser``.

    Raises:
        HTTPException: HTTP 401 if the token is invalid or expired.
    """
    try:
        claims = await provider.verify_token(credentials.credentials)
        claims = await provider.enrich(claims)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=exc.detail) from exc

    return CurrentUser(
        user_id=claims.sub,
        email=claims.email,
        name=claims.name,
        organization_id=claims.organization_id,
        organization_slug=claims.organization_slug,
        organization_role=claims.organization_role,
    )
