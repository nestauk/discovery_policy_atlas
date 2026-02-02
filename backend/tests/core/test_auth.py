"""
Reusable auth test suite for provider implementations.

This module provides:
- Shared fixtures and mocks for JWT/JWKS handling
- Clerk-specific tests (current implementation)
- Keycloak TDD stubs (for driving implementation)

Run with: pytest tests/core/test_auth.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import jwt

from app.core.models import CurrentUser


# =============================================================================
# SHARED FIXTURES AND HELPERS
# =============================================================================


class MockSigningKey:
    """Mock signing key returned by PyJWKClient."""

    def __init__(self, key: str = "test-public-key"):
        self.key = key


def make_credentials(token: str) -> HTTPAuthorizationCredentials:
    """Create mock HTTPAuthorizationCredentials."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def make_jwt_payload(
    sub: str = "user_123",
    email: Optional[str] = "test@example.com",
    first_name: Optional[str] = "Test",
    last_name: Optional[str] = "User",
    full_name: Optional[str] = None,
    org_id: Optional[str] = "org_456",
    org_slug: Optional[str] = "test-org",
    org_role: Optional[str] = "member",
    exp: int = 9999999999,
    iss: str = "https://test.clerk.accounts.dev",
    **extra,
) -> dict:
    """Create a JWT payload with configurable claims."""
    payload = {"sub": sub, "exp": exp, "iss": iss}
    if email is not None:
        payload["email"] = email
    if first_name is not None:
        payload["first_name"] = first_name
    if last_name is not None:
        payload["last_name"] = last_name
    if full_name is not None:
        payload["full_name"] = full_name
    if org_id is not None:
        payload["org_id"] = org_id
    if org_slug is not None:
        payload["org_slug"] = org_slug
    if org_role is not None:
        payload["org_role"] = org_role
    payload.update(extra)
    return payload


@pytest.fixture
def mock_jwks_client():
    """Mock PyJWKClient for JWT verification."""
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = MockSigningKey()
    return client


@pytest.fixture
def mock_jwt_decode():
    """Mock jwt.decode function."""
    with patch("jwt.decode") as mock:
        yield mock


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for API calls (Clerk user fetch, etc.)."""
    with patch("httpx.AsyncClient") as mock:
        client_instance = AsyncMock()
        mock.return_value.__aenter__.return_value = client_instance
        mock.return_value.__aexit__.return_value = None
        yield client_instance


# =============================================================================
# CLERK TESTS
# =============================================================================


class TestClerkGetCurrentUser:
    """Tests for Clerk auth provider get_current_user function."""

    @pytest.fixture(autouse=True)
    def setup_clerk_env(self, monkeypatch):
        """Set required Clerk environment variables."""
        monkeypatch.setenv("AUTH_PROVIDER", "clerk")
        monkeypatch.setenv("CLERK_JWT_ISSUER", "https://test.clerk.accounts.dev")
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_secret")

    @pytest.fixture
    def clerk_module(self, mock_jwks_client):
        """Import clerk module with mocked JWKS client."""
        with patch("app.core.auth_providers.clerk.jwks_client", mock_jwks_client):
            # Re-import to get the patched version
            from app.core.auth_providers import clerk

            yield clerk

    @pytest.mark.asyncio
    async def test_valid_token_with_all_claims(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Valid token with full claims returns complete CurrentUser."""
        payload = make_jwt_payload()
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            user = await clerk_module.get_current_user(credentials)

        assert isinstance(user, CurrentUser)
        assert user.user_id == "user_123"
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert user.organization_id == "org_456"
        assert user.organization_slug == "test-org"
        assert user.organization_role == "member"

    @pytest.mark.asyncio
    async def test_valid_token_full_name_claim(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token with full_name claim uses it instead of first/last."""
        payload = make_jwt_payload(
            first_name="First",
            last_name="Last",
            full_name="Full Name Override",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            user = await clerk_module.get_current_user(credentials)

        assert user.name == "Full Name Override"

    @pytest.mark.asyncio
    async def test_valid_token_name_from_email_fallback(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without name claims falls back to email prefix."""
        payload = make_jwt_payload(
            first_name=None,
            last_name=None,
            full_name=None,
            email="john.doe@example.com",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            user = await clerk_module.get_current_user(credentials)

        assert user.name == "john.doe"

    @pytest.mark.asyncio
    async def test_valid_token_nested_org_claim(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token with nested 'o' claim extracts org info."""
        payload = make_jwt_payload(
            org_id=None,
            org_slug=None,
            org_role=None,
            o={"id": "nested_org", "slg": "nested-slug", "rol": "admin"},
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            user = await clerk_module.get_current_user(credentials)

        assert user.organization_id == "nested_org"
        assert user.organization_slug == "nested-slug"
        assert user.organization_role == "admin"

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Expired token raises HTTPException with 401."""
        mock_jwt_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        credentials = make_credentials("expired.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await clerk_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Invalid token raises HTTPException with 401."""
        mock_jwt_decode.side_effect = jwt.InvalidTokenError("Bad token")

        credentials = make_credentials("invalid.jwt.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await clerk_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_missing_user_id_raises_401(
        self, clerk_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without sub claim raises HTTPException with 401."""
        payload = make_jwt_payload()
        del payload["sub"]
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("no.sub.token")
        with patch.object(clerk_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await clerk_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401
        assert "user id" in exc_info.value.detail.lower()


class TestClerkFetchUserFromClerkCached:
    """Tests for Clerk API user fetch with caching."""

    @pytest.fixture(autouse=True)
    def setup_clerk_env(self, monkeypatch):
        """Set required Clerk environment variables."""
        monkeypatch.setenv("AUTH_PROVIDER", "clerk")
        monkeypatch.setenv("CLERK_JWT_ISSUER", "https://test.clerk.accounts.dev")
        monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_secret")

    @pytest.fixture
    def clerk_module(self):
        """Import clerk module."""
        from app.core.auth_providers import clerk

        # Clear cache before each test
        clerk._user_cache.clear()
        return clerk

    @pytest.mark.asyncio
    async def test_fetch_user_success(self, clerk_module, mock_httpx_client):
        """Successful API fetch returns email and name."""
        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "email_addresses": [
                    {"email_address": "api@example.com", "primary": True}
                ],
                "first_name": "API",
                "last_name": "User",
            },
        )

        email, name = await clerk_module.fetch_user_from_clerk_cached("user_api")

        assert email == "api@example.com"
        assert name == "API User"

    @pytest.mark.asyncio
    async def test_fetch_user_cached(self, clerk_module, mock_httpx_client):
        """Second call returns cached result without API call."""
        mock_httpx_client.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "email_addresses": [{"email_address": "cached@example.com"}],
                "first_name": "Cached",
            },
        )

        # First call
        await clerk_module.fetch_user_from_clerk_cached("user_cached")
        # Second call
        email, name = await clerk_module.fetch_user_from_clerk_cached("user_cached")

        assert email == "cached@example.com"
        # Only one API call should have been made
        assert mock_httpx_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_user_api_failure_returns_none(
        self, clerk_module, mock_httpx_client
    ):
        """API failure returns None, None."""
        mock_httpx_client.get.return_value = MagicMock(status_code=500)

        email, name = await clerk_module.fetch_user_from_clerk_cached("user_fail")

        assert email is None
        assert name is None


# =============================================================================
# KEYCLOAK TDD STUBS
# These tests define expected behavior for Keycloak implementation.
# They are marked xfail until the implementation exists.
# =============================================================================


@pytest.mark.xfail(reason="Keycloak implementation not yet complete", strict=True)
class TestKeycloakGetCurrentUser:
    """TDD stubs for Keycloak auth provider get_current_user function.

    Implement keycloak.py to make these tests pass. Expected interface:
    - async def get_current_user(credentials: HTTPAuthorizationCredentials) -> CurrentUser
    - Should verify JWT using Keycloak's JWKS endpoint
    - Should extract user_id from 'sub' claim
    - Should extract email from 'email' claim
    - Should extract name from 'name' or 'preferred_username' claim
    - Should extract organization from realm_access or resource_access claims
    """

    @pytest.fixture(autouse=True)
    def setup_keycloak_env(self, monkeypatch):
        """Set required Keycloak environment variables."""
        monkeypatch.setenv("AUTH_PROVIDER", "keycloak")
        monkeypatch.setenv(
            "KEYCLOAK_REALM_URL", "https://keycloak.example.com/realms/test"
        )
        monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "test-client")

    @pytest.fixture
    def keycloak_module(self, mock_jwks_client):
        """Import keycloak module with mocked JWKS client."""
        with patch("app.core.auth_providers.keycloak.jwks_client", mock_jwks_client):
            from app.core.auth_providers import keycloak

            yield keycloak

    @pytest.mark.asyncio
    async def test_valid_token_with_all_claims(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Valid Keycloak token returns complete CurrentUser."""
        payload = {
            "sub": "kc_user_123",
            "email": "keycloak@example.com",
            "name": "Keycloak User",
            "preferred_username": "kcuser",
            "realm_access": {"roles": ["user", "admin"]},
            "azp": "test-client",
            "exp": 9999999999,
            "iss": "https://keycloak.example.com/realms/test",
        }
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert isinstance(user, CurrentUser)
        assert user.user_id == "kc_user_123"
        assert user.email == "keycloak@example.com"
        assert user.name == "Keycloak User"

    @pytest.mark.asyncio
    async def test_valid_token_name_from_preferred_username(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without name uses preferred_username."""
        payload = {
            "sub": "kc_user_456",
            "email": "kc2@example.com",
            "preferred_username": "preferred_name",
            "exp": 9999999999,
            "iss": "https://keycloak.example.com/realms/test",
        }
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert user.name == "preferred_name"

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Expired Keycloak token raises HTTPException with 401."""
        mock_jwt_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        credentials = make_credentials("expired.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Invalid Keycloak token raises HTTPException with 401."""
        mock_jwt_decode.side_effect = jwt.InvalidTokenError("Bad token")

        credentials = make_credentials("invalid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_user_id_raises_401(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without sub claim raises HTTPException with 401."""
        payload = {"email": "no-sub@example.com", "exp": 9999999999}
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("no.sub.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401


# =============================================================================
# AUTH PROVIDER SELECTION TESTS
# =============================================================================


class TestAuthProviderSelection:
    """Tests for auth.py provider selection logic."""

    def test_missing_auth_provider_raises_error(self, monkeypatch):
        """Missing AUTH_PROVIDER env var raises ValueError."""
        monkeypatch.delenv("AUTH_PROVIDER", raising=False)

        # Need to reload the module to test import-time behavior
        import sys

        # Remove cached modules
        modules_to_remove = [
            k for k in sys.modules.keys() if k.startswith("app.core.auth")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        with pytest.raises(ValueError, match="AUTH_PROVIDER"):
            import app.core.auth  # noqa: F401

    def test_unsupported_provider_raises_error(self, monkeypatch):
        """Unsupported AUTH_PROVIDER raises NotImplementedError."""
        monkeypatch.setenv("AUTH_PROVIDER", "unsupported_provider")

        import sys

        modules_to_remove = [
            k for k in sys.modules.keys() if k.startswith("app.core.auth")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        with pytest.raises(NotImplementedError, match="unsupported_provider"):
            import app.core.auth  # noqa: F401
