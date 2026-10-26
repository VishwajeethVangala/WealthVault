"""Stock suggestions for the Momentum and Strategy symbol boxes.

Kite's instrument search needs no login, so it answers even when the day's login has lapsed. It is asked twice
(by symbol and by company name) because each finds stocks the other misses, the results are limited to listed
shares and ETFs, and a stock listed on both exchanges appears once, as its NSE listing. If Kite cannot be reached,
INDmoney's name lookup stands in when connected (its keys are turned into exchange symbols by its own details).
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.market_data.indmoney_market import details_for, get_user_indmoney_client

logger = logging.getLogger("wealthvault.market_data.stock_search")

MIN_CHARS = 3
LIMIT = 8
CACHE_SECONDS = 300.0
_cache: Dict[str, Any] = {}


def _suggestion(row: Dict[str, Any]) -> Dict[str, str]:
    exchange = str(row.get("exchange") or "")
    code = str(row.get("tradingsymbol") or "")
    return {"symbol": code if exchange == "NSE" else f"{exchange}:{code}", "instrument": f"{exchange}:{code}", "name": str(row.get("name") or "").title(), "exchange": exchange}


def rank(query: str, rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Listed shares and ETFs matching `query`: symbol starts with it, then name starts with it, then the rest."""
    q = query.strip().upper()
    seen: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if r.get("instrument_type") != "EQ" or r.get("exchange") not in ("NSE", "BSE") or not r.get("name") or not r.get("tradingsymbol"):
            continue
        key = str(r.get("isin") or r["name"]).upper()
        have = seen.get(key)
        if have is None or (have["exchange"] != "NSE" and r["exchange"] == "NSE"):
            seen[key] = r

    def order(r: Dict[str, Any]) -> tuple:
        code, name = str(r["tradingsymbol"]).upper(), str(r["name"]).upper()
        tier = 0 if code.startswith(q) else 1 if name.startswith(q) else 2 if q in name or q in code else 3
        return (tier, r["exchange"] != "NSE", len(code), code)

    return [_suggestion(r) for r in sorted(seen.values(), key=order)[:LIMIT]]


async def _from_indmoney(owner_id: str, query: str) -> List[Dict[str, str]]:
    client = await get_user_indmoney_client(owner_id)
    if client is None:
        return []
    found = await client.call_tool("lookup_ind_keys", {"names": [query], "filter_type": "IN_STOCKS"})
    keys = [r["ind_key"] for r in found if isinstance(r, dict) and str(r.get("ind_key", "")).startswith("INDS")][:LIMIT] if isinstance(found, list) else []
    out = []
    for row in (await details_for(client, keys)).values():
        basic = row.get("entity_basic") or {}
        if basic.get("symbol"):
            out.append({"symbol": basic["symbol"], "instrument": f"NSE:{basic['symbol']}", "name": str(basic.get("display_name") or basic.get("name") or ""), "exchange": "NSE"})
    return out


async def search_stocks(kite_client: Any, owner_id: str, query: str) -> List[Dict[str, str]]:
    q = query.strip()
    if len(q) < MIN_CHARS:
        return []
    hit = _cache.get(q.upper())
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        by_symbol, by_name = await asyncio.gather(kite_client.search_instruments(q), kite_client.search_instruments(q, "name"))
        result = rank(q, list(by_symbol) + list(by_name))
    except Exception as exc:
        logger.warning("Kite instrument search failed (%s); trying INDmoney", exc)
        try:
            return await _from_indmoney(owner_id, q)
        except Exception as exc2:
            logger.warning("INDmoney name lookup failed: %s", exc2)
            return []
    _cache[q.upper()] = (time.monotonic(), result)
    return result
