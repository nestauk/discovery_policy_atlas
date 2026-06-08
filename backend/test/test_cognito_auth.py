"""Unit tests for ``CognitoAuthProvider``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.core.auth.base import AuthError
from app.core.auth.factory import get_auth_provider
from app.core.auth.providers.cognito import CognitoAuthProvider

_POOL = "eu-west-2_TestPool"
_REGION = "eu-west-2"
_CLIENT_ID = "test-client-id"


def _provider() -> CognitoAuthProvider:
    return CognitoAuthProvider(
        region=_REGION,
        user_pool_id=_POOL,
        app_client_id=_CLIENT_ID,
    )


def _access_token_payload(**overrides: object) -> dict:
    payload = {
        "sub": "cognito-user-123",
        "token_use": "access",
        "client_id": _CLIENT_ID,
        "username": "alice",
        "iss": f"https://cognito-idp.{_REGION}.amazonaws.com/{_POOL}",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_verify_token_maps_valid_access_token():
    provider = _provider()
    payload = _access_token_payload(email="[email protected]", name="Alice Example")

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        claims = await provider.verify_token("fake-token")

    assert claims.sub == "cognito-user-123"
    assert claims.email == "[email protected]"
    assert claims.name == "Alice Example"
    assert claims.organization_id is None
    assert claims.organization_slug is None
    assert claims.organization_role is None


@pytest.mark.asyncio
async def test_verify_token_rejects_id_token():
    provider = _provider()
    payload = _access_token_payload(token_use="id", aud=_CLIENT_ID)

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        with pytest.raises(AuthError, match="expected access token"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_verify_token_rejects_wrong_client_id():
    provider = _provider()
    payload = _access_token_payload(client_id="other-client")

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        with pytest.raises(AuthError, match="client_id mismatch"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_verify_token_rejects_missing_token_use():
    provider = _provider()
    payload = _access_token_payload()
    del payload["token_use"]

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        with pytest.raises(AuthError, match="expected access token"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_verify_token_rejects_missing_client_id():
    provider = _provider()
    payload = _access_token_payload()
    del payload["client_id"]

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        with pytest.raises(AuthError, match="client_id mismatch"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_verify_token_falls_back_to_username_for_name():
    """Access tokens lack ``name``; we should fall back to username."""
    provider = _provider()
    payload = _access_token_payload()  # username="alice", no email/name

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        claims = await provider.verify_token("fake-token")

    assert claims.email is None
    assert claims.name == "alice"


@pytest.mark.asyncio
async def test_verify_token_rejects_missing_sub():
    provider = _provider()
    payload = _access_token_payload()
    del payload["sub"]

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        with pytest.raises(AuthError, match="no user ID"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_verify_token_maps_expired_to_auth_error():
    provider = _provider()

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch(
        "app.core.auth.providers.cognito.jwt.decode",
        side_effect=jwt.ExpiredSignatureError("expired"),
    ):
        with pytest.raises(AuthError, match="Token has expired"):
            await provider.verify_token("fake-token")


@pytest.mark.asyncio
async def test_enrich_is_noop():
    provider = _provider()
    payload = _access_token_payload()

    with patch.object(
        provider._jwks_client,
        "get_signing_key_from_jwt",
        return_value=MagicMock(key="key"),
    ), patch("app.core.auth.providers.cognito.jwt.decode", return_value=payload):
        claims = await provider.verify_token("fake-token")

    enriched = await provider.enrich(claims)
    assert enriched is claims


def test_factory_returns_cognito_provider():
    get_auth_provider.cache_clear()

    mock_settings = MagicMock()
    mock_settings.AUTH_PROVIDER = "cognito"
    mock_settings.COGNITO_REGION = _REGION
    mock_settings.COGNITO_USER_POOL_ID = _POOL
    mock_settings.COGNITO_APP_CLIENT_ID = _CLIENT_ID

    with patch("app.core.auth.factory.settings", mock_settings):
        provider = get_auth_provider()

    assert isinstance(provider, CognitoAuthProvider)
    get_auth_provider.cache_clear()
