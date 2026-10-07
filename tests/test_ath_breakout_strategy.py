import asyncio
import math
import unittest
from datetime import date, datetime, timedelta

from core.analytics.ath_breakout_strategy import EXIT_DMA_BREAK, run_ath_breakout_strategy
from core.analytics.momentum import sma_series
from core.market_data.history import HistoricalDataService
from core.models import AthBreakoutParams

START = date(2016, 1, 1)


def candles_from(closes, start=START):
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "high": c + 0.5, "low": c - 0.5, "close": c}
        for i, c in enumerate(closes)
    ]


def cycle_closes():
    """Rise to an ATH, fall below the 200-DMA, rally through the old ATH, then break down."""
    closes = [100 + i / 3 for i in range(300)]          # A: steady rise, ATH ~200
    closes += [closes[-1] - 0.5 * k for k in range(1, 101)]  # B: decline below the DMA
    low = closes[-1]
    closes += [low + k for k in range(1, 81)]            # C: rally through the old ATH
    top = closes[-1]
    closes += [top - 2 * k for k in range(1, 61)]        # D: sharp fall below the DMA
    return closes


class TestAthBreakout(unittest.TestCase):

    def test_entry_on_ath_break_and_exit_on_dma_break(self):
        closes = cycle_closes()
        candles = candles_from(closes)
        res = run_ath_breakout_strategy("NSE:TEST", candles, AthBreakoutParams(start_date="2016-01-01"))

        highs = [c + 0.5 for c in closes]
        dma = sma_series(closes, 200)
        entry_idx = next(i for i in range(400, len(closes)) if closes[i] > max(highs[:i]))
        exit_idx = next(j for j in range(entry_idx + 1, len(closes)) if dma[j] is not None and closes[j] < dma[j])

        self.assertEqual(len(res.trades), 1)
        t = res.trades[0]
        self.assertEqual(t.entry_date, candles[entry_idx]["date"])
        self.assertAlmostEqual(t.entry_price, closes[entry_idx], places=2)  # fills at the signal close
        self.assertEqual(t.quantity, math.floor(50000 / closes[entry_idx]))
        self.assertEqual(t.exit_date, candles[exit_idx]["date"])
        self.assertEqual(t.exit_reason, EXIT_DMA_BREAK)
        self.assertAlmostEqual(t.pnl, round(t.quantity * (closes[exit_idx] - closes[entry_idx]), 2), places=1)
        self.assertEqual(res.stats.signal_exits, 1)
        self.assertEqual(res.stats.stop_exits, 0)
        self.assertAlmostEqual(res.stats.final_equity, 50000 + t.pnl, places=1)
        self.assertEqual(res.status.state, "FLAT")

    def test_no_entry_when_ath_break_is_outside_window(self):
        closes = [100 + i / 3 for i in range(300)]
        closes += [closes[-1] - 0.5 * k for k in range(1, 101)]
        low = closes[-1]
        closes += [low + k * 0.75 for k in range(1, 61)]     # recover above the DMA, still below the ATH
        plateau = closes[-1]
        closes += [plateau + 0.01 * k for k in range(260)]   # drift up, above the lagging DMA, for > window
        dma = sma_series(closes, 200)
        last_below = max(i for i, c in enumerate(closes) if dma[i] is not None and c < dma[i])
        self.assertGreater(len(closes) - last_below, 200)  # setup window has expired
        closes += [plateau + 3 * k for k in range(1, 30)]    # late breakout through the ATH
        res = run_ath_breakout_strategy("NSE:TEST", candles_from(closes), AthBreakoutParams(start_date="2016-01-01"))
        self.assertEqual(res.trades, [])
        self.assertFalse(res.status.in_window)

    def test_start_date_blocks_earlier_entries(self):
        closes = cycle_closes()
        res = run_ath_breakout_strategy("NSE:TEST", candles_from(closes), AthBreakoutParams(start_date="2030-01-01"))
        self.assertEqual(res.trades, [])

    def test_open_position_and_setup_status(self):
        closes = cycle_closes()[:-60]  # stop at the top of the rally, still in the trade
        res = run_ath_breakout_strategy("NSE:TEST", candles_from(closes), AthBreakoutParams(start_date="2016-01-01"))
        self.assertTrue(res.trades[-1].is_open)
        self.assertEqual(res.status.state, "IN_POSITION")
        self.assertGreater(res.status.pct_above_dma, 0)

        setup = cycle_closes()[:420]  # rallying but not yet through the old ATH
        res = run_ath_breakout_strategy("NSE:TEST", candles_from(setup), AthBreakoutParams(start_date="2016-01-01"))
        self.assertEqual(res.status.state, "FLAT")
        self.assertTrue(res.status.in_window)
        self.assertIsNotNone(res.status.window_days_left)
        self.assertGreater(res.status.pct_to_ath, 0)

    def test_requires_dma_history(self):
        with self.assertRaises(ValueError):
            run_ath_breakout_strategy("NSE:TEST", candles_from([100.0] * 150))


class FakeKite:
    """Serves daily candles from a synthetic history for the requested date range."""

    def __init__(self, first: date, last: date):
        self.calls = []
        self.days = []
        d = first
        while d <= last:
            self.days.append(d)
            d += timedelta(days=1)

    async def get_historical_data(self, token, from_date, to_date, interval="day"):
        self.calls.append((from_date, to_date))
        lo = datetime.strptime(from_date[:10], "%Y-%m-%d").date()
        hi = datetime.strptime(to_date[:10], "%Y-%m-%d").date()
        return [
            {"date": f"{d.isoformat()}T00:00:00+0530", "open": 1, "high": 1, "low": 1, "close": 1}
            for d in self.days
            if lo <= d <= hi
        ]


class TestFullHistory(unittest.TestCase):

    def test_pages_back_to_listing_date_without_duplicates(self):
        today = date.today()
        listed = today - timedelta(days=4500)
        fake = FakeKite(listed, today)
        candles = asyncio.run(HistoricalDataService().get_full_daily_history(fake, 1, earliest=listed.isoformat()))
        self.assertEqual(candles[0]["date"][:10], listed.isoformat())
        self.assertEqual(candles[-1]["date"][:10], today.isoformat())
        self.assertEqual(len(candles), len({c["date"][:10] for c in candles}))
        self.assertEqual(len(candles), 4501)
        self.assertEqual(len(fake.calls), 3)  # 4500 days -> three 2000-day chunks

    def test_stops_at_first_empty_chunk(self):
        today = date.today()
        fake = FakeKite(today - timedelta(days=2500), today)
        candles = asyncio.run(HistoricalDataService().get_full_daily_history(fake, 1))
        self.assertEqual(len(candles), 2501)
        self.assertEqual(len(fake.calls), 3)  # two with data, one empty


if __name__ == "__main__":
    unittest.main()
