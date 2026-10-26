"""INDmoney as the stand-in for Kite's prices and recent candles when Kite's login has lapsed."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.api import auto_refresh as ar
from core.market_data import candle_store, indmoney_market as im
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.service import MCPMarketDataService


def run(coro):
    return asyncio.run(coro)


def stats(symbol, price, prev, exchange="NSE"):
    return {
        "entity_basic": {"symbol": symbol, "name": symbol.title(), "exchange": exchange},
        "entity_stats": {"live_price": price, "prev_close": prev, "day_change": price - prev, "day_open": prev, "day_high": price, "day_low": prev},
    }


class FakeIndmoney:
    """Answers lookup_ind_keys loosely (best guess first, as the real one does) and details by key."""

    def __init__(self):
        self.calls = []
        self.details = {"INDS1": stats("RELIANCE", 1190.0, 1184.5), "INDS2": stats("RPOWER", 16.0, 17.0), "INDI1": stats("NIFTY 50", 22600.0, 22687.65)}
        self.lookups = {"RELIANCE": ["INDS1", "INDS2"], "NIFTY 50": ["INDI1"], "TATAMOTORS": ["INDS2"], "NOPE": []}
        self.candles = [{"datetime_ist": "2026-10-22 05:30:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    async def call_tool(self, name, args=None):
        self.calls.append(name)
        if name == "lookup_ind_keys":
            return [{"ind_key": k, "name": k} for k in self.lookups.get(args["names"][0], [])]
        if name == "get_indian_stocks_details":
            return {k: self.details[k] for k in args["ind_keys"] if k in self.details}
        if name == "get_indian_stocks_ohlc":
            return {"candles": self.candles}
        raise AssertionError(name)


def fresh_module():
    im._keys.clear()
    im._misses.clear()
    im._loaded = True  # no saved keys, and no table to write to
    return patch.object(im, "SymbolMapRepository", return_value=SimpleNamespace(save=AsyncMock()))


def test_a_key_is_accepted_only_when_its_details_show_the_exact_symbol():
    fake = FakeIndmoney()
    with fresh_module():
        keys = run(im.resolve_keys(fake, ["NSE:RELIANCE", "NSE:NIFTY 50", "NSE:TATAMOTORS", "NSE:NOPE"]))
    assert keys == {"NSE:RELIANCE": "INDS1", "NSE:NIFTY 50": "INDI1"}  # TATAMOTORS' only candidate is another company


def test_keys_found_once_are_not_looked_up_again_and_misses_rest_for_a_while():
    fake = FakeIndmoney()
    with fresh_module():
        run(im.resolve_keys(fake, ["NSE:RELIANCE", "NSE:NOPE"]))
        before = len(fake.calls)
        run(im.resolve_keys(fake, ["NSE:RELIANCE", "NSE:NOPE"]))
    assert len(fake.calls) == before


def test_quotes_carry_the_previous_close_and_the_day_change_from_it():
    with fresh_module():
        q = run(im.fetch_quotes(FakeIndmoney(), ["NSE:RELIANCE"]))["NSE:RELIANCE"]
    assert (q.last_price, q.close_price, q.day_change, q.day_change_percentage) == (1190.0, 1184.5, 5.5, 0.46)


def test_candles_are_read_as_dates_and_a_history_longer_than_a_year_is_refused():
    fake = FakeIndmoney()
    with fresh_module():
        rows = run(im.fetch_daily_candles(fake, "NSE:RELIANCE", 10))
        assert rows == [{"date": "2026-10-22", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}]
        assert run(im.fetch_daily_candles(fake, "NSE:RELIANCE", 900)) == []


def test_live_quotes_fall_back_to_indmoney_when_kite_is_logged_out():
    class LoggedOut:
        owner_id = "u1"

        async def get_quotes(self, batch):
            raise KiteAuthRequiredError("login", auth_url="x")

    service = MCPMarketDataService()
    with fresh_module(), patch("core.market_data.service.get_user_indmoney_client", AsyncMock(return_value=FakeIndmoney())):
        quotes, ok = run(service.fetch_live_quotes(["NSE:RELIANCE"], client=LoggedOut()))
    assert ok and quotes["NSE:RELIANCE"].last_price == 1190.0


def test_no_indmoney_login_means_no_quotes_not_an_error():
    class LoggedOut:
        owner_id = "u1"

        async def get_quotes(self, batch):
            raise KiteAuthRequiredError("login", auth_url="x")

    with patch("core.market_data.service.get_user_indmoney_client", AsyncMock(return_value=None)):
        quotes, ok = run(MCPMarketDataService().fetch_live_quotes(["NSE:RELIANCE"], client=LoggedOut()))
    assert quotes == {} and not ok


def stored(last="2026-10-20", close=100.0):
    return [{"date": last, "open": close, "high": close, "low": close, "close": close, "volume": 1}]


def test_stored_candles_are_topped_up_from_indmoney_when_kite_is_logged_out():
    class History:
        async def get_daily_candles(self, client, token, lookback):
            raise KiteAuthRequiredError("login", auth_url="x")

    fresh = [{"date": "2026-10-22", "open": 1, "high": 1, "low": 1, "close": 101.0, "volume": 1}]
    with patch.object(candle_store, "get_user_indmoney_client", AsyncMock(return_value=object())), \
            patch.object(candle_store, "fetch_daily_candles", AsyncMock(return_value=fresh)), \
            patch.object(candle_store, "latest_completed_session", return_value="2026-10-22"):
        got, from_indmoney = run(candle_store._recent(SimpleNamespace(owner_id="u1"), History(), 1, {"id": "NSE:X"}, 12))
    assert from_indmoney and got[-1]["close"] == 101.0


def test_without_an_indmoney_login_the_kite_error_still_stops_the_run():
    class History:
        async def get_daily_candles(self, client, token, lookback):
            raise KiteAuthRequiredError("login", auth_url="x")

    with patch.object(candle_store, "get_user_indmoney_client", AsyncMock(return_value=None)):
        try:
            run(candle_store._recent(SimpleNamespace(owner_id="u1"), History(), 1, {"id": "NSE:X"}, 12))
        except KiteAuthRequiredError:
            return
    raise AssertionError("expected the Kite login error")


def test_indmoney_candles_that_disagree_with_the_stored_ones_never_rebuild_the_history():
    class History:
        async def get_daily_candles(self, client, token, lookback):
            raise KiteAuthRequiredError("login", auth_url="x")

    candle_store._mem["9"] = (stored("2026-10-20", 100.0), {"checked_at": 0})
    differing = [{"date": "2026-10-20", "open": 1, "high": 1, "low": 1, "close": 150.0, "volume": 1}, {"date": "2026-10-22", "open": 1, "high": 1, "low": 1, "close": 150.0, "volume": 1}]
    saved = AsyncMock()
    try:
        with patch.object(candle_store, "get_history_service", return_value=History()), \
                patch.object(candle_store, "get_user_indmoney_client", AsyncMock(return_value=object())), \
                patch.object(candle_store, "fetch_daily_candles", AsyncMock(return_value=differing)), \
                patch.object(candle_store, "latest_completed_session", return_value="2026-10-22"), \
                patch.object(candle_store, "_save", saved):
            got, _ = run(candle_store.get_india_candles(SimpleNamespace(owner_id="u1"), {"instrument_token": 9, "id": "NSE:X"}))
    finally:
        candle_store._mem.pop("9", None)
    assert got[-1]["close"] == 100.0 and not saved.called


def test_users_with_an_indmoney_login_are_found_from_their_token_files(tmp_path):
    for name in ("indmoney_tokens_google_1__conn_indmoney_live.json", "indmoney_tokens_google_2__conn_indmoney_live.json", "indmoney_tokens.json"):
        (tmp_path / name).write_text(json.dumps({}), encoding="utf-8")
    with patch.object(ar, "data_dir", return_value=tmp_path):
        assert ar.indmoney_owners() == ["google_1", "google_2"]


def test_the_timer_serves_a_user_whose_kite_lapsed_but_whose_indmoney_is_connected():
    async def case():
        with patch.object(ar, "kite_owners", return_value=["a", "b"]), \
                patch.object(ar, "indmoney_owners", return_value=["b", "c"]), \
                patch.object(ar, "get_user_kite_client", AsyncMock(side_effect=lambda o: f"kite-{o}")), \
                patch.object(ar, "session_really_expired", AsyncMock(side_effect=lambda c: c == "kite-b")), \
                patch.object(ar, "get_user_indmoney_client", AsyncMock(side_effect=lambda o: object() if o in ("b",) else None)):
            return await ar._live_clients()

    # a: Kite live; b: Kite lapsed, INDmoney connected; c: INDmoney file but no usable login
    assert run(case()) == [("a", "kite-a"), ("b", "kite-b")]


def test_a_failed_kite_search_is_not_remembered_as_a_stock_with_no_match():
    from core.market_data import symbol_resolver as sr

    class Down:
        async def search_instruments(self, q, by):
            raise KiteAuthRequiredError("login", auth_url="x")

    repo = SimpleNamespace(get_all=AsyncMock(return_value={}), save=AsyncMock())
    with patch.object(sr, "SymbolMapRepository", return_value=repo):
        out = run(sr.resolve_indmoney_symbols(["INDS03339 (Paras Defence And Space)"], Down()))
    assert out == {} and not repo.save.called


def test_a_stock_on_the_be_series_is_matched_by_its_plain_symbol():
    fake = FakeIndmoney()
    fake.lookups["RELIANCE"] = ["INDS1"]
    with fresh_module():
        keys = run(im.resolve_keys(fake, ["NSE:RELIANCE-BE"]))
    assert keys == {"NSE:RELIANCE-BE": "INDS1"}


def test_indmoney_is_never_asked_while_kite_answers():
    class Healthy:
        owner_id = "u1"

        async def get_quotes(self, batch):
            return {}  # Kite is up but has nothing for this instrument

    asked = AsyncMock(return_value=FakeIndmoney())
    with patch("core.market_data.service.get_user_indmoney_client", asked):
        quotes, _ = run(MCPMarketDataService().fetch_live_quotes(["NSE:NOQUOTE"], client=Healthy()))
    assert quotes == {} and not asked.called
