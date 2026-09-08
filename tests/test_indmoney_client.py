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
        status = asyncio.run(provider.get_account_status())
        self.assertEqual(status["status"], "auth_required")
        self.assertIn("auth_url", status)
        self.assertIn("https://mcp.indmoney.com/authorize", status["auth_url"])

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

        # NPS should be included
        self.assertEqual(len(transformed["NPS"]["holdings"]), 1)
        self.assertEqual(transformed["NPS"]["holdings"][0]["investment"], "NPS Tier 1")

        # Mutual funds managed by Zerodha Coin should be deduplicated (excluded)
        self.assertEqual(len(transformed["MF"]["holdings"]), 0)

        # Indian stocks held in Zerodha should be deduplicated (excluded)
        self.assertEqual(len(transformed["IND_STOCK"]["holdings"]), 0)

        # Normalize holdings
        normalizer = NormalizationService()
        normalized = normalizer.normalize_holdings(
            transformed, "indmoney", "test_user", "conn_indmoney_live"
        )
        self.assertEqual(len(normalized), 2)
        classes = {h.asset_class for h in normalized}
        self.assertIn(AssetClass.US_STOCKS, classes)
        self.assertIn(AssetClass.NPS, classes)


if __name__ == "__main__":
    unittest.main()
