"""Account deletion erases one user's data and nothing else; the Android link file is built from settings."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from core import account_deletion
from core.market_data.kite_client import KiteMCPClient


def test_prefix_matches_scoped_keys():
    from core.market_data.scope import scoped_key

    owner = "google_109909149391234323377"
    assert scoped_key("conn_zerodha_live", owner, "x").startswith(account_deletion._prefix(owner))


def test_deletes_only_this_users_session_files(tmp_path):
    mine = tmp_path / "kite_session_google_111__conn_zerodha_live.json"
    mine2 = tmp_path / "indmoney_tokens_google_111__conn_indmoney_live.json"
    theirs = tmp_path / "kite_session_google_1112__conn_zerodha_live.json"  # a longer id that merely starts the same
    other = tmp_path / "kite_session_google_222__conn_zerodha_live.json"
    for p in (mine, mine2, theirs, other):
        p.write_text("{}")
    with patch.object(account_deletion, "data_dir", return_value=tmp_path):
        removed = asyncio.run(account_deletion._forget_broker_sessions("google_111"))
    assert removed == 2
    assert not mine.exists() and not mine2.exists()
    assert theirs.exists() and other.exists()


def test_live_client_is_dropped_from_memory(tmp_path):
    key = "google_111__conn_zerodha_live"
    client = AsyncMock()
    KiteMCPClient._instances[key] = client
    try:
        with patch.object(account_deletion, "data_dir", return_value=tmp_path):
            asyncio.run(account_deletion._forget_broker_sessions("google_111"))
        assert key not in KiteMCPClient._instances
        client.close.assert_awaited()
    finally:
        KiteMCPClient._instances.pop(key, None)


def test_delete_user_data_wipes_every_table_and_profile_last():
    order = []

    def repo(label):
        r = AsyncMock()
        r.delete_partition = AsyncMock(side_effect=lambda uid: order.append(label) or 3)
        return r

    with patch.object(account_deletion, "HoldingsRepository", lambda: repo("holdings")), patch.object(
        account_deletion, "SnapshotsRepository", lambda: repo("snapshots")
    ), patch.object(account_deletion, "TargetAllocationRepository", lambda: repo("targets")), patch.object(
        account_deletion, "BrokerCredentialRepository", lambda: repo("credentials")
    ), patch.object(account_deletion, "BrokerConnectionRepository", lambda: repo("connections")), patch.object(
        account_deletion, "FeedbackRepository", lambda: repo("feedback")
    ), patch.object(
        account_deletion, "UserRepository", lambda: repo("profile")
    ), patch.object(account_deletion, "DeviceTokenRepository", lambda: repo("devices")), patch.object(
        account_deletion, "NotificationPrefsRepository", lambda: repo("notification_prefs")
    ), patch.object(account_deletion, "NotificationRepository", lambda: repo("notifications")), patch.object(
        account_deletion, "PushSentRepository", lambda: repo("push_sent")
    ), patch.object(account_deletion, "_forget_broker_sessions", AsyncMock(return_value=2)), patch.object(
        account_deletion, "purge_owner_blobs", AsyncMock(return_value=5)
    ):
        out = asyncio.run(account_deletion.delete_user_data("google_111"))
    assert order[-1] == "profile"
    assert set(order) == {"holdings", "snapshots", "targets", "credentials", "connections", "feedback", "profile", "devices", "notification_prefs", "notifications", "push_sent"}
    assert out["session_files"] == 2 and out["archived_payloads"] == 5


def test_blob_failure_does_not_stop_deletion():
    with patch.object(account_deletion, "_forget_broker_sessions", AsyncMock(return_value=0)), patch.object(
        account_deletion, "purge_owner_blobs", AsyncMock(side_effect=RuntimeError("storage down"))
    ), patch.object(account_deletion, "HoldingsRepository") as h, patch.object(account_deletion, "SnapshotsRepository") as s, patch.object(
        account_deletion, "TargetAllocationRepository"
    ) as t, patch.object(account_deletion, "BrokerCredentialRepository") as c, patch.object(
        account_deletion, "BrokerConnectionRepository"
    ) as b, patch.object(account_deletion, "FeedbackRepository") as f, patch.object(account_deletion, "UserRepository") as u, patch.object(
        account_deletion, "DeviceTokenRepository"
    ) as d, patch.object(account_deletion, "NotificationPrefsRepository") as np_, patch.object(
        account_deletion, "NotificationRepository"
    ) as nr, patch.object(account_deletion, "PushSentRepository") as ps:
        for m in (h, s, t, c, b, f, u, d, np_, nr, ps):
            m.return_value.delete_partition = AsyncMock(return_value=1)
            m.return_value.close = AsyncMock()
        out = asyncio.run(account_deletion.delete_user_data("google_111"))
    assert out["archived_payloads"] == 0 and out["profile"] == 1


@pytest.fixture
def client():
    from apps.api.main import app

    return TestClient(app)


def test_delete_requires_login(client):
    assert client.request("DELETE", "/api/v1/auth/account", json={"confirm": "DELETE"}).status_code == 401


def test_delete_requires_typed_confirmation(client):
    from core.security import create_access_token

    token = create_access_token({"sub": "google_111"})
    with patch("apps.api.routers.auth.delete_user_data", AsyncMock(return_value={"holdings": 1})) as gone:
        r = client.request("DELETE", "/api/v1/auth/account", json={"confirm": "yes"}, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        gone.assert_not_awaited()
        r = client.request("DELETE", "/api/v1/auth/account", json={"confirm": "DELETE"}, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        gone.assert_awaited_once_with("google_111")
