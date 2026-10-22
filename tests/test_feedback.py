"""The feedback form: what it accepts, where it is kept, and that it belongs to the sender."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import feedback
from apps.api.routers.accounts import get_current_user
from core.models import User


def _client():
    app = FastAPI()
    app.include_router(feedback.router)
    app.dependency_overrides[get_current_user] = lambda: "google_111"
    return TestClient(app)


def _repos(saved):
    repo = AsyncMock()
    repo.save_feedback = AsyncMock(side_effect=lambda **kw: saved.append(kw) or {"id": "20261022T101500_abcd1234", **kw})
    repo.list_feedback = AsyncMock(return_value=[{"id": "x", "message": "hi"}])
    users = AsyncMock()
    users.get_user = AsyncMock(return_value=User(user_id="google_111", email="me@example.com", name="Me"))
    return repo, users


def test_a_message_is_saved_under_the_sender_with_their_email():
    saved = []
    repo, users = _repos(saved)
    with patch.object(feedback, "FeedbackRepository", lambda: repo), patch.object(feedback, "UserRepository", lambda: users):
        r = _client().post("/feedback", json={"category": "idea", "message": "  Add a dark chart  ", "platform": "android", "app_version": "0.3.9"})
    assert r.status_code == 201 and r.json()["status"] == "received"
    assert saved == [{"owner_id": "google_111", "category": "idea", "message": "Add a dark chart", "platform": "android", "app_version": "0.3.9", "email": "me@example.com"}]


def test_empty_long_or_odd_messages_are_refused():
    saved = []
    repo, users = _repos(saved)
    with patch.object(feedback, "FeedbackRepository", lambda: repo), patch.object(feedback, "UserRepository", lambda: users):
        c = _client()
        assert c.post("/feedback", json={"message": "   "}).status_code == 422
        assert c.post("/feedback", json={"message": "x" * 2001}).status_code == 422
        assert c.post("/feedback", json={"message": "hi", "category": "spam"}).status_code == 422
    assert saved == []


def test_you_only_read_your_own_feedback():
    repo, users = _repos([])
    with patch.object(feedback, "FeedbackRepository", lambda: repo), patch.object(feedback, "UserRepository", lambda: users):
        r = _client().get("/feedback")
    assert r.status_code == 200
    repo.list_feedback.assert_awaited_with("google_111")
