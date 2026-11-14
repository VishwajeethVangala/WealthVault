import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from apps.api.routers import analytics
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data import stock_search as ss


def make_candles(n=100, end_price=100.0):
    return [
        {
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": end_price,
            "high": end_price * 1.02,
            "low": end_price * 0.98,
            "close": end_price,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


class TestAnalyticsMultiBroker(unittest.TestCase):

    def test_momentum_loads_from_groww_when_kite_signed_out(self):
        """When Kite is logged out, Momentum loads price history from Groww (Priority 2)."""
        kite_client = SimpleNamespace(is_authenticated=False, owner_id="user_groww")
        groww_client = object()
        groww_candles = make_candles(100, 55.0)

        with patch.object(analytics, "_get_user_kite_client", AsyncMock(return_value=kite_client)), \
             patch.object(analytics, "get_user_groww_client", AsyncMock(return_value=groww_client)), \
             patch.object(analytics, "resolve_titles", AsyncMock(return_value={"NSE:MOREPENLAB-BE": ("Morepen Laboratories Ltd.", "Stocks")})), \
             patch.object(analytics, "fetch_groww_daily_candles", AsyncMock(return_value=groww_candles)), \
             patch.object(analytics, "get_user_indmoney_client", AsyncMock(return_value=None)):

            inst, candles, bench = asyncio.run(analytics._load_candles("user_groww", "MOREPENLAB-BE", 400, with_benchmark=True))

            self.assertEqual(inst["id"], "NSE:MOREPENLAB-BE")
            self.assertEqual(inst["name"], "Morepen Laboratories Ltd.")
            self.assertEqual(len(candles), 100)
            self.assertEqual(candles[-1]["close"], 55.0)

    def test_momentum_loads_from_indmoney_when_kite_and_groww_absent(self):
        """When Kite is logged out and Groww is absent, Momentum loads from INDmoney (Priority 3)."""
        kite_client = SimpleNamespace(is_authenticated=False, owner_id="user_ind")
        ind_candles = make_candles(80, 120.0)

        with patch.object(analytics, "_get_user_kite_client", AsyncMock(return_value=kite_client)), \
             patch.object(analytics, "get_user_groww_client", AsyncMock(return_value=None)), \
             patch.object(analytics, "get_user_indmoney_client", AsyncMock(return_value=object())), \
             patch.object(analytics, "fetch_daily_candles", AsyncMock(return_value=ind_candles)):

            inst, candles, bench = asyncio.run(analytics._load_candles("user_ind", "INFY", 400, with_benchmark=False))

            self.assertEqual(inst["id"], "NSE:INFY")
            self.assertEqual(len(candles), 80)
            self.assertEqual(candles[-1]["close"], 120.0)

    def test_momentum_raises_kite_auth_when_no_other_broker_connected(self):
        """When Kite session has lapsed and user has no other brokers, raises 409 KITE_AUTH_REQUIRED."""
        kite_client = SimpleNamespace(is_authenticated=True, owner_id="user_kite_only")
        history = SimpleNamespace(resolve_instrument=AsyncMock(side_effect=KiteAuthRequiredError("login required", auth_url="https://kite.trade/connect/login")))

        with patch.object(analytics, "_get_user_kite_client", AsyncMock(return_value=kite_client)), \
             patch.object(analytics, "get_history_service", return_value=history), \
             patch.object(analytics, "get_user_groww_client", AsyncMock(return_value=None)), \
             patch.object(analytics, "get_user_indmoney_client", AsyncMock(return_value=None)):

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(analytics._load_candles("user_kite_only", "RELIANCE", 400))

            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(ctx.exception.detail.get("code"), "KITE_AUTH_REQUIRED")

    def test_stock_search_falls_back_to_groww_then_indmoney(self):
        """Stock search tries Kite -> Groww -> INDmoney in priority order."""
        ss._cache.clear()
        kite_client = SimpleNamespace(is_authenticated=False)
        groww_client = SimpleNamespace(call_tool=AsyncMock(return_value={
            "result": {
                "matches": [
                    {"symbol": "MOREPENLAB", "title": "Morepen Laboratories Ltd.", "exchange": "NSE"}
                ]
            }
        }))

        with patch.object(ss, "get_user_groww_client", AsyncMock(return_value=groww_client)), \
             patch.object(ss, "get_user_indmoney_client", AsyncMock(return_value=None)):

            res = asyncio.run(ss.search_stocks(kite_client, "u_test", "more"))

            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["symbol"], "MOREPENLAB")
            self.assertEqual(res[0]["instrument"], "NSE:MOREPENLAB")
            self.assertEqual(res[0]["name"], "Morepen Laboratories Ltd.")


if __name__ == "__main__":
    unittest.main()
