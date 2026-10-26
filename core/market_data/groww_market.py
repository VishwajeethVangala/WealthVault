"""Prices and recent daily candles from Groww MCP, for when a user's Kite login is not active.

Groww's tools take company *names* and answer loosely (a query for RELIANCE returns Reliance Power, Communications and
others too), so nothing here trusts a name match. A stock is first resolved with `curate_symbols`, and only the
result whose exchange and symbol are exactly the ones asked for is used: its full title then drives the candle call,
and the quote call is read only at that exact symbol. A stock that does not resolve exactly (a renamed or demerged
symbol, a name Groww does not know) gets nothing rather than another company's numbers.

Groww's candle tool is the weakest link: it resolves its name loosely and its reply names no instrument, so a wrong
guess comes back looking perfectly normal (asking for "Nifty 50" returned Reliance's candles). Candles are therefore
accepted only when they agree with the live quote of the exact symbol (previous close and last price), and indices never
use that tool at all.

A stand-in for the top-up of history and for live quotes, never a source of full history.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from core.market_data.groww_client import GrowwMCPClient, get_groww_mcp_client
from core.models import QuoteItem
from storage.tables.repositories import BrokerConnectionRepository, SymbolMapRepository

logger = logging.getLogger("wealthvault.market_data.groww_market")

IST = ZoneInfo("Asia/Kolkata")
CONCURRENCY = 4
KEY_PREFIX = "GRW:"  # symbol table rows are keyed "GRW:NSE:RELIANCE"; INDmoney's own codes never start so
MISS_SECONDS = 3600.0  # a stock Groww cannot match exactly is not searched again for an hour
LTP_BATCH = 50  # the tool's limit per call
MAX_DAYS = 1825  # the tool's limit: about five years
PREV_CLOSE_TOLERANCE = 0.002  # candle closes and the quote's previous close are the same figure; allow rounding only
LAST_PRICE_TOLERANCE = 0.02  # the latest candle may be a running intraday bar a moment behind the quote
KINDS = ("Stocks", "etf", "index")
SERIES_SUFFIX = re.compile(r"-(BE|BZ|SM|ST|SO|T0|IL|X1)$")

_titles: Dict[str, Tuple[str, str]] = {}  # "NSE:RELIANCE" -> (title, entity type)
_misses: Dict[str, float] = {}
_loaded = False
_sem: Optional[asyncio.Semaphore] = None


def _gate() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(CONCURRENCY)
    return _sem


async def get_user_groww_client(owner_id: Optional[str]) -> Optional[GrowwMCPClient]:
    """The user's Groww client when one is connected and holds a usable login, else None."""
    if not owner_id:
        return None
    try:
        connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    except Exception as exc:
        logger.warning("Could not list connections of %s: %s", owner_id, exc)
        return None
    for c in connections:
        if c.broker_name.lower().strip() != "groww":
            continue
        client = get_groww_mcp_client(c.connection_id, owner_id=owner_id)
        if client.is_authenticated():
            return client
    return None


def split_instrument(instrument: str) -> Tuple[str, str]:
    """('NSE', 'HFCL') for 'NSE:HFCL-BE'; a bare symbol is NSE. Kite lists stocks on a special trading series as
    'HFCL-BE'; Groww knows the company by 'HFCL', and its price is for the same company."""
    s = instrument.upper().strip()
    exchange, _, symbol = s.rpartition(":")
    exchange = exchange or "NSE"
    return exchange, (SERIES_SUFFIX.sub("", symbol) if exchange == "NSE" else symbol)


def _inner(res: Any) -> Dict[str, Any]:
    """Groww answers {'result_timestamp': ..., 'result': {...}}."""
    if isinstance(res, dict):
        inner = res.get("result", res)
        return inner if isinstance(inner, dict) else {}
    return {}


async def _load_titles() -> None:
    global _loaded
    if _loaded:
        return
    try:
        for code, row in (await SymbolMapRepository().get_all()).items():
            if code.startswith(KEY_PREFIX) and row.get("kite_id"):
                title, _, kind = row["kite_id"].partition("|")
                _titles[code[len(KEY_PREFIX):]] = (title, kind or "Stocks")
    except Exception as exc:
        logger.warning("Saved Groww titles unavailable: %s", exc)
    _loaded = True


async def _curate(client: GrowwMCPClient, exchange: str, symbol: str) -> Optional[Tuple[str, str]]:
    """(title, entity type) of the listing whose exchange and symbol are exactly these, else None."""
    for kind in KINDS:
        async with _gate():
            res = await client.call_tool("curate_symbols", {"query": symbol, "entity_type": kind})
        for m in _inner(res).get("matches") or []:
            if not isinstance(m, dict) or str(m.get("exchange", "")).upper() != exchange or not m.get("title"):
                continue
            # an index is known by its name ('NIFTY 50'; Groww's own symbol for it is 'NIFTY'), everything else by symbol
            if str(m.get("symbol", "")).upper() == symbol or (kind == "index" and str(m["title"]).upper() == symbol):
                return str(m["title"]), kind
    return None


async def resolve_titles(client: GrowwMCPClient, instruments: List[str]) -> Dict[str, Tuple[str, str]]:
    """instrument -> (Groww title, entity type) for the ones Groww matches exactly."""
    await _load_titles()
    out: Dict[str, Tuple[str, str]] = {}
    now = time.monotonic()
    todo: List[Tuple[str, str, str, str]] = []
    for inst in dict.fromkeys(i.upper().strip() for i in instruments if i and i.strip()):
        exchange, symbol = split_instrument(inst)
        key = f"{exchange}:{symbol}"
        if key in _titles:
            out[inst] = _titles[key]
        elif now - _misses.get(key, -MISS_SECONDS) >= MISS_SECONDS:
            todo.append((inst, key, exchange, symbol))

    async def one(inst: str, key: str, exchange: str, symbol: str) -> None:
        try:
            found = await _curate(client, exchange, symbol)
        except Exception as exc:
            logger.warning("Groww symbol lookup failed for %s: %s", key, exc)
            return  # not a miss: the next try may work
        if not found:
            _misses[key] = time.monotonic()
            return
        _titles[key] = found
        out[inst] = found
        try:
            await SymbolMapRepository().save(KEY_PREFIX + key, f"{found[0]}|{found[1]}", key)
        except Exception as exc:
            logger.warning("Could not save Groww title for %s: %s", key, exc)

    await asyncio.gather(*(one(*t) for t in todo))
    return out


def _number(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def to_ist_date(raw: Any) -> Optional[str]:
    """The trading day (IST) a candle timestamp belongs to. Groww sends local-time ISO text ('2026-10-23T00:00:00');
    a zone-aware time or an epoch (seconds or milliseconds) is converted to IST first, so a UTC midnight cannot
    land on the wrong day."""
    try:
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().replace(".", "", 1).isdigit()):
            n = float(raw)
            return datetime.fromtimestamp(n / 1000.0 if n > 1e11 else n, timezone.utc).astimezone(IST).date().isoformat()
        when = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        if when.tzinfo is not None:
            when = when.astimezone(IST)
        return when.date().isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _parse_candle(c: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(c, dict):
        return None
    date = to_ist_date(c.get("timestamp") or c.get("date") or c.get("datetime") or c.get("date_time"))
    o, h, l, cl = (_number(c.get(k)) for k in ("open", "high", "low", "close"))
    # a candle with a missing or impossible price is dropped, not guessed at
    if not date or min(o, h, l, cl) <= 0 or h < l or not (l <= cl <= h) or not (l <= o <= h):
        return None
    return {"date": date, "open": o, "high": h, "low": l, "close": cl, "volume": _number(c.get("volume"))}


def consistent_with_quote(rows: List[Dict[str, Any]], quote: Optional[QuoteItem]) -> bool:
    """Whether candles can be the instrument the quote is for: the quote's previous close is the close of one of the
    last three sessions, and the latest candle is near the last price."""
    if not rows or quote is None or not quote.close_price or quote.close_price <= 0 or quote.last_price <= 0:
        return False
    prev_ok = any(abs(r["close"] - quote.close_price) / quote.close_price <= PREV_CLOSE_TOLERANCE for r in rows[-3:])
    last_ok = abs(rows[-1]["close"] - quote.last_price) / quote.last_price <= LAST_PRICE_TOLERANCE
    return prev_ok and last_ok


async def fetch_groww_daily_candles(client: GrowwMCPClient, instrument: str, lookback_days: int) -> List[Dict[str, Any]]:
    """Daily candles for the last `lookback_days` days, oldest first; [] when Groww does not match the stock exactly,
    when the stock is an index, or when the candles do not agree with the stock's own live quote."""
    key = instrument.upper().strip()
    found = (await resolve_titles(client, [key])).get(key)
    if not found or found[1] == "index":
        return []
    args = {"company_name": found[0], "segment": "CASH", "interval_in_minutes": 1440, "last_n_days": max(1, min(MAX_DAYS, lookback_days))}
    try:
        async with _gate():
            raw = await client.call_tool("fetch_historical_candle_data", args)
    except Exception as exc:
        logger.warning("Groww candle fetch failed for %s: %s", instrument, exc)
        return []
    by_date: Dict[str, Dict[str, Any]] = {}
    for item in _inner(raw).get("candles") or []:
        row = _parse_candle(item)
        if row:
            by_date[row["date"]] = row
    rows = [by_date[d] for d in sorted(by_date)]
    quote = (await fetch_groww_quotes(client, [key])).get(key)
    if not consistent_with_quote(rows, quote):
        logger.warning("Groww candles for %s do not match its live quote; not used", instrument)
        return []
    return rows


async def fetch_groww_quotes(client: GrowwMCPClient, instruments: List[str]) -> Dict[str, QuoteItem]:
    """Live quotes (same shape as Kite's) for the instruments Groww matches exactly, keyed as asked."""
    wanted = list(dict.fromkeys(i.upper().strip() for i in instruments if i and i.strip()))
    titles = await resolve_titles(client, wanted)
    if not titles:
        return {}
    out: Dict[str, QuoteItem] = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for kind in KINDS:
        # curate_symbols files ETFs under "Stocks" as well, and get_ltp only finds an ETF under "etf": so a stock or ETF
        # still unpriced is asked for under each of the two. An index is only ever asked for as an index.
        same = ("index",) if kind == "index" else ("Stocks", "etf")
        group = {inst: split_instrument(inst) for inst, (_, k) in titles.items() if k in same and inst not in out}
        queries = sorted({titles[inst][0] for inst in group})
        for i in range(0, len(queries), LTP_BATCH):
            try:
                async with _gate():
                    res = await client.call_tool("get_ltp", {"search_queries": queries[i : i + LTP_BATCH], "segment": "CASH", "query_type": kind})
            except Exception as exc:
                logger.warning("Groww get_ltp failed: %s", exc)
                continue
            # answers are keyed 'NSE-Reliance Industries Ltd.' and carry the symbol; take only the exact ones asked for
            by_exchange_symbol: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for key, data in (_inner(res).get("ltp_results") or {}).items():
                if not isinstance(data, dict) or not data.get("symbol"):
                    continue
                exch, _, name = str(key).partition("-")
                by_exchange_symbol[(exch.upper(), str(data["symbol"]).upper())] = data
                if kind == "index":
                    by_exchange_symbol[(exch.upper(), name.strip().upper())] = data  # an index is asked for by its name
            for inst, (exchange, symbol) in group.items():
                data = by_exchange_symbol.get((exchange, symbol))
                price = _number(data.get("ltp")) if data else 0.0
                if not data or price <= 0:
                    continue
                prev = _number(data.get("prev_close"))
                change = round(price - prev, 2) if prev > 0 else _number(data.get("day_change"))
                out[inst] = QuoteItem(
                    instrument=inst,
                    last_price=price,
                    day_change=change,
                    day_change_percentage=round(change / prev * 100.0, 2) if prev > 0 else _number(data.get("day_change_perc")),
                    open_price=_number(data.get("open")),
                    high_price=_number(data.get("high")),
                    low_price=_number(data.get("low")),
                    close_price=prev,
                    timestamp=now_iso,
                )
    return out
