"""Read a saved Chartink screener: its conditions and the stocks it currently returns.

Chartink renders results with JavaScript, so the page itself holds no list. The page does embed the
screener's scan clause, and the site's own endpoint (`/screener/process`) returns the matching stocks for it.
The clause is re-read from the page on every fetch, so any edit made to the screener on Chartink (conditions
or added columns) is picked up automatically. Extra columns added on Chartink arrive in each row unchanged.
"""

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("wealthvault.screeners.chartink")

BASE = "https://chartink.com"
USER_AGENT = "Mozilla/5.0 (WealthVault screener reader)"
CORE_COLUMNS = {"sr", "nsecode", "name", "bsecode", "close", "per_chg", "volume"}
CLAUSE_MARKER = "atlas_query&quot;:&quot;"


class ScreenerError(Exception):
    pass


@dataclass
class ScreenerResult:
    slug: str
    title: str
    clause: str
    rows: List[Dict[str, Any]]
    fetched_at: str
    url: str
    extra_columns: List[str] = field(default_factory=list)


# one column of the screener: its measure, its parameters (if any) and its display name
_COLUMN_RE = re.compile(
    r'"measure":\{"id":"[^"]+","value":"([^"]+)","type":\d+,"offset":\{[^}]*\},"parameters":(\[[^\]]*\])\}\},"name":"([^"]+)","isEnabled":(true|false)'
)


def parse_extra_columns(page: str) -> List[Dict[str, str]]:
    """Columns added to the screener beyond Chartink's default ones (close, % change, volume).

    Only plain measures such as `sector` or `market_cap` are supported; a column with parameters (for example an
    SMA length) is skipped because its query form cannot be derived reliably from the saved definition.
    """
    text = html.unescape(page).replace('\\"', '"')
    i = text.find('"columns":{"id"')
    if i < 0:
        return []
    out: List[Dict[str, str]] = []
    for measure, params, name, enabled in _COLUMN_RE.findall(text[i : i + 60000]):
        if enabled != "true" or params != "[]" or name in ("close", "%_change", "volume"):
            continue
        if all(c["alias"] != name for c in out):
            out.append({"measure": measure, "alias": name})
    return out


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i)
    return text[i:j] if j >= 0 else ""


async def _fetch_column(http: aiohttp.ClientSession, url: str, token: str, clause: str, col: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Run the screener with one extra column. Price measures need a `daily` prefix and fundamentals do not,
    so both forms are tried; the first that Chartink accepts wins."""
    text = col["measure"].replace("_", " ")
    headers = {
        "User-Agent": USER_AGENT,
        "X-CSRF-TOKEN": token,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": url,
        "Origin": BASE,
    }
    for form in (text, f"daily {text}"):
        async with http.post(
            f"{BASE}/screener/process",
            data={"scan_clause": clause, "debug_clause": "", "column_clause": f"{form} as '{col['alias']}'"},
            headers=headers,
        ) as r:
            if r.status != 200:
                continue
            payload = await r.json(content_type=None)
        if payload.get("scan_error") or not payload.get("data"):
            continue
        return {row["nsecode"]: row.get(col["alias"]) for row in payload["data"] if row.get("nsecode")}
    return None


async def fetch_screener(slug: str) -> ScreenerResult:
    url = f"{BASE}/screener/{slug}"
    timeout = aiohttp.ClientTimeout(total=40)
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), timeout=timeout) as http:
            async with http.get(url, headers={"User-Agent": USER_AGENT}) as r:
                if r.status != 200:
                    raise ScreenerError(f"Chartink returned HTTP {r.status} for the screener page")
                page = await r.text()

            token = re.search(r'name="csrf-token"\s+content="([^"]+)"', page)
            clause = html.unescape(_between(page, CLAUSE_MARKER, "&quot;"))
            if not token or not clause:
                raise ScreenerError("Could not read the screener conditions from the Chartink page (the page layout may have changed)")
            title = html.unescape(_between(page, "<title>", "</title>")).strip() or slug

            headers = {
                "User-Agent": USER_AGENT,
                "X-CSRF-TOKEN": token.group(1),
                "X-Requested-With": "XMLHttpRequest",
                "Referer": url,
                "Origin": BASE,
            }
            async with http.post(f"{BASE}/screener/process", data={"scan_clause": clause, "debug_clause": ""}, headers=headers) as r:
                if r.status != 200:
                    raise ScreenerError(f"Chartink returned HTTP {r.status} when running the screener")
                payload = await r.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise ScreenerError(f"Could not reach Chartink: {exc}") from exc

    if payload.get("scan_error"):
        raise ScreenerError(f"Chartink reported an error in the screener: {payload['scan_error']}")
    rows = [r for r in payload.get("data", []) if r.get("nsecode")]

    # Added columns are not part of the default response; each is requested with its own column clause
    by_code = {r["nsecode"]: r for r in rows}
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), timeout=timeout) as http:
            async with http.get(url, headers={"User-Agent": USER_AGENT}) as r:
                page2 = await r.text()
            token2 = re.search(r'name="csrf-token"\s+content="([^"]+)"', page2)
            for col in parse_extra_columns(page2) if token2 else []:
                values = await _fetch_column(http, url, token2.group(1), clause, col)
                if values is None:
                    logger.warning("Could not read Chartink column %s; skipped", col["alias"])
                    continue
                for code, value in values.items():
                    if code in by_code:
                        by_code[code][col["alias"]] = value
    except aiohttp.ClientError as exc:
        logger.warning("Chartink extra columns unavailable: %s", exc)
    extras = sorted({k for r in rows for k in r} - CORE_COLUMNS)
    return ScreenerResult(
        slug=slug,
        title=title,
        clause=clause,
        rows=rows,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        url=url,
        extra_columns=extras,
    )
