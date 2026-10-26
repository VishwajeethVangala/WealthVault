"""Groww over MCP: the login flow, the holdings it returns, and its prices and candles as a stand-in for Kite.

The response shapes below are the real ones Groww's MCP sends (captured from a live account); numbers are made up."""

import asyncio
import os
import socket
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
from cryptography.fernet import Fernet

os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from apps.api import auto_refresh as ar
from core.analytics import equity_signals
from core.market_data import candle_store, groww_client as gc, groww_market as gm
from core.market_data.groww_client import GrowwMCPClient, complete_authorization
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.service import MCPMarketDataService
from core.models import AssetClass
from core.portfolio.normalization import NormalizationService
from providers.brokers.groww_mcp import GrowwMCPProvider as GrowwProvider


def run(coro):
    return asyncio.run(coro)


# ---- real shapes -----------------------------------------------------------------------------------------------

HOLDINGS_REPLY = {
    "result_timestamp": "2026-10-26 Monday 09:51:34 PM IST",
    "result": {
        "holdings": [
            {
                "invested_value": "41.21 Thousands", "tradable_exchanges": ["NSE", "BSE"], "demat_locked_quantity": 0.0,
                "t1_quantity": 0.0, "corporate_action_additional_quantity": 0, "pledge_quantity": 0.0,
                "groww_locked_quantity": 0.0, "repledge_quantity": 0.0, "demat_free_quantity": 941.0,
                "trading_symbol": "MONEYVIEW", "average_price": 43.79, "quantity": 941.0, "active_demat_transfer_quantity": 0,
                "title": "Moneyview Ltd.", "current_value": "48.13 Thousands", "p&l": "6.93 Thousands",
                "p&l_percent": "16.81%", "symbol_isin": "INE0PTN01011",
            }
        ],
        "total_invested_value": "41.21 Thousands",
        "total_current_value": "48.13 Thousands",
    },
}


def curate(*rows):
    return {"result": {"matches": [{"title": t, "exchange": e, "symbol": s, "symbol_isin": "x"} for t, e, s in rows], "count": len(rows)}}


RELIANCE_MATCHES = curate(
    ("Reliance Industries Ltd.", "NSE", "RELIANCE"), ("Reliance Power Ltd.", "NSE", "RPOWER"), ("Reliance Infrastructure Ltd.", "NSE", "RELINFRA")
)
TATAMOTORS_MATCHES = curate(("Tata Motors Passenger Vehicles Ltd.", "NSE", "TMPV"), ("Tata Motors Ltd.", "NSE", "TMCV"))

LTP_REPLY = {
    "result": {
        "ltp_results": {
            "NSE-Reliance Industries Ltd.": {"symbol": "RELIANCE", "ltp": 1201.8, "day_change": 11.8, "day_change_perc": 0.99, "open": 1186.1, "high": 1204.5, "low": 1174.5, "prev_close": 1190.0},
            "BSE-Reliance Industries Ltd.": {"symbol": "500325", "ltp": 1202.0, "day_change": 12.0, "day_change_perc": 1.01, "open": 1189.0, "high": 1204.35, "low": 1174.35, "prev_close": 1190.0},
            "NSE-Reliance Power Ltd.": {"symbol": "RPOWER", "ltp": 16.54, "day_change": 0.11, "day_change_perc": 0.67, "open": 16.4, "high": 16.7, "low": 16.06, "prev_close": 16.43},
        }
    }
}

def ltp_for(title, symbol, last, prev, exchange="NSE"):
    return {"result": {"ltp_results": {f"{exchange}-{title}": {"symbol": symbol, "ltp": last, "prev_close": prev, "day_change": round(last - prev, 2), "day_change_perc": 0.0}}}}


NIFTY_MATCHES = curate(("NIFTY 50", "NSE", "NIFTY"), ("NIFTY NEXT 50", "NSE", "NIFTYJR"))
NIFTY_LTP = ltp_for("NIFTY 50", "NIFTY", 22753.2, 22600.0)

CANDLES_REPLY = {
    "result": {
        "coverage": {"complete": False},
        "candles": [
            {"timestamp": "2026-10-22T00:00:00", "open": 1206.2, "high": 1208.0, "low": 1184.5, "close": 1184.5, "volume": 14957042.0},
            {"timestamp": "2026-10-23T00:00:00", "open": 1184.0, "high": 1201.9, "low": 1163.1, "close": 1190.0, "volume": 14905641.0},
        ],
    }
}


class FakeGroww:
    """Answers the tools the way Groww does, and records the calls."""

    def __init__(self, curates=None, ltp=LTP_REPLY, candles=CANDLES_REPLY):
        self.curates = curates or {"RELIANCE": RELIANCE_MATCHES, "TATAMOTORS": TATAMOTORS_MATCHES, "NIFTY 50": NIFTY_MATCHES}
        self.ltp, self.candles, self.calls = ltp, candles, []

    async def call_tool(self, name, args=None):
        self.calls.append((name, args))
        if name == "curate_symbols":
            return self.curates.get(args["query"], curate())
        if name == "get_ltp":
            return self.ltp
        if name == "fetch_historical_candle_data":
            return self.candles
        raise AssertionError(name)


def fresh_market():
    gm._titles.clear()
    gm._misses.clear()
    gm._loaded = True  # no saved titles, and no table to write to
    return patch.object(gm, "SymbolMapRepository", return_value=SimpleNamespace(save=AsyncMock()))


# ---- login -----------------------------------------------------------------------------------------------------


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.client = GrowwMCPClient(connection_id="test_conn_groww", owner_id="test_user")
        self.client.client_id = "test_client_id"
        GrowwMCPClient._instances[self.client.client_key] = self.client

    def tearDown(self):
        GrowwMCPClient._instances.pop(self.client.client_key, None)
        self.client.reset_tokens()

    def test_pkce_link_carries_the_challenge_and_a_state_this_client_owns(self):
        url = self.client.get_authorization_url()
        for part in ("https://groww.in/oauth/authorize", "response_type=code", "code_challenge_method=S256", "code_challenge=", "client_id=test_client_id"):
            self.assertIn(part, url)
        state = next(iter(self.client._pending_verifiers))
        self.assertTrue(self.client.owns_state(state))
        self.assertFalse(self.client.owns_state("someone-else::nonce"))
        self.assertFalse(self.client.owns_state(None))

    def test_asking_again_gives_the_same_link_and_does_not_pile_up_requests(self):
        first = self.client.get_authorization_url()
        for _ in range(30):  # a page re-checking status every minute
            self.assertEqual(self.client.get_authorization_url(), first)
        self.assertEqual(len(self.client._pending_verifiers), 1)

    def test_an_old_link_is_dropped_and_replaced(self):
        first = self.client.get_authorization_url()
        state = next(iter(self.client._pending_verifiers))
        self.client._pending_verifiers[state]["created_at"] -= gc.PENDING_TTL_SECONDS + 1
        self.assertFalse(self.client.owns_state(state))
        self.assertNotEqual(self.client.get_authorization_url(), first)
        self.assertNotIn(state, self.client._pending_verifiers)

    def test_unused_requests_are_capped(self):
        for i in range(gc.MAX_PENDING + 15):
            self.client._pending_verifiers[f"s{i}"] = {"verifier": "v", "created_at": time.time() + i}
        self.client._last_link = None
        self.client.get_authorization_url()
        self.assertLessEqual(len(self.client._pending_verifiers), gc.MAX_PENDING + 1)

    def test_redirect_is_the_loopback_listener_locally_and_the_app_when_deployed(self):
        with patch.object(gc, "public_base_url", return_value=""):
            self.assertEqual(gc.default_redirect_uri(), "http://localhost:52155/oauth/callback")
        with patch.object(gc, "public_base_url", return_value="https://wv.example.com"):
            self.assertEqual(gc.default_redirect_uri(), "https://wv.example.com/api/v1/portfolio/oauth/groww/callback")
            self.assertEqual(GrowwMCPClient(connection_id="c", owner_id="o").redirect_uri, "https://wv.example.com/api/v1/portfolio/oauth/groww/callback")

    def test_a_code_for_an_unknown_or_expired_login_is_refused_and_never_exchanged(self):
        with patch.object(GrowwMCPClient, "exchange_code", new_callable=AsyncMock) as exchange:
            for state in (None, "", "no-separator", "nobody::nonce", f"{self.client.client_key}::forged"):
                status, page = run(complete_authorization("code", state))
                self.assertEqual(status, 400)
                self.assertIn("expired", page)
            self.assertFalse(exchange.called)

    def test_error_text_from_the_url_is_escaped_in_the_page(self):
        status, page = run(complete_authorization(None, None, "<script>alert(1)</script>", "<img src=x onerror=alert(2)>"))
        self.assertEqual(status, 400)
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;script&gt;", page)

    def test_a_missing_code_is_refused(self):
        self.assertEqual(run(complete_authorization(None, "x::y"))[0], 400)

    def test_a_good_login_is_exchanged_once_and_marks_the_connection_connected(self):
        self.client.get_authorization_url()
        state = next(iter(self.client._pending_verifiers))
        repo = SimpleNamespace(update_status=AsyncMock())

        async def fake_exchange(code, st):
            self.client._pending_verifiers.pop(st)  # what the real one does

        with patch.object(GrowwMCPClient, "exchange_code", side_effect=fake_exchange), patch("storage.tables.repositories.BrokerConnectionRepository", return_value=repo):
            status, page = run(complete_authorization("code", state))
        self.assertEqual(status, 200)
        self.assertIn("Groww connected", page)
        repo.update_status.assert_awaited_once()
        self.assertEqual(repo.update_status.await_args.kwargs["connection_id"], "test_conn_groww")
        self.assertEqual(run(complete_authorization("code", state))[0], 400)  # the same link does not work twice

    def test_a_failed_exchange_shows_no_internal_detail(self):
        self.client.get_authorization_url()
        state = next(iter(self.client._pending_verifiers))
        with patch.object(GrowwMCPClient, "exchange_code", AsyncMock(side_effect=RuntimeError("secret internal detail <b>"))):
            status, page = run(complete_authorization("code", state))
        self.assertEqual(status, 502)
        self.assertNotIn("secret internal detail", page)

    def test_exchange_code_itself_refuses_an_unknown_state(self):
        with self.assertRaises(RuntimeError):
            run(self.client.exchange_code("code", "nope"))

    def test_status_follows_the_token(self):
        self.client.access_token, self.client.refresh_token, self.client.expires_at = None, None, 0.0
        provider = GrowwProvider(connection_id="test_conn_groww", owner_id="test_user")
        with patch.object(self.client, "ensure_client", new_callable=AsyncMock):
            status = run(provider.get_account_status())
        self.assertEqual(status["status"], "auth_required")
        self.assertIn("https://groww.in/oauth/authorize", status["auth_url"])
        self.client.access_token, self.client.expires_at = "t", time.time() + 3600
        self.assertEqual(run(provider.get_account_status())["status"], "success")


class LoopbackListenerTests(unittest.TestCase):
    def test_listener_serves_only_the_callback_and_escapes_what_it_echoes(self):
        async def case():
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            GrowwMCPClient._local_server = None
            with patch.object(gc, "public_base_url", return_value=""):
                await GrowwMCPClient.ensure_local_callback_server(port)
            try:
                async def get(path):
                    r, w = await asyncio.open_connection("127.0.0.1", port)
                    w.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
                    await w.drain()
                    data = await r.read()
                    w.close()
                    return data.decode()

                bad = await get("/oauth/callback?error=%3Cscript%3Ealert(1)%3C/script%3E")
                other = await get("/anything-else")
                forged = await get("/oauth/callback?code=c&state=nobody::n")
                return bad, other, forged
            finally:
                await GrowwMCPClient.close_all()

        bad, other, forged = run(case())
        self.assertIn("400", bad.splitlines()[0])
        self.assertIn("nosniff", bad)
        self.assertNotIn("<script>alert", bad)
        self.assertIn("404", other.splitlines()[0])
        self.assertIn("400", forged.splitlines()[0])

    def test_a_deployed_server_does_not_open_the_loopback_port(self):
        GrowwMCPClient._local_server = None
        with patch.object(gc, "public_base_url", return_value="https://wv.example.com"):
            run(GrowwMCPClient.ensure_local_callback_server(0))
        self.assertIsNone(GrowwMCPClient._local_server)


# ---- holdings --------------------------------------------------------------------------------------------------


class HoldingsTests(unittest.TestCase):
    def provider(self):
        return GrowwProvider(connection_id="test_conn_groww", owner_id="test_user")

    def get(self, reply):
        with patch.object(GrowwMCPClient, "call_tool", AsyncMock(return_value=reply)) as tool:
            rows = run(self.provider().get_holdings())
        return rows, tool

    def test_the_real_reply_is_read_and_asks_for_the_quantity_parts(self):
        rows, tool = self.get(HOLDINGS_REPLY)
        self.assertEqual([r["trading_symbol"] for r in rows], ["MONEYVIEW"])
        cols = tool.await_args.args[1]["extra_cols"]
        for c in ("quantity", "average_price", "t1_quantity", "pledge_quantity", "demat_free_quantity"):
            self.assertIn(c, cols)

    def test_an_empty_portfolio_is_an_empty_list(self):
        self.assertEqual(self.get({"result": {"holdings": []}})[0], [])

    def test_a_notice_or_error_reply_is_an_error_not_a_holding(self):
        for reply in ({"result": {"status": "something went wrong"}}, {"status": "error"}, "plain text", None, {"result": None}):
            with self.assertRaises(RuntimeError, msg=str(reply)):
                self.get(reply)

    def test_a_login_problem_still_reaches_the_sync_as_a_login_problem(self):
        with patch.object(GrowwMCPClient, "call_tool", AsyncMock(side_effect=gc.GrowwAuthRequiredError("x", auth_url="u"))):
            with self.assertRaises(gc.GrowwAuthRequiredError):
                run(self.provider().get_holdings())

    def test_the_real_row_becomes_a_holding_valued_at_cost_until_priced(self):
        h = NormalizationService().normalize_holdings(HOLDINGS_REPLY["result"]["holdings"], "groww", "u", "c")
        self.assertEqual(len(h), 1)
        self.assertEqual((h[0].instrument_symbol, h[0].asset_class, h[0].quantity, h[0].average_price), ("MONEYVIEW", AssetClass.EQUITY, 941.0, 43.79))
        self.assertEqual(h[0].current_value, 41206.39)
        self.assertEqual(h[0].data_freshness, "cached")

    def norm(self, **row):
        base = {"trading_symbol": "ABB", "average_price": 100.0, "symbol_isin": "INE1"}
        return NormalizationService().normalize_holdings([{**base, **row}], "groww", "u", "c")

    def test_settling_and_pledged_shares_are_counted_once(self):
        # Groww's own sample: net 10 = 5 free + 3 settling + 2 pledged. Adding the parts again would show 20.
        h = self.norm(quantity=10, demat_free_quantity=5, t1_quantity=3, pledge_quantity=2)
        self.assertEqual(h[0].quantity, 10.0)

    def test_parts_are_a_floor_when_the_net_lags(self):
        self.assertEqual(self.norm(quantity=0, demat_free_quantity=0, t1_quantity=3)[0].quantity, 3.0)
        self.assertEqual(self.norm(quantity=5, demat_free_quantity=5, t1_quantity=3)[0].quantity, 8.0)

    def test_a_sold_out_line_or_a_junk_row_is_not_a_holding(self):
        raw = [{"trading_symbol": "GONE", "quantity": 0, "average_price": 10}, "junk", None, {"trading_symbol": "KEEP", "quantity": 1, "average_price": 10}]
        self.assertEqual([h.instrument_symbol for h in NormalizationService().normalize_holdings(raw, "groww", "u", "c")], ["KEEP"])

    def test_a_gold_bond_is_gold_and_one_isin_is_one_holding_id(self):
        sgb = self.norm(trading_symbol="SGBMAY29", quantity=2, average_price=4800.0)[0]
        self.assertEqual(sgb.asset_class, AssetClass.GOLD)
        a = self.norm(quantity=1)[0].holding_id
        b = self.norm(quantity=9, trading_symbol="ABB2")[0].holding_id  # same ISIN keeps its id if the symbol changes
        self.assertEqual(a, b)

    def test_mutual_funds_are_not_available_from_groww_mcp(self):
        # Groww's get_mutualfund_details answers {"status": "GROWWMCP doesn't support mutual fund details"}; the
        # provider therefore never calls it and never invents mutual fund rows.
        with patch.object(GrowwMCPClient, "call_tool", AsyncMock(return_value=HOLDINGS_REPLY)) as tool:
            run(self.provider().get_holdings())
        self.assertEqual([c.args[0] for c in tool.await_args_list], ["get_equity_portfolio_holdings"])


# ---- prices and candles ----------------------------------------------------------------------------------------


class SymbolTests(unittest.TestCase):
    def test_exchange_and_series_are_split_off(self):
        self.assertEqual(gm.split_instrument("NSE:HFCL-BE"), ("NSE", "HFCL"))
        self.assertEqual(gm.split_instrument("nse:reliance"), ("NSE", "RELIANCE"))
        self.assertEqual(gm.split_instrument("RELIANCE"), ("NSE", "RELIANCE"))
        self.assertEqual(gm.split_instrument("BSE:500325"), ("BSE", "500325"))
        self.assertEqual(gm.split_instrument("NSE:BAJAJ-AUTO"), ("NSE", "BAJAJ-AUTO"))  # a hyphen in the name is not a series

    def test_only_the_exact_listing_resolves(self):
        fake = FakeGroww()
        with fresh_market():
            got = run(gm.resolve_titles(fake, ["NSE:RELIANCE", "NSE:TATAMOTORS", "NSE:NOSUCH"]))
        self.assertEqual(got, {"NSE:RELIANCE": ("Reliance Industries Ltd.", "Stocks")})  # TATAMOTORS is TMPV/TMCV now

    def test_a_name_that_is_only_a_prefix_of_another_company_does_not_resolve(self):
        with fresh_market():
            self.assertEqual(run(gm.resolve_titles(FakeGroww(), ["NSE:RELIANC"])), {})

    def test_an_etf_is_found_through_the_etf_search(self):
        fake = FakeGroww(curates={"TATAGOLD": curate()})
        orig = fake.call_tool

        async def call(name, args=None):
            if name == "curate_symbols" and args["entity_type"] == "etf" and args["query"] == "TATAGOLD":
                return curate(("Tata Gold Exchange Traded Fund", "NSE", "TATAGOLD"))
            return await orig(name, args)

        fake.call_tool = call
        with fresh_market():
            self.assertEqual(run(gm.resolve_titles(fake, ["NSE:TATAGOLD"])), {"NSE:TATAGOLD": ("Tata Gold Exchange Traded Fund", "etf")})

    def test_found_titles_and_misses_are_remembered(self):
        fake = FakeGroww()
        with fresh_market():
            run(gm.resolve_titles(fake, ["NSE:RELIANCE", "NSE:NOSUCH"]))
            before = len(fake.calls)
            run(gm.resolve_titles(fake, ["NSE:RELIANCE", "NSE:NOSUCH"]))
        self.assertEqual(len(fake.calls), before)

    def test_a_failed_lookup_is_not_remembered_as_a_miss(self):
        fake = FakeGroww()
        fake.call_tool = AsyncMock(side_effect=RuntimeError("down"))
        with fresh_market():
            self.assertEqual(run(gm.resolve_titles(fake, ["NSE:RELIANCE"])), {})
            self.assertEqual(gm._misses, {})


class QuoteTests(unittest.TestCase):
    def quotes(self, instruments, fake=None):
        with fresh_market():
            return run(gm.fetch_groww_quotes(fake or FakeGroww(), instruments))

    def test_the_exact_nse_symbol_is_read_from_a_reply_full_of_other_companies(self):
        q = self.quotes(["NSE:RELIANCE"])
        self.assertEqual(set(q), {"NSE:RELIANCE"})  # not RPOWER, not the BSE listing, nothing invented
        item = q["NSE:RELIANCE"]
        self.assertEqual((item.last_price, item.close_price, item.day_change, item.day_change_percentage), (1201.8, 1190.0, 11.8, 0.99))

    def test_an_nse_request_never_picks_up_the_bse_listing_and_the_reverse(self):
        reply = {"result": {"ltp_results": {"BSE-Reliance Industries Ltd.": LTP_REPLY["result"]["ltp_results"]["BSE-Reliance Industries Ltd."]}}}
        self.assertEqual(self.quotes(["NSE:RELIANCE"], FakeGroww(ltp=reply)), {})  # only the BSE row came back
        fake = FakeGroww(curates={"500325": curate(("Reliance Industries Ltd.", "BSE", "500325"))})
        bse = self.quotes(["BSE:500325"], fake)
        self.assertEqual(bse["BSE:500325"].last_price, 1202.0)

    def test_a_series_suffixed_symbol_gets_the_companys_price_under_the_name_asked(self):
        fake = FakeGroww(curates={"RELIANCE": RELIANCE_MATCHES})
        q = self.quotes(["NSE:RELIANCE-BE"], fake)
        self.assertEqual(set(q), {"NSE:RELIANCE-BE"})
        self.assertEqual(q["NSE:RELIANCE-BE"].last_price, 1201.8)

    def test_the_day_change_is_from_the_previous_close_and_a_missing_close_is_not_made_up(self):
        no_prev = {"result": {"ltp_results": {"NSE-Reliance Industries Ltd.": {"symbol": "RELIANCE", "ltp": 1201.8, "day_change": 11.8, "day_change_perc": 0.99}}}}
        item = self.quotes(["NSE:RELIANCE"], FakeGroww(ltp=no_prev))["NSE:RELIANCE"]
        self.assertEqual(item.close_price, 0.0)  # unknown, never set to the price itself
        self.assertEqual((item.day_change, item.day_change_percentage), (11.8, 0.99))

    def test_an_index_is_resolved_by_its_name_and_priced_from_the_index_search(self):
        fake = FakeGroww(ltp=NIFTY_LTP)
        q = self.quotes(["NSE:NIFTY 50"], fake)
        self.assertEqual((q["NSE:NIFTY 50"].last_price, q["NSE:NIFTY 50"].close_price), (22753.2, 22600.0))
        asked = next(c[1] for c in fake.calls if c[0] == "get_ltp")
        self.assertEqual((asked["search_queries"], asked["query_type"]), (["NIFTY 50"], "index"))

    def test_a_neighbouring_index_is_not_taken_for_the_one_asked(self):
        fake = FakeGroww(ltp=ltp_for("NIFTY NEXT 50", "NIFTYJR", 66477.0, 65828.6))
        self.assertEqual(self.quotes(["NSE:NIFTY 50"], fake), {})

    def test_an_etf_filed_under_stocks_is_still_priced_through_the_etf_search(self):
        etf_ltp = {"result": {"ltp_results": {"NSE-Tata Gold Exchange Traded Fund": {"symbol": "TATAGOLD", "ltp": 13.66, "prev_close": 13.63}}}}
        fake = FakeGroww(curates={"TATAGOLD": curate(("Tata Gold Exchange Traded Fund", "NSE", "TATAGOLD"))})
        asked_as = []
        orig = fake.call_tool

        async def call(name, args=None):
            if name == "get_ltp":
                asked_as.append(args["query_type"])
                return etf_ltp if args["query_type"] == "etf" else {"result": {"ltp_results": {"NSE-Some Other Ltd.": {"symbol": "OTHER", "ltp": 5, "prev_close": 5}}}}
            return await orig(name, args)

        fake.call_tool = call
        q = self.quotes(["NSE:TATAGOLD"], fake)
        self.assertEqual(q["NSE:TATAGOLD"].last_price, 13.66)
        self.assertEqual(asked_as, ["Stocks", "etf"])  # tried as a stock first, then as an ETF; never as an index

    def test_a_zero_or_missing_price_is_dropped(self):
        zero = {"result": {"ltp_results": {"NSE-Reliance Industries Ltd.": {"symbol": "RELIANCE", "ltp": 0, "prev_close": 1190.0}}}}
        self.assertEqual(self.quotes(["NSE:RELIANCE"], FakeGroww(ltp=zero)), {})

    def test_nothing_unresolved_is_ever_asked_for(self):
        fake = FakeGroww()
        self.assertEqual(self.quotes(["NSE:TATAMOTORS", "NSE:NOSUCH"], fake), {})
        self.assertNotIn("get_ltp", [c[0] for c in fake.calls])

    def test_the_search_is_by_the_exact_title_not_by_the_loose_symbol(self):
        fake = FakeGroww()
        self.quotes(["NSE:RELIANCE"], fake)
        asked = next(c[1] for c in fake.calls if c[0] == "get_ltp")
        self.assertEqual(asked["search_queries"], ["Reliance Industries Ltd."])

    def test_a_failed_call_gives_no_quotes(self):
        fake = FakeGroww()
        orig = fake.call_tool

        async def call(name, args=None):
            if name == "get_ltp":
                raise RuntimeError("down")
            return await orig(name, args)

        fake.call_tool = call
        self.assertEqual(self.quotes(["NSE:RELIANCE"], fake), {})


class CandleTests(unittest.TestCase):
    def candles(self, instrument="NSE:RELIANCE", days=14, fake=None):
        with fresh_market():
            return run(gm.fetch_groww_daily_candles(fake or FakeGroww(), instrument, days))

    def test_the_real_reply_is_read_by_trading_day(self):
        rows = self.candles()
        self.assertEqual([r["date"] for r in rows], ["2026-10-22", "2026-10-23"])
        self.assertEqual((rows[1]["open"], rows[1]["high"], rows[1]["low"], rows[1]["close"], rows[1]["volume"]), (1184.0, 1201.9, 1163.1, 1190.0, 14905641.0))

    def test_the_call_uses_the_exact_title_and_never_asks_for_more_than_groww_allows(self):
        fake = FakeGroww()
        self.candles(days=99999, fake=fake)
        args = next(c[1] for c in fake.calls if c[0] == "fetch_historical_candle_data")
        self.assertEqual((args["company_name"], args["last_n_days"], args["interval_in_minutes"]), ("Reliance Industries Ltd.", 1825, 1440))

    def test_a_stock_groww_does_not_match_exactly_gets_no_candles(self):
        fake = FakeGroww()
        self.assertEqual(self.candles("NSE:TATAMOTORS", fake=fake), [])
        self.assertNotIn("fetch_historical_candle_data", [c[0] for c in fake.calls])

    def test_times_become_the_indian_trading_day(self):
        self.assertEqual(gm.to_ist_date("2026-10-23T00:00:00"), "2026-10-23")  # local text stays as is
        self.assertEqual(gm.to_ist_date("2026-10-22T18:30:00Z"), "2026-10-23")  # UTC evening is the next IST day
        self.assertEqual(gm.to_ist_date("2026-10-23T00:00:00+05:30"), "2026-10-23")
        self.assertEqual(gm.to_ist_date(1792694400), "2026-10-23")  # seconds
        self.assertEqual(gm.to_ist_date(1792694400000), "2026-10-23")  # milliseconds
        self.assertEqual(gm.to_ist_date("1792694400000"), "2026-10-23")
        for junk in (None, "", "soon", {}):
            self.assertIsNone(gm.to_ist_date(junk))

    def test_impossible_candles_are_dropped_not_repaired(self):
        good = {"timestamp": "2026-10-22T00:00:00", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1}
        reply = {"result": {"candles": [
            good,
            {**good, "timestamp": "2026-10-23T00:00:00", "close": 0},
            {**good, "timestamp": "2026-10-26T00:00:00", "high": 8},  # high under low
            {**good, "timestamp": "2026-10-27T00:00:00", "close": 13},  # close outside the range
            {**good, "timestamp": None},
            "junk",
        ]}}
        rows = self.candles(fake=FakeGroww(candles=reply, ltp=ltp_for("Reliance Industries Ltd.", "RELIANCE", 11.0, 11.0)))
        self.assertEqual([r["date"] for r in rows], ["2026-10-22"])

    def test_a_repeated_day_keeps_one_candle_and_the_order_is_by_date(self):
        a = {"timestamp": "2026-10-23T00:00:00", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 1}
        b = {**a, "timestamp": "2026-10-22T00:00:00"}
        rows = self.candles(fake=FakeGroww(candles={"result": {"candles": [a, b, {**a, "close": 1.5}]}}, ltp=ltp_for("Reliance Industries Ltd.", "RELIANCE", 1.5, 2.0)))
        self.assertEqual([r["date"] for r in rows], ["2026-10-22", "2026-10-23"])
        self.assertEqual(len(rows), 2)

    def test_candles_of_another_instrument_are_refused(self):
        # what Groww really did for "Nifty 50": it answered with Reliance's candles, naming no instrument
        nifty_like = {"result": {"candles": [{"timestamp": f"2026-10-2{d}T00:00:00", "open": 22500, "high": 22800, "low": 22400, "close": 22600.0 + d, "volume": 1} for d in (1, 2, 3)]}}
        fake = FakeGroww(candles=nifty_like)  # the quote is Reliance's, 1190 -> 1201.8
        self.assertEqual(self.candles(fake=fake), [])

    def test_candles_that_cannot_be_checked_against_a_quote_are_refused(self):
        self.assertEqual(self.candles(fake=FakeGroww(ltp={"result": {"ltp_results": {}}})), [])

    def test_an_index_never_uses_the_candle_tool(self):
        fake = FakeGroww()
        with fresh_market():
            self.assertEqual(run(gm.fetch_groww_daily_candles(fake, "NSE:NIFTY 50", 14)), [])
        self.assertNotIn("fetch_historical_candle_data", [c[0] for c in fake.calls])

    def test_the_consistency_check(self):
        from core.models import QuoteItem

        def rows(*closes):
            return [{"date": f"2026-10-{20 + i}", "open": c, "high": c, "low": c, "close": c, "volume": 1} for i, c in enumerate(closes)]

        def q(last, prev):
            return QuoteItem(instrument="NSE:X", last_price=last, close_price=prev, day_change=last - prev)

        ok = gm.consistent_with_quote
        self.assertTrue(ok(rows(98.0, 100.0, 103.0), q(103.0, 100.0)))  # after the close
        self.assertTrue(ok(rows(98.0, 100.0, 101.5), q(102.0, 100.0)))  # a running bar a little behind the quote
        self.assertTrue(ok(rows(98.0, 100.0), q(100.0, 98.0)))  # a weekend: last price is Friday's close
        self.assertFalse(ok(rows(98.0, 100.0, 103.0), q(103.0, 90.0)))  # previous close appears nowhere
        self.assertFalse(ok(rows(98.0, 100.0, 130.0), q(103.0, 100.0)))  # latest candle far from the price
        self.assertFalse(ok(rows(98.0, 100.0, 103.0), q(103.0, 0.0)))  # no previous close to check against
        self.assertFalse(ok(rows(), q(103.0, 100.0)))
        self.assertFalse(ok(rows(100.0), None))

    def test_a_failed_call_gives_no_candles(self):
        fake = FakeGroww()
        orig = fake.call_tool

        async def call(name, args=None):
            if name == "fetch_historical_candle_data":
                raise RuntimeError("down")
            return await orig(name, args)

        fake.call_tool = call
        self.assertEqual(self.candles(fake=fake), [])


# ---- as the stand-in for Kite ----------------------------------------------------------------------------------


class LoggedOutKite:
    owner_id = "u1"

    async def get_quotes(self, batch):
        raise KiteAuthRequiredError("login", auth_url="x")


def quote(inst, price):
    from core.models import QuoteItem

    return QuoteItem(instrument=inst, last_price=price, day_change=1.0, day_change_percentage=0.5, close_price=price - 1)


class StandInTests(unittest.TestCase):
    def fetch(self, kite, ind, groww, budget=8.0, instruments=("NSE:A", "NSE:B")):
        svc = MCPMarketDataService()
        with patch("core.market_data.service.get_user_indmoney_client", AsyncMock(return_value=ind[0])), \
                patch("core.market_data.service.fetch_indmoney_quotes", ind[1]), \
                patch("core.market_data.service.get_user_groww_client", AsyncMock(return_value=groww[0])), \
                patch("core.market_data.service.fetch_groww_quotes", groww[1]), \
                patch("core.market_data.service.INDMONEY_FALLBACK_SECONDS", budget):
            return run(svc.fetch_live_quotes(list(instruments), client=kite))

    def test_indmoney_first_then_groww_for_what_is_left(self):
        ind = AsyncMock(return_value={"NSE:A": quote("NSE:A", 10.0)})
        grw = AsyncMock(return_value={"NSE:B": quote("NSE:B", 20.0)})
        quotes, ok = self.fetch(LoggedOutKite(), (object(), ind), (object(), grw))
        self.assertTrue(ok)
        self.assertEqual({k: v.last_price for k, v in quotes.items()}, {"NSE:A": 10.0, "NSE:B": 20.0})
        self.assertEqual(grw.await_args.args[1], ["NSE:B"])  # Groww is only asked for what INDmoney did not price

    def test_groww_alone_serves_a_user_without_indmoney(self):
        grw = AsyncMock(return_value={"NSE:A": quote("NSE:A", 10.0), "NSE:B": quote("NSE:B", 20.0)})
        quotes, _ = self.fetch(LoggedOutKite(), (None, AsyncMock()), (object(), grw))
        self.assertEqual(set(quotes), {"NSE:A", "NSE:B"})

    def test_groww_is_not_asked_when_indmoney_priced_everything(self):
        ind = AsyncMock(return_value={"NSE:A": quote("NSE:A", 1.0), "NSE:B": quote("NSE:B", 2.0)})
        grw = AsyncMock(return_value={})
        self.fetch(LoggedOutKite(), (object(), ind), (object(), grw))
        self.assertFalse(grw.called)

    def test_neither_broker_is_asked_while_kite_is_up_or_fails_for_another_reason(self):
        class Flaky:
            owner_id = "u1"

            async def get_quotes(self, batch):
                raise TimeoutError("network")

        class Healthy:
            owner_id = "u1"

            async def get_quotes(self, batch):
                return {}

        for kite in (Flaky(), Healthy()):
            ind, grw = AsyncMock(return_value={}), AsyncMock(return_value={})
            quotes, _ = self.fetch(kite, (object(), ind), (object(), grw))
            self.assertEqual(quotes, {})
            self.assertFalse(ind.called or grw.called)

    def test_the_brokers_share_one_time_budget(self):
        async def slow(client, instruments):
            await asyncio.sleep(5)
            return {}

        grw = AsyncMock(return_value={"NSE:A": quote("NSE:A", 1.0)})
        started = time.monotonic()
        quotes, _ = self.fetch(LoggedOutKite(), (object(), slow), (object(), grw), budget=0.4)
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual(quotes, {})  # INDmoney used the whole budget, so Groww was not waited for
        self.assertFalse(grw.called)

    def test_a_broker_that_errors_does_not_stop_the_next_one(self):
        ind = AsyncMock(side_effect=RuntimeError("down"))
        grw = AsyncMock(return_value={"NSE:A": quote("NSE:A", 3.0)})
        quotes, _ = self.fetch(LoggedOutKite(), (object(), ind), (object(), grw))
        self.assertEqual(quotes["NSE:A"].last_price, 3.0)


class CandleStandInTests(unittest.TestCase):
    class Lapsed:
        owner_id = "u1"

    class History:
        async def get_daily_candles(self, client, token, lookback):
            raise KiteAuthRequiredError("login", auth_url="x")

    def recent(self, ind_client, groww_client, ind_rows, groww_rows):
        with patch.object(candle_store, "get_user_indmoney_client", AsyncMock(return_value=ind_client)), \
                patch.object(candle_store, "fetch_daily_candles", AsyncMock(return_value=ind_rows)), \
                patch.object(candle_store, "get_user_groww_client", AsyncMock(return_value=groww_client)), \
                patch.object(candle_store, "fetch_groww_daily_candles", AsyncMock(return_value=groww_rows)), \
                patch.object(candle_store, "latest_completed_session", return_value="2026-10-23"):
            return run(candle_store._recent(self.Lapsed(), self.History(), 1, {"id": "NSE:X"}, 12))

    ROW = [{"date": "2026-10-22", "open": 1, "high": 1, "low": 1, "close": 5.0, "volume": 1}]

    def test_groww_tops_up_when_indmoney_is_absent_or_empty(self):
        self.assertEqual(self.recent(None, object(), [], self.ROW), (self.ROW, True))
        self.assertEqual(self.recent(object(), object(), [], self.ROW), (self.ROW, True))

    def test_indmoney_wins_when_it_has_candles(self):
        other = [{**self.ROW[0], "close": 9.0}]
        self.assertEqual(self.recent(object(), object(), other, self.ROW), (other, True))

    def test_with_neither_the_kite_login_error_stands(self):
        with self.assertRaises(KiteAuthRequiredError):
            self.recent(None, None, [], [])

    def top_up(self, stored_date, fallback_rows):
        candle_store._mem["7"] = ([{"date": stored_date, "open": 5, "high": 5, "low": 5, "close": 5.0, "volume": 1}], {"checked_at": 0})
        saved = AsyncMock()
        try:
            with patch.object(candle_store, "get_history_service", return_value=self.History()), \
                    patch.object(candle_store, "get_user_indmoney_client", AsyncMock(return_value=None)), \
                    patch.object(candle_store, "get_user_groww_client", AsyncMock(return_value=object())), \
                    patch.object(candle_store, "fetch_groww_daily_candles", AsyncMock(return_value=fallback_rows)), \
                    patch.object(candle_store, "latest_completed_session", return_value="2026-10-23"), \
                    patch.object(candle_store, "_save", saved):
                got, _ = run(candle_store.get_india_candles(self.Lapsed(), {"instrument_token": 7, "id": "NSE:X"}))
        finally:
            candle_store._mem.pop("7", None)
        return got, saved

    def test_fallback_candles_that_share_no_day_with_the_stored_ones_are_not_trusted(self):
        # a different company's candles would not overlap any stored day
        got, saved = self.top_up("2026-10-01", [{"date": "2026-10-22", "open": 99, "high": 99, "low": 99, "close": 99.0, "volume": 1}])
        self.assertEqual([c["date"] for c in got], ["2026-10-01"])
        self.assertFalse(saved.called)

    def test_matching_fallback_candles_extend_the_history(self):
        rows = [{"date": "2026-10-20", "open": 5, "high": 5, "low": 5, "close": 5.0, "volume": 1}, {"date": "2026-10-22", "open": 6, "high": 6, "low": 6, "close": 6.0, "volume": 1}]
        got, saved = self.top_up("2026-10-20", rows)
        self.assertEqual([c["date"] for c in got], ["2026-10-20", "2026-10-22"])
        self.assertTrue(saved.called)

    def test_a_disagreeing_overlap_keeps_the_stored_history(self):
        rows = [{"date": "2026-10-20", "open": 9, "high": 9, "low": 9, "close": 9.0, "volume": 1}, {"date": "2026-10-22", "open": 9, "high": 9, "low": 9, "close": 9.0, "volume": 1}]
        got, saved = self.top_up("2026-10-20", rows)
        self.assertEqual([c["close"] for c in got], [5.0])
        self.assertFalse(saved.called)


class SignalsAndTimerTests(unittest.TestCase):
    def test_a_groww_only_user_can_refresh_known_stocks_but_a_new_stock_needs_kite(self):
        class Lapsed:
            owner_id = "u1"

        history = SimpleNamespace(resolve_instrument=AsyncMock(side_effect=KiteAuthRequiredError("login", auth_url="x")))
        with patch.object(equity_signals, "get_history_service", return_value=history), \
                patch.object(equity_signals, "get_user_indmoney_client", AsyncMock(return_value=None)), \
                patch.object(equity_signals, "get_user_groww_client", AsyncMock(return_value=object())), \
                patch.object(equity_signals, "_stored_instrument", AsyncMock(return_value=None)):
            with self.assertRaises(ValueError) as caught:  # a per-stock failure, not "the login expired"
                run(equity_signals.compute_stock_signals(Lapsed(), "NEWSTOCK", None))
            self.assertIn("Kite login", str(caught.exception))
        with patch.object(equity_signals, "get_history_service", return_value=history), \
                patch.object(equity_signals, "get_user_indmoney_client", AsyncMock(return_value=None)), \
                patch.object(equity_signals, "get_user_groww_client", AsyncMock(return_value=None)):
            with self.assertRaises(KiteAuthRequiredError):
                run(equity_signals.compute_stock_signals(Lapsed(), "ANY", None))

    def test_groww_users_are_found_from_their_token_files(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            for name in ("groww_tokens_google_1__conn_groww_live.json", "groww_tokens_google_2__conn_groww_live.json", "groww_tokens_conn_groww_live.json", "groww_tokens.json"):
                (Path(d) / name).write_text(json.dumps({}), encoding="utf-8")
            with patch.object(ar, "data_dir", return_value=Path(d)):
                self.assertEqual(ar.groww_owners(), ["google_1", "google_2"])

    def test_the_timer_serves_a_user_whose_only_login_is_groww(self):
        async def case():
            with patch.object(ar, "kite_owners", return_value=[]), \
                    patch.object(ar, "indmoney_owners", return_value=["g"]), \
                    patch.object(ar, "groww_owners", return_value=["g", "h"]), \
                    patch.object(ar, "get_user_kite_client", AsyncMock(side_effect=lambda o: f"kite-{o}")), \
                    patch.object(ar, "get_user_indmoney_client", AsyncMock(return_value=None)), \
                    patch.object(ar, "get_user_groww_client", AsyncMock(side_effect=lambda o: object() if o == "g" else None)):
                return await ar._live_clients()

        self.assertEqual(run(case()), [("g", "kite-g")])  # h has a token file but no usable login


class CallbackRouteTests(unittest.TestCase):
    def test_the_indmoney_callback_escapes_the_error_it_echoes(self):
        from apps.api.routers import portfolio

        evil = "<script>alert(1)</script>"
        resp = run(portfolio.indmoney_oauth_callback(code=None, state=None, error=evil, error_description=evil))
        body = resp.body.decode()
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn(evil, body)
        self.assertIn("&lt;script&gt;", body)

    def test_groww_is_a_credential_broker_and_angel_one_stays_switched_off(self):
        from apps.api.routers.portfolio import BROKER_METADATA_CATALOG as cat, CREDENTIAL_BROKERS

        self.assertIn("groww", CREDENTIAL_BROKERS)
        self.assertFalse(cat["angelone"]["supported"])  # deliberately not offered for now
        self.assertTrue(cat["angelone"]["coming_soon"])
        keys = {f["key"]: f for f in cat["groww"]["credential_fields"]}
        self.assertTrue(keys["api_key"]["required"])
        self.assertIn("totp_secret", keys)
        self.assertIn("TOTP", cat["groww"]["auth_type"])


AZURE = "https://wv.example.com/api/v1/portfolio/oauth/groww/callback"


class FakeRegistration:
    """Groww's registration endpoint: answers with `reply` and records what was asked."""

    def __init__(self, reply, status=200):
        self.reply, self.status, self.asked = reply, status, []

    def post(self, url, json=None, **k):
        self.asked.append(json)
        outer = self

        class Resp:
            status = outer.status

            async def json(self, content_type=None):
                return outer.reply

            async def __aenter__(self):
                return self

            async def __aexit__(self, *e):
                return False

        return Resp()


class RegistrationTests(unittest.TestCase):
    """A login client is only good for the address it was registered with."""

    def setUp(self):
        import json
        import tempfile
        from pathlib import Path

        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)
        self.json = json
        self.patches = [patch.object(gc, "data_dir", return_value=self.dir)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self._dir.cleanup()

    def registry(self, data=None):
        path = self.dir / "groww_oauth_clients.json"
        if data is not None:
            path.write_text(self.json.dumps(data), encoding="utf-8")
        return self.json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def deployed_client(self):
        with patch.object(gc, "public_base_url", return_value="https://wv.example.com"):
            return GrowwMCPClient(connection_id="c", owner_id="o")

    def test_a_deployed_server_never_borrows_a_client_registered_for_another_address(self):
        # what happened on Azure: a client registered for the laptop's address was used for the Azure one
        self.registry({"http://127.0.0.1:8000/api/v1/portfolio/oauth/groww/callback": {"client_id": "laptop"}, "default": {"client_id": "laptop"}})
        self.assertEqual(self.deployed_client().client_id, "")

    def test_a_deployed_server_ignores_a_client_id_from_settings(self):
        with patch.object(gc, "get_settings", return_value=SimpleNamespace(GROWW_CLIENT_ID="from-settings", GROWW_CLIENT_SECRET="s")):
            self.assertEqual(self.deployed_client().client_id, "")

    def test_an_old_entry_for_this_address_without_its_address_recorded_is_not_trusted(self):
        self.registry({AZURE: {"client_id": "unknown-origin"}})
        self.assertEqual(self.deployed_client().client_id, "")

    def test_a_client_registered_for_exactly_this_address_is_used(self):
        self.registry({AZURE: {"client_id": "azure-client", "client_secret": "x", "registered_for": AZURE}})
        self.assertEqual(self.deployed_client().client_id, "azure-client")

    def test_a_local_run_may_reuse_a_client_registered_for_another_local_port(self):
        self.registry({"http://127.0.0.1:8000/api/v1/portfolio/oauth/groww/callback": {"client_id": "laptop"}})
        with patch.object(gc, "public_base_url", return_value=""):
            self.assertEqual(GrowwMCPClient(connection_id="c", owner_id="o").client_id, "laptop")

    def register(self, reply, status=200):
        client = self.deployed_client()
        fake = FakeRegistration(reply, status)
        client._get_http_session = lambda: fake
        return client, fake

    def test_registration_asks_for_this_address_and_records_it(self):
        client, fake = self.register({"client_id": "new", "client_secret": "s", "client_name": "WealthVault", "redirect_uris": [AZURE]})
        run(client.ensure_client())
        self.assertEqual(fake.asked[0]["redirect_uris"], [AZURE])
        self.assertEqual(client.client_id, "new")
        saved = self.registry()
        self.assertEqual(saved[AZURE]["registered_for"], AZURE)
        self.assertNotIn("default", saved)  # a public address never becomes everyone's fallback
        self.assertEqual(self.deployed_client().client_id, "new")  # and the next start uses it

    def test_a_registration_that_leaves_out_this_address_is_refused_and_not_saved(self):
        client, _ = self.register({"client_id": "shared", "client_secret": "s", "redirect_uris": ["http://localhost:52155/oauth/callback"]})
        with self.assertRaises(gc.GrowwRegistrationError) as caught:
            run(client.ensure_client())
        self.assertIn(AZURE, str(caught.exception))
        self.assertEqual(self.registry(), {})
        self.assertEqual(client.client_id, "")

    def test_a_failed_registration_never_shows_the_secret(self):
        client, _ = self.register({"error": "invalid_redirect_uri", "client_secret": "TOPSECRET"}, status=400)
        with self.assertRaises(gc.GrowwRegistrationError) as caught:
            run(client.ensure_client())
        self.assertNotIn("TOPSECRET", str(caught.exception))

    def test_login_link_reports_the_reason_instead_of_raising(self):
        client, _ = self.register({"client_id": "shared", "redirect_uris": ["http://localhost:52155/oauth/callback"]})
        link, problem = run(gc.login_link(client))
        self.assertIsNone(link)
        self.assertIn("can't be started", problem)

    def test_login_link_gives_a_link_for_a_good_registration(self):
        client, _ = self.register({"client_id": "new", "client_secret": "s", "redirect_uris": [AZURE]})
        link, problem = run(gc.login_link(client))
        self.assertIsNone(problem)
        self.assertIn("client_id=new", link)
        self.assertIn("redirect_uri=https%3A%2F%2Fwv.example.com", link)


if __name__ == "__main__":
    unittest.main()
