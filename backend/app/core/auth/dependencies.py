"""FastAPI dependency that turns a bearer token into a ``CurrentUser``."""

from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth.base import AuthError, AuthProvider, CurrentUser
from app.core.auth.factory import get_auth_provider
from app.core.auth.identity import find_or_provision
from app.core.config import settings

logger = logging.getLogger(__name__)

_security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    provider: AuthProvider = Depends(get_auth_provider),
) -> CurrentUser:
    """Verify the bearer token, resolve app-owned identity, and return the user.

    The provider produces ``ProviderClaims``; this dependency then calls
    ``find_or_provision`` to resolve (or create) the internal ``users`` row,
    giving every route a stable ``internal_user_id`` regardless of which auth
    provider was used.

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

    internal_user_id = None
    try:
        # The Supabase client is synchronous; run it in a worker thread so
        # identity resolution never blocks the event loop. Cache hits inside
        # find_or_provision make this cheap on subsequent requests.
        identity = await asyncio.to_thread(
            find_or_provision,
            provider=settings.AUTH_PROVIDER.lower(),
            provider_user_id=claims.sub,
            email=claims.email,
            name=claims.name,
            email_verified=claims.raw.get("email_verified") is True,
        )
        internal_user_id = str(identity.internal_user_id)
    except Exception:
        logger.warning(
            "find_or_provision failed for %s — continuing without internal_user_id",
            claims.sub,
            exc_info=True,
        )

    return CurrentUser(
        user_id=claims.sub,
        internal_user_id=internal_user_id,
        email=claims.email,
        name=claims.name,
        organization_id=claims.organization_id,
        organization_slug=claims.organization_slug,
        organization_role=claims.organization_role,
    )
