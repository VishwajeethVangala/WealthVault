"""Real-Time Market Data Provider Service via MCP.

Provides:
- In-memory thread-safe TTL cache for real-time instrument quotes.
- Batching queries to Kite MCP ('get_ltp' and 'get_quotes').
- Dynamic holding enrichment: updating market prices, current valuations,
  unrealized P&L, and 1-day change metrics.
- Fallback mechanisms for offline sessions, API quotas, and non-quoted assets.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from mcp import ClientSession
from core.market_data.kite_client import get_kite_mcp_client
from core.models import AssetClass, Holding, QuoteItem

logger = logging.getLogger("wealthvault.market_data.service")

NPX_BIN = shutil.which("npx") or shutil.which("npx.cmd") or "npx"


class MarketQuoteCache:
    """Thread-safe in-memory cache with Time-To-Live (TTL) expiration."""

    def __init__(self, default_ttl_seconds: float = 30.0) -> None:
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, Tuple[QuoteItem, float]] = {}

    def get(self, instrument: str) -> Optional[QuoteItem]:
        """Retrieve cached quote if not expired."""
        entry = self._cache.get(instrument.upper())
        if not entry:
            return None
        quote, expires_at = entry
        if time.time() >= expires_at:
            del self._cache[instrument.upper()]
            return None
        return quote

    def set(self, instrument: str, quote: QuoteItem, ttl_seconds: Optional[float] = None) -> None:
        """Store quote with expiration."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._cache[instrument.upper()] = (quote, time.time() + ttl)

    def get_multi(self, instruments: List[str]) -> Tuple[Dict[str, QuoteItem], List[str]]:
        """Batch retrieve cached quotes, returning hits and missing instruments."""
        hits: Dict[str, QuoteItem] = {}
        missing: List[str] = []
        now = time.time()

        for inst in instruments:
            norm = inst.upper()
            entry = self._cache.get(norm)
            if entry and now < entry[1]:
                hits[norm] = entry[0]
            else:
                missing.append(norm)

        return hits, missing

    def clear(self) -> None:
        """Purge all cached entries."""
        self._cache.clear()


class MCPMarketDataService:
    """Service providing live market quotes directly from Market Data Providers (MCPs)."""

    def __init__(
        self,
        server_url: str = "https://mcp.kite.trade/mcp",
        cache_ttl_seconds: float = 30.0,
        request_timeout_seconds: float = 45.0,
    ) -> None:
        self.server_url = server_url
        self.cache = MarketQuoteCache(default_ttl_seconds=cache_ttl_seconds)
        self.timeout = request_timeout_seconds

    @staticmethod
    def format_instrument(symbol: str, asset_class: Optional[Union[AssetClass, str]] = None) -> Optional[str]:
        """Normalize symbol into MCP exchange:symbol format (e.g. 'NSE:INFY')."""
        clean = symbol.strip().upper()
        if not clean or clean.startswith("MUTUAL_") or ("FUND" in clean and len(clean) > 30):
            return None

        # Already qualified (e.g. 'NSE:INFY', 'BSE:500209')
        if ":" in clean:
            return clean

        # Extract root ticker if there are extra descriptions
        root = clean.split()[0].replace("-", "_")
        return f"NSE:{root}"

    async def fetch_live_quotes(
        self,
        instruments: List[str],
    ) -> Tuple[Dict[str, QuoteItem], bool]:
        """Fetch quotes for instruments, utilizing TTL cache and batching to Kite MCP.

        Returns:
            Tuple of (Map of instrument to QuoteItem, boolean indicating if live fetch succeeded).
        """
        if not instruments:
            return {}, True

        # Check in-memory cache first
        cached_quotes, missing = self.cache.get_multi(instruments)
        if not missing:
            logger.debug("Served %d market quotes entirely from TTL cache", len(cached_quotes))
            return cached_quotes, True

        combined: Dict[str, QuoteItem] = dict(cached_quotes)
        live_fetched = False

        # Batch query Kite MCP for missing instruments via persistent client (max 250 per batch)
        batch_size = 250
        batches = [missing[i : i + batch_size] for i in range(0, len(missing), batch_size)]
        client = get_kite_mcp_client()

        for batch in batches:
            try:
                payload = await client.get_quotes(batch)
                now_iso = datetime.now(timezone.utc).isoformat()
                for inst_key, data in payload.items():
                    if not isinstance(data, dict):
                        continue

                    last_price = float(data.get("last_price", 0.0) or 0.0)
                    ohlc = data.get("ohlc", {})
                    close_price = float(ohlc.get("close", 0.0) or 0.0)
                    open_price = float(ohlc.get("open", 0.0) or 0.0)
                    high_price = float(ohlc.get("high", 0.0) or 0.0)
                    low_price = float(ohlc.get("low", 0.0) or 0.0)

                    net_change = data.get("net_change")
                    if net_change is not None:
                        day_change = float(net_change)
                    elif close_price > 0:
                        day_change = round(last_price - close_price, 2)
                    else:
                        day_change = 0.0

                    day_pct = (
                        round((day_change / close_price) * 100.0, 2)
                        if close_price > 0
                        else 0.0
                    )

                    item = QuoteItem(
                        instrument=inst_key.upper(),
                        last_price=last_price,
                        day_change=day_change,
                        day_change_percentage=day_pct,
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        close_price=close_price,
                        timestamp=now_iso,
                    )
                    self.cache.set(inst_key.upper(), item)
                    combined[inst_key.upper()] = item

                if payload:
                    live_fetched = True
            except Exception as exc:
                logger.warning("Live MCP market quotes query note (%s): %s", self.server_url, exc)
                break

        return combined, live_fetched

    async def enrich_holdings_with_live_quotes(
        self,
        holdings: List[Holding],
    ) -> Tuple[List[Holding], str]:
        """Enrich a list of holdings with live market prices, updating current value and P&L.

        Returns:
            Tuple of (Enriched Holdings, data_freshness string 'live' or 'cached').
        """
        if not holdings:
            return [], "live"

        # Map each holding to an MCP instrument query
        symbol_to_instrument: Dict[str, str] = {}
        for h in holdings:
            inst = self.format_instrument(h.instrument_symbol, h.asset_class)
            if inst:
                symbol_to_instrument[h.instrument_symbol] = inst

        instruments_to_query = list(set(symbol_to_instrument.values()))
        quotes_map, live_succeeded = await self.fetch_live_quotes(instruments_to_query)

        enriched: List[Holding] = []
        for h in holdings:
            inst = symbol_to_instrument.get(h.instrument_symbol)
            quote = quotes_map.get(inst) if inst else None

            if quote and quote.last_price > 0:
                new_price = quote.last_price
                new_val = round(h.quantity * new_price, 2)
                invested = round(h.quantity * h.average_price, 2)
                new_pnl = round(new_val - invested, 2)
                day_pnl = round(h.quantity * (quote.day_change or 0.0), 2) if quote.day_change is not None else None

                updated_dict = h.model_dump()
                updated_dict.update({
                    "current_price": new_price,
                    "current_value": new_val,
                    "pnl": new_pnl,
                    "day_pnl": day_pnl,
                    "day_change_percentage": quote.day_change_percentage,
                    "data_freshness": "live",
                    "last_price_updated_at": quote.timestamp,
                })
                enriched.append(Holding(**updated_dict))
            else:
                # Retain existing prices from live broker sync.
                # Mutual funds from Coin do not have intraday exchange ticks; their live price is the official NAV
                # from Zerodha Coin, so their 'live' freshness is preserved.
                # Equities that failed to fetch live exchange quotes fall back to 'cached'.
                updated_dict = h.model_dump()
                if h.asset_class == AssetClass.MUTUAL_FUND and h.data_freshness == "live":
                    updated_dict["data_freshness"] = "live"
                else:
                    updated_dict["data_freshness"] = "cached"
                enriched.append(Holding(**updated_dict))

        # Overall freshness is 'live' if exchange quotes succeeded or if the portfolio is all live mutual funds
        has_live_holdings = any(h.data_freshness == "live" for h in enriched)
        if instruments_to_query:
            overall_freshness = "live" if (live_succeeded and has_live_holdings) else "cached"
        else:
            overall_freshness = "live" if has_live_holdings else "cached"

        return enriched, overall_freshness


# Global singleton instance for app-wide use
_market_data_service: Optional[MCPMarketDataService] = None


def get_market_data_service() -> MCPMarketDataService:
    """Retrieve or initialize application-wide market data service."""
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MCPMarketDataService()
    return _market_data_service
