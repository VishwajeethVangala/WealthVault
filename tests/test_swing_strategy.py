import unittest
from datetime import date, datetime, timedelta, timezone

from core.analytics.swing_strategy import (
    EXIT_SIGNAL,
    EXIT_STOP,
    atr_series,
    rma_series,
    run_swing_strategy,
    true_range,
    ut_trailing_stop,
)
from core.market_data.history import drop_incomplete_today
from core.models import SwingStrategyParams


def bars_from_closes(closes, spread=1.0, opens=None):
    """Daily candles with open = previous close (or explicit opens) and a fixed high/low spread."""
    start = date(2020, 1, 1)
    out = []
    for i, c in enumerate(closes):
        o = opens[i] if opens and opens[i] is not None else (closes[i - 1] if i else c)
        out.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": o,
            "high": max(o, c) + spread,
            "low": min(o, c) - spread,
            "close": c,
        })
    return out


def uptrend(n=260, start=100.0, step=0.5):
    return [start + step * i for i in range(n)]


class TestIndicators(unittest.TestCase):

    def test_true_range_and_rma(self):
        tr = true_range([12, 13, 15], [10, 11, 12], [11, 12, 14])
        self.assertEqual(tr, [2, 2, 3])  # bar 3: max(3, |15-12|, |12-12|)
        self.assertEqual(rma_series([2, 2, 2, 6], 3), [None, None, 2.0, (2 * 2 + 6) / 3])

    def test_atr_constant_range(self):
        closes = [100.0] * 20
        atr = atr_series([101.0] * 20, [99.0] * 20, closes, 10)
        self.assertIsNone(atr[8])
        self.assertAlmostEqual(atr[9], 2.0)
        self.assertAlmostEqual(atr[-1], 2.0)

    def test_ut_stop_ratchets_and_flips(self):
        closes = [100, 101, 102, 103, 99, 98, 97, 101]
        stop = ut_trailing_stop(closes, [None] + [2.0] * 7, key=1.0)
        self.assertIsNone(stop[0])
        self.assertEqual(stop[1:4], [99, 100, 101])  # trails 2 below a rising close
        self.assertEqual(stop[4], 101)                # close 99 < prev stop 101, prior close above -> branch 4
        self.assertEqual(stop[5], 100)                # both below -> min(prev, close + loss)
        self.assertEqual(stop[6], 99)
        self.assertEqual(stop[7], 99)                 # close 101 > 99 but prior close 97 < 99 -> close - loss


class TestSwingBacktest(unittest.TestCase):

    def dip_and_recover(self):
        """Steady uptrend, a 3-bar dip that flips the UT stop down, then a recovery that flips it up."""
        closes = uptrend()
        last = closes[-1]
        closes += [last - 4, last - 8, last - 12]
        closes += [last - 9, last - 5, last - 1, last + 3, last + 6]
        return closes

    def test_buy_fills_next_open_with_slippage_and_commission(self):
        candles = bars_from_closes(self.dip_and_recover())
        res = run_swing_strategy("NSE:TEST", candles, tick_size=0.05)
        buy_bars = [b for b in res.series if b.buy]
        self.assertEqual(len(buy_bars), 1)
        trade = res.trades[0]
        signal_idx = next(i for i, c in enumerate(candles) if c["date"] == buy_bars[0].date)
        self.assertEqual(trade.entry_date, candles[signal_idx + 1]["date"])
        self.assertAlmostEqual(trade.entry_price, candles[signal_idx + 1]["open"] + 0.05, places=2)
        # Whole shares sized so cost incl. 0.10% commission fits in capital
        self.assertLessEqual(trade.quantity * trade.entry_price * 1.001, 100000)
        self.assertGreater((trade.quantity + 1) * trade.entry_price * 1.001, 100000)
        self.assertTrue(trade.is_open)
        self.assertEqual(res.status.state, "IN_POSITION")
        self.assertTrue(res.stats.open_trade)

    def test_no_entry_without_bullish_regime(self):
        closes = list(reversed(self.dip_and_recover()))  # downtrend: below a falling 200-SMA
        res = run_swing_strategy("NSE:TEST", bars_from_closes(closes))
        self.assertEqual(res.trades, [])
        self.assertEqual(res.status.state, "FLAT")
        self.assertFalse(res.status.regime_bullish)

    def test_gap_down_through_stop_fills_at_open(self):
        closes = self.dip_and_recover()
        entry_close = closes[-1]
        # Hold a few bars, then gap far below the 2xATR stop
        closes += [entry_close + 1, entry_close + 2, entry_close - 40, entry_close - 41]
        opens = [None] * len(closes)
        opens[-2] = entry_close - 38
        candles = bars_from_closes(closes, opens=opens)
        res = run_swing_strategy("NSE:TEST", candles)
        stopped = [t for t in res.trades if t.exit_reason == EXIT_STOP]
        self.assertEqual(len(stopped), 1)
        self.assertEqual(stopped[0].exit_date, candles[-2]["date"])
        self.assertAlmostEqual(stopped[0].exit_price, opens[-2] - 0.05, places=2)
        self.assertLess(stopped[0].pnl, 0)
        self.assertTrue(any(b.stop_exit for b in res.series))

    def test_stop_disabled_leaves_position_open_through_gap(self):
        closes = self.dip_and_recover()
        closes += [closes[-1] - 40]
        res = run_swing_strategy("NSE:TEST", bars_from_closes(closes), params=SwingStrategyParams(use_stop=False))
        self.assertFalse(any(t.exit_reason == EXIT_STOP for t in res.trades))

    def test_missed_exit_when_ut_flips_above_ema(self):
        # Faithful to the Pine script: UT flips down while the close is still above the 20-EMA,
        # so no SELL fires, and later closes under the EMA do not trigger one either.
        closes = self.dip_and_recover()
        peak = closes[-1]
        closes += [peak + 2, peak + 3, peak - 3, peak - 8, peak - 12, peak - 14]
        res = run_swing_strategy("NSE:TEST", bars_from_closes(closes), params=SwingStrategyParams(use_stop=False))
        self.assertFalse(any(b.sell for b in res.series))
        self.assertTrue(res.trades[-1].is_open)
        self.assertLess(res.series[-1].close, res.series[-1].exit_ema)

    def test_signal_exit_requires_close_below_ema(self):
        closes = self.dip_and_recover()
        peak = closes[-1]
        # Sharp break: UT flips down on a bar that also closes under the 20-EMA
        closes += [peak + 2, peak + 3, peak - 15, peak - 16, peak - 17]
        candles = bars_from_closes(closes)
        res = run_swing_strategy("NSE:TEST", candles, params=SwingStrategyParams(use_stop=False))
        exits = [t for t in res.trades if t.exit_reason == EXIT_SIGNAL]
        self.assertEqual(len(exits), 1)
        sell_bar = next(b for b in res.series if b.sell)
        self.assertLess(sell_bar.close, sell_bar.exit_ema)
        self.assertLess(sell_bar.close, sell_bar.ut_stop)
        sell_idx = next(i for i, c in enumerate(candles) if c["date"] == sell_bar.date)
        self.assertEqual(exits[0].exit_date, candles[sell_idx + 1]["date"])
        self.assertAlmostEqual(exits[0].exit_price, candles[sell_idx + 1]["open"] - 0.05, places=2)

    def test_equity_reconciles_with_closed_trades(self):
        closes = self.dip_and_recover()
        closes += [closes[-1] + 2, closes[-1] - 40, closes[-1] - 41]
        res = run_swing_strategy("NSE:TEST", bars_from_closes(closes))
        self.assertFalse(res.stats.open_trade)
        self.assertAlmostEqual(
            res.stats.final_equity,
            res.stats.initial_capital + sum(t.pnl for t in res.trades),
            places=1,
        )

    def test_requires_warmup_history(self):
        with self.assertRaises(ValueError):
            run_swing_strategy("NSE:TEST", bars_from_closes(uptrend(n=200)))


class TestPartialBar(unittest.TestCase):

    def test_drop_incomplete_today(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        candles = [{"date": "2026-10-06T00:00:00+0530", "close": 1}, {"date": "2026-10-07T00:00:00+0530", "close": 2}]
        kept, dropped = drop_incomplete_today(candles, now=datetime(2026, 10, 7, 11, 0, tzinfo=ist))
        self.assertTrue(dropped)
        self.assertEqual(len(kept), 1)
        kept, dropped = drop_incomplete_today(candles, now=datetime(2026, 10, 7, 15, 45, tzinfo=ist))
        self.assertFalse(dropped)
        kept, dropped = drop_incomplete_today(candles, now=datetime(2026, 10, 8, 10, 0, tzinfo=ist))
        self.assertFalse(dropped)


if __name__ == "__main__":
    unittest.main()
