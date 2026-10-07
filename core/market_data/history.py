"""Historical Price Data Service.

Resolves exchange-qualified symbols to Kite instrument tokens and fetches daily
candles via the Kite MCP `get_historical_data` tool, with a short in-memory TTL
cache so repeated momentum lookups do not re-query the broker.
"""

from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.market_data.kite_client import KiteMCPClient

logger = logging.getLogger("wealthvault.market_data.history")

# NSE:NIFTY 50 index token (stable Kite instrument token)
NIFTY_50_TOKEN = 256265
NIFTY_50_SYMBOL = "NSE:NIFTY 50"

# ~400 calendar days covers 252 trading days for 12M momentum plus 200-DMA slope history
DEFAULT_LOOKBACK_DAYS = 400
CANDLE_CACHE_TTL_SECONDS = 600.0

CASH_SEGMENTS = {"NSE", "BSE", "INDICES"}


class InstrumentNotFoundError(Exception):
    """Raised when a symbol cannot be resolved to a cash-segment instrument."""


def normalize_symbol(symbol: str) -> str:
    """Normalize user input into EXCHANGE:SYMBOL form, defaulting to NSE."""
    clean = symbol.strip().upper()
    if ":" in clean:
        exchange, _, ticker = clean.partition(":")
        return f"{exchange.strip()}:{ticker.strip()}"
    return f"NSE:{clean}"


def parse_candles(raw: Any) -> List[Dict[str, Any]]:
    """Parse Kite historical payloads into candles sorted oldest-first.

    Accepts a list of dicts ({date, open, high, low, close, volume}), a list of
    arrays ([date, open, high, low, close, volume]), or either wrapped in
    {"data": ...} / {"candles": ...}.
    """
    if isinstance(raw, dict):
        raw = raw.get("data", raw.get("candles", []))
        if isinstance(raw, dict):
            raw = raw.get("candles", [])
    if not isinstance(raw, list):
        return []

    candles: List[Dict[str, Any]] = []
    for row in raw:
        try:
            if isinstance(row, dict):
                lowered = {str(k).lower(): v for k, v in row.items()}
                candle = {
                    "date": str(lowered.get("date") or lowered.get("timestamp")),
                    "open": float(lowered.get("open") or 0.0),
                    "high": float(lowered.get("high") or 0.0),
                    "low": float(lowered.get("low") or 0.0),
                    "close": float(lowered.get("close") or 0.0),
                    "volume": float(lowered.get("volume") or 0.0),
                }
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                candle = {
                    "date": str(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                }
            else:
                continue
        except (TypeError, ValueError):
            continue
        if candle["close"] > 0 and candle["date"] not in ("", "None"):
            candles.append(candle)

    candles.sort(key=lambda c: c["date"])
    return candles


class HistoricalDataService:
    """Resolves instruments and serves cached daily candles from Kite MCP."""

    def __init__(self, cache_ttl_seconds: float = CANDLE_CACHE_TTL_SECONDS) -> None:
        self.cache_ttl = cache_ttl_seconds
        self._candle_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
        self._instrument_cache: Dict[str, Dict[str, Any]] = {}

    async def resolve_instrument(self, client: KiteMCPClient, symbol: str) -> Dict[str, Any]:
        """Resolve a symbol to its Kite instrument record (falls back from NSE to BSE)."""
        qualified = normalize_symbol(symbol)
        if qualified in self._instrument_cache:
            return self._instrument_cache[qualified]

        candidates = [qualified]
        if qualified.startswith("NSE:") and ":" not in symbol:
            candidates.append("BSE:" + qualified[4:])

        for candidate in candidates:
            results = await client.search_instruments(candidate)
            cash = [r for r in results if isinstance(r, dict) and r.get("segment") in CASH_SEGMENTS and r.get("instrument_token")]
            exact = next((r for r in cash if str(r.get("id", "")).upper() == candidate), None)
            match = exact or (cash[0] if cash else None)
            if match:
                self._instrument_cache[qualified] = match
                return match

        raise InstrumentNotFoundError(f"No NSE/BSE instrument found for '{symbol}'.")

    async def get_daily_candles(
        self,
        client: KiteMCPClient,
        instrument_token: int,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> List[Dict[str, Any]]:
        """Fetch daily candles for the lookback window, served from cache when fresh."""
        cached = self._candle_cache.get(instrument_token)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return cached[1]

        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        from_date = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d 00:00:00")
        to_date = now.strftime("%Y-%m-%d %H:%M:%S")
        raw = await client.get_historical_data(instrument_token, from_date, to_date, interval="day")
        candles = parse_candles(raw)
        if candles:
            self._candle_cache[instrument_token] = (time.monotonic(), candles)
        else:
            logger.warning("Kite returned no daily candles for token %s: %s", instrument_token, str(raw)[:200])
        return candles


_history_service: Optional[HistoricalDataService] = None


def get_history_service() -> HistoricalDataService:
    """Retrieve or initialize the application-wide historical data service."""
    global _history_service
    if _history_service is None:
        _history_service = HistoricalDataService()
    return _history_service
