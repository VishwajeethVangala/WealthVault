import asyncio
import unittest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from core.market_data.indmoney_client import IndmoneyMCPClient, IndmoneyAuthRequiredError
from providers.brokers.indmoney import IndmoneyProvider
from core.portfolio.normalization import NormalizationService
from core.models import AssetClass


class TestIndmoneyClient(unittest.TestCase):

    def setUp(self):
        self.client = IndmoneyMCPClient()

    def test_pkce_authorization_url(self):
        auth_url = self.client.get_authorization_url()
        self.assertIn("https://mcp.indmoney.com/authorize", auth_url)
        self.assertIn("response_type=code", auth_url)
        self.assertIn("code_challenge_method=S256", auth_url)
        self.assertIn("code_challenge=", auth_url)
        self.assertIn("client_id=", auth_url)
        self.assertIn("state=", auth_url)
        self.assertIsNotNone(self.client._pending_verifier)

    def test_unauthenticated_status(self):
        self.client.access_token = None
        self.client.refresh_token = None
        self.client.expires_at = 0.0
        self.assertFalse(self.client.is_authenticated())

        provider = IndmoneyProvider()
        # the provider uses the shared per-connection client, which may hold real tokens on a dev machine
        with patch.object(IndmoneyMCPClient, "is_authenticated", return_value=False):
            status = asyncio.run(provider.get_account_status())
        self.assertEqual(status["status"], "auth_required")
        self.assertIn("auth_url", status)
        self.assertIn("https://mcp.indmoney.com/authorize", status["auth_url"])

    def test_capped_member_lists_are_completed(self):
        """INDmoney lists only a member's top 25 holdings in the whole-family view; the rest is fetched per member."""
        def stocks(n):
            return [{"id": f"S{i}", "name": f"Stock {i}"} for i in range(n)]

        overall = {"family_asset_holdings": [
            {"name": "A", "asset": "indian_stock", "holdings": stocks(25), "holdings_omitted": 13},
            {"name": "A", "asset": "us_stock", "holdings": stocks(3)},
            {"name": "B", "asset": "indian_stock", "holdings": stocks(25), "holdings_omitted": 7},
        ]}
        calls = []

        async def fake_call(name, arguments=None):
            calls.append(dict(arguments or {}))
            if arguments.get("family_member") is None:
                return overall
            n = {"A": 38, "B": 32}[arguments["family_member"]]
            return {"family_asset_holdings": [{"name": arguments["family_member"], "asset": arguments["asset"], "holdings": stocks(n)}]}

        with patch.object(self.client, "call_tool", side_effect=fake_call):
            data = asyncio.run(self.client.get_family_asset_holdings("overall"))
        sizes = [(m["name"], m["asset"], len(m["holdings"])) for m in data["family_asset_holdings"]]
        self.assertEqual(sizes, [("A", "indian_stock", 38), ("A", "us_stock", 3), ("B", "indian_stock", 32)])
        # one whole-family call, then one per capped list; the uncapped US list is not asked for again
        self.assertEqual(len(calls), 3)

    def test_capped_list_kept_when_the_full_read_fails(self):
        overall = {"family_asset_holdings": [{"name": "A", "asset": "indian_stock", "holdings": [{"id": "S1"}], "holdings_omitted": 5}]}

        async def fake_call(name, arguments=None):
            if arguments.get("family_member") is None:
                return overall
            raise RuntimeError("boom")

        with patch.object(self.client, "call_tool", side_effect=fake_call):
            data = asyncio.run(self.client.get_family_asset_holdings("overall"))
        self.assertEqual(len(data["family_asset_holdings"][0]["holdings"]), 1)

    def test_transform_live_payload_deduplication(self):
        raw_payload = {
            "overall": {
                "asset": "overall",
                "family_asset_holdings": [
                    {
                        "name": "Vangala Vishwajeeth",
                        "asset": "us_stock",
                        "holdings": [
                            {
                                "name": "Amazon.com Inc.",
                                "investment_code": "AMZN",
                                "current_value": 24000.0,
                                "invested_amount": 23000.0,
                                "quantity": 1.5,
                                "unit_price": 16000.0,
                                "brokers": ["Alpaca"],
                                "asset_class": "us_stock",
                            }
                        ],
                    },
                    {
                        "name": "Vangala Vishwajeeth",
                        "asset": "nps",
                        "holdings": [
                            {
                                "name": "NPS Tier 1",
                                "investment_code": "NPS123",
                                "current_value": 250000.0,
                                "invested_amount": 200000.0,
                                "brokers": ["INDmoney"],
                                "asset_class": "nps",
                            }
                        ],
                    },
                    {
                        "name": "Nagishetti Mounika",
                        "asset": "mutual_fund",
                        "holdings": [
                            {
                                "name": "Parag Parikh Flexi Cap",
                                "investment_code": "INF879O01015",
                                "current_value": 700000.0,
                                "brokers": ["Zerodha"],
                            }
                        ],
                    },
                    {
                        "name": "Nagishetti Mounika",
                        "asset": "indian_stock",
                        "holdings": [
                            {
                                "name": "ABB India Ltd",
                                "investment_code": "INE117A01022",
                                "current_value": 50000.0,
                                "brokers": ["Zerodha"],
                            }
                        ],
                    },
                ],
            }
        }

        transformed = IndmoneyProvider._transform_live_payload(raw_payload)

        # US Stock should be included
        self.assertEqual(len(transformed["US_STOCK"]["holdings"]), 1)
        self.assertEqual(transformed["US_STOCK"]["holdings"][0]["investment_code"], "AMZN")

        # NPS is not tracked
        self.assertEqual(len(transformed["NPS"]["holdings"]), 0)

        # Mutual funds managed by Zerodha Coin should be deduplicated (excluded)
        self.assertEqual(len(transformed["MF"]["holdings"]), 0)

        # Indian stocks held in Zerodha should be deduplicated (excluded)
        self.assertEqual(len(transformed["IND_STOCK"]["holdings"]), 0)

        # Normalize holdings
        normalizer = NormalizationService()
        normalized = normalizer.normalize_holdings(
            transformed, "indmoney", "test_user", "conn_indmoney_live"
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual({h.asset_class for h in normalized}, {AssetClass.US_STOCKS})

    def test_indian_stocks_held_at_groww_are_not_listed_again_under_indmoney(self):
        def stock(name, brokers):
            return {"name": name, "investment_code": name, "current_value": 1000.0, "brokers": brokers}

        raw = {"overall": {"family_asset_holdings": [{"name": "A", "asset": "indian_stock", "holdings": [
            stock("MONEYVIEW", ["Groww"]), stock("ABB", ["zerodha"]), stock("NOBROKER", []), stock("TCS", ["INDmoney"])]},
            {"name": "A", "asset": "us_stock", "holdings": [stock("AMZN", ["Alpaca"]), stock("AAPL", ["Groww"]), stock("MSFT", [])]}]}}
        out = IndmoneyProvider._transform_live_payload(raw)
        self.assertEqual([h["investment_code"] for h in out["IND_STOCK"]["holdings"]], ["TCS"])
        self.assertEqual([h["investment_code"] for h in out["US_STOCK"]["holdings"]], ["AMZN", "AAPL", "MSFT"])  # no broker filter


class SnapshotWithoutNpsTests(unittest.TestCase):
    def test_nps_is_taken_out_of_snapshots_stored_while_it_was_tracked(self):
        import json
        from storage.tables.repositories import SnapshotsRepository

        alloc = {"EQUITY": {"absolute_value": 800.0, "percentage_weight": 80.0}, "NPS": {"absolute_value": 200.0, "percentage_weight": 20.0}}
        row = {"snapshot_id": "snapshot_2026-10-01", "owner_id": "u", "as_of_date": "2026-10-01", "total_current_value": 1000.0,
               "total_invested_value": 800.0, "total_unrealized_pnl": 200.0, "total_pnl_percentage": 25.0,
               "asset_allocation_json": json.dumps(alloc), "holdings_count": 3}
        snap = SnapshotsRepository.__new__(SnapshotsRepository)._parse_snapshot(row)
        self.assertEqual(snap.total_current_value, 800.0)
        self.assertEqual(snap.total_invested_value, 640.0)  # NPS removed at the day's own invested/value ratio (0.8)
        self.assertEqual(snap.total_unrealized_pnl, 160.0)
        self.assertEqual(list(snap.asset_allocation), ["EQUITY"])
        self.assertEqual(snap.asset_allocation["EQUITY"]["percentage_weight"], 100.0)


if __name__ == "__main__":
    unittest.main()
