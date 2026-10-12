"""Full daily price history for US stocks and ETFs, stored in Azure Table Storage.

INDmoney's US price history (`get_us_stocks_ohlc`) is exact but capped: one stock, one year, 250 candles;
longer windows are thinned out, which would corrupt 200-day averages and all-time highs. So history is built
once per ticker and then only topped up:

  * Backfill (new ticker, or after a split/restatement): Yahoo's daily chart supplies everything older than
    INDmoney's window, INDmoney supplies the most recent year. Before Yahoo is trusted it is compared with
    INDmoney over the whole overlap; if they disagree materially it is not used and the history is marked
    partial rather than guessed.
  * Top-up (every refresh): INDmoney's latest candles are appended. Overlapping stored days are compared
    first; a difference means the data was restated (a split), and the ticker is rebuilt from scratch.
  * Precedence: for any date INDmoney has supplied, INDmoney's candle is the one kept. Yahoo only fills
    dates before INDmoney's window.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp

from storage.tables.repositories import UsCandleRepository

logger = logging.getLogger("wealthvault.market_data.us_history")

ET = ZoneInfo("America/New_York")
RESTATED_TOLERANCE = 0.005  # a stored close differing from INDmoney's by more than 0.5% means restated data
VENDOR_MEDIAN_TOLERANCE = 0.002  # Yahoo must match INDmoney's closes to within 0.2% (median) to be trusted
MAX_VENDOR_BAD_DAYS = 3  # isolated one-day disagreements (e.g. a fresh IPO's first days) are tolerated
YAHOO_ATTEMPTS = 3

Candle = List[Any]  # [date, open, high, low, close, volume, source]


class UsHistoryError(Exception):
    pass


@dataclass
class HistoryInfo:
    ticker: str
    status: str  # complete | partial
    first_date: str
    last_date: str
    count: int
    note: str
    rebuilt: bool = False


def us_session_closed(now: Optional[datetime] = None) -> bool:
    """True once the regular US session has ended for the current ET date (after 16:15 ET), or on weekends."""
    now_et = (now or datetime.now(ET)).astimezone(ET)
    if now_et.weekday() >= 5:
        return True
    return (now_et.hour, now_et.minute) >= (16, 15)


def _today_et() -> date:
    return datetime.now(ET).date()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(c: Dict[str, Any], source: str) -> Candle:
    return [str(c["date"])[:10], c["open"], c["high"], c["low"], c["close"], c.get("volume", 0), source]


def to_candle_dicts(rows: List[Candle]) -> List[Dict[str, Any]]:
    return [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


# --- sources ---------------------------------------------------------------------------------------------


async def fetch_indmoney_candles(client: Any, ticker: str, duration: str) -> List[Dict[str, Any]]:
    """Exact daily candles from INDmoney. Raises if the response was thinned out (never use sampled data)."""
    resp = await client.call_tool("get_us_stocks_ohlc", {"symbols": [ticker], "duration": duration})
    entry = (resp.get("prices") or {}).get(ticker) if isinstance(resp, dict) else None
    if not entry or entry.get("error"):
        raise UsHistoryError(f"INDmoney has no price history for {ticker}: {(entry or {}).get('error', 'unknown ticker')}")
    candles = entry.get("candles") or []
    total = entry.get("candles_total")
    if total is not None and total != len(candles):
        raise UsHistoryError(f"INDmoney returned thinned history for {ticker} ({len(candles)} of {total}); refusing to use it")
    rows = [
        {
            "date": str(c["date"])[:10],
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": float(c.get("volume") or 0),
        }
        for c in candles
        if c.get("close")
    ]
    rows.sort(key=lambda r: r["date"])
    return rows


async def fetch_yahoo_history(ticker: str) -> List[Dict[str, Any]]:
    """Full daily split-adjusted history from Yahoo's chart endpoint (since listing)."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.replace(chr(46), chr(45))}"
        f"?period1=0&period2={int(time.time()) + 86400}&interval=1d&events=div,split"
    )
    last_err = "unknown"
    for attempt in range(YAHOO_ATTEMPTS):
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status != 200:
                        last_err = f"HTTP {r.status}"
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    data = await r.json()
            result = data["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            offset = result.get("meta", {}).get("gmtoffset", 0)
            out: List[Dict[str, Any]] = []
            for i, ts in enumerate(result["timestamp"]):
                o, h, lo, c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
                if None in (o, h, lo, c) or c <= 0:
                    continue
                day = datetime.fromtimestamp(ts + offset, tz=timezone.utc).strftime("%Y-%m-%d")
                out.append(
                    {
                        "date": day,
                        "open": round(o, 4),
                        "high": round(h, 4),
                        "low": round(lo, 4),
                        "close": round(c, 4),
                        "volume": float(quote["volume"][i] or 0),
                    }
                )
            out.sort(key=lambda r: r["date"])
            if not out:
                raise UsHistoryError("empty")
            return _drop_live_today(out)
        except Exception as exc:
            last_err = str(exc)[:120]
            await asyncio.sleep(1.5 * (attempt + 1))
    raise UsHistoryError(f"Yahoo history unavailable for {ticker}: {last_err}")


# --- merge & validation ----------------------------------------------------------------------------------


def _drop_live_today(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The current session's candle is still forming until the close, so it is never stored."""
    if rows and rows[-1]["date"] >= _today_et().isoformat() and not us_session_closed():
        return rows[:-1]
    return rows


def _vendor_check(ind: List[Dict[str, Any]], yahoo: List[Dict[str, Any]]) -> Tuple[bool, int, str]:
    """Compare the two sources over INDmoney's window. Returns (trusted, bad_days, note)."""
    ymap = {r["date"]: r for r in yahoo}
    diffs = [abs(r["close"] - ymap[r["date"]]["close"]) / r["close"] for r in ind if r["date"] in ymap]
    if len(diffs) < min(20, len(ind)):
        return False, len(ind), "Yahoo covers too few of INDmoney's dates"
    bad = sum(1 for d in diffs if d > RESTATED_TOLERANCE)
    median = statistics.median(diffs)
    if median > VENDOR_MEDIAN_TOLERANCE or bad > MAX_VENDOR_BAD_DAYS:
        return False, bad, f"Yahoo disagrees with INDmoney (median {median:.2%}, {bad} days off)"
    return True, bad, f"Yahoo matches INDmoney ({bad} isolated day(s) differ; INDmoney is kept)"


def _merge(yahoo: Optional[List[Dict[str, Any]]], ind: List[Dict[str, Any]]) -> List[Candle]:
    first_ind = ind[0]["date"] if ind else "9999-12-31"
    rows: Dict[str, Candle] = {}
    for r in yahoo or []:
        if r["date"] < first_ind:
            rows[r["date"]] = _row(r, "y")
    for r in ind:
        rows[r["date"]] = _row(r, "i")
    return [rows[d] for d in sorted(rows)]


# --- public API ------------------------------------------------------------------------------------------


async def _backfill(repo: UsCandleRepository, ticker: str, client: Any, rebuilt: bool) -> HistoryInfo:
    ind = _drop_live_today(await fetch_indmoney_candles(client, ticker, "1y"))
    if not ind:
        raise UsHistoryError(f"No INDmoney candles for {ticker}")
    yahoo: Optional[List[Dict[str, Any]]] = None
    note = ""
    try:
        y = await fetch_yahoo_history(ticker)
        trusted, _bad, note = _vendor_check(ind, y)
        yahoo = y if trusted else None
    except UsHistoryError as exc:
        note = str(exc)

    merged = _merge(yahoo, ind)
    complete = yahoo is not None
    older = sum(1 for r in merged if r[6] == "y")
    if complete:
        note = f"{note}. {older} earlier days from Yahoo, {len(merged) - older} from INDmoney."
    else:
        note = f"Only the last {len(merged)} trading days (INDmoney). {note}"
    meta = {"status": "complete" if complete else "partial", "note": note, "built_at": _utcnow_iso()}
    await repo.clear(ticker)
    await repo.save_years(ticker, merged, sorted({str(r[0])[:4] for r in merged}), meta)
    return HistoryInfo(ticker, meta["status"], merged[0][0], merged[-1][0], len(merged), note, rebuilt)


def _window_for_gap(days: int) -> str:
    return "1m" if days <= 25 else "3m" if days <= 85 else "6m" if days <= 170 else "1y"


async def ensure_history(ticker: str, client: Any, force_rebuild: bool = False) -> HistoryInfo:
    """Make sure the stored history for `ticker` is complete and current, building or topping it up as needed."""
    ticker = ticker.strip().upper()
    repo = UsCandleRepository()
    stored, meta = await repo.load(ticker)
    if force_rebuild or not stored or not meta:
        return await _backfill(repo, ticker, client, rebuilt=bool(stored))

    last = datetime.strptime(stored[-1][0], "%Y-%m-%d").date()
    gap = (_today_et() - last).days
    if gap > 240:  # INDmoney's one-year window would leave a hole, so rebuild
        return await _backfill(repo, ticker, client, rebuilt=True)

    fresh = _drop_live_today(await fetch_indmoney_candles(client, ticker, _window_for_gap(gap + 5)))
    by_date = {r[0]: r for r in stored}
    for r in fresh:
        old = by_date.get(r["date"])
        if old and abs(old[4] - r["close"]) / old[4] > RESTATED_TOLERANCE:
            logger.info("US history for %s was restated (%s: %s vs %s); rebuilding", ticker, r["date"], old[4], r["close"])
            return await _backfill(repo, ticker, client, rebuilt=True)

    added = [r for r in fresh if r["date"] not in by_date]
    if added:
        for r in added:
            by_date[r["date"]] = _row(r, "i")
        merged = [by_date[d] for d in sorted(by_date)]
        meta["updated_at"] = _utcnow_iso()
        await repo.save_years(ticker, merged, sorted({r["date"][:4] for r in added}), meta)
        stored = merged
    return HistoryInfo(ticker, meta.get("status", "partial"), stored[0][0], stored[-1][0], len(stored), meta.get("note", ""))


async def get_candles(ticker: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, meta = await UsCandleRepository().load(ticker.strip().upper())
    return to_candle_dicts(rows), meta
