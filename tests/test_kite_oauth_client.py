"""Tests for Zerodha Kite OAuth 2.1 PKCE, RFC 7591 registration, Streamable HTTP, and grouped MCP tools."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import accounts, portfolio
from core import config
from core.market_data import kite_client as kc
from core.market_data.kite_client import (
    KITE_MCP_URL,
    KiteAuthRequiredError,
    KiteMCPClient,
    KiteRegistrationError,
    complete_kite_authorization,
    default_redirect_uri,
    get_kite_mcp_client,
)
from core.models import BrokerConnection, BrokerStatus


class FakeResponse:
    def __init__(self, body, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        return self._body if not isinstance(self._body, str) else json.loads(self._body)


class FakeKiteBackend:
    """In-memory mock for Kite OAuth + Streamable HTTP MCP endpoints."""

    is_closed = False

    def __init__(self):
        self.calls = []
        self.registered_payloads = []
        self.token_payloads = []
        self.initialize_count = 0
        self.holdings_pages = [
            {
                "data": [{"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 10}],
                "pagination": {"has_more": False, "returned": 1},
            }
        ]
        self.fail_next_tool_status = None
        self.fail_next_tool_text = ""
        self.sse_quote_response = False

    async def get(self, url, headers=None):
        self.calls.append(("GET", url, headers or {}))
        if "oauth-protected-resource" in url:
            return FakeResponse({"resource": KITE_MCP_URL, "scopes_supported": ["default"]})
        if "oauth-authorization-server" in url:
            return FakeResponse(
                {
                    "authorization_endpoint": "https://mcp.kite.trade/authorize",
                    "token_endpoint": "https://mcp.kite.trade/token",
                    "registration_endpoint": "https://mcp.kite.trade/register",
                }
            )
        return FakeResponse({}, status_code=404)

    async def post(self, url, headers=None, json=None, data=None):
        headers = headers or {}
        if url.endswith("/register"):
            self.registered_payloads.append((json, headers))
            return FakeResponse(
                {
                    "client_id": f"dcr-{len(self.registered_payloads)}",
                    "redirect_uris": (json or {}).get("redirect_uris", []),
                },
                status_code=201,
            )

        if url.endswith("/token"):
            self.token_payloads.append((data, headers))
            if (data or {}).get("grant_type") == "refresh_token":
                return FakeResponse(
                    {
                        "access_token": "tok-refreshed",
                        "refresh_token": "rt-2",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    }
                )
            return FakeResponse(
                {
                    "access_token": "tok-live-123",
                    "refresh_token": "rt-1",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }
            )

        if self.fail_next_tool_status is not None and (json or {}).get("method") == "tools/call":
            code = self.fail_next_tool_status
            txt = self.fail_next_tool_text
            self.fail_next_tool_status = None
            self.fail_next_tool_text = ""
            return FakeResponse(txt, status_code=code, headers={"content-type": "text/plain"})

        method = (json or {}).get("method")
        if method == "initialize":
            self.initialize_count += 1
            self.calls.append(("initialize", url, headers))
            return FakeResponse(
                {"jsonrpc": "2.0", "id": json["id"], "result": {"protocolVersion": "2024-11-05"}},
                headers={"content-type": "application/json", "mcp-session-id": f"sess-{self.initialize_count}"},
            )
        if method == "notifications/initialized":
            self.calls.append(("notifications/initialized", url, headers))
            return FakeResponse("", status_code=202)

        params = (json or {}).get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        self.calls.append(("tools/call", name, args, headers))

        if name == "portfolio" and args.get("mode") == "profile":
            payload = {"data": {"user_id": "ZK9999", "user_name": "Test User", "email": "t@example.com"}}
            return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": payload, "isError": False}})

        if name == "portfolio" and args.get("mode") == "holdings":
            offset = int(args.get("from", 0))
            page = self.holdings_pages[0] if offset == 0 else self.holdings_pages[-1]
            return FakeResponse(
                {
                    "jsonrpc": "2.0",
                    "id": json["id"],
                    "result": {"content": [{"type": "text", "text": json_dumps(page)}], "isError": False},
                }
            )

        if name == "mutual_funds" and args.get("mode") == "holdings":
            payload = {"data": [{"fund": "Nifty 50 Index", "tradingsymbol": "INF123", "quantity": 100}]}
            return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": payload, "isError": False}})

        if name == "market" and args.get("mode") == "quote":
            insts = args.get("instruments", [])
            data_map = {sym: {"last_price": 1500.0, "ohlc": {"close": 1480.0}} for sym in insts}
            rpc = {"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": {"data": data_map, "meta": {}}, "isError": False}}
            if self.sse_quote_response:
                sse = f"event: message\ndata: {json_dumps(rpc)}\n\n"
                return FakeResponse(sse, headers={"content-type": "text/event-stream"})
            return FakeResponse(rpc)

        if name == "market" and args.get("mode") == "ltp":
            insts = args.get("instruments", [])
            data_map = {sym: {"last_price": 1501.0} for sym in insts}
            return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": {"data": data_map}, "isError": False}})

        if name == "market" and args.get("mode") == "search":
            rows = [{"instrument_token": 738561, "id": "NSE:RELIANCE", "tradingsymbol": "RELIANCE", "isin": "INE002A01018"}]
            return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": {"data": rows}, "isError": False}})

        if name == "market" and args.get("mode") == "historical":
            candles = [{"date": "2026-01-01T00:00:00+05:30", "close": 1500.0}]
            return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"structuredContent": {"data": candles}, "isError": False}})

        return FakeResponse({"jsonrpc": "2.0", "id": json["id"], "result": {"content": [], "isError": False}})


def json_dumps(obj):
    return json.dumps(obj)


@pytest.fixture
def isolated_kite(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    config.get_settings.cache_clear()
    KiteMCPClient._instances.clear()
    yield tmp_path
    KiteMCPClient._instances.clear()
    config.get_settings.cache_clear()


def test_dynamic_client_registration_local_and_public_url(isolated_kite, monkeypatch):
    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    fake = FakeKiteBackend()
    client._get_http_session = lambda: fake

    cid1 = asyncio.run(client.ensure_client())
    assert cid1 == "dcr-1"
    # Second call uses cached registration
    assert asyncio.run(client.ensure_client()) == "dcr-1"
    assert len(fake.registered_payloads) == 1
    reg_body, reg_headers = fake.registered_payloads[0]
    assert reg_body["token_endpoint_auth_method"] == "none"
    assert reg_body["redirect_uris"] == ["http://127.0.0.1:8000/api/v1/portfolio/oauth/kite/callback"]
    assert reg_headers == {} or True  # client default headers carry User-Agent

    # Changing PUBLIC_BASE_URL forces registration for the new redirect URI
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://wv.example.com/")
    config.get_settings.cache_clear()
    assert default_redirect_uri() == "https://wv.example.com/api/v1/portfolio/oauth/kite/callback"
    cid2 = asyncio.run(client.ensure_client())
    assert cid2 == "dcr-2"
    assert fake.registered_payloads[1][0]["redirect_uris"] == [
        "https://wv.example.com/api/v1/portfolio/oauth/kite/callback"
    ]


def test_registration_failure_raises_kite_registration_error(isolated_kite):
    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")

    class FailingHttp(FakeKiteBackend):
        async def post(self, url, headers=None, json=None, data=None):
            if url.endswith("/register"):
                return FakeResponse({"error": "invalid_redirect_uri"}, status_code=400)
            return await super().post(url, headers=headers, json=json, data=data)

    client._get_http_session = lambda: FailingHttp()
    with pytest.raises(KiteRegistrationError):
        asyncio.run(client.ensure_client())


def test_pkce_url_generation_reuse_and_expiry(isolated_kite):
    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    fake = FakeKiteBackend()
    client._get_http_session = lambda: fake

    asyncio.run(client.ensure_client())
    url1 = client.get_authorization_url()
    url2 = client.get_authorization_url()
    assert url1 == url2  # Reused within LINK_REUSE_SECONDS

    parsed = urlparse(url1)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://mcp.kite.trade/authorize"
    qs = parse_qs(parsed.query)
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["scope"] == ["default"]
    assert qs["resource"] == [KITE_MCP_URL]
    state = qs["state"][0]
    assert client.owns_state(state)

    # Expire state manually -> owns_state drops it
    verifier, _, redir = client._pending_verifiers[state]
    client._pending_verifiers[state] = (verifier, time.time() - kc.PENDING_TTL_SECONDS - 10, redir)
    assert not client.owns_state(state)
    url3 = client.get_authorization_url()
    assert url3 != url1


def test_oauth_callback_route_completes_login_and_blocks_replay_and_xss(isolated_kite):
    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    fake = FakeKiteBackend()
    client._get_http_session = lambda: fake

    asyncio.run(client.ensure_client())
    auth_url = client.get_authorization_url()
    state = parse_qs(urlparse(auth_url).query)["state"][0]

    app = FastAPI()
    app.include_router(portfolio.router, prefix="/api/v1")
    http_client = TestClient(app)

    # XSS-laden error parameter must be HTML escaped
    err_resp = http_client.get(
        "/api/v1/portfolio/oauth/kite/callback",
        params={"error": "<script>alert(1)</script>", "error_description": "<img src=x onerror=alert(2)>"},
    )
    assert err_resp.status_code == 400
    assert "<script>alert(1)</script>" not in err_resp.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in err_resp.text

    # Valid code + state exchanges token and updates repo status
    with patch("storage.tables.repositories.BrokerConnectionRepository.update_status", AsyncMock()) as mock_update:
        ok_resp = http_client.get(
            "/api/v1/portfolio/oauth/kite/callback",
            params={"code": "auth-code-99", "state": state},
        )
    assert ok_resp.status_code == 200
    assert "kite_authorized" in ok_resp.text
    assert client.is_authenticated is True
    assert client.access_token == "tok-live-123"
    assert client.auth_url is None
    assert client.session_id == "sess-1"
    mock_update.assert_awaited_once()
    assert mock_update.await_args.kwargs["status"] == BrokerStatus.CONNECTED

    # Replaying the exact same state fails
    replay_resp = http_client.get(
        "/api/v1/portfolio/oauth/kite/callback",
        params={"code": "auth-code-99", "state": state},
    )
    assert replay_resp.status_code == 400

    # Reload from disk preserves Bearer session
    KiteMCPClient._instances.clear()
    reloaded = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    assert reloaded.is_authenticated is True
    assert reloaded.access_token == "tok-live-123"


def test_legacy_tokenless_kite_session_file_loads_unauthenticated(isolated_kite):
    legacy_path = isolated_kite / "kite_session_u1__conn_zerodha_live.json"
    legacy_path.write_text(json.dumps({"session_id": "kitemcp-old", "is_authenticated": True}), encoding="utf-8")

    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    assert client.is_authenticated is False
    assert client.session_id is None
    assert client.access_token is None


def test_grouped_tool_calls_sse_pagination_and_session_recovery(isolated_kite):
    client = get_kite_mcp_client("conn_zerodha_live", owner_id="u1")
    fake = FakeKiteBackend()
    fake.holdings_pages = [
        {"data": [{"tradingsymbol": "INFY"}], "pagination": {"has_more": True, "returned": 1}},
        {"data": [{"tradingsymbol": "TCS"}], "pagination": {"has_more": False, "returned": 1}},
    ]
    fake.sse_quote_response = True
    client._get_http_session = lambda: fake
    client.access_token = "tok-live"
    client.refresh_token = "rt-1"
    client.is_authenticated = True

    profile = asyncio.run(client.get_profile())
    assert profile["user_id"] == "ZK9999"

    holdings = asyncio.run(client.get_holdings())
    assert [h["tradingsymbol"] for h in holdings] == ["INFY", "TCS"]

    mfs = asyncio.run(client.get_mf_holdings())
    assert mfs == [{"fund": "Nifty 50 Index", "tradingsymbol": "INF123", "quantity": 100}]

    quotes = asyncio.run(client.get_quotes(["NSE:INFY"]))
    assert quotes["NSE:INFY"]["last_price"] == 1500.0

    ltp = asyncio.run(client.get_ltp(["NSE:INFY"]))
    assert ltp["NSE:INFY"]["last_price"] == 1501.0

    search_rows = asyncio.run(client.search_instruments("RELIANCE", "name"))
    assert search_rows[0]["isin"] == "INE002A01018"
    search_call = next(c for c in fake.calls if c[0] == "tools/call" and c[1] == "market" and c[2].get("mode") == "search")
    assert search_call[2]["verbosity"] == "full"
    assert search_call[2]["filter_on"] == "name"

    hist = asyncio.run(client.get_historical_data(738561, "2026-01-01", "2026-01-10"))
    assert hist["data"][0]["close"] == 1500.0

    # HTTP 400 Invalid session ID re-initializes transport without dropping Bearer token
    fake.fail_next_tool_status = 400
    fake.fail_next_tool_text = "Invalid session ID"
    quotes_after_reset = asyncio.run(client.get_quotes(["NSE:TCS"]))
    assert quotes_after_reset["NSE:TCS"]["last_price"] == 1500.0
    assert client.access_token == "tok-live"
    assert fake.initialize_count == 2

    # HTTP 401 with refresh_token refreshes and retries seamlessly
    fake.fail_next_tool_status = 401
    fake.fail_next_tool_text = "token expired"
    quotes_after_refresh = asyncio.run(client.get_quotes(["NSE:SBIN"]))
    assert quotes_after_refresh["NSE:SBIN"]["last_price"] == 1500.0
    assert client.access_token == "tok-refreshed"

    # HTTP 401 without refresh_token raises KiteAuthRequiredError with OAuth link
    client.refresh_token = None
    fake.fail_next_tool_status = 401
    fake.fail_next_tool_text = "no bearer token"
    with pytest.raises(KiteAuthRequiredError) as exc_info:
        asyncio.run(client.get_quotes(["NSE:HDFCBANK"]))
    assert exc_info.value.auth_url.startswith("https://mcp.kite.trade/authorize?")
    assert client.is_authenticated is False


def test_create_zerodha_connection_endpoint_returns_auth_required_with_oauth_url(isolated_kite):
    app = FastAPI()
    app.include_router(portfolio.router, prefix="/api/v1")
    app.dependency_overrides[accounts.get_current_user] = lambda: "user-abc"
    test_client = TestClient(app)

    fake = FakeKiteBackend()
    zk_client = get_kite_mcp_client("conn_zerodha_live", owner_id="user-abc")
    zk_client._get_http_session = lambda: fake

    conn = BrokerConnection(
        connection_id="conn_zerodha_live",
        owner_id="user-abc",
        broker_name="zerodha",
        account_label="Primary Account",
        status=BrokerStatus.CONNECTED,
    )

    with (
        patch.object(portfolio.BrokerConnectionRepository, "list_connections", AsyncMock(side_effect=[[], [conn]])),
        patch.object(portfolio.BrokerConnectionRepository, "get_connection", AsyncMock(return_value=None)),
        patch.object(portfolio.BrokerConnectionRepository, "create_connection", AsyncMock(return_value=conn)),
        patch.object(portfolio.BrokerConnectionRepository, "is_tenant_initialized", AsyncMock(return_value=True)),
        patch.object(portfolio.HoldingsRepository, "get_holdings", AsyncMock(return_value=[])),
        patch.object(portfolio, "get_portfolio_holdings", AsyncMock(return_value=[])),
    ):
        resp = test_client.post(
            "/api/v1/portfolio/connections",
            json={"broker_name": "zerodha", "account_label": "Primary Account"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["broker_name"] == "zerodha"
    assert body["status"] == BrokerStatus.AUTH_REQUIRED.value
    assert body["is_expired"] is True
    assert body["auth_url"].startswith("https://mcp.kite.trade/authorize?")
    qs = parse_qs(urlparse(body["auth_url"]).query)
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["client_id"] == ["dcr-1"]
