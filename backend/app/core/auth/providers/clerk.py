"""Clerk implementation of ``AuthProvider``.

Verifies Clerk-issued JWTs against Clerk's published JWKS and, when the
token doesn't carry email/name, enriches by calling Clerk's REST API.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
import jwt
from jwt import PyJWKClient

from app.core.auth.base import AuthError, AuthProvider, ProviderClaims

logger = logging.getLogger(__name__)

_USER_CACHE_TTL_SECONDS = 3600
_CLOCK_SKEW_LEEWAY_SECONDS = 30


class ClerkAuthProvider:
    """Verifies Clerk JWTs and resolves Clerk org claims.

    Args:
        jwt_issuer: Clerk JWT issuer URL (e.g.
            ``https://example.clerk.accounts.dev``). The JWKS endpoint is
            derived from this.
        secret_key: Clerk secret key used to call the REST API for enrichment.
    """

    def __init__(self, jwt_issuer: str, secret_key: str):
        self._jwt_issuer = jwt_issuer
        self._secret_key = secret_key
        self._jwks_client = PyJWKClient(f"{jwt_issuer}/.well-known/jwks.json")
        self._user_cache: dict[str, tuple[Optional[str], Optional[str], float]] = {}

    async def verify_token(self, token: str) -> ProviderClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._jwt_issuer,
                options={"verify_exp": True},
                leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}") from exc
        except Exception as exc:
            raise AuthError(f"Authentication failed: {exc}") from exc

        user_id = payload.get("sub")
        if not user_id:
            raise AuthError("Invalid token: no user ID")

        email = payload.get("email")
        name = _extract_name_from_jwt(payload, email)

        organization_id = payload.get("org_id")
        organization_slug = payload.get("org_slug")
        organization_role = payload.get("org_role")

        # Clerk also embeds active-org info in a nested "o" claim; fall back
        # to that if the top-level fields are absent.
        org_claim = payload.get("o")
        if isinstance(org_claim, dict):
            organization_id = organization_id or org_claim.get("id")
            organization_slug = (
                organization_slug or org_claim.get("slg") or org_claim.get("slug")
            )
            organization_role = (
                organization_role or org_claim.get("rol") or org_claim.get("role")
            )

        if not organization_id:
            logger.warning(
                "No org_id in JWT for user %s. User may not have an active organization.",
                user_id,
            )

        return ProviderClaims(
            sub=user_id,
            email=email,
            name=name,
            organization_id=organization_id,
            organization_slug=organization_slug,
            organization_role=organization_role,
            raw=payload,
        )

    async def enrich(self, claims: ProviderClaims) -> ProviderClaims:
        """Fill missing email/name by calling Clerk's REST API (cached)."""
        if claims.email and claims.name:
            return claims

        api_email, api_name = await self._fetch_user_from_clerk_cached(claims.sub)

        return ProviderClaims(
            sub=claims.sub,
            email=claims.email or api_email,
            name=claims.name or api_name,
            organization_id=claims.organization_id,
            organization_slug=claims.organization_slug,
            organization_role=claims.organization_role,
            raw=claims.raw,
        )

    async def _fetch_user_from_clerk_cached(
        self, user_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        cached = self._user_cache.get(user_id)
        if cached is not None:
            email, name, ts = cached
            if time.time() - ts < _USER_CACHE_TTL_SECONDS:
                return email, name

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.clerk.com/v1/users/{user_id}",
                    headers={
                        "Authorization": f"Bearer {self._secret_key}",
                        "Content-Type": "application/json",
                    },
                )
            if response.status_code != 200:
                return None, None

            user_data = response.json()
            email = _primary_email(user_data.get("email_addresses", []))
            name = _full_name(
                user_data.get("first_name"), user_data.get("last_name"), email
            )

            self._user_cache[user_id] = (email, name, time.time())
            return email, name
        except Exception as exc:
            logger.warning("Failed to enrich Clerk user %s: %s", user_id, exc)
            return None, None


def _extract_name_from_jwt(payload: dict, email: Optional[str]) -> Optional[str]:
    full_name = payload.get("full_name")
    if full_name:
        return full_name
    first_name = payload.get("first_name")
    last_name = payload.get("last_name")
    if first_name or last_name:
        return " ".join(p for p in (first_name, last_name) if p)
    if email:
        return email.split("@")[0]
    return None


def _primary_email(email_addresses: list[dict]) -> Optional[str]:
    if not email_addresses:
        return None
    primary = next(
        (addr for addr in email_addresses if addr.get("primary")), email_addresses[0]
    )
    return primary.get("email_address")


def _full_name(
    first_name: Optional[str], last_name: Optional[str], email: Optional[str]
) -> Optional[str]:
    if first_name or last_name:
        parts = [p for p in (first_name, last_name) if p]
        return " ".join(parts) if parts else None
    if email:
        return email.split("@")[0]
    return None


__all__ = ["ClerkAuthProvider", "AuthProvider"]
