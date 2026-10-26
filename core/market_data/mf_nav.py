"""Mutual fund values and their one-day change, from the NAV each fund publishes every business day.

Neither Kite nor Coin dates a fund's price or reports a day change, and the price can be days behind (Coin's was the
21 Oct NAV on 26 Oct, while AMFI had published 23 Oct, a 2.2% overstatement across the portfolio). The fund's ISIN
(which Zerodha supplies) maps to its AMFI scheme code in AMFI's published NAV file, and the NAV history of that scheme
gives the latest NAV and the one before it. `apply_latest_nav` values the holding at the latest published NAV; when
the NAV sources cannot be reached the broker's price stays, and `apply_mf_day_changes` still measures the change from
the NAV the broker used so the day P&L agrees with the holding's value.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp

from core.models import AssetClass, Holding

logger = logging.getLogger("wealthvault.market_data.mf_nav")

AMFI_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
MFAPI_URL = "https://api.mfapi.in/mf/{code}"
AMFI_TTL = 6 * 3600.0
NAV_TTL = 3 * 3600.0
CONCURRENCY = 5
MATCH_TOLERANCE = 0.0005  # a NAV within 0.05% of the broker's is the same day's NAV
MAX_NAV_GAP = 0.25  # a published NAV 25% from the broker's is a wrong scheme match or a restructured fund, not a price
FAILURE_BACKOFF = 300.0  # after a failed NAV download the next attempt waits this long, so a slow source is not hit on every poll

_amfi: Optional[Tuple[float, Dict[str, str]]] = None  # (fetched, isin -> scheme code)
_amfi_failed_at = -FAILURE_BACKOFF
_amfi_lock: Optional[asyncio.Lock] = None
_failed: Dict[str, float] = {}  # scheme code -> when its history last failed
_navs: Dict[str, Tuple[float, List[Tuple[str, float]]]] = {}  # scheme code -> (fetched, [(date, nav)] newest first)


def parse_amfi(text: str) -> Dict[str, str]:
    """ISIN -> scheme code from AMFI's NAVAll.txt (`code;ISIN;ISIN reinvest;name;...`)."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split(";")
        if len(parts) < 4 or not parts[0].strip().isdigit():
            continue
        for isin in parts[1:3]:
            isin = isin.strip().upper()
            if isin.startswith("INF"):
                out[isin] = parts[0].strip()
    return out


async def _isin_map(http: aiohttp.ClientSession) -> Dict[str, str]:
    global _amfi, _amfi_failed_at, _amfi_lock
    if _amfi and time.monotonic() - _amfi[0] < AMFI_TTL:
        return _amfi[1]
    if _amfi_lock is None:
        _amfi_lock = asyncio.Lock()
    async with _amfi_lock:  # simultaneous reads share one download
        if _amfi and time.monotonic() - _amfi[0] < AMFI_TTL:
            return _amfi[1]
        if time.monotonic() - _amfi_failed_at < FAILURE_BACKOFF:
            return _amfi[1] if _amfi else {}
        try:
            async with http.get(AMFI_URL, allow_redirects=True) as resp:
                resp.raise_for_status()
                mapping = parse_amfi(await resp.text())
        except Exception:
            _amfi_failed_at = time.monotonic()
            if _amfi:
                return _amfi[1]  # an older list is still right: an ISIN's scheme code rarely changes
            raise
        if mapping:
            _amfi = (time.monotonic(), mapping)
        return mapping


async def _history(http: aiohttp.ClientSession, code: str) -> List[Tuple[str, float]]:
    hit = _navs.get(code)
    if hit and time.monotonic() - hit[0] < NAV_TTL:
        return hit[1]
    if time.monotonic() - _failed.get(code, -FAILURE_BACKOFF) < FAILURE_BACKOFF:
        return hit[1] if hit else []
    try:
        async with http.get(MFAPI_URL.format(code=code)) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    except Exception:
        _failed[code] = time.monotonic()
        if hit:
            return hit[1]  # the last NAVs known are better than none
        raise
    series: List[Tuple[str, float]] = []
    for row in (data.get("data") or [])[:12]:
        try:
            d, n = str(row["date"]), float(row["nav"])
        except (KeyError, TypeError, ValueError):
            continue
        if n > 0:
            series.append((d, n))
    if series:
        _navs[code] = (time.monotonic(), series)
    return series


def day_change_pct(series: List[Tuple[str, float]], broker_nav: Optional[float]) -> Optional[Tuple[float, str]]:
    """% change of the NAV the broker used versus the NAV before it, and that NAV's date."""
    if len(series) < 2:
        return None
    idx = 0
    if broker_nav:
        match = next((i for i, (_, n) in enumerate(series) if abs(n - broker_nav) / broker_nav <= MATCH_TOLERANCE), None)
        if match is None:
            return None  # the broker's NAV is not one of the recent published ones; do not guess
        idx = match
    if idx + 1 >= len(series):
        return None
    now, prev = series[idx][1], series[idx + 1][1]
    return (now / prev - 1.0) * 100.0, series[idx][0]


async def apply_mf_day_changes(holdings: Iterable[Holding]) -> List[Holding]:
    """Fill day P&L and day % on mutual-fund holdings that have an ISIN and no broker-reported change.

    Never raises: with the NAV sources unreachable the holdings come back unchanged.
    """
    items = list(holdings)
    todo = [h for h in items if h.asset_class == AssetClass.MUTUAL_FUND and getattr(h, "isin", None) and h.day_pnl is None]
    if not todo:
        return items
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
            mapping = await _isin_map(http)
            sem = asyncio.Semaphore(CONCURRENCY)

            async def one(h: Holding) -> None:
                code = mapping.get((h.isin or "").upper())
                if not code:
                    return
                try:
                    async with sem:
                        series = await _history(http, code)
                except Exception as exc:
                    logger.info("NAV history unavailable for %s: %s", h.isin, exc)
                    return
                change = day_change_pct(series, h.current_price)
                if change is None:
                    return
                pct, _date = change
                h.day_change_percentage = round(pct, 2)
                h.day_pnl = round(h.current_value - h.current_value / (1 + pct / 100.0), 2)

            await asyncio.gather(*(one(h) for h in todo))
    except Exception as exc:
        logger.warning("Mutual fund day change unavailable: %s", exc)
    return items


def _nav_date(text: str) -> Optional[str]:
    """'23-10-2026' (mfapi) -> '2026-10-23'."""
    try:
        return datetime.strptime(text, "%d-%m-%Y").date().isoformat()
    except ValueError:
        return None


async def apply_latest_nav(holdings: Iterable[Holding]) -> List[Holding]:
    """Value each mutual fund holding at the latest NAV its fund has published, with the day change against the NAV
    before it. A holding with no ISIN, no scheme match, no NAV history, or a NAV nowhere near the broker's price keeps
    what the broker said. Never raises."""
    items = list(holdings)
    todo = [h for h in items if h.asset_class == AssetClass.MUTUAL_FUND and getattr(h, "isin", None) and h.quantity > 0]
    if not todo:
        return items
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as http:
            mapping = await _isin_map(http)
            sem = asyncio.Semaphore(CONCURRENCY)

            async def one(h: Holding) -> None:
                code = mapping.get((h.isin or "").upper())
                if not code:
                    return
                try:
                    async with sem:
                        series = await _history(http, code)
                except Exception as exc:
                    logger.info("NAV history unavailable for %s: %s", h.isin, exc)
                    return
                if not series:
                    return
                when, nav = series[0]
                if h.current_price and abs(nav / h.current_price - 1.0) > MAX_NAV_GAP:
                    logger.warning("Published NAV %s for %s is far from the broker's %s; keeping the broker's", nav, h.isin, h.current_price)
                    return
                h.current_price = nav
                h.current_value = round(h.quantity * nav, 2)
                h.pnl = round(h.current_value - h.quantity * h.average_price, 2)
                h.data_freshness = "live"  # the official NAV of the latest day published
                h.last_price_updated_at = _nav_date(when)
                if len(series) >= 2 and series[1][1] > 0:
                    pct = (nav / series[1][1] - 1.0) * 100.0
                    h.day_change_percentage = round(pct, 2)
                    h.day_pnl = round(h.current_value - h.current_value / (1 + pct / 100.0), 2)

            await asyncio.gather(*(one(h) for h in todo))
    except Exception as exc:
        logger.warning("Latest mutual fund NAV unavailable: %s", exc)
    return items


async def apply_mf_values(holdings: Iterable[Holding]) -> List[Holding]:
    """Latest NAV for every fund that has one; for any left, the broker's price with a day change measured from it."""
    return await apply_mf_day_changes(await apply_latest_nav(holdings))
