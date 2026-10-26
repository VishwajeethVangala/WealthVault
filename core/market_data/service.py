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
from zoneinfo import ZoneInfo

from mcp import ClientSession
from core.market_data.groww_market import fetch_groww_quotes, get_user_groww_client
from core.market_data.indmoney_market import fetch_quotes as fetch_indmoney_quotes, get_user_indmoney_client
from core.market_data.kite_client import KiteAuthRequiredError, get_kite_mcp_client
from core.market_data.symbol_resolver import resolve_indmoney_symbols, split_indmoney_symbol
from core.models import AssetClass, Holding, QuoteItem

logger = logging.getLogger("wealthvault.market_data.service")

INDMONEY_FALLBACK_SECONDS = 8.0
MIN_FALLBACK_SECONDS = 0.05

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
        cache_ttl_seconds: float = 15.0,
        request_timeout_seconds: float = 45.0,
    ) -> None:
        self.server_url = server_url
        self.cache = MarketQuoteCache(default_ttl_seconds=cache_ttl_seconds)
        self.timeout = request_timeout_seconds

    @staticmethod
    def _read_within(iso: Optional[str], seconds: float) -> bool:
        if not iso:
            return False
        try:
            when = datetime.fromisoformat(iso)
        except ValueError:
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - when).total_seconds() <= seconds

    @staticmethod
    def _bought_this_session(h: Holding) -> bool:
        """True when the broker itself measures this holding's day from the buy price.

        INDmoney reports a day change equal to the total profit for shares bought during the current session. The
        exchange's previous close then predates the purchase (for a stock bought on its listing day it can even be
        the issue price), so applying it would credit the holder with a move they never held through."""
        if h.day_pnl is None or h.average_price <= 0:
            return False
        # a holding straight from a sync has no timestamp yet: it was read just now
        if h.last_price_updated_at:
            try:
                when = datetime.fromisoformat(h.last_price_updated_at)
            except ValueError:
                return False
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            ist = ZoneInfo("Asia/Kolkata")
            if when.astimezone(ist).date() != datetime.now(ist).date():
                return False  # read on an earlier day: that day change belongs to that day
        invested = h.quantity * h.average_price
        return abs(h.day_pnl - (h.pnl or 0.0)) <= max(1.0, 0.0005 * abs(invested))

    @staticmethod
    def format_instrument(symbol: str, asset_class: Optional[Union[AssetClass, str]] = None) -> Optional[str]:
        """Normalize symbol into MCP exchange:symbol format (e.g. 'NSE:INFY')."""
        # Only Indian-listed instruments have Kite quotes. US stocks, NPS and funds keep the broker's own price,
        # and a US ticker like 'MU' or 'BE' must never be looked up as an NSE symbol.
        if asset_class is not None and str(getattr(asset_class, "value", asset_class)) in ("US_STOCKS", "NPS", "MUTUAL_FUND", "DEBT"):
            return None
        if split_indmoney_symbol(symbol):
            return None  # broker-specific code; resolved separately
        clean = symbol.strip().upper()
        if not clean or clean.startswith("MUTUAL_") or ("FUND" in clean and len(clean) > 30):
            return None

        # Already qualified (e.g. 'NSE:INFY', 'BSE:500209')
        if ":" in clean:
            return clean

        # Extract root ticker if there are extra descriptions
        root = clean.split()[0]  # keep series suffixes such as HFCL-BE as Kite lists them
        return f"NSE:{root}"

    async def fetch_live_quotes(
        self,
        instruments: List[str],
        client: Optional[Any] = None,
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
        client = client or get_kite_mcp_client()
        kite_login_lapsed = False

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

                    # Kite's own `net_change` reads 0 through the MCP even while the price is moving, so the day
                    # change is always last price minus the previous close; net_change is only a fallback.
                    net_change = data.get("net_change")
                    if close_price > 0:
                        day_change = round(last_price - close_price, 2)
                    elif net_change is not None:
                        day_change = float(net_change)
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
                kite_login_lapsed = isinstance(exc, KiteAuthRequiredError)
                break

        # Only when Kite's login has lapsed (it does daily): the user's other brokers price what is missing, INDmoney
        # first, then Groww, inside one shared time budget. A live Kite session is never second-guessed, and slow
        # brokers must not hold up the page.
        owner_id = getattr(client, "owner_id", None)
        if kite_login_lapsed and owner_id:
            deadline = time.monotonic() + INDMONEY_FALLBACK_SECONDS
            for name, get_client, fetch in (
                ("INDmoney", get_user_indmoney_client, fetch_indmoney_quotes),
                ("Groww", get_user_groww_client, fetch_groww_quotes),
            ):
                left = [i for i in missing if i not in combined]
                remaining = deadline - time.monotonic()
                if not left or remaining < MIN_FALLBACK_SECONDS:  # a sliver of budget cannot finish a broker call
                    break
                try:
                    other = await get_client(owner_id)
                    if other is None:
                        continue
                    found = await asyncio.wait_for(fetch(other, left), timeout=max(0.1, deadline - time.monotonic()))
                    for inst_key, item in found.items():
                        self.cache.set(inst_key, item)
                        combined[inst_key] = item
                        live_fetched = True
                except Exception as exc:
                    logger.warning("%s quote fallback unavailable: %s", name, exc)

        return combined, live_fetched

    async def enrich_holdings_with_live_quotes(
        self,
        holdings: List[Holding],
        client: Optional[Any] = None,
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

        # INDmoney Indian stocks carry INDmoney codes; resolve them to exchange symbols via the Kite instrument search
        indmoney_codes = [
            h.instrument_symbol
            for h in holdings
            if h.instrument_symbol not in symbol_to_instrument and h.asset_class == AssetClass.EQUITY
        ]
        if indmoney_codes and client is not None:
            symbol_to_instrument.update(await resolve_indmoney_symbols(indmoney_codes, client))

        instruments_to_query = list(set(symbol_to_instrument.values()))
        quotes_map, live_succeeded = await self.fetch_live_quotes(instruments_to_query, client=client)

        enriched: List[Holding] = []
        for h in holdings:
            inst = symbol_to_instrument.get(h.instrument_symbol)
            quote = quotes_map.get(inst) if inst else None

            if quote and quote.last_price > 0:
                new_price = quote.last_price
                new_val = round(h.quantity * new_price, 2)
                invested = round(h.quantity * h.average_price, 2)
                new_pnl = round(new_val - invested, 2)
                # A zero quote change (e.g. market closed, weekend) must not erase the broker's
                # own day change for the last session.
                if self._bought_this_session(h):
                    # day change = change since the purchase, which is the total profit
                    day_pnl = new_pnl
                    day_pct = round(new_pnl / invested * 100.0, 2) if invested > 0 else None
                elif (quote.day_change and quote.day_change != 0) or (quote.close_price or 0) > 0:
                    # A real previous close makes the quote authoritative, even when the change is exactly zero
                    day_pnl = round(h.quantity * quote.day_change, 2)
                    day_pct = quote.day_change_percentage
                elif h.day_pnl is not None:
                    day_pnl = h.day_pnl
                    day_pct = h.day_change_percentage
                else:
                    day_pnl = round(h.quantity * (quote.day_change or 0.0), 2) if quote.day_change is not None else None
                    day_pct = quote.day_change_percentage

                updated_dict = h.model_dump()
                updated_dict.update({
                    "current_price": new_price,
                    "current_value": new_val,
                    "pnl": new_pnl,
                    "day_pnl": day_pnl,
                    "day_change_percentage": day_pct,
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
                elif self._read_within(h.last_price_updated_at, 120):
                    # Priced by the broker itself moments ago (e.g. INDmoney's live read for US stocks / NPS)
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
