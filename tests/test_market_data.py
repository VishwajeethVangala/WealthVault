import asyncio
import unittest
import time
from datetime import datetime, timedelta, timezone
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
        self.assertEqual(MCPMarketDataService.format_instrument("HFCL-BE"), "NSE:HFCL-BE")

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

    def test_day_change_of_a_holding_bought_this_session_is_its_total_profit(self):
        """A stock bought on listing day: the exchange's previous close is the issue price, not what the holder paid."""
        service = MCPMarketDataService()
        mock_quotes = {"NSE:TONBO": QuoteItem(instrument="NSE:TONBO", last_price=1133.8, day_change=433.8, day_change_percentage=61.97, close_price=700.0)}
        service.fetch_live_quotes = AsyncMock(return_value=(mock_quotes, True))
        now = datetime.now(timezone.utc).isoformat()

        def holding(**kw):
            base = dict(holding_id="h1", owner_id="u", connection_id="c", instrument_symbol="TONBO", asset_class=AssetClass.EQUITY,
                        quantity=20, average_price=1113.55, current_value=22676.0, pnl=405.0, currency="INR", last_price_updated_at=now)
            base.update(kw)
            return Holding(**base)

        # the broker's own day change equals its total profit: bought today
        h = asyncio.run(service.enrich_holdings_with_live_quotes([holding(day_pnl=405.0, day_change_percentage=1.82)]))[0][0]
        self.assertEqual(h.day_pnl, 405.0)
        self.assertEqual(h.day_change_percentage, 1.82)

        # straight from a sync: no timestamp yet, which means it was read just now
        h = asyncio.run(service.enrich_holdings_with_live_quotes([holding(day_pnl=405.0, day_change_percentage=1.82, last_price_updated_at=None)]))[0][0]
        self.assertEqual(h.day_pnl, 405.0)

        # a different broker figure: held through the previous close, so the exchange's change applies
        h = asyncio.run(service.enrich_holdings_with_live_quotes([holding(day_pnl=8676.0, day_change_percentage=61.97)]))[0][0]
        self.assertEqual(h.day_pnl, 8676.0)

        # equal figures but read on an earlier day: that day change belongs to that day, so the quote is used
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        h = asyncio.run(service.enrich_holdings_with_live_quotes([holding(day_pnl=405.0, last_price_updated_at=old)]))[0][0]
        self.assertEqual(h.day_pnl, 8676.0)

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

    def test_enrich_mutual_fund_preserves_live_freshness(self):
        """Verify that live Coin mutual fund holdings are NOT falsely downgraded to cached."""
        service = MCPMarketDataService()
        service.fetch_live_quotes = AsyncMock(return_value=({}, True))

        mf_holding = Holding(
            holding_id="hld_mf_1",
            owner_id="user1",
            connection_id="conn_zerodha_live",
            instrument_symbol="SBI CONTRA FUND - DIRECT PLAN",
            asset_class=AssetClass.MUTUAL_FUND,
            quantity=77.688,
            average_price=424.75,
            current_price=414.74,
            current_value=32220.32,
            data_freshness="live",
            currency="INR",
        )

        enriched, freshness = asyncio.run(service.enrich_holdings_with_live_quotes([mf_holding]))
        self.assertEqual(freshness, "live")
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].data_freshness, "live")
        self.assertEqual(enriched[0].current_price, 414.74)

    def test_default_cache_ttl_is_120_seconds(self):
        """Verify 2-minute (120s) quote cache TTL for rate limiting."""
        cache = MarketQuoteCache()
        self.assertEqual(cache.default_ttl, 120.0)
        service = MCPMarketDataService()
        self.assertEqual(service.cache.default_ttl, 120.0)

    @patch("core.market_data.service.get_user_indmoney_client")
    @patch("core.market_data.service.get_user_groww_client")
    def test_priority_order_when_kite_lapsed_or_absent(self, mock_groww_cli, mock_ind_cli):
        """When Kite is absent or logged out: Priority 2 (Groww) is queried first, then Priority 3 (INDmoney)."""
        service = MCPMarketDataService(cache_ttl_seconds=120.0)

        # Kite is unauthenticated / absent
        kite_client = AsyncMock()
        kite_client.owner_id = "user_123"
        kite_client.is_authenticated = False

        # Mock Groww client that knows RELIANCE
        groww_client = AsyncMock()
        mock_groww_cli.return_value = groww_client

        # Mock INDmoney client that knows TCS
        ind_client = AsyncMock()
        mock_ind_cli.return_value = ind_client

        with patch("core.market_data.service.fetch_groww_quotes") as mock_groww_fetch, \
             patch("core.market_data.service.fetch_indmoney_quotes") as mock_ind_fetch:

            mock_groww_fetch.return_value = {
                "NSE:RELIANCE": QuoteItem(instrument="NSE:RELIANCE", last_price=2800.0, day_change=30.0, day_change_percentage=1.08, close_price=2770.0)
            }
            mock_ind_fetch.return_value = {
                "NSE:TCS": QuoteItem(instrument="NSE:TCS", last_price=4100.0, day_change=45.0, day_change_percentage=1.11, close_price=4055.0)
            }

            combined, live_succeeded = asyncio.run(service.fetch_live_quotes(
                ["NSE:RELIANCE", "NSE:TCS"],
                client=kite_client,
                owner_id="user_123"
            ))

            self.assertTrue(live_succeeded)
            self.assertEqual(len(combined), 2)
            self.assertEqual(combined["NSE:RELIANCE"].last_price, 2800.0)
            self.assertEqual(combined["NSE:TCS"].last_price, 4100.0)

            # Groww was asked first for both RELIANCE and TCS
            mock_groww_fetch.assert_called_once()
            groww_asked = mock_groww_fetch.call_args[0][1]
            self.assertIn("NSE:RELIANCE", groww_asked)
            self.assertIn("NSE:TCS", groww_asked)

            # INDmoney was asked second ONLY for TCS (since Groww resolved RELIANCE)
            mock_ind_fetch.assert_called_once()
            ind_asked = mock_ind_fetch.call_args[0][1]
            self.assertEqual(ind_asked, ["NSE:TCS"])

    @patch("core.market_data.service.get_user_groww_client")
    def test_kite_unauthenticated_skips_to_groww_directly(self, mock_groww_cli):
        """When Kite is unauthenticated (e.g. user has no Kite or logged out), Kite is skipped and Groww is queried directly."""
        service = MCPMarketDataService(cache_ttl_seconds=120.0)

        kite_client = AsyncMock()
        kite_client.owner_id = "user_groww_only"
        kite_client.is_authenticated = False
        kite_client.get_quotes = AsyncMock()

        groww_client = AsyncMock()
        mock_groww_cli.return_value = groww_client

        with patch("core.market_data.service.fetch_groww_quotes") as mock_groww_fetch:
            mock_groww_fetch.return_value = {
                "NSE:HDFCBANK": QuoteItem(instrument="NSE:HDFCBANK", last_price=1750.0, day_change=12.0, day_change_percentage=0.69, close_price=1738.0)
            }

            combined, live_succeeded = asyncio.run(service.fetch_live_quotes(
                ["NSE:HDFCBANK"],
                client=kite_client,
                owner_id="user_groww_only"
            ))

            self.assertTrue(live_succeeded)
            self.assertEqual(combined["NSE:HDFCBANK"].last_price, 1750.0)

            # Kite get_quotes was NEVER called
            kite_client.get_quotes.assert_not_called()
            # Groww was called directly
            mock_groww_fetch.assert_called_once()

    @patch("core.market_data.service.get_user_groww_client")
    def test_two_minute_cache_prevents_subsequent_broker_calls(self, mock_groww_cli):
        """Within the 120-second TTL window, subsequent requests are served from memory cache with 0 broker calls."""
        service = MCPMarketDataService(cache_ttl_seconds=120.0)

        kite_client = AsyncMock()
        kite_client.owner_id = "user_123"
        kite_client.is_authenticated = False

        groww_client = AsyncMock()
        mock_groww_cli.return_value = groww_client

        with patch("core.market_data.service.fetch_groww_quotes") as mock_groww_fetch:
            mock_groww_fetch.return_value = {
                "NSE:ITC": QuoteItem(instrument="NSE:ITC", last_price=470.0, day_change=3.0, day_change_percentage=0.64, close_price=467.0)
            }

            # Call 1: Fetches from Groww
            res1, _ = asyncio.run(service.fetch_live_quotes(["NSE:ITC"], client=kite_client, owner_id="user_123"))
            self.assertEqual(res1["NSE:ITC"].last_price, 470.0)
            self.assertEqual(mock_groww_fetch.call_count, 1)

            # Call 2: Within 120s TTL -> must be served from cache
            res2, _ = asyncio.run(service.fetch_live_quotes(["NSE:ITC"], client=kite_client, owner_id="user_123"))
            self.assertEqual(res2["NSE:ITC"].last_price, 470.0)
            # Call count should STILL be 1!
            self.assertEqual(mock_groww_fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
