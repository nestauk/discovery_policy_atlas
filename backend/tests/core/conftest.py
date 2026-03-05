import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional
from fastapi.security import HTTPAuthorizationCredentials


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
