"""Resolves the configured ``AuthProvider`` once at startup."""

from __future__ import annotations

from functools import lru_cache

from app.core.auth.base import AuthProvider
from app.core.auth.providers.clerk import ClerkAuthProvider
from app.core.auth.providers.cognito import CognitoAuthProvider
from app.core.config import settings


@lru_cache(maxsize=1)
def get_auth_provider() -> AuthProvider:
    """Return the active auth provider based on ``settings.AUTH_PROVIDER``.

    The provider is cached for the process lifetime so JWKS clients and
    in-memory caches are shared across requests.

    Returns:
        The configured ``AuthProvider`` implementation.

    Raises:
        ValueError: If ``AUTH_PROVIDER`` is unknown or its required env vars
            are missing.
    """
    provider = settings.AUTH_PROVIDER.lower()

    if provider == "clerk":
        if not settings.CLERK_JWT_ISSUER:
            raise ValueError("CLERK_JWT_ISSUER is required when AUTH_PROVIDER=clerk")
        if not settings.CLERK_SECRET_KEY:
            raise ValueError("CLERK_SECRET_KEY is required when AUTH_PROVIDER=clerk")
        return ClerkAuthProvider(
            jwt_issuer=settings.CLERK_JWT_ISSUER,
            secret_key=settings.CLERK_SECRET_KEY,
        )

    if provider == "cognito":
        if not settings.COGNITO_REGION:
            raise ValueError("COGNITO_REGION is required when AUTH_PROVIDER=cognito")
        if not settings.COGNITO_USER_POOL_ID:
            raise ValueError(
                "COGNITO_USER_POOL_ID is required when AUTH_PROVIDER=cognito"
            )
        if not settings.COGNITO_APP_CLIENT_ID:
            raise ValueError(
                "COGNITO_APP_CLIENT_ID is required when AUTH_PROVIDER=cognito"
            )
        return CognitoAuthProvider(
            region=settings.COGNITO_REGION,
            user_pool_id=settings.COGNITO_USER_POOL_ID,
            app_client_id=settings.COGNITO_APP_CLIENT_ID,
        )

    raise ValueError(f"Unknown AUTH_PROVIDER: {settings.AUTH_PROVIDER!r}")
