import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import jwt

from app.core.models import CurrentUser
from tests.core.conftest import make_credentials, make_jwt_payload


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

        await clerk_module.fetch_user_from_clerk_cached("user_cached")
        email, name = await clerk_module.fetch_user_from_clerk_cached("user_cached")

        assert email == "cached@example.com"
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
