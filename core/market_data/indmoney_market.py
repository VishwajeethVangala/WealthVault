"""Prices and recent daily candles from INDmoney, for when a user's Kite login is not active.

Kite's login lapses every morning, and INDmoney's MCP can answer the same two questions without it:
`get_indian_stocks_details` gives the live price with the previous close, and `get_indian_stocks_ohlc` gives daily
candles (at most a year). Both want INDmoney's own key for a stock, found with `lookup_ind_keys`, which returns a
loose list of candidates; a key is only accepted after its details show the exact exchange symbol asked for, and
the answer is remembered (in the shared symbol table, so a restart does not repeat the lookups).

This is a stand-in for the top-up of history and for live quotes, never a source of full history: a year of candles
must not be stored as if it were everything.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.market_data.indmoney_client import IndmoneyMCPClient, get_indmoney_mcp_client
from core.models import QuoteItem
from storage.tables.repositories import BrokerConnectionRepository, SymbolMapRepository

logger = logging.getLogger("wealthvault.market_data.indmoney_market")

KEY_PREFIX = "KEY:"  # symbol table rows for these are keyed "KEY:NSE:RELIANCE"; INDmoney's own codes never start so
DETAILS_BATCH = 10  # the tool's limit per call
CONCURRENCY = 4
MISS_SECONDS = 3600.0  # a stock INDmoney cannot match is not searched again for an hour
MAX_CANDIDATES = 5

_keys: Dict[str, str] = {}
_misses: Dict[str, float] = {}
_loaded = False
_sem: Optional[asyncio.Semaphore] = None


def _gate() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(CONCURRENCY)
    return _sem


async def get_user_indmoney_client(owner_id: Optional[str]) -> Optional[IndmoneyMCPClient]:
    """The user's INDmoney client when one is connected and holds a usable login, else None."""
    if not owner_id:
        return None
    try:
        connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    except Exception as exc:
        logger.warning("Could not list connections of %s: %s", owner_id, exc)
        return None
    for c in connections:
        if c.broker_name.lower().strip() != "indmoney":
            continue
        client = get_indmoney_mcp_client(c.connection_id, owner_id=owner_id)
        if client.is_authenticated():
            return client
    return None


SERIES_SUFFIX = re.compile(r"-(BE|BZ|SM|ST|SO|T0|IL|X1)$")


def _symbol_of(instrument: str) -> str:
    """The plain exchange symbol. Kite lists stocks on a special trading series as 'HFCL-BE'; INDmoney knows the
    company by 'HFCL' only, and the price it gives is for the same company (the series tags how it trades)."""
    return SERIES_SUFFIX.sub("", instrument.split(":", 1)[-1].strip().upper())


async def _load_keys() -> None:
    global _loaded
    if _loaded:
        return
    try:
        for code, row in (await SymbolMapRepository().get_all()).items():
            if code.startswith(KEY_PREFIX) and row.get("kite_id"):
                _keys[code[len(KEY_PREFIX):]] = row["kite_id"]
    except Exception as exc:
        logger.warning("Saved INDmoney keys unavailable: %s", exc)
    _loaded = True


def _stat_rows(details: Any) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in details.items() if isinstance(v, dict)} if isinstance(details, dict) else {}


async def details_for(client: IndmoneyMCPClient, keys: List[str]) -> Dict[str, Dict[str, Any]]:
    return await _details(client, keys)


async def _details(client: IndmoneyMCPClient, keys: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(keys), DETAILS_BATCH):
        async with _gate():
            out.update(_stat_rows(await client.call_tool("get_indian_stocks_details", {"ind_keys": keys[i : i + DETAILS_BATCH]})))
    return out


def _is_match(symbol: str, row: Dict[str, Any]) -> bool:
    basic = row.get("entity_basic") or {}
    names = {str(basic.get(f) or "").strip().upper() for f in ("symbol", "name", "short_name", "display_name")}
    return symbol in names and str(basic.get("exchange") or "NSE").upper() == "NSE"


async def _find_key(client: IndmoneyMCPClient, instrument: str) -> Optional[str]:
    """INDmoney's key for 'NSE:SYMBOL': the first candidate whose own details show that exact symbol."""
    symbol = _symbol_of(instrument)
    async with _gate():
        found = await client.call_tool("lookup_ind_keys", {"names": [symbol], "filter_type": "IN_STOCKS"})
    candidates = [r["ind_key"] for r in found if isinstance(r, dict) and r.get("ind_key")] if isinstance(found, list) else []
    candidates = candidates[:MAX_CANDIDATES]
    if not candidates:
        return None
    rows = await _details(client, candidates)
    for key in candidates:  # lookup order is its ranking
        if key in rows and _is_match(symbol, rows[key]):
            return key
    return None


async def resolve_keys(client: IndmoneyMCPClient, instruments: List[str]) -> Dict[str, str]:
    """'NSE:SYMBOL' -> INDmoney key, for the ones INDmoney can match. NSE only: BSE-only stocks are left out."""
    await _load_keys()
    want = sorted({i.upper() for i in instruments if i.upper().startswith("NSE:")})
    out = {i: _keys[i] for i in want if i in _keys}
    now = time.monotonic()
    todo = [i for i in want if i not in out and now - _misses.get(i, -MISS_SECONDS) >= MISS_SECONDS]

    async def one(inst: str) -> None:
        try:
            key = await _find_key(client, inst)
        except Exception as exc:
            logger.warning("INDmoney key lookup failed for %s: %s", inst, exc)
            return  # not a miss: the next try may work
        if not key:
            _misses[inst] = time.monotonic()
            return
        _keys[inst] = key
        out[inst] = key
        try:
            await SymbolMapRepository().save(KEY_PREFIX + inst, key, inst)
        except Exception as exc:
            logger.warning("Could not save INDmoney key for %s: %s", inst, exc)

    await asyncio.gather(*(one(i) for i in todo))
    return out


def _number(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def fetch_quotes(client: IndmoneyMCPClient, instruments: List[str]) -> Dict[str, QuoteItem]:
    """Live quotes (same shape as Kite's) for the instruments INDmoney can match."""
    keys = await resolve_keys(client, instruments)
    if not keys:
        return {}
    rows = await _details(client, sorted(set(keys.values())))
    now_iso = datetime.now(timezone.utc).isoformat()
    out: Dict[str, QuoteItem] = {}
    for inst, key in keys.items():
        stats = (rows.get(key) or {}).get("entity_stats") or {}
        price = _number(stats.get("live_price"))
        if price <= 0:
            continue
        prev = _number(stats.get("prev_close"))
        change = round(price - prev, 2) if prev > 0 else _number(stats.get("day_change"))
        out[inst] = QuoteItem(
            instrument=inst,
            last_price=price,
            day_change=change,
            day_change_percentage=round(change / prev * 100.0, 2) if prev > 0 else _number(stats.get("day_change_percentage")),
            open_price=_number(stats.get("day_open")),
            high_price=_number(stats.get("day_high")),
            low_price=_number(stats.get("day_low")),
            close_price=prev,
            timestamp=now_iso,
        )
    return out


async def fetch_daily_candles(client: IndmoneyMCPClient, instrument: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Daily candles for the last `lookback_days` days (at most a year), oldest first; [] when not matched."""
    if lookback_days > 360:
        return []
    keys = await resolve_keys(client, [instrument])
    key = keys.get(instrument.upper())
    if not key:
        return []
    async with _gate():
        raw = await client.call_tool("get_indian_stocks_ohlc", {"ind_key": key, "interval": "1day", "lookback": "14d" if lookback_days <= 14 else "1y"})
    out: List[Dict[str, Any]] = []
    for c in (raw or {}).get("candles") or []:
        try:
            out.append({
                "date": str(c["datetime_ist"])[:10],
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume") or 0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out
