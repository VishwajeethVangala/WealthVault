import unittest
from datetime import date, timedelta

from core.analytics.momentum import (
    analyze_momentum,
    annualized_volatility,
    ema_series,
    last_cross,
    rate_of_change,
    rsi,
    sma_series,
)
from core.market_data.history import normalize_symbol, parse_candles


def make_candles(closes):
    start = date(2025, 1, 1)
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "close": c, "high": c * 1.01, "low": c * 0.99}
        for i, c in enumerate(closes)
    ]


class TestMomentumIndicators(unittest.TestCase):

    def test_sma_and_ema(self):
        values = [1, 2, 3, 4, 5]
        self.assertEqual(sma_series(values, 3), [None, None, 2.0, 3.0, 4.0])
        ema = ema_series(values, 3)
        self.assertIsNone(ema[1])
        self.assertAlmostEqual(ema[2], 2.0)
        self.assertAlmostEqual(ema[3], 3.0)
        self.assertEqual(sma_series(values, 10), [None] * 5)

    def test_rate_of_change(self):
        closes = [100.0] * 10 + [110.0]
        self.assertAlmostEqual(rate_of_change(closes, 10), 10.0)
        self.assertIsNone(rate_of_change(closes, 11))
        # 12-1 style: skip the most recent day
        self.assertAlmostEqual(rate_of_change(closes, 10, skip_recent=1), 0.0)

    def test_rsi_extremes(self):
        self.assertEqual(rsi([float(i) for i in range(1, 30)]), 100.0)
        self.assertLess(rsi([float(i) for i in range(30, 1, -1)]), 1.0)
        self.assertIsNone(rsi([1.0, 2.0]))

    def test_volatility_zero_for_constant_growth(self):
        closes = [100.0 * (1.01 ** i) for i in range(60)]
        self.assertAlmostEqual(annualized_volatility(closes, 50), 0.0, places=6)

    def test_last_cross(self):
        fast = [None, 1.0, 1.0, 3.0, 3.0]
        slow = [None, 2.0, 2.0, 2.0, 2.0]
        self.assertEqual(last_cross(fast, slow), {"state": "golden", "days_since": 1})
        self.assertEqual(last_cross([3.0, 3.0], [2.0, 2.0]), {"state": "golden", "days_since": None})


class TestAnalyzeMomentum(unittest.TestCase):

    def test_steady_uptrend_scores_full_marks(self):
        closes = [100.0 * (1.002 ** i) + (1.5 if i % 2 else 0.0) for i in range(300)]
        report = analyze_momentum("NSE:TEST", make_candles(closes))
        self.assertEqual(report.trend_max_score, 5)
        self.assertGreaterEqual(report.trend_score, 4)
        self.assertIn(report.trend_verdict, ("Strong Uptrend", "Uptrend"))
        self.assertEqual(report.cross_state, "golden")
        self.assertGreater(report.returns["12M"], 0)
        self.assertGreater(report.risk_adjusted_12m, 0)
        self.assertEqual(len(report.series), 252)

    def test_steady_downtrend(self):
        closes = [500.0 * (0.998 ** i) + (1.5 if i % 2 else 0.0) for i in range(300)]
        report = analyze_momentum("NSE:TEST", make_candles(closes))
        self.assertLessEqual(report.trend_score, 1)
        self.assertIn(report.trend_verdict, ("Strong Downtrend", "Downtrend"))
        self.assertEqual(report.cross_state, "death")
        self.assertLess(report.returns["6M"], 0)

    def test_short_history_skips_unavailable_checks(self):
        closes = [100.0 + i for i in range(60)]
        report = analyze_momentum("NSE:TEST", make_candles(closes))
        keys = {c.key for c in report.trend_checks}
        self.assertIn("above_50dma", keys)
        self.assertNotIn("above_200dma", keys)
        self.assertIsNone(report.sma_200)
        self.assertIsNone(report.returns["12M"])

    def test_relative_strength_vs_benchmark(self):
        stock = [100.0 * (1.003 ** i) for i in range(300)]
        bench = [100.0 * (1.001 ** i) for i in range(300)]
        report = analyze_momentum("NSE:TEST", make_candles(stock), benchmark_candles=make_candles(bench))
        self.assertGreater(report.relative_strength["12M"], 0)
        self.assertGreater(report.relative_strength["1M"], 0)

    def test_requires_history(self):
        with self.assertRaises(ValueError):
            analyze_momentum("NSE:TEST", make_candles([100.0]))


class TestHistoryHelpers(unittest.TestCase):

    def test_normalize_symbol(self):
        self.assertEqual(normalize_symbol(" infy "), "NSE:INFY")
        self.assertEqual(normalize_symbol("bse:500209"), "BSE:500209")

    def test_parse_candles_formats(self):
        dict_rows = [
            {"date": "2025-01-02T00:00:00+05:30", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"date": "2025-01-01T00:00:00+05:30", "open": 1, "high": 2, "low": 0.5, "close": 1.2, "volume": 10},
        ]
        parsed = parse_candles(dict_rows)
        self.assertEqual([c["close"] for c in parsed], [1.2, 1.5])

        array_rows = {"data": {"candles": [["2025-01-01T00:00:00+0530", 1, 2, 0.5, 1.1, 100]]}}
        self.assertEqual(parse_candles(array_rows)[0]["close"], 1.1)
        self.assertEqual(parse_candles("Please log in first"), [])


if __name__ == "__main__":
    unittest.main()
