"""Core types and the provider interface used by every auth backend.

Concrete providers (Clerk, Cognito, etc.) implement ``AuthProvider`` and live
under ``app.core.auth.providers``. The FastAPI dependency in
``app.core.auth.dependencies`` only depends on this module.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass(frozen=True)
class ProviderClaims:
    """Verified claims returned by an ``AuthProvider``.

    This is the raw, provider-specific output of token verification. The
    FastAPI dependency layers app-side lookups (organisations, internal user
    IDs in later phases) on top of this to produce a ``CurrentUser``.

    Attributes:
        sub: The subject identifier from the provider (e.g. Clerk user ID,
            Cognito ``sub``).
        email: User email, if available in the token or via enrichment.
        name: Display name, if available.
        organization_id: Organisation identifier, if the provider embeds one
            in the token (Clerk's ``org_id``; ``None`` for providers like
            Cognito that don't have native org support).
        organization_slug: Organisation slug, where applicable.
        organization_role: User's role within the active organisation.
        raw: Any additional provider-specific claims (e.g. Clerk's nested
            ``o`` claim or Cognito's ``cognito:groups``). Reserved for
            providers that want to expose extra data without expanding the
            shared shape.
    """

    sub: str
    email: Optional[str] = None
    name: Optional[str] = None
    organization_id: Optional[str] = None
    organization_slug: Optional[str] = None
    organization_role: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated user as seen by API handlers.

    This is the shape that the existing routes consume. It mirrors
    ``ProviderClaims`` today; in later phases it will diverge as we add an
    internal Policy Atlas ``user_id`` and resolve organisations from the
    database rather than from token claims.
    """

    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    organization_id: Optional[str] = None
    organization_slug: Optional[str] = None
    organization_role: Optional[str] = None


class AuthError(Exception):
    """Raised by a provider when token verification fails.

    The FastAPI dependency maps this to HTTP 401 so providers stay
    framework-agnostic and unit-testable.
    """

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class AuthProvider(Protocol):
    """Interface every authentication provider implements."""

    async def verify_token(self, token: str) -> ProviderClaims:
        """Verify a bearer token and return its claims.

        Args:
            token: The raw bearer token from the ``Authorization`` header.

        Returns:
            The verified claims as a ``ProviderClaims`` instance.

        Raises:
            AuthError: If the token is invalid, expired, or cannot be
                verified.
        """
        ...

    async def enrich(self, claims: ProviderClaims) -> ProviderClaims:
        """Fill in missing fields by calling the provider's REST API.

        Implementations that don't need enrichment can return the claims
        unchanged. This is intentionally separate from ``verify_token`` so
        that providers can decide whether the extra network call is worth it
        (cached or behind a feature flag).
        """
        ...
