"""INDmoney's hourly call allowance: a limit notice is never data, never wipes holdings, and is not hammered."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.market_data import indmoney_live
from core.market_data.indmoney_client import IndmoneyMCPClient, IndmoneyRateLimitError
from core.models import Holding
from providers.brokers.indmoney import IndmoneyProvider

NOTICE = {"error": "rate_limit_exceeded", "message": "Rate limit exceeded for this tool: 250 calls per hour. Try again in 337s.", "retry_after_seconds": 337, "tool": "get_family_asset_holdings"}


def run(coro):
    return asyncio.run(coro)


class FakeHttp:
    """Answers tools/call with a canned MCP reply and counts the calls."""

    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    def post(self, *a, **k):
        outer = self
        outer.calls += 1

        class Ctx:
            status = 200
            headers = {"Content-Type": "application/json"}

            async def __aenter__(s):
                return s

            async def __aexit__(s, *e):
                return False

            async def text(s):
                import json

                return json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(outer.payload)}]}})

        return Ctx()


def client_with(payload):
    c = IndmoneyMCPClient(connection_id="rl_test", owner_id="rl_owner")
    http = FakeHttp(payload)
    c._get_http_session = lambda: http
    c.ensure_valid_token = AsyncMock(return_value="tok")
    return c, http


def test_the_limit_notice_is_an_error_with_the_wait_not_an_empty_portfolio():
    c, _ = client_with(NOTICE)
    with pytest.raises(IndmoneyRateLimitError) as e:
        run(c.get_family_asset_holdings("overall"))
    assert 330 <= e.value.retry_after <= 340


def test_while_told_to_wait_no_further_call_is_made():
    c, http = client_with(NOTICE)
    with pytest.raises(IndmoneyRateLimitError):
        run(c.call_tool("get_family_asset_holdings", {"asset": "overall"}))
    assert http.calls == 1
    for _ in range(5):
        with pytest.raises(IndmoneyRateLimitError):
            run(c.call_tool("get_family_asset_holdings", {"asset": "overall"}))
    assert http.calls == 1  # the five retries cost nothing


def test_the_wait_is_per_tool_and_ends():
    c, http = client_with(NOTICE)
    with pytest.raises(IndmoneyRateLimitError):
        run(c.call_tool("get_family_asset_holdings", {}))
    http.payload = {"ok": True}
    assert run(c.call_tool("get_indian_stocks_details", {})) == {"ok": True}  # another tool is unaffected
    c._blocked_until["get_family_asset_holdings"] = time.monotonic() - 1
    assert run(c.call_tool("get_family_asset_holdings", {})) == {"ok": True}  # allowed again once the wait is over


def test_an_absurd_wait_is_capped_at_an_hour():
    c, _ = client_with({**NOTICE, "retry_after_seconds": 10**9})
    with pytest.raises(IndmoneyRateLimitError) as e:
        run(c.call_tool("get_family_asset_holdings", {}))
    assert e.value.retry_after == 3600.0


@pytest.mark.parametrize("reply", [{}, {"status": "ok"}, {"error": "boom"}, "plain text", None, ["x"]])
def test_anything_that_is_not_a_holdings_reply_is_an_error_not_an_empty_portfolio(reply):
    c, _ = client_with(reply)
    with pytest.raises(RuntimeError):
        run(c.get_family_asset_holdings("overall"))


def test_a_genuinely_empty_portfolio_is_still_empty():
    c, _ = client_with({"family_asset_holdings": []})
    assert run(c.get_family_asset_holdings("overall")) == {"family_asset_holdings": []}


def test_the_provider_passes_the_limit_through_so_a_sync_keeps_what_is_stored():
    p = IndmoneyProvider(connection_id="rl_test", owner_id="rl_owner")
    with patch.object(IndmoneyMCPClient, "get_family_asset_holdings", AsyncMock(side_effect=IndmoneyRateLimitError("slow down", retry_after=5))):
        with pytest.raises(IndmoneyRateLimitError):
            run(p.get_holdings())


def test_price_refreshes_skip_the_per_member_calls_and_are_spaced_out():
    calls = []

    async def fake(self, asset="overall", complete=True):
        calls.append(complete)
        return {"family_asset_holdings": []}

    indmoney_live._cache.clear()
    with patch.object(IndmoneyMCPClient, "get_family_asset_holdings", fake):
        run(indmoney_live._fresh_for_connection("o", "conn_indmoney_live"))
        run(indmoney_live._fresh_for_connection("o", "conn_indmoney_live"))  # served from the cache
    assert calls == [False]
    assert indmoney_live.CACHE_SECONDS >= 120


def test_a_sync_still_asks_for_the_complete_lists():
    calls = []

    async def fake(self, asset="overall", complete=True):
        calls.append(complete)
        return {"family_asset_holdings": []}

    with patch.object(IndmoneyMCPClient, "get_family_asset_holdings", fake):
        run(IndmoneyProvider(connection_id="rl_test", owner_id="rl_owner").get_holdings())
    assert calls == [True]


def holding():
    return Holding(holding_id="h1", owner_id="o", connection_id="conn_indmoney_live", instrument_symbol="X", asset_class="EQUITY", quantity=1, average_price=10, current_price=11, current_value=11, pnl=1)


def test_a_rate_limited_overlay_leaves_the_stored_holdings_untouched():
    indmoney_live._cache.clear()
    h = holding()
    with patch.object(IndmoneyMCPClient, "get_family_asset_holdings", AsyncMock(side_effect=IndmoneyRateLimitError("slow", retry_after=5))):
        out = run(indmoney_live.overlay_indmoney_live("o", [h]))
    assert out == [h]
