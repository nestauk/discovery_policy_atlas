"""Cognito implementation of ``AuthProvider``.

Verifies Cognito **access** tokens against the User Pool JWKS. The frontend
should send the access token on API calls (not the ID token).

Access tokens don't carry user attributes, so ``enrich`` calls the Cognito
Admin ``GetUser`` API to fill ``email``, ``name`` and ``email_verified``
(cached per process). This is what lets app-side identity resolution link a
Cognito sign-in to an existing internal user by verified email.

Note: organisation fields are always ``None`` — Cognito has no Clerk-style org
claims. Org membership is resolved app-side from the ``organizations`` /
``organization_memberships`` tables introduced in Phase 6.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import boto3
import jwt
from jwt import PyJWKClient

from app.core.auth.base import AuthError, ProviderClaims

logger = logging.getLogger(__name__)

_CLOCK_SKEW_LEEWAY_SECONDS = 30
_ATTR_CACHE_TTL_SECONDS = 3600
# Failures are cached for a short window so a missing IAM permission or a
# transient Cognito error can't turn every request into a fresh AdminGetUser
# call (and a fresh traceback). Short enough that genuine transients recover.
_ATTR_ERROR_CACHE_TTL_SECONDS = 300


class CognitoAuthProvider:
    """Verifies Cognito access tokens for a single User Pool app client.

    Args:
        region: AWS region of the User Pool (e.g. ``eu-west-2``).
        user_pool_id: Cognito User Pool ID.
        app_client_id: SPA app client ID; ``client_id`` in the token must
            match this value.
    """

    def __init__(self, region: str, user_pool_id: str, app_client_id: str):
        self._region = region
        self._user_pool_id = user_pool_id
        self._app_client_id = app_client_id
        self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self._jwks_client = PyJWKClient(f"{self._issuer}/.well-known/jwks.json")
        self._idp_client: Optional[Any] = None
        # Maps username -> (attributes, expiry_epoch). A negatively cached
        # failure is stored as an empty dict with a shorter expiry.
        self._attr_cache: dict[str, tuple[dict[str, str], float]] = {}

    async def verify_token(self, token: str) -> ProviderClaims:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={"verify_aud": False},
                leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}") from exc
        except Exception as exc:
            raise AuthError(f"Authentication failed: {exc}") from exc

        token_use = payload.get("token_use")
        if token_use != "access":
            raise AuthError(
                f"Invalid token: expected access token, got token_use={token_use!r}"
            )

        client_id = payload.get("client_id")
        if client_id != self._app_client_id:
            raise AuthError("Invalid token: client_id mismatch")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthError("Invalid token: no user ID")

        email = payload.get("email")
        name = _extract_name(payload, email)

        return ProviderClaims(
            sub=user_id,
            email=email,
            name=name,
            organization_id=None,
            organization_slug=None,
            organization_role=None,
            raw=payload,
        )

    async def enrich(self, claims: ProviderClaims) -> ProviderClaims:
        """Fill email/name/email_verified via Cognito Admin ``GetUser`` (cached).

        Access tokens carry neither user attributes nor ``email_verified``, so
        this is the only way the app sees them for Cognito. ``email_verified``
        is written into ``raw`` because that's where the FastAPI dependency
        reads it to decide whether email-based identity linking is allowed.

        Failures degrade gracefully: the original claims are returned unchanged
        so a transient Cognito/IAM problem can't break authentication.

        Args:
            claims: The claims produced by ``verify_token``.

        Returns:
            The claims, enriched with attributes from the User Pool where
            available.
        """
        if claims.email and claims.name and "email_verified" in claims.raw:
            return claims

        username = claims.raw.get("username") or claims.sub
        try:
            attrs = await asyncio.to_thread(self._fetch_attributes_cached, username)
        except Exception:
            logger.warning(
                "Cognito AdminGetUser failed for %s — returning unenriched claims",
                username,
                exc_info=True,
            )
            return claims

        if not attrs:
            return claims

        email = claims.email or attrs.get("email")
        name = claims.name or _name_from_attributes(attrs, email)

        new_raw = {**claims.raw}
        if "email_verified" in attrs:
            new_raw["email_verified"] = attrs["email_verified"] == "true"

        return ProviderClaims(
            sub=claims.sub,
            email=email,
            name=name,
            organization_id=claims.organization_id,
            organization_slug=claims.organization_slug,
            organization_role=claims.organization_role,
            raw=new_raw,
        )

    def _get_idp_client(self) -> Any:
        if self._idp_client is None:
            self._idp_client = boto3.client("cognito-idp", region_name=self._region)
        return self._idp_client

    def _fetch_attributes_cached(self, username: str) -> dict[str, str]:
        cached = self._attr_cache.get(username)
        if cached is not None and time.time() < cached[1]:
            return cached[0]

        try:
            response = self._get_idp_client().admin_get_user(
                UserPoolId=self._user_pool_id,
                Username=username,
            )
        except Exception:
            # Negatively cache so a missing permission or transient error
            # doesn't trigger an AdminGetUser call on every subsequent request.
            self._attr_cache[username] = (
                {},
                time.time() + _ATTR_ERROR_CACHE_TTL_SECONDS,
            )
            raise

        attrs = {
            attr["Name"]: attr["Value"] for attr in response.get("UserAttributes", [])
        }
        self._attr_cache[username] = (attrs, time.time() + _ATTR_CACHE_TTL_SECONDS)
        return attrs


def _extract_name(payload: dict[str, Any], email: Optional[str]) -> Optional[str]:
    name = payload.get("name")
    if name:
        return name
    username = payload.get("username")
    if username and "@" not in username:
        return username
    if email:
        return email.split("@")[0]
    return None


def _name_from_attributes(attrs: dict[str, str], email: Optional[str]) -> Optional[str]:
    name = attrs.get("name")
    if name:
        return name
    given = attrs.get("given_name")
    family = attrs.get("family_name")
    if given or family:
        return " ".join(p for p in (given, family) if p)
    if email:
        return email.split("@")[0]
    return None
