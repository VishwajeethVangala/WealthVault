"""INDmoney Broker Provider Implementation.

Connects to the INDmoney MCP server or loads live schema fixture data,
returning raw JSON mutual fund and wealth holding payloads.
"""

import asyncio
import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from core.market_data.indmoney_client import IndmoneyAuthRequiredError, get_indmoney_mcp_client
from providers.brokers.base import BrokerProvider

logger = logging.getLogger("wealthvault.providers.indmoney")

SCHEMA_FILE = Path("storage/blobs/schemas/indmoney_raw.json")


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, handling None, empty strings, and invalid values."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class IndmoneyProvider(BrokerProvider):
    """INDmoney wealth provider using direct HTTP MCP client with OAuth PKCE."""

    def __init__(
        self,
        credentials: Optional[Dict[str, Any]] = None,
        server_url: str = "https://mcp.indmoney.com/mcp",
        timeout_seconds: float = 45.0,
        connection_id: str = "conn_indmoney_live",
    ) -> None:
        super().__init__(credentials)
        self.server_url = server_url
        self.timeout = timeout_seconds
        self.connection_id = connection_id
        self.live_fetched = False

    @property
    def client(self) -> Any:
        return get_indmoney_mcp_client(connection_id=self.connection_id)

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Verify broker connection."""
        if credentials:
            self.credentials.update(credentials)
        status = await self.get_account_status()
        return status.get("status") == "success"

    async def get_account_status(self) -> Dict[str, Any]:
        """Fetch account and OAuth connection status."""
        client = self.client
        if client.is_authenticated():
            return {
                "status": "success",
                "profile": {
                    "broker": "INDMONEY",
                    "account_id": self.credentials.get("account_id", "IND_LIVE"),
                    "status": "active",
                },
            }

        auth_url = client.get_authorization_url()
        return {
            "status": "auth_required",
            "message": "INDmoney OAuth authorization required",
            "auth_url": auth_url,
        }

    async def get_holdings(self) -> Any:
        """Retrieve live family asset holdings directly from INDmoney MCP."""
        client = self.client
        try:
            raw_overall = await client.get_family_asset_holdings("overall")
            if not raw_overall:
                return {}
            transformed = self._transform_live_payload(raw_overall)
            self.live_fetched = True
            return transformed
        except IndmoneyAuthRequiredError:
            raise
        except Exception as exc:
            logger.error("INDmoney live holdings retrieval failed: %s", exc)
            raise RuntimeError(f"INDmoney live MCP communication failure: {exc}") from exc

    @staticmethod
    def _transform_live_payload(raw_overall: Dict[str, Any]) -> Dict[str, Any]:
        """Format live INDmoney overall family asset holdings into standard category dictionary."""
        transformed: Dict[str, Any] = {
            "US_STOCK": {"asset_summary": {}, "holdings": []},
            "MF": {"asset_summary": {}, "holdings": []},
            "BOND": {"asset_summary": {}, "holdings": []},
            "NPS": {"asset_summary": {}, "holdings": []},
            "IND_STOCK": {"asset_summary": {}, "holdings": []},
        }

        # Support both {"family_asset_holdings": [...]} and {"overall": {"family_asset_holdings": [...]}}
        if isinstance(raw_overall, list):
            members = raw_overall
        elif isinstance(raw_overall, dict):
            members = (
                raw_overall.get("family_asset_holdings")
                or (raw_overall.get("overall", {}).get("family_asset_holdings") if isinstance(raw_overall.get("overall"), dict) else None)
                or (raw_overall.get("data", {}).get("family_asset_holdings") if isinstance(raw_overall.get("data"), dict) else None)
                or []
            )
        else:
            members = []

        for member in members:
            if not isinstance(member, dict):
                continue
            m_name = member.get("name")
            m_asset = str(member.get("asset") or "").lower()

            for h in member.get("holdings") or []:
                if not isinstance(h, dict):
                    continue
                brokers = h.get("brokers") or []
                # Avoid duplicating mutual funds managed directly by Zerodha Coin
                if m_asset == "mutual_fund":
                    continue
                # Avoid duplicating Indian stocks managed by Zerodha (handled directly by Kite MCP)
                if m_asset == "indian_stock" and "Zerodha" in brokers:
                    continue
                # Filter out non-portfolio assets
                if m_asset in ("vehicle", "savings_account", "stock_wallet", "digital_assets", "epf", "ppf"):
                    continue

                inv_code = str(h.get("id") or h.get("investment_code") or "").strip()
                # Exclude Sovereign Gold Bonds managed directly by Zerodha Kite (IN0020230069)
                if m_asset == "bond" and ("IN0020230069" in inv_code or "SGB" in str(h.get("name") or "").upper()):
                    continue

                raw_units = h.get("quantity") if h.get("quantity") is not None else h.get("total_units")
                total_units = _safe_float(raw_units, 1.0)
                if total_units <= 0:
                    total_units = 1.0

                holding_item = {
                    "investment_code": h.get("id") or h.get("investment_code") or inv_code,
                    "investment": h.get("name") or h.get("investment") or inv_code or "Unknown Investment",
                    "asset_type": str(h.get("asset_class") or h.get("investment_type") or "").upper(),
                    "assetclass_l2": h.get("asset_class") or h.get("investment_type"),
                    "invested_amount": _safe_float(h.get("invested_amount"), 0.0),
                    "market_value": _safe_float(h.get("current_value"), 0.0),
                    "holding_percent": _safe_float(h.get("holding_percentage"), 0.0),
                    "total_pnl": _safe_float(h.get("absolute_change"), 0.0),
                    "pnl_per": _safe_float(h.get("absolute_change_percentage"), 0.0),
                    "total_units": total_units,
                    "unit_price": _safe_float(h.get("unit_price"), 0.0),
                    "broker": "INDmoney" if "INDmoney" in brokers else ("Alpaca" if "Alpaca" in brokers else (brokers[0] if brokers else "INDmoney")),
                    "market_cap": h.get("market_cap"),
                    "one_day_change": _safe_float(h.get("one_day_change"), 0.0),
                    "one_day_change_percentage": _safe_float(h.get("one_day_change_percentage"), 0.0),
                    "family_member": m_name,
                }

                if m_asset == "us_stock":
                    transformed["US_STOCK"]["holdings"].append(holding_item)
                elif m_asset == "nps":
                    holding_item["asset_type"] = "NPS"
                    transformed["NPS"]["holdings"].append(holding_item)
                elif m_asset == "bond":
                    # Deduplicate any remaining bonds by investment_code
                    existing_bonds = {b["investment_code"] for b in transformed["BOND"]["holdings"]}
                    if holding_item["investment_code"] not in existing_bonds:
                        transformed["BOND"]["holdings"].append(holding_item)
                elif m_asset == "indian_stock":
                    transformed["IND_STOCK"]["holdings"].append(holding_item)

        return transformed

    async def get_transactions(self) -> List[Dict[str, Any]]:
        """Fetch mutual fund transactions."""
        # INDmoney's MCP exposes no transaction history
        return []
