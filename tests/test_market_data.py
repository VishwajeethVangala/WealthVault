import asyncio
import unittest
import time
from unittest.mock import AsyncMock, patch
from core.models import Holding, AssetClass, QuoteItem
from core.market_data.service import MarketQuoteCache, MCPMarketDataService


class TestMarketData(unittest.TestCase):

    def test_quote_cache_ttl(self):
        cache = MarketQuoteCache(default_ttl_seconds=0.5)
        self.assertIsNone(cache.get("NSE:INFY"))

        quote = QuoteItem(
            instrument="NSE:INFY",
            last_price=1850.50,
            day_change=25.5,
            day_change_percentage=1.39,
            close_price=1825.0,
        )
        cache.set("NSE:INFY", quote)
        self.assertIsNotNone(cache.get("NSE:INFY"))
        self.assertEqual(cache.get("NSE:INFY").last_price, 1850.50)

        # Wait for expiry
        time.sleep(0.6)
        self.assertIsNone(cache.get("NSE:INFY"))

    def test_symbol_formatting(self):
        self.assertEqual(MCPMarketDataService.format_instrument("INFY"), "NSE:INFY")
        self.assertEqual(MCPMarketDataService.format_instrument("NSE:TCS"), "NSE:TCS")
        self.assertEqual(MCPMarketDataService.format_instrument("BSE:500325"), "BSE:500325")
        self.assertEqual(MCPMarketDataService.format_instrument("TCS-EQ"), "NSE:TCS_EQ")

    def test_enrich_holdings_with_live_quotes(self):
        service = MCPMarketDataService()

        # Mock quotes
        mock_quotes = {
            "NSE:INFY": QuoteItem(
                instrument="NSE:INFY",
                last_price=1900.0,
                day_change=20.0,
                day_change_percentage=1.06,
                close_price=1880.0,
            )
        }

        service.fetch_live_quotes = AsyncMock(return_value=(mock_quotes, True))

        holding = Holding(
            holding_id="h1",
            owner_id="user1",
            connection_id="zerodha-conn-1",
            instrument_symbol="INFY",
            asset_class=AssetClass.EQUITY,
            quantity=10,
            average_price=1500.0,
            current_value=15000.0,
            currency="INR",
        )

        enriched, freshness = asyncio.run(service.enrich_holdings_with_live_quotes([holding]))
        self.assertEqual(freshness, "live")
        self.assertEqual(len(enriched), 1)
        h = enriched[0]

        self.assertEqual(h.current_price, 1900.0)
        self.assertEqual(h.current_value, 19000.0)  # 10 * 1900.0
        self.assertEqual(h.pnl, 4000.0)  # 19000.0 - (10 * 1500.0)
        self.assertEqual(h.day_pnl, 200.0)  # 10 * 20.0
        self.assertEqual(h.day_change_percentage, 1.06)
        self.assertEqual(h.data_freshness, "live")

    def test_enrich_holdings_fallback_on_mcp_error(self):
        service = MCPMarketDataService()
        service.fetch_live_quotes = AsyncMock(return_value=({}, False))

        holding = Holding(
            holding_id="h2",
            owner_id="user1",
            connection_id="zerodha-conn-1",
            instrument_symbol="TCS",
            asset_class=AssetClass.EQUITY,
            quantity=5,
            average_price=3500.0,
            current_value=17500.0,
            currency="INR",
        )

        # Must not raise, but return holding with data_freshness = "cached"
        enriched, freshness = asyncio.run(service.enrich_holdings_with_live_quotes([holding]))
        self.assertEqual(freshness, "cached")
        self.assertEqual(len(enriched), 1)
        h = enriched[0]
        self.assertEqual(h.current_value, 17500.0)
        self.assertEqual(h.data_freshness, "cached")


if __name__ == "__main__":
    unittest.main()
