import unittest
from datetime import date, timedelta

from core.analytics.supertrend_strategy import (
    compute_adx,
    compute_supertrend,
    run_supertrend_strategy,
)
from core.models import SupertrendParams

START = date(2020, 1, 1)


def generate_candles(closes, volumes=None):
    if volumes is None:
        volumes = [100000.0] * len(closes)
    return [
        {
            "date": (START + timedelta(days=i)).isoformat(),
            "open": c - 0.2,
            "high": c + 1.0,
            "low": c - 1.0,
            "close": c,
            "volume": v,
        }
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]


class TestSupertrendStrategy(unittest.TestCase):

    def test_compute_supertrend_basic(self):
        # 50 candles rising then falling
        closes = [100.0 + i for i in range(30)] + [130.0 - 2 * i for i in range(20)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        st, dirs = compute_supertrend(highs, lows, closes, period=10, factor=3.0)

        self.assertEqual(len(st), len(closes))
        self.assertEqual(len(dirs), len(closes))
        # During the strong rise, direction should be -1 (bullish)
        self.assertEqual(dirs[25], -1)
        # After the strong drop, direction should flip to 1 (bearish)
        self.assertEqual(dirs[-1], 1)

    def test_compute_adx_basic(self):
        closes = [100.0 + 2 * i for i in range(50)]
        highs = [c + 1.5 for c in closes]
        lows = [c - 1.5 for c in closes]
        adx = compute_adx(highs, lows, closes, 14, 14)
        self.assertEqual(len(adx), 50)
        # Strong trend should produce high ADX > 20
        valid_adx = [v for v in adx if v is not None]
        self.assertTrue(len(valid_adx) > 0)
        self.assertGreater(valid_adx[-1], 20.0)

    def test_run_strategy_execution(self):
        # Generate 100 days of trending data with a volume surge
        closes = [100.0 + (i * 0.5) for i in range(60)] + [130.0 - (i * 1.5) for i in range(40)]
        volumes = [50000.0] * 35 + [200000.0] * 5 + [80000.0] * 60
        candles = generate_candles(closes, volumes)

        params = SupertrendParams(
            start_date="2020-01-01",
            atr_period=10,
            factor=3.0,
            use_adx_filter=True,
            adx_threshold=15.0,
            use_vol_filter=True,
            max_bars_after_flip=5,
        )
        res = run_supertrend_strategy("NSE:TEST", candles, params)

        self.assertEqual(res.instrument, "NSE:TEST")
        self.assertIsNotNone(res.status)
        self.assertIsNotNone(res.stats)
        self.assertTrue(len(res.series) > 0)


if __name__ == "__main__":
    unittest.main()
