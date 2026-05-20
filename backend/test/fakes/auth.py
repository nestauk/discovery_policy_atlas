"""Fake ``AuthProvider`` for tests.

Lets a test set up an authenticated user without standing up Clerk or
Cognito. Use ``install_fake_auth(app, user)`` from a fixture to override
the FastAPI dependency in a ``TestClient``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from fastapi import FastAPI

from app.core.auth.base import AuthError, ProviderClaims
from app.core.auth.dependencies import get_current_user
from app.core.auth.factory import get_auth_provider


class FakeAuthProvider:
    """An ``AuthProvider`` that returns canned claims for any token.

    Args:
        claims: The claims to return from ``verify_token``. If ``None``,
            any token presented will be rejected with ``AuthError``.
        raise_on_verify: Override to force ``verify_token`` failures.
    """

    def __init__(
        self,
        claims: Optional[ProviderClaims] = None,
        raise_on_verify: bool = False,
    ):
        self._claims = claims
        self._raise = raise_on_verify
        self.last_token: Optional[str] = None

    async def verify_token(self, token: str) -> ProviderClaims:
        self.last_token = token
        if self._raise or self._claims is None:
            raise AuthError("Invalid token (fake provider)")
        return self._claims

    async def enrich(self, claims: ProviderClaims) -> ProviderClaims:
        return replace(claims)


def install_fake_auth(
    app: FastAPI,
    *,
    user_id: str = "user_test",
    email: Optional[str] = "[email protected]",
    name: Optional[str] = "Test User",
    organization_id: Optional[str] = None,
    organization_slug: Optional[str] = None,
    organization_role: Optional[str] = None,
) -> FakeAuthProvider:
    """Wire a ``FakeAuthProvider`` into ``app`` for the duration of a test.

    This overrides ``get_auth_provider`` so any route that depends on
    ``get_current_user`` resolves to the fake user. The returned provider
    can be mutated by tests via its public attributes.

    Args:
        app: The FastAPI application under test.
        user_id: The ``sub`` to return in the canned claims.
        email: Email to return (or ``None``).
        name: Display name to return (or ``None``).
        organization_id: Optional organisation identifier.
        organization_slug: Optional organisation slug.
        organization_role: Optional organisation role.

    Returns:
        The installed ``FakeAuthProvider`` instance.
    """
    claims = ProviderClaims(
        sub=user_id,
        email=email,
        name=name,
        organization_id=organization_id,
        organization_slug=organization_slug,
        organization_role=organization_role,
    )
    fake = FakeAuthProvider(claims=claims)
    app.dependency_overrides[get_auth_provider] = lambda: fake
    return fake


def uninstall_fake_auth(app: FastAPI) -> None:
    """Remove the fake auth override from ``app``."""
    app.dependency_overrides.pop(get_auth_provider, None)
    app.dependency_overrides.pop(get_current_user, None)
