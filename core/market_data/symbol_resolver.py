"""Resolve broker-specific instrument codes to Kite exchange symbols.

INDmoney identifies Indian stocks by its own code (e.g. 'INDS03339') plus a company name, while Kite quotes
need 'NSE:PARASDEFNC'. The Kite MCP instrument search matches on name, so the company name is searched,
candidates are scored by word overlap, and the result is cached in Azure Table Storage (including misses,
so an unmatched stock is retried only after a week).
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from storage.tables.repositories import SymbolMapRepository

logger = logging.getLogger("wealthvault.market_data.symbol_resolver")

CODE_PATTERN = re.compile(r"^(INDS\d+)\s*\((.+)\)\s*$", re.IGNORECASE)
RETRY_MISSES_AFTER = timedelta(days=7)
MIN_SCORE = 0.75

_STOP = {"ltd", "limited", "the", "co", "company", "corp", "corporation", "inc", "pvt", "private", "and", "of"}


def _tokens(name: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " "))
    return [t for t in cleaned.split() if t and t not in _STOP]


def split_indmoney_symbol(symbol: str) -> Optional[tuple]:
    """('INDS03339', 'Paras Defence ...') for INDmoney Indian-stock symbols, else None."""
    m = CODE_PATTERN.match(symbol.strip())
    return (m.group(1).upper(), m.group(2).strip()) if m else None


def _matches(cand_tok: str, ours: Set[str]) -> bool:
    # Kite truncates and abbreviates names ('TECHNO', 'DEF', 'SHIP&ENG'), so a prefix counts as a match
    return any(o == cand_tok or (len(cand_tok) >= 3 and o.startswith(cand_tok)) for o in ours)


def _score(want: Set[str], candidate_name: str) -> float:
    cand = [t for t in _tokens(candidate_name) if len(t) >= 2]
    if not cand or not want:
        return 0.0
    # Kite names are shorter than ours, so measure how much of Kite's name is covered by ours
    return sum(1 for t in cand if _matches(t, want)) / len(cand)


async def _search(client: Any, name: str) -> List[Dict[str, Any]]:
    toks = _tokens(name)
    found: Dict[str, Dict[str, Any]] = {}
    for q in dict.fromkeys([" ".join(toks[:2]), toks[0] if toks else ""]):
        if not q:
            continue
        try:
            rows = await client.search_instruments(q, "name")
        except Exception as exc:  # network / auth: let the caller fall back
            logger.warning("Instrument search failed for %s: %s", name, exc)
            return []
        for r in rows:
            if r.get("instrument_type") == "EQ" and r.get("exchange") in ("NSE", "BSE"):
                found[r.get("id") or f"{r.get('exchange')}:{r.get('tradingsymbol')}"] = r
    return list(found.values())


def best_match(name: str, rows: List[Dict[str, Any]]) -> Optional[str]:
    """Best company by name overlap, then its NSE listing (same ISIN) if there is one, else BSE."""
    want = set(_tokens(name))
    if not want:
        return None
    first = _tokens(name)[0]
    best_score, best_isin = 0.0, None
    for r in rows:
        cand_toks = _tokens(str(r.get("name", "")))
        if not cand_toks or not _matches(cand_toks[0], {first}) and cand_toks[0] != first:
            continue
        sc = _score(want, str(r.get("name", "")))
        if sc > best_score:
            best_score, best_isin = sc, r.get("isin")
    if best_score < MIN_SCORE or not best_isin:
        return None
    listings = [r for r in rows if r.get("isin") == best_isin]
    listings.sort(key=lambda r: (r.get("exchange") != "NSE", r.get("series") != "EQ"))
    top = listings[0]
    return top.get("id") or f"{top.get('exchange')}:{top.get('tradingsymbol')}"


async def resolve_indmoney_symbols(symbols: List[str], client: Optional[Any]) -> Dict[str, str]:
    """Map INDmoney symbols ('INDS... (Name)') to 'NSE:XYZ' / 'BSE:XYZ'. Unmatched ones are omitted."""
    wanted = {s: p for s in symbols if (p := split_indmoney_symbol(s))}
    if not wanted:
        return {}

    repo = SymbolMapRepository()
    try:
        cache = await repo.get_all()
    except Exception as exc:
        logger.warning("Symbol cache unavailable: %s", exc)
        cache = {}

    now = datetime.now(timezone.utc)
    out: Dict[str, str] = {}
    for sym, (code, name) in wanted.items():
        hit = cache.get(code)
        if hit and hit["kite_id"]:
            out[sym] = hit["kite_id"]
            continue
        if hit:
            try:
                if now - datetime.fromisoformat(hit["resolved_at"]) < RETRY_MISSES_AFTER:
                    continue
            except ValueError:
                pass
        if client is None:
            continue  # cache-only lookup
        kite_id = best_match(name, await _search(client, name))
        try:
            await repo.save(code, kite_id or "", name)
        except Exception as exc:
            logger.warning("Could not cache symbol %s: %s", code, exc)
        if kite_id:
            out[sym] = kite_id
        else:
            logger.info("No Kite symbol matched for %s (%s)", code, name)
    return out
