"""App-owned identity resolution (find-or-provision).

Given a provider name and provider-specific user ID (from ``ProviderClaims``),
resolves or creates the internal ``users`` / ``user_identities`` rows so that
the rest of the application works with a stable internal UUID regardless of
which auth provider the user signed in with.

Resolutions are cached in memory (per process) so the database is only hit
once per user per TTL window, not on every request. The function itself is
synchronous (the Supabase client is sync); async callers should dispatch it
via ``asyncio.to_thread`` to keep the event loop unblocked.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from supabase import Client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 3600

_client: Optional[Client] = None
_identity_cache: dict[tuple[str, str], tuple["InternalIdentity", float]] = {}


def _get_client() -> Client:
    global _client
    if _client is None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY are required for identity resolution"
            )
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client


@dataclass(frozen=True)
class InternalIdentity:
    """The resolved internal identity for an authenticated user.

    Attributes:
        internal_user_id: The app-owned UUID from the ``users`` table.
        email: Email address (from our DB, may differ from token claims).
        name: Display name.
    """

    internal_user_id: UUID
    email: Optional[str] = None
    name: Optional[str] = None


def find_or_provision(
    provider: str,
    provider_user_id: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    email_verified: bool = False,
) -> InternalIdentity:
    """Resolve an external identity to an internal user, creating if needed.

    Looks up the ``user_identities`` table for a matching
    (provider, provider_user_id) pair. If found, returns the linked internal
    user. If not, provisions a new user (or links to an existing one matched
    by verified email) and creates the ``user_identities`` link.

    Results are cached in memory for ``_CACHE_TTL_SECONDS`` keyed on
    (provider, provider_user_id).

    Args:
        provider: Auth provider name (``clerk`` or ``cognito``).
        provider_user_id: The subject identifier from the provider.
        email: User email from the token claims (used when provisioning).
        name: Display name from the token claims (used when provisioning).
        email_verified: Whether the provider asserts the email is verified.
            Linking a new provider identity to an existing user by email is
            only allowed when this is True, to prevent account takeover via
            unverified email claims.

    Returns:
        The resolved ``InternalIdentity``.
    """
    cache_key = (provider, provider_user_id)
    cached = _identity_cache.get(cache_key)
    if cached and time.time() - cached[1] < _CACHE_TTL_SECONDS:
        return cached[0]

    client = _get_client()

    result = (
        client.table("user_identities")
        .select("user_id, users(id, email, name)")
        .eq("provider", provider)
        .eq("provider_user_id", provider_user_id)
        .maybe_single()
        .execute()
    )

    if result and result.data:
        user_data = result.data.get("users") or {}
        identity = InternalIdentity(
            internal_user_id=UUID(result.data["user_id"]),
            email=user_data.get("email"),
            name=user_data.get("name"),
        )
    else:
        identity = _provision(
            client, provider, provider_user_id, email, name, email_verified
        )

    _identity_cache[cache_key] = (identity, time.time())
    return identity


def _provision(
    client: Client,
    provider: str,
    provider_user_id: str,
    email: Optional[str],
    name: Optional[str],
    email_verified: bool,
) -> InternalIdentity:
    existing = None
    if email and email_verified:
        existing = (
            client.table("users")
            .select("id, email, name")
            .eq("email", email)
            .maybe_single()
            .execute()
        )

    if existing and existing.data:
        internal_user_id = UUID(existing.data["id"])
        user_email = existing.data.get("email")
        user_name = existing.data.get("name")
        logger.info(
            "Linking new provider identity %s/%s to existing user %s (matched by verified email)",
            provider,
            provider_user_id,
            internal_user_id,
        )
    else:
        new_user = (
            client.table("users").insert({"email": email, "name": name}).execute()
        )
        internal_user_id = UUID(new_user.data[0]["id"])
        user_email = email
        user_name = name
        logger.info(
            "Provisioned new user %s for %s/%s",
            internal_user_id,
            provider,
            provider_user_id,
        )

    client.table("user_identities").insert(
        {
            "user_id": str(internal_user_id),
            "provider": provider,
            "provider_user_id": provider_user_id,
        }
    ).execute()

    return InternalIdentity(
        internal_user_id=internal_user_id,
        email=user_email,
        name=user_name,
    )
