"""Daily candles for Indian stocks, kept in Azure Table Storage.

Each stock's completed daily candles are fetched from Kite in full once and then only topped up. Having them
stored means the signal tables can be recomputed from the live price without calling Kite for history, and a
refresh needs one small request per stock instead of paging the whole history again.

A stored candle is always a finished session. Today's forming candle is never saved; live prices are folded
in at read time (see live_bar). Overlapping days are compared on every top-up, and a close that differs by
more than 0.5% means the data was restated (split, bonus), so that stock is rebuilt from scratch.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.market_data.history import IST, drop_incomplete_today, get_history_service
from core.market_data.indmoney_market import fetch_daily_candles, get_user_indmoney_client
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.live_bar import india_today
from storage.tables.repositories import IndiaCandleRepository

logger = logging.getLogger("wealthvault.market_data.candle_store")

RESTATED_TOLERANCE = 0.005
RECHECK_SECONDS = 3 * 3600  # a stock with nothing new (holiday, suspension) is not re-asked more often than this
SESSION_FINAL_AFTER = (15, 45)  # Kite's daily candle is final shortly after the 15:30 close

# token -> (candles, meta); filled from Azure on first use and kept for the life of the process
_mem: Dict[str, Tuple[List[Dict[str, Any]], Dict[str, Any]]] = {}


def latest_completed_session(now: Optional[datetime] = None) -> str:
    """The most recent weekday whose session has finished (holidays are not known, see RECHECK_SECONDS)."""
    n = (now or datetime.now(IST)).astimezone(IST)
    d = n.date()
    if n.weekday() < 5 and (n.hour, n.minute) < SESSION_FINAL_AFTER:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _to_dicts(rows: List[List[Any]]) -> List[Dict[str, Any]]:
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


def _to_rows(candles: List[Dict[str, Any]]) -> List[List[Any]]:
    return [[str(c["date"])[:10], c["open"], c["high"], c["low"], c["close"], c.get("volume", 0), "k"] for c in candles]


def _clean(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Finished sessions only, one per date, dates as YYYY-MM-DD."""
    done, _ = drop_incomplete_today(candles)
    final = latest_completed_session()
    by_date = {str(c["date"])[:10]: {**c, "date": str(c["date"])[:10]} for c in done if str(c["date"])[:10] <= final}
    return [by_date[d] for d in sorted(by_date)]


def restated(stored: List[Dict[str, Any]], fresh: List[Dict[str, Any]]) -> bool:
    have = {c["date"]: c["close"] for c in stored}
    for c in fresh:
        old = have.get(c["date"])
        if old and abs(c["close"] - old) / old > RESTATED_TOLERANCE:
            return True
    return False


async def _save(token: str, candles: List[Dict[str, Any]], years: List[str], meta: Dict[str, Any]) -> None:
    await IndiaCandleRepository().save_years(token, _to_rows(candles), years, meta)


async def _recent(client: Any, history: Any, token: int, instrument: Dict[str, Any], lookback: int) -> Tuple[List[Dict[str, Any]], bool]:
    """The latest finished candles: from Kite, or from INDmoney when Kite's login has lapsed (second item True)."""
    try:
        return _clean(await history.get_daily_candles(client, token, lookback)), False
    except KiteAuthRequiredError:
        owner_id = getattr(client, "owner_id", None)
        ind_client = await get_user_indmoney_client(owner_id)
        if ind_client is None:
            raise
        fresh = _clean(await fetch_daily_candles(ind_client, str(instrument.get("id") or ""), lookback))
        if not fresh:
            raise
        return fresh, True


async def get_india_candles(
    client: Any,
    instrument: Dict[str, Any],
    allow_fetch: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Stored finished candles for a stock, topped up from Kite when `allow_fetch` and behind.

    With `allow_fetch=False` nothing is requested from Kite: whatever is stored is returned (possibly
    behind, possibly empty), so a live recompute never waits on Kite's history endpoint.
    """
    token = str(int(instrument["instrument_token"]))
    if token not in _mem:
        rows, meta = await IndiaCandleRepository().load(token)
        _mem[token] = (_to_dicts(rows), meta)
    candles, meta = _mem[token]

    expected = latest_completed_session()
    if not allow_fetch or (candles and candles[-1]["date"] >= expected):
        return candles, meta
    if candles and time.time() - float(meta.get("checked_at", 0)) < RECHECK_SECONDS:
        return candles, meta

    history = get_history_service()
    rebuilt = False
    if candles:
        lookback = (datetime.now(IST).date() - datetime.fromisoformat(candles[-1]["date"]).date()).days + 10
        fresh, from_indmoney = await _recent(client, history, int(token), instrument, lookback)
        if fresh and restated(candles, fresh):
            if from_indmoney:
                # INDmoney can only supply a year, so it cannot rebuild a history; a refresh with Kite logged in will
                logger.info("INDmoney candles for %s disagree with the stored ones; keeping the stored history", instrument.get("id"))
                return candles, {**meta, "checked_at": time.time()}
            logger.info("Stored candles for %s were restated; rebuilding", instrument.get("id"))
            rebuilt = True
        elif fresh:
            by_date = {c["date"]: c for c in candles}
            by_date.update({c["date"]: c for c in fresh if c["date"] > candles[-1]["date"]})
            merged = [by_date[d] for d in sorted(by_date)]
            added = [c for c in merged if c["date"] > candles[-1]["date"]]
            meta = {**meta, "checked_at": time.time(), "count": len(merged), "last": merged[-1]["date"]}
            if added:
                await _save(token, merged, sorted({c["date"][:4] for c in added}), meta)
            else:
                await _save(token, merged, [], meta)
            _mem[token] = (merged, meta)
            return merged, meta
        else:
            return candles, {**meta, "checked_at": time.time()}
    if not candles or rebuilt:
        full = _clean(await history.get_full_daily_history(client, int(token), earliest=instrument.get("listing_date") or None))
        if not full:
            return candles, meta
        meta = {
            "checked_at": time.time(),
            "count": len(full),
            "first": full[0]["date"],
            "last": full[-1]["date"],
            "instrument": {k: instrument.get(k) for k in ("id", "instrument_token", "tradingsymbol", "exchange", "name", "tick_size", "listing_date")},
        }
        repo = IndiaCandleRepository()
        await repo.clear(token)
        await _save(token, full, sorted({c["date"][:4] for c in full}), meta)
        _mem[token] = (full, meta)
        return full, meta
    return candles, meta


def forget(token: Any) -> None:
    _mem.pop(str(token), None)


def is_live_window() -> bool:
    return india_today() is not None
