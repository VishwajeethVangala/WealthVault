"""Kite words many failed requests ("Failed to get quotes") like an expired login. A live login must not be reported as
lapsed because one request failed; only an explicit "log in first", or a profile call that fails too, means it is gone.

Everything runs on a scripted fake of Kite's MCP endpoint: nothing is sent anywhere."""

import asyncio
import json

import pytest

from core.market_data import kite_client as kc
from core.market_data.kite_client import KiteAuthRequiredError, KiteMCPClient, KiteToolError
from core.market_data.service import MCPMarketDataService

LOGIN_LINK = "https://mcp.kite.trade/authorize?session_id=kitemcp-test"


def ok(obj):
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(obj)}], "isError": False}}


def err(text):
    return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": text}], "isError": True}}


class Resp:
    status = 200

    def __init__(self, body):
        self.body = body

    async def text(self):
        return json.dumps(self.body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeHttp:
    """Answers each tool by name from a script; a list is used up one reply at a time."""

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def post(self, url, headers=None, json=None):
        name = json["params"]["name"]
        self.calls.append(name)
        reply = self.replies[name]
        return Resp(reply.pop(0) if isinstance(reply, list) else reply)


def client_with(tmp_path, monkeypatch, replies):
    monkeypatch.setattr(kc, "data_dir", lambda: tmp_path)
    client = KiteMCPClient(connection_id="c1", owner_id="owner1")
    client.session_id, client.auth_url, client.is_authenticated = "s1", LOGIN_LINK, True
    http = FakeHttp({"login": ok(f"[Login to Kite]({LOGIN_LINK})"), **replies})
    client._get_http_session = lambda: http
    return client, http


def test_a_failed_request_with_a_live_login_is_not_a_lapsed_login(tmp_path, monkeypatch):
    client, http = client_with(tmp_path, monkeypatch, {"get_quotes": err("Failed to get quotes"), "get_profile": ok({"user_name": "A"})})
    with pytest.raises(KiteToolError):
        asyncio.run(client.get_quotes(["NSE:RELIANCE"]))
    assert client.is_authenticated is True  # not flipped, so the Signals page keeps showing the person as logged in
    assert http.calls == ["get_quotes", "get_profile"]


def test_a_failed_request_with_a_dead_login_is_a_lapsed_login(tmp_path, monkeypatch):
    client, http = client_with(tmp_path, monkeypatch, {"get_quotes": err("Failed to get quotes"), "get_profile": err("Failed to execute get_profile")})
    with pytest.raises(KiteAuthRequiredError) as info:
        asyncio.run(client.get_quotes(["NSE:RELIANCE"]))
    assert client.is_authenticated is False and info.value.auth_url == LOGIN_LINK


def test_an_explicit_log_in_first_needs_no_profile_check(tmp_path, monkeypatch):
    client, http = client_with(tmp_path, monkeypatch, {"get_quotes": err("Please log in first using the login tool")})
    with pytest.raises(KiteAuthRequiredError):
        asyncio.run(client.get_quotes(["NSE:RELIANCE"]))
    assert "get_profile" not in http.calls and client.is_authenticated is False


def test_a_dead_login_asks_for_one_new_login_link_not_two(tmp_path, monkeypatch):
    client, http = client_with(tmp_path, monkeypatch, {"get_quotes": err("Failed to get quotes"), "get_profile": err("Failed to execute get_profile")})
    with pytest.raises(KiteAuthRequiredError):
        asyncio.run(client.get_quotes(["NSE:RELIANCE"]))
    assert http.calls.count("login") == 1


# --- one refused symbol must not cost every price ---------------------------------------------------------------


class QuoteClient:
    owner_id = None

    def __init__(self, bad):
        self.bad = bad
        self.calls = 0

    async def get_quotes(self, batch):
        self.calls += 1
        if self.bad & set(batch):
            raise KiteToolError("Kite could not complete 'get_quotes' (the login is live): Failed to get quotes")
        return {i: {"last_price": 100.0, "ohlc": {"close": 98.0, "open": 99.0, "high": 101.0, "low": 97.0}} for i in batch}


def test_one_refused_symbol_is_found_by_splitting_and_the_rest_are_priced():
    names = [f"NSE:S{i}" for i in range(20)] + ["NSE:BAD"]
    quotes, live = asyncio.run(MCPMarketDataService().fetch_live_quotes(names, client=QuoteClient({"NSE:BAD"})))
    assert live is True and "NSE:BAD" not in quotes and len(quotes) == 20


def test_splitting_has_a_budget_so_a_hopeless_request_does_not_hammer_kite():
    client = QuoteClient({f"NSE:S{i}" for i in range(200)})
    names = [f"NSE:S{i}" for i in range(200)]
    quotes, live = asyncio.run(MCPMarketDataService().fetch_live_quotes(names, client=client))
    assert quotes == {} and live is False and client.calls <= 1 + 16 + 1  # the first call, the budgeted splits, and a final refusal


# --- a stale "needs today's login" note must not outlive the login --------------------------------------------------


def test_a_login_note_from_an_earlier_refresh_is_dropped_once_kite_is_logged_in_again():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from apps.api.routers import signals
    from apps.api.routers.signals import Job

    def report(job, authenticated):
        store = {"u": job} if job else {}
        with patch.object(signals, "get_user_kite_client", AsyncMock(return_value=SimpleNamespace(is_authenticated=authenticated))):
            return asyncio.run(signals.current_job(store, "u", "u")), store

    stuck = Job(state="error", message="Kite needs today's login to fetch price history.", auth_url="https://x/authorize")
    out, store = report(stuck, authenticated=True)
    assert out.state == "idle" and "u" not in store  # the web and the phone now agree
    out, store = report(stuck, authenticated=False)
    assert out is stuck and "u" in store  # still logged out: the note stays
    other = Job(state="error", message="Refresh failed: boom")
    assert report(other, authenticated=True)[0] is other  # an unrelated failure is never hidden
    assert report(None, authenticated=True)[0].state == "idle"
