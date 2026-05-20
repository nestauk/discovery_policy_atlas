"""Smoke tests for the new ``app.core.auth`` package."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.auth import CurrentUser, get_current_user
from test.fakes import install_fake_auth, uninstall_fake_auth


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/me")
    def me(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "organization_id": user.organization_id,
            "organization_slug": user.organization_slug,
            "organization_role": user.organization_role,
        }

    return app


def test_get_current_user_returns_fake_claims():
    app = _build_app()
    install_fake_auth(
        app,
        user_id="user_abc",
        email="[email protected]",
        name="Ada Lovelace",
        organization_id="org_123",
        organization_slug="nesta-dev",
        organization_role="admin",
    )

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer fake-token"})

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "user_abc",
        "email": "[email protected]",
        "name": "Ada Lovelace",
        "organization_id": "org_123",
        "organization_slug": "nesta-dev",
        "organization_role": "admin",
    }

    uninstall_fake_auth(app)


def test_invalid_token_returns_401():
    app = _build_app()
    fake = install_fake_auth(app)
    fake._raise = True  # force verify_token to fail

    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token (fake provider)"
    uninstall_fake_auth(app)


def test_current_user_is_frozen():
    user = CurrentUser(user_id="u1")
    with pytest.raises(Exception):
        user.user_id = "u2"  # frozen dataclass
