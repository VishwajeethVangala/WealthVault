"""Portfolio Normalization Service.

Transforms heterogeneous broker-specific raw payloads discovered via MCP
(Zerodha Kite and INDmoney) into canonical Holding and Transaction models with
exact key mapping, asset classification, and owner_id attribution.
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, List, Optional, Union

from core.models import AssetClass, Holding, Transaction, TransactionType

logger = logging.getLogger("wealthvault.portfolio.normalization")


class NormalizationService:
    """Service normalizing raw broker responses into canonical financial models."""

    def normalize_holdings(
        self,
        raw_data: Union[List[Dict[str, Any]], Dict[str, Any]],
        broker_name: str,
        owner_id: str,
        connection_id: str,
    ) -> List[Holding]:
        """Normalize raw holdings from a specified broker into canonical Holding models.

        Uses exact JSON keys discovered via live schema introspection:
        - Zerodha: tradingsymbol, quantity, average_price, last_price, pnl
        - INDmoney: security_name, holding_units, average_buy_nav, current_nav, current_valuation, unrealized_gain_loss, asset_type

        Args:
            raw_data: Raw JSON payload from the broker provider.
            broker_name: Identifier of the broker ('zerodha', 'indmoney', etc.).
            owner_id: User identifier of the portfolio owner.
            connection_id: Identifier of the source broker connection.

        Returns:
            List of canonical Holding objects.
        """
        broker = broker_name.lower().strip()
        if broker == "zerodha":
            items = raw_data if isinstance(raw_data, list) else raw_data.get("holdings", [])
            return [
                self._normalize_zerodha_holding(item, owner_id, connection_id)
                for item in items
            ]
        elif broker == "indmoney":
            items: List[Dict[str, Any]] = []
            if isinstance(raw_data, dict):
                # Check for category dict: {"US_STOCK": {"holdings": [...]}, "BOND": {"holdings": [...]}, ...}
                for k, v in raw_data.items():
                    if isinstance(v, dict) and "holdings" in v and isinstance(v["holdings"], list):
                        items.extend(v["holdings"])
                if not items:
                    data_block = raw_data.get("data", raw_data)
                    if isinstance(data_block, dict):
                        items = data_block.get("holdings", [])
            elif isinstance(raw_data, list):
                items = raw_data

            return [
                self._normalize_indmoney_holding(item, owner_id, connection_id)
                for item in items
            ]
        else:
            items = raw_data if isinstance(raw_data, list) else []
            return [
                self._normalize_generic_holding(item, owner_id, connection_id)
                for item in items
            ]

    def _normalize_zerodha_holding(
        self,
        item: Dict[str, Any],
        owner_id: str,
        connection_id: str,
    ) -> Holding:
        # Check if Zerodha Coin Mutual Fund (has 'fund' key) or standard Kite Equity
        if "fund" in item:
            symbol = str(item.get("fund")).strip()
            quantity = float(item.get("quantity", 0.0))
            average_price = float(item.get("average_price", 0.0))
            last_price = float(item.get("last_price", average_price))
            current_value = round(quantity * last_price, 2)
            pnl = round((last_price - average_price) * quantity, 2)

            if "GOLD" in symbol.upper():
                asset_class = AssetClass.GOLD
            else:
                asset_class = AssetClass.MUTUAL_FUND

            isin = str(item.get("tradingsymbol") or symbol)
            holding_id = self._generate_id("hld_mf", owner_id, connection_id, isin)
        else:
            # Standard Zerodha Kite Equity schema
            symbol = str(item.get("tradingsymbol", "UNKNOWN")).upper()
            quantity = float(item.get("quantity", 0))
            average_price = float(item.get("average_price", 0.0))
            last_price = float(item.get("last_price", average_price))
            current_value = round(quantity * last_price, 2)
            pnl = float(item.get("pnl", round(current_value - (quantity * average_price), 2)))

            # Asset classification (Equities vs Gold / Sovereign Gold Bonds)
            if "GOLD" in symbol or symbol.startswith("SGB") or symbol.endswith("GOLDBEES"):
                asset_class = AssetClass.GOLD
            else:
                asset_class = AssetClass.EQUITY

            holding_id = self._generate_id("hld", owner_id, connection_id, symbol)

        return Holding(
            holding_id=holding_id,
            owner_id=owner_id,
            connection_id=connection_id,
            instrument_symbol=symbol,
            asset_class=asset_class,
            quantity=quantity,
            average_price=average_price,
            current_value=current_value,
            current_price=last_price,
            pnl=pnl,
            currency="INR",
        )

    # --- INDmoney Exact Key Normalizer ---

    def _normalize_indmoney_holding(
        self,
        item: Dict[str, Any],
        owner_id: str,
        connection_id: str,
    ) -> Holding:
        # Support live INDmoney schema: investment, investment_code, total_units, unit_price, market_value, total_pnl, invested_amount
        name = str(item.get("investment") or item.get("security_name") or item.get("scheme_name") or "Unknown Investment").strip()
        code = str(item.get("investment_code") or item.get("isin") or name).strip()
        symbol = f"{code} ({name})" if code and code != name and len(code) <= 12 else name

        quantity = float(item.get("total_units") or item.get("holding_units") or item.get("units") or 1.0)
        invested_amount = float(item.get("invested_amount") or 0.0)
        current_value = float(
            item.get("market_value") or item.get("current_valuation") or item.get("current_value") or invested_amount
        )
        current_price = float(
            item.get("unit_price") or item.get("current_nav") or (current_value / quantity if quantity > 0 else 0.0)
        )
        average_price = (
            invested_amount / quantity if quantity > 0 and invested_amount > 0 else float(item.get("average_buy_nav") or current_price)
        )
        pnl = float(item.get("total_pnl") or item.get("unrealized_gain_loss") or round(current_value - invested_amount, 2))

        # Asset classification
        raw_asset_type = str(item.get("asset_type", "")).upper()
        if "NPS" in raw_asset_type or "NPS" in name.upper() or "NPS" in code.upper():
            asset_class = AssetClass.NPS
            if symbol == "NPS":
                symbol = "NPS (National Pension Scheme)"
        elif "GOLD" in name.upper() or "GOLD" in raw_asset_type or "SGB" in code.upper():
            asset_class = AssetClass.GOLD
        elif raw_asset_type in ("MF", "MUTUAL_FUND") or "FUND" in name.upper():
            asset_class = AssetClass.MUTUAL_FUND
        else:
            asset_class = AssetClass.EQUITY

        broker = str(item.get("broker") or "").strip()
        family_member = str(item.get("family_member") or "").strip()
        unique_key = f"{code or name}_{broker}_{family_member}" if broker or family_member else (code or name)
        holding_id = self._generate_id("hld_ind", owner_id, connection_id, unique_key)

        return Holding(
            holding_id=holding_id,
            owner_id=owner_id,
            connection_id=connection_id,
            instrument_symbol=symbol,
            asset_class=asset_class,
            quantity=round(quantity, 4),
            average_price=round(average_price, 2),
            current_value=round(current_value, 2),
            current_price=round(current_price, 2),
            pnl=round(pnl, 2),
            currency="INR",
        )

    # --- Generic Normalizer Fallback ---

    def _normalize_generic_holding(
        self,
        item: Dict[str, Any],
        owner_id: str,
        connection_id: str,
    ) -> Holding:
        symbol = str(item.get("symbol") or item.get("instrument_symbol") or "GENERIC")
        quantity = float(item.get("quantity", 0.0))
        avg_price = float(item.get("average_price", 0.0))
        current_val = float(item.get("current_value", round(quantity * avg_price, 2)))
        holding_id = self._generate_id("hld", owner_id, connection_id, symbol)

        return Holding(
            holding_id=holding_id,
            owner_id=owner_id,
            connection_id=connection_id,
            instrument_symbol=symbol,
            asset_class=AssetClass.EQUITY,
            quantity=quantity,
            average_price=avg_price,
            current_value=current_val,
            currency="INR",
        )

    # --- Helper Utilities ---

    @staticmethod
    def _generate_id(prefix: str, *parts: str) -> str:
        """Deterministically generate clean identifiers."""
        combined = "_".join(parts)
        hash_digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{hash_digest}"
