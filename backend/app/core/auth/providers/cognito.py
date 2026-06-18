"""Cognito implementation of ``AuthProvider``.

Verifies Cognito **access** tokens against the User Pool JWKS. The frontend
should send the access token on API calls (not the ID token).

Known limitations (resolved in Phase 6 via app-owned identity + org tables):

* **Organisation fields are always ``None``.** Cognito has no Clerk-style
  org claims, so org-scoped project access
  (``can_access_project``, ``get_user_projects``) only allows users to see
  their own projects and demo-org projects.
* **``email``/``name`` are usually absent.** Cognito puts user attributes
  on the ID token, not the access token, so ``email`` will typically be
  ``None`` and ``name`` falls back to ``username`` (which can be a
  Cognito-generated UUID for federated users). Routes that store these
  alongside ``user_id`` (e.g. ``user_feedback``) will record those
  fallbacks until Phase 6 resolves identities from our own DB.
* **User identifier shape differs.** Cognito ``sub`` is a UUID, whereas
  existing Clerk-owned rows store ``user_<...>`` strings. The two cannot
  coexist on the same dataset without the ``user_identities`` mapping
  Phase 6 introduces.
"""

from __future__ import annotations

from typing import Any, Optional

import jwt
from jwt import PyJWKClient

from app.core.auth.base import AuthError, ProviderClaims

_CLOCK_SKEW_LEEWAY_SECONDS = 30


class CognitoAuthProvider:
    """Verifies Cognito access tokens for a single User Pool app client.

    Args:
        region: AWS region of the User Pool (e.g. ``eu-west-2``).
        user_pool_id: Cognito User Pool ID.
        app_client_id: SPA app client ID; ``client_id`` in the token must
            match this value.
    """

    def __init__(self, region: str, user_pool_id: str, app_client_id: str):
        self._app_client_id = app_client_id
        self._issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self._jwks_client = PyJWKClient(f"{self._issuer}/.well-known/jwks.json")

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
        """Access tokens rarely carry email/name; no Cognito REST fallback yet."""
        return claims


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
