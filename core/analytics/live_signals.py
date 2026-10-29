"""Signal rows recomputed on the live price.

The refresh jobs compute signals from finished daily candles and cache them. Between refreshes the price
moves, so this module rebuilds the rows from the stored candles with today's bar made from the live quote
(see live_bar). Nothing here calls the brokers for history: candles come from Azure/memory, quotes from one
batched live call. A stock whose stored history is behind, or whose quote is missing, keeps its cached row.

Rows carry `live: {price, date, at}` so the UI can say which numbers rest on an unfinished session, and
`live_date` (today) so a call that fired on today's bar can be tagged "Live".
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.analytics.equity_signals import MOMENTUM_LOOKBACK_DAYS, _no_partial, _since, build_signal_row
from core.market_data.candle_store import get_india_candles
from core.market_data.history import NIFTY_50_SYMBOL, NIFTY_50_TOKEN
from core.market_data.live_bar import apply_live_quote, india_today, us_today
from core.market_data.service import get_market_data_service
from core.market_data.us_history import get_candles as get_us_candles

logger = logging.getLogger("wealthvault.analytics.live_signals")

REUSE_SECONDS = 20.0  # a row is rebuilt at most this often unless the price moved
CONCURRENCY = 8
US_MEM_SECONDS = 600.0

_row_cache: Dict[str, Tuple[float, float, str, Dict[str, Any]]] = {}  # id -> (monotonic, price, day, row)
_us_mem: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}


def _previous_weekday(day: str) -> str:
    d = date.fromisoformat(day) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _stamp(row: Dict[str, Any], price: float, day: str) -> Dict[str, Any]:
    row["live"] = {"price": price, "date": day, "at": datetime.now(timezone.utc).isoformat()}
    row["live_date"] = day
    return row


def _reusable(key: str, price: float, day: str) -> Optional[Dict[str, Any]]:
    hit = _row_cache.get(key)
    if hit and hit[2] == day and (hit[1] == price or time.monotonic() - hit[0] < REUSE_SECONDS):
        return hit[3]
    return None


def _spread(cached: Dict[str, Dict[str, Any]], built: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map each cache key (a stock can be stored under two keys) to its live row, if there is one."""
    return {key: built[row["instrument"]] for key, row in cached.items() if row.get("instrument") in built}


async def _in_executor(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


# --- India ----------------------------------------------------------------------------------------------


def _build_india(items: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]], Optional[List[Dict[str, Any]]], Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for instrument_id, instrument, candles, bench, extra in items:
        out[instrument_id] = build_signal_row(instrument_id, instrument, candles, bench, drop_partial=_no_partial, extra=extra)
    return out


async def live_india_rows(client: Any, cached: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Live rows for the cached Indian rows that can be recomputed; others are left out."""
    today = india_today()
    unique: Dict[str, Dict[str, Any]] = {}
    for row in cached.values():
        if row.get("instrument") and row.get("token") and (row.get("momentum") or row.get("ath")):
            unique.setdefault(row["instrument"], row)
    if not today or not unique:
        return {}

    quotes, ok = await get_market_data_service().fetch_live_quotes(sorted({i.upper() for i in unique} | {NIFTY_50_SYMBOL.upper()}), client=client)
    if not quotes:
        return {}

    nifty_candles, _ = await get_india_candles(client, {"instrument_token": NIFTY_50_TOKEN, "id": NIFTY_50_SYMBOL}, allow_fetch=False)
    bench = _since(nifty_candles, MOMENTUM_LOOKBACK_DAYS)
    nq = quotes.get(NIFTY_50_SYMBOL.upper())
    if bench and nq:
        bench, _ = apply_live_quote(bench, today, nq.last_price, nq.open_price, nq.high_price, nq.low_price)
    bench = bench or None

    need = _previous_weekday(today)
    sem = asyncio.Semaphore(CONCURRENCY)
    built: Dict[str, Dict[str, Any]] = {}
    work: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]], Optional[List[Dict[str, Any]]], Dict[str, Any]]] = []
    prices: Dict[str, float] = {}

    async def prepare(instrument_id: str, row: Dict[str, Any]) -> None:
        q = quotes.get(instrument_id.upper())
        if not q or not q.last_price:
            return
        reuse = _reusable(instrument_id, q.last_price, today)
        if reuse:
            built[instrument_id] = reuse
            return
        async with sem:
            candles, _meta = await get_india_candles(client, {"instrument_token": row["token"], "id": instrument_id}, allow_fetch=False)
        if not candles or candles[-1]["date"] < need:
            return  # history is behind the last finished session; a refresh brings it up to date
        live, applied = apply_live_quote(candles, today, q.last_price, q.open_price, q.high_price, q.low_price, 0.0)
        if not applied:
            return
        inst = {"name": row.get("name"), "tick_size": row.get("tick_size") or 0.05, "id": instrument_id}
        work.append((instrument_id, inst, live, bench, {"token": row["token"], "tick_size": row.get("tick_size")}))
        prices[instrument_id] = q.last_price

    await asyncio.gather(*(prepare(i, r) for i, r in unique.items()))
    for i in range(0, len(work), 40):
        for instrument_id, row in (await _in_executor(_build_india, work[i : i + 40])).items():
            built[instrument_id] = _stamp(row, prices[instrument_id], today)
            _row_cache[instrument_id] = (time.monotonic(), prices[instrument_id], today, built[instrument_id])
    return _spread(cached, built)


# --- US -------------------------------------------------------------------------------------------------


async def _us_candles(ticker: str) -> List[Dict[str, Any]]:
    hit = _us_mem.get(ticker)
    if hit and time.monotonic() - hit[0] < US_MEM_SECONDS:
        return hit[1]
    candles, _meta = await get_us_candles(ticker)
    _us_mem[ticker] = (time.monotonic(), candles)
    return candles


def _build_us(items: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]], Optional[List[Dict[str, Any]]], Dict[str, Any], bool]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for instrument_id, instrument, candles, bench, extra, complete in items:
        row = build_signal_row(instrument_id, instrument, candles, bench, benchmark_name="S&P 500 (SPY)", drop_partial=_no_partial, extra=extra)
        if not complete:
            for section in ("ath",):
                row[section] = None
                row["errors"][section] = "History incomplete; not shown rather than guessed"
        out[instrument_id] = row
    return out


async def live_us_rows(cached: Dict[str, Dict[str, Any]], quotes: Dict[str, Dict[str, Any]], names: Dict[str, str], tick_size: float) -> Dict[str, Dict[str, Any]]:
    """Live rows for the cached US rows. `quotes` is {ticker: {price, ...}} from INDmoney."""
    today = us_today()
    unique = {r["instrument"]: r for r in cached.values() if r.get("instrument", "").startswith("US:") and (r.get("momentum") or r.get("ath"))}
    if not today or not unique or not quotes:
        return {}

    bench = None
    spy = await _us_candles("SPY")
    if spy:
        sq = quotes.get("SPY")
        bench = _since(spy, MOMENTUM_LOOKBACK_DAYS)
        if sq and bench:
            bench, _ = apply_live_quote(bench, today, sq.get("price"))

    built: Dict[str, Dict[str, Any]] = {}
    work: List[Tuple[str, Dict[str, Any], List[Dict[str, Any]], Optional[List[Dict[str, Any]]], Dict[str, Any], bool]] = []
    prices: Dict[str, float] = {}
    for instrument_id, row in unique.items():
        ticker = instrument_id.split(":", 1)[1]
        q = quotes.get(ticker)
        if not q or not q.get("price"):
            continue
        reuse = _reusable(instrument_id, q["price"], today)
        if reuse:
            built[instrument_id] = reuse
            continue
        candles = await _us_candles(ticker)
        live, applied = apply_live_quote(candles, today, q["price"])
        if not applied:
            continue
        extra = {k: row.get(k) for k in ("currency", "history_status", "history_note", "history_first")}
        work.append((instrument_id, {"name": names.get(ticker) or row.get("name"), "tick_size": tick_size}, live, bench, extra, row.get("history_status") == "complete"))
        prices[instrument_id] = q["price"]

    for instrument_id, row in (await _in_executor(_build_us, work)).items():
        built[instrument_id] = _stamp(row, prices[instrument_id], today)
        _row_cache[instrument_id] = (time.monotonic(), prices[instrument_id], today, built[instrument_id])
    return _spread(cached, built)
