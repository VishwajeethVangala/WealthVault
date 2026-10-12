"""Two users with the same default connection id must never share a broker session."""

import os

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

import asyncio

from core import config
from core.market_data.indmoney_client import IndmoneyMCPClient, get_indmoney_mcp_client
from core.market_data.kite_client import KiteMCPClient, get_kite_mcp_client
from providers.brokers.indmoney import IndmoneyProvider
from providers.brokers.zerodha import ZerodhaProvider


def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()
    KiteMCPClient._instances.clear()
    IndmoneyMCPClient._instances.clear()


def test_same_connection_id_gives_each_user_their_own_kite_client(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    a = get_kite_mcp_client("conn_zerodha_live", owner_id="google_A")
    b = get_kite_mcp_client("conn_zerodha_live", owner_id="google_B")
    assert a is not b
    assert a.session_file != b.session_file
    assert a is get_kite_mcp_client("conn_zerodha_live", owner_id="google_A")

    a.session_id, a.is_authenticated = "sess-A", True
    a._save_session() if hasattr(a, "_save_session") else None
    assert get_kite_mcp_client("conn_zerodha_live", owner_id="google_B").session_id != "sess-A"
    assert not get_kite_mcp_client("conn_zerodha_live", owner_id="google_B").is_authenticated


def test_a_saved_session_is_not_inherited_by_another_owner(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    # the old single-user files must not be handed to a signed-in user
    (tmp_path / "kite_session.json").write_text('{"session_id": "legacy", "is_authenticated": true}')
    (tmp_path / "indmoney_tokens.json").write_text('{"access_token": "legacy", "expires_at": 9999999999}')
    k = get_kite_mcp_client("conn_zerodha_live", owner_id="google_B")
    i = get_indmoney_mcp_client("conn_indmoney_live", owner_id="google_B")
    assert k.session_id is None and not k.is_authenticated
    assert i.access_token is None


def test_providers_resolve_to_the_owners_client(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    za = ZerodhaProvider(connection_id="conn_zerodha_live", owner_id="google_A").client
    zb = ZerodhaProvider(connection_id="conn_zerodha_live", owner_id="google_B").client
    ia = IndmoneyProvider(connection_id="conn_indmoney_live", owner_id="google_A").client
    ib = IndmoneyProvider(connection_id="conn_indmoney_live", owner_id="google_B").client
    assert za is not zb and ia is not ib


def test_indmoney_oauth_state_finds_only_the_issuing_client(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    a = get_indmoney_mcp_client("conn_indmoney_live", owner_id="google_A")
    url = a.get_authorization_url()
    state = [p.split("=")[1] for p in url.split("?")[1].split("&") if p.startswith("state=")][0]
    from urllib.parse import unquote

    state = unquote(state)
    key = state.split("::")[0]
    assert IndmoneyMCPClient.find(key) is a
    assert state in a._pending_verifiers
    b = get_indmoney_mcp_client("conn_indmoney_live", owner_id="google_B")
    assert state not in b._pending_verifiers


def test_cleanup():
    config.get_settings.cache_clear()
    KiteMCPClient._instances.clear()
    IndmoneyMCPClient._instances.clear()
