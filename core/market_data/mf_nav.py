"""One-day change for mutual funds.

Neither Kite nor Coin reports a day change for a fund, but every fund publishes a NAV each business day. The
fund's ISIN (which Zerodha supplies) maps to its AMFI scheme code in AMFI's published NAV file, and the NAV
history of that scheme gives the previous NAV. The change is measured between the NAV the broker used to value
the holding and the NAV before it, so the day P&L always agrees with the holding's current value.
"""

import asyncio
import logging
import time
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

_amfi: Optional[Tuple[float, Dict[str, str]]] = None  # (fetched, isin -> scheme code)
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
    global _amfi
    if _amfi and time.monotonic() - _amfi[0] < AMFI_TTL:
        return _amfi[1]
    async with http.get(AMFI_URL, allow_redirects=True) as resp:
        resp.raise_for_status()
        mapping = parse_amfi(await resp.text())
    if mapping:
        _amfi = (time.monotonic(), mapping)
    return mapping


async def _history(http: aiohttp.ClientSession, code: str) -> List[Tuple[str, float]]:
    hit = _navs.get(code)
    if hit and time.monotonic() - hit[0] < NAV_TTL:
        return hit[1]
    async with http.get(MFAPI_URL.format(code=code)) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
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
