import pytest
from unittest.mock import patch
from fastapi import HTTPException
import jwt

from app.core.models import CurrentUser
from tests.core.conftest import make_credentials, make_jwt_payload


class TestKeycloakGetCurrentUser:
    """Tests for Keycloak auth provider get_current_user function."""

    @pytest.fixture(autouse=True)
    def setup_keycloak_env(self, monkeypatch):
        """Set required Keycloak environment variables."""
        monkeypatch.setenv("AUTH_PROVIDER", "keycloak")
        monkeypatch.setenv(
            "KEYCLOAK_ISSUER", "https://keycloak.example.com/realms/test"
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
        payload = make_jwt_payload(
            sub="kc_user_123",
            email="keycloak@example.com",
            first_name="Key",
            last_name="Cloak",
            full_name="Keycloak User",
            org_id="org_123",
            org_slug="kc-org",
            org_role="member",
            iss="https://keycloak.example.com/realms/test",
            azp="test-client",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert isinstance(user, CurrentUser)
        assert user.user_id == "kc_user_123"
        assert user.email == "keycloak@example.com"
        assert user.name == "Keycloak User"
        assert user.organization_id == "org_123"
        assert user.organization_slug == "kc-org"
        assert user.organization_role == "member"

    @pytest.mark.asyncio
    async def test_valid_token_name_from_preferred_username(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without name uses preferred_username."""
        payload = make_jwt_payload(
            sub="kc_user_456",
            email="kc2@example.com",
            first_name=None,
            last_name=None,
            full_name=None,
            iss="https://keycloak.example.com/realms/test",
            preferred_username="preferred_name",
            azp="test-client",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert user.name == "preferred_name"

    @pytest.mark.asyncio
    async def test_valid_token_name_from_email_fallback(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token without name claims falls back to email prefix."""
        payload = make_jwt_payload(
            sub="kc_user_789",
            email="kc.user@example.com",
            first_name=None,
            last_name=None,
            full_name=None,
            iss="https://keycloak.example.com/realms/test",
            azp="test-client",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert user.name == "kc.user"

    @pytest.mark.asyncio
    async def test_valid_token_nested_org_claim(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token with nested 'o' claim extracts org info."""
        payload = make_jwt_payload(
            org_id=None,
            org_slug=None,
            org_role=None,
            iss="https://keycloak.example.com/realms/test",
            azp="test-client",
            o={"id": "nested_org", "slg": "nested-slug", "rol": "admin"},
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert user.organization_id == "nested_org"
        assert user.organization_slug == "nested-slug"
        assert user.organization_role == "admin"

    @pytest.mark.asyncio
    async def test_valid_token_orgs_claim_slug_mapping(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token with orgs claim maps organization slug from path."""
        payload = make_jwt_payload(
            org_id=None,
            org_slug=None,
            org_role=None,
            iss="https://keycloak.example.com/realms/test",
            azp="test-client",
            orgs=["/orgs/acme"],
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("valid.kc.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            user = await keycloak_module.get_current_user(credentials)

        assert user.organization_slug == "acme"

    @pytest.mark.asyncio
    async def test_audience_mismatch_raises_401(
        self, keycloak_module, mock_jwks_client, mock_jwt_decode
    ):
        """Token with mismatched audience/azp raises 401."""
        payload = make_jwt_payload(
            iss="https://keycloak.example.com/realms/test",
            azp="other-client",
        )
        mock_jwt_decode.return_value = payload

        credentials = make_credentials("bad.aud.token")
        with patch.object(keycloak_module, "jwks_client", mock_jwks_client):
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_module.get_current_user(credentials)

        assert exc_info.value.status_code == 401

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
