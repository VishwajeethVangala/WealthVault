"""Strategies and signal tables must run on today's live price, not wait for the close."""

import asyncio
import os
import random
from datetime import date, timedelta
from types import SimpleNamespace as NS

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

from core.analytics import live_signals
from core.analytics.equity_signals import build_signal_row
from core.market_data import candle_store
from core.market_data.live_bar import apply_live_quote, india_today, us_today
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
TODAY = "2026-10-13"  # a Tuesday


def _candles(n=420, end="2026-10-12", start_price=100.0, drift=0.001):
    random.seed(7)
    out, p = [], start_price
    d = date.fromisoformat(end) - timedelta(days=n * 7 // 5 + 10)
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() >= 5:
            continue
        p *= 1 + drift + random.uniform(-0.01, 0.01)
        out.append({"date": d.isoformat(), "open": p, "high": p * 1.005, "low": p * 0.995, "close": p, "volume": 1e5})
    out[-1]["date"] = end
    return out


def test_live_quote_replaces_todays_forming_candle():
    c = _candles(5, end=TODAY)
    last = c[-1]
    live, applied = apply_live_quote(c, TODAY, last["close"] * 1.03, high=last["high"] * 1.04, low=last["low"] * 0.99)
    assert applied and len(live) == len(c) and live[-1]["close"] == last["close"] * 1.03
    assert live[-1]["high"] >= live[-1]["close"] and live[-1]["open"] == last["open"]
    assert c[-1]["close"] == last["close"]  # the input is untouched


def test_live_quote_adds_a_bar_for_today():
    c = _candles(5, end="2026-10-12")
    live, applied = apply_live_quote(c, TODAY, 150.0, open_=148.0, high=151.0, low=147.0, volume=5000)
    assert applied and len(live) == len(c) + 1
    assert live[-1] == {"date": TODAY, "open": 148.0, "high": 151.0, "low": 147.0, "close": 150.0, "volume": 5000}


def test_a_holiday_echo_of_the_last_session_adds_no_phantom_bar():
    c = _candles(5, end="2026-10-12")
    last = c[-1]
    live, applied = apply_live_quote(c, TODAY, last["close"], open_=last["open"], high=last["high"], low=last["low"])
    assert not applied and live is c
    live, applied = apply_live_quote(c, TODAY, last["close"])  # no OHLC (US quotes), price unchanged
    assert not applied


def test_no_live_bar_before_the_session_opens_or_without_a_price():
    assert india_today(datetime(2026, 10, 13, 9, 0, tzinfo=IST)) is None
    assert india_today(datetime(2026, 10, 13, 9, 15, tzinfo=IST)) == TODAY
    assert india_today(datetime(2026, 10, 17, 12, 0, tzinfo=IST)) is None  # Saturday
    assert us_today(datetime(2026, 10, 13, 9, 29, tzinfo=ZoneInfo("America/New_York"))) is None
    c = _candles(5)
    assert apply_live_quote(c, TODAY, None) == (c, False)
    assert apply_live_quote(c, None, 100.0) == (c, False)


def test_stored_candles_are_rebuilt_when_the_data_was_restated():
    stored = [{"date": "2026-10-09", "close": 100.0}, {"date": "2026-10-12", "close": 102.0}]
    assert not candle_store.restated(stored, [{"date": "2026-10-12", "close": 102.3}])  # a rounding difference
    assert candle_store.restated(stored, [{"date": "2026-10-12", "close": 51.0}])  # a 2:1 split


def _setup_live(monkeypatch, last_price, history_end="2026-10-12"):
    candles = _candles(420, end=history_end)
    nifty = _candles(420, end=history_end, start_price=20000, drift=0.0005)
    candle_store._mem.clear()
    candle_store._mem["111"] = (candles, {})
    candle_store._mem["256265"] = (nifty, {})
    live_signals._row_cache.clear()

    cached = build_signal_row("NSE:ABC", {"name": "ABC", "tick_size": 0.05}, candles, nifty[-300:], extra={"token": 111, "tick_size": 0.05})
    quote = NS(last_price=last_price, open_price=candles[-1]["close"], high_price=last_price * 1.01, low_price=candles[-1]["close"] * 0.99)
    nq = NS(last_price=nifty[-1]["close"] * 1.002, open_price=nifty[-1]["close"], high_price=nifty[-1]["close"] * 1.004, low_price=nifty[-1]["close"] * 0.998)

    class _Svc:
        async def fetch_live_quotes(self, ids, client=None):
            return {"NSE:ABC": quote, "NSE:NIFTY 50": nq}, True

    monkeypatch.setattr(live_signals, "get_market_data_service", lambda: _Svc())
    monkeypatch.setattr(live_signals, "india_today", lambda: TODAY)
    return candles, cached


def test_signal_rows_are_rebuilt_on_the_live_price(monkeypatch):
    price = _candles(420)[-1]["close"] * 1.05
    candles, cached = _setup_live(monkeypatch, last_price=price)

    rows = asyncio.run(live_signals.live_india_rows(object(), {"NSE:ABC": cached, "ABC": cached}))

    live = rows["NSE:ABC"]
    assert rows["ABC"] is live  # a stock stored under two keys gets the same live row
    assert live["live"]["price"] == price and live["live_date"] == TODAY
    assert live["as_of"] == TODAY and live["last_sessions"][-1] == TODAY
    assert cached["as_of"] == "2026-10-12"  # the cached row rests on finished sessions only
    assert live["momentum"]["verdict"]
    assert live["history_days"] == cached["history_days"] + 1


def test_rows_whose_stored_history_is_behind_keep_their_cached_row(monkeypatch):
    _, cached = _setup_live(monkeypatch, last_price=120.0, history_end="2026-10-08")  # misses the 9th and 12th
    rows = asyncio.run(live_signals.live_india_rows(object(), {"NSE:ABC": cached}))
    assert rows == {}


def test_nothing_is_recomputed_while_the_session_has_not_opened(monkeypatch):
    _, cached = _setup_live(monkeypatch, last_price=120.0)
    monkeypatch.setattr(live_signals, "india_today", lambda: None)
    assert asyncio.run(live_signals.live_india_rows(object(), {"NSE:ABC": cached})) == {}


def test_cleanup():
    candle_store._mem.clear()
    live_signals._row_cache.clear()


class _FakeRepo:
    saved = {}

    async def load(self, token):
        rows, meta = _FakeRepo.saved.get(token, ([], {}))
        return list(rows), dict(meta)

    async def save_years(self, token, candles, years, meta):
        _FakeRepo.saved[token] = (list(candles), dict(meta))

    async def clear(self, token):
        _FakeRepo.saved.pop(token, None)


def _store_env(monkeypatch, history_candles, full_candles=None):
    calls = {"topup": 0, "full": 0}

    class _Hist:
        async def get_daily_candles(self, client, token, lookback):
            calls["topup"] += 1
            return history_candles

        async def get_full_daily_history(self, client, token, earliest=None):
            calls["full"] += 1
            return full_candles if full_candles is not None else history_candles

    _FakeRepo.saved = {}
    candle_store._mem.clear()
    monkeypatch.setattr(candle_store, "IndiaCandleRepository", _FakeRepo)
    monkeypatch.setattr(candle_store, "get_history_service", lambda: _Hist())
    monkeypatch.setattr(candle_store, "latest_completed_session", lambda now=None: "2026-10-12")
    return calls


def test_first_use_fetches_the_full_history_once_then_serves_it_from_the_store(monkeypatch):
    history = _candles(300, end="2026-10-12")
    calls = _store_env(monkeypatch, history)
    inst = {"instrument_token": 5, "id": "NSE:X"}

    first, meta = asyncio.run(candle_store.get_india_candles(object(), inst))
    assert calls == {"topup": 0, "full": 1} and len(first) == 300 and meta["last"] == "2026-10-12"

    candle_store._mem.clear()  # a restart: the store, not Kite, supplies the history
    again, _ = asyncio.run(candle_store.get_india_candles(object(), inst))
    assert calls == {"topup": 0, "full": 1} and len(again) == 300


def test_a_top_up_adds_only_new_sessions_and_a_restatement_triggers_a_rebuild(monkeypatch):
    newer = _candles(300, end="2026-10-12")
    old = [c for c in newer if c["date"] <= "2026-10-09"]
    calls = _store_env(monkeypatch, newer, full_candles=newer)
    candle_store._mem["5"] = (old, {})
    got, _ = asyncio.run(candle_store.get_india_candles(object(), {"instrument_token": 5, "id": "NSE:X"}))
    assert calls["topup"] == 1 and calls["full"] == 0 and got[-1]["date"] == "2026-10-12"
    assert len(got) == len(newer) and got[: len(old)] == old

    split = [{**c, "close": c["close"] / 2} for c in newer]
    calls = _store_env(monkeypatch, split, full_candles=split)
    candle_store._mem["5"] = (old, {})
    got, _ = asyncio.run(candle_store.get_india_candles(object(), {"instrument_token": 5, "id": "NSE:X"}))
    assert calls["full"] == 1  # prices no longer match, so the stock is rebuilt


def test_reading_without_fetching_never_calls_kite(monkeypatch):
    calls = _store_env(monkeypatch, _candles(10))
    got, _ = asyncio.run(candle_store.get_india_candles(object(), {"instrument_token": 9, "id": "NSE:Y"}, allow_fetch=False))
    assert got == [] and calls == {"topup": 0, "full": 0}


def test_us_rows_are_rebuilt_on_the_live_price_and_incomplete_history_stays_suppressed(monkeypatch):
    spy = _candles(420, end="2026-10-12", start_price=400)
    nvda = _candles(420, end="2026-10-12", start_price=100, drift=0.002)

    async def fake_candles(ticker):
        return {"SPY": spy, "NVDA": nvda}.get(ticker, [])

    monkeypatch.setattr(live_signals, "_us_candles", fake_candles)
    monkeypatch.setattr(live_signals, "us_today", lambda: TODAY)
    live_signals._row_cache.clear()
    extra = {"currency": "USD", "history_status": "complete"}
    cached = build_signal_row("US:NVDA", {"name": "NVIDIA", "tick_size": 0.01}, nvda, spy[-300:], benchmark_name="S&P 500 (SPY)", extra=extra)
    price = nvda[-1]["close"] * 1.04
    quotes = {"NVDA": {"price": price}, "SPY": {"price": spy[-1]["close"] * 1.001}}

    rows = asyncio.run(live_signals.live_us_rows({"US:NVDA": cached}, quotes, {"NVDA": "NVIDIA"}, 0.01))
    live = rows["US:NVDA"]
    assert live["live"]["price"] == price and live["as_of"] == TODAY and live["currency"] == "USD"

    live_signals._row_cache.clear()
    partial = {**cached, "history_status": "partial"}
    rows = asyncio.run(live_signals.live_us_rows({"US:NVDA": partial}, quotes, {"NVDA": "NVIDIA"}, 0.01))
    assert rows["US:NVDA"]["swing"] is None and rows["US:NVDA"]["ath"] is None
    live_signals._row_cache.clear()
