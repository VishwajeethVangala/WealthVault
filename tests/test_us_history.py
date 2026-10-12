"""Rules that keep stored US price history exact: source precedence, vendor validation, thinned data refusal."""

import asyncio

import pytest

from core.market_data import us_history as uh


def _c(date, close, volume=1000.0):
    return {"date": date, "open": close, "high": close, "low": close, "close": close, "volume": volume}


def test_merge_keeps_indmoney_for_every_date_it_covers():
    ind = [_c("2026-01-02", 100.0), _c("2026-01-05", 101.0)]
    yahoo = [_c("2025-12-31", 99.0), _c("2026-01-02", 555.0), _c("2026-01-05", 555.0)]
    merged = uh._merge(yahoo, ind)
    assert [r[0] for r in merged] == ["2025-12-31", "2026-01-02", "2026-01-05"]
    assert [r[4] for r in merged] == [99.0, 100.0, 101.0]
    assert [r[6] for r in merged] == ["y", "i", "i"]  # Yahoo only fills dates before INDmoney's window


def test_vendor_check_trusts_matching_sources_and_tolerates_a_stray_day():
    ind = [_c(f"2026-02-{d:02d}", 100.0 + d) for d in range(1, 29)]
    yahoo = [dict(r) for r in ind]
    yahoo[3]["close"] *= 1.05  # one isolated disagreement, like a fresh IPO's early days
    trusted, bad, _ = uh._vendor_check(ind, yahoo)
    assert trusted and bad == 1


def test_vendor_check_rejects_a_source_on_a_different_price_basis():
    ind = [_c(f"2026-02-{d:02d}", 100.0) for d in range(1, 29)]
    yahoo = [_c(r["date"], 90.0) for r in ind]  # e.g. dividend-adjusted: every day is off
    trusted, _bad, note = uh._vendor_check(ind, yahoo)
    assert not trusted and "disagrees" in note


def test_vendor_check_rejects_too_little_overlap():
    ind = [_c(f"2026-02-{d:02d}", 100.0) for d in range(1, 29)]
    yahoo = [_c("2026-02-01", 100.0)]
    assert not uh._vendor_check(ind, yahoo)[0]


class _FakeClient:
    def __init__(self, entry):
        self.entry = entry

    async def call_tool(self, name, args):
        return {"prices": {"NVDA": self.entry}}


def test_thinned_indmoney_history_is_refused():
    candles = [{"date": "2026-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    client = _FakeClient({"count": 1, "candles": candles, "candles_total": 250})
    with pytest.raises(uh.UsHistoryError):
        asyncio.run(uh.fetch_indmoney_candles(client, "NVDA", "1y"))


def test_complete_indmoney_history_is_accepted_and_sorted():
    candles = [
        {"date": "2026-01-05", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 1},
        {"date": "2026-01-02", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ]
    rows = asyncio.run(uh.fetch_indmoney_candles(_FakeClient({"count": 2, "candles": candles}), "NVDA", "1y"))
    assert [r["date"] for r in rows] == ["2026-01-02", "2026-01-05"]


def test_gap_picks_the_smallest_window_that_covers_it():
    assert uh._window_for_gap(3) == "1m"
    assert uh._window_for_gap(60) == "3m"
    assert uh._window_for_gap(120) == "6m"
    assert uh._window_for_gap(220) == "1y"
