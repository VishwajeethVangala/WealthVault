"""The reviewer demo login is off by default, rejects wrong credentials, and issues a session for the sample account."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import auth
from core import demo_account
from core.models import User


def _client():
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def _settings(user="", password=""):
    return SimpleNamespace(DEMO_USERNAME=user, DEMO_PASSWORD=password, GOOGLE_CLIENT_ID="", ENVIRONMENT="test", SUPPORT_EMAIL="")


def test_off_unless_configured():
    with patch.object(auth, "get_settings", return_value=_settings()):
        assert _client().post("/auth/demo", json={"username": "a", "password": "b"}).status_code == 404
        assert _client().get("/auth/config").json()["demo_login"] is False


def test_wrong_password_is_rejected():
    s = _settings("reviewer", "s3cret")
    with patch.object(auth, "get_settings", return_value=s), patch.object(demo_account, "get_settings", return_value=s):
        r = _client().post("/auth/demo", json={"username": "reviewer", "password": "nope"})
    assert r.status_code == 401


def test_right_login_gives_a_session_for_the_sample_account():
    s = _settings("reviewer", "s3cret")
    user = User(user_id=demo_account.DEMO_USER_ID, email="demo@example.invalid", name="Demo Reviewer")
    with patch.object(auth, "get_settings", return_value=s), patch.object(demo_account, "get_settings", return_value=s), \
            patch.object(auth, "ensure_demo_account", AsyncMock(return_value=user)), \
            patch.object(auth, "create_access_token", return_value="tok"):
        c = _client()
        r = c.post("/auth/demo", json={"username": " reviewer ", "password": "s3cret"})
        assert c.get("/auth/config").json()["demo_login"] is True
    assert r.status_code == 200
    assert r.json()["access_token"] == "tok" and r.json()["user"]["user_id"] == "demo_reviewer"
