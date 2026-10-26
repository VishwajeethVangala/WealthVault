"""Refresh Momentum Stocks on a timer.

Every AUTO_REFRESH_MINUTES (15) from 09:15 to 15:30 IST, Monday to Friday, the server does what the "Refresh
Momentum Stocks" button does: re-read the Chartink Stage 2 list, then compute signals for it and for the holdings
of every user whose Kite login is active, or failing that whose INDmoney/Groww login is (INDmoney/Groww can top up the price
history of stocks already stored; a stock never seen before still needs a Kite login for its first history). The
list is read once per run and a stock already computed in this run for one user is not computed again for the next.

A weekday the exchange does not trade (a market holiday) is recognised from Nifty 50: when its live quote shows no
trading today compared with the last stored daily candle, the run is skipped. Nothing outside market hours runs.

It runs inside the web app (one worker, see startup.sh), so on Azure the app must stay loaded: App Service
"Always On". It is on by default in production and off elsewhere; AUTO_REFRESH_ENABLED overrides that.
"""

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apps.api.routers.signals import Job, session_really_expired
from apps.api.routers.stage2 import _jobs, _run_job, read_screener
from core.config import data_dir, get_settings
from core.market_data.candle_store import get_india_candles
from core.market_data.history import NIFTY_50_SYMBOL, NIFTY_50_TOKEN
from core.market_data.groww_market import get_user_groww_client
from core.market_data.indmoney_market import get_user_indmoney_client
from core.market_data.live_bar import apply_live_quote
from core.market_data.service import get_market_data_service
from core.market_data.user_client import get_user_kite_client

logger = logging.getLogger("wealthvault.api.auto_refresh")

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
WINDOW_TEXT = "09:15–15:30 IST, Monday to Friday"

_task: Optional[asyncio.Task] = None
_last: Dict[str, Any] = {}


def auto_enabled() -> bool:
    s = get_settings()
    return s.AUTO_REFRESH_ENABLED if s.AUTO_REFRESH_ENABLED is not None else s.is_production


def slots(day: date, every_minutes: int) -> List[datetime]:
    """The run times on one trading day: the open, then every `every_minutes`, up to and including the close."""
    t = datetime.combine(day, SESSION_OPEN, IST)
    end = datetime.combine(day, SESSION_CLOSE, IST)
    out = []
    while t <= end:
        out.append(t)
        t += timedelta(minutes=every_minutes)
    return out


def next_slot(now: datetime, every_minutes: int) -> datetime:
    """The first run time strictly after `now`, skipping weekends."""
    now = now.astimezone(IST)
    day = now.date()
    for _ in range(8):
        if day.weekday() < 5:
            for t in slots(day, every_minutes):
                if t > now:
                    return t
        day += timedelta(days=1)
    raise RuntimeError("no run time found")  # not reachable: a weekday comes within a week


def kite_owners() -> List[str]:
    """Users whose saved Kite session says it is logged in (one session file per user connection)."""
    owners = set()
    for f in data_dir().glob("kite_session_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not data.get("is_authenticated"):
            continue
        owner = data.get("owner_id")
        if not owner:
            # files saved before the owner was written into them: kite_session_<owner>__<connection>.json
            stem = f.stem[len("kite_session_"):]
            if "__" not in stem:
                continue  # the old single-user file belongs to nobody in particular
            owner = stem.split("__", 1)[0]
        owners.add(owner)
    return sorted(owners)


async def traded_today(client: Any, today: str) -> Optional[bool]:
    """Whether NSE trades today, from Nifty 50's live quote against its last stored daily candle. None when it
    cannot be told (no quote or no stored candles), in which case the run goes ahead."""
    quotes, _ok = await get_market_data_service().fetch_live_quotes([NIFTY_50_SYMBOL.upper()], client=client)
    q = quotes.get(NIFTY_50_SYMBOL.upper())
    if not q or not q.last_price:
        return None
    candles, _meta = await get_india_candles(client, {"instrument_token": NIFTY_50_TOKEN, "id": NIFTY_50_SYMBOL}, allow_fetch=False)
    if not candles:
        return None
    _, applied = apply_live_quote(candles, today, q.last_price, q.open_price, q.high_price, q.low_price)
    return applied


def _record(slot: datetime, outcome: str, message: str, users: int = 0) -> None:
    _last.clear()
    _last.update({"slot": slot.isoformat(), "at": datetime.now(timezone.utc).isoformat(), "outcome": outcome, "message": message, "users": users})
    log = logger.info if outcome != "failed" else logger.error
    log("Auto refresh %s at %s: %s", outcome, slot.strftime("%H:%M"), message)


def indmoney_owners() -> List[str]:
    """Users with a saved INDmoney login (one token file per user connection: indmoney_tokens_<owner>__<connection>.json)."""
    owners = set()
    for f in data_dir().glob("indmoney_tokens_*__*.json"):
        owners.add(f.stem[len("indmoney_tokens_"):].split("__", 1)[0])
    return sorted(owners)


def groww_owners() -> List[str]:
    """Users with a saved Groww login (one token file per user connection: groww_tokens_<owner>__<connection>.json)."""
    owners = set()
    for f in data_dir().glob("groww_tokens_*__*.json"):
        owners.add(f.stem[len("groww_tokens_"):].split("__", 1)[0])
    return sorted(owners)


async def _live_clients() -> List[Tuple[str, Any]]:
    """(owner, Kite client) for each user the run can serve: Kite logged in, or else an INDmoney/Groww login to stand in."""
    out = []
    kite = set(kite_owners())
    for owner in sorted(kite | set(indmoney_owners()) | set(groww_owners())):
        try:
            client = await get_user_kite_client(owner)
            if owner in kite and not await session_really_expired(client):
                out.append((owner, client))
            elif await get_user_indmoney_client(owner) is not None:
                out.append((owner, client))
            elif await get_user_groww_client(owner) is not None:
                out.append((owner, client))
        except Exception as exc:
            logger.warning("Auto refresh could not check the logins of %s: %s", owner, exc)
    return out


async def run_tick(slot: datetime) -> None:
    """One scheduled refresh: the Chartink list once, then each logged-in user's signals job in turn."""
    today = slot.astimezone(IST).date().isoformat()
    live = await _live_clients()
    if not live:
        _record(slot, "skipped", "Nobody is logged in to Kite, INDmoney, or Groww today, so price history cannot be read.")
        return
    if await traded_today(live[0][1], today) is False:
        _record(slot, "skipped", "The exchange is not trading today.")
        return

    screener = await read_screener()
    started = datetime.now(timezone.utc)
    ran = 0
    for owner, _client in live:
        current = _jobs.get(owner)
        if current and current.state == "running":
            continue  # a refresh that person started is already running
        job = Job(state="running", started_at=datetime.now(timezone.utc).isoformat(), trigger="schedule")
        _jobs[owner] = job
        await _run_job(owner, job, fresh_since=started, screener=screener)
        ran += 1
    note = f" Chartink: {screener[1]}" if screener[1] else ""
    _record(slot, "ran", f"Refreshed for {ran} user{'s' if ran != 1 else ''}.{note}", ran)


async def _sleep_until(target: datetime) -> None:
    # short naps, so a laptop sleep or a clock change cannot push a run far past its time
    while True:
        left = (target - datetime.now(IST)).total_seconds()
        if left <= 0:
            return
        await asyncio.sleep(min(left, 60.0))


async def _loop() -> None:
    every = get_settings().AUTO_REFRESH_MINUTES
    logger.info("Auto refresh on: every %d minutes, %s", every, WINDOW_TEXT)
    while True:
        slot = next_slot(datetime.now(IST), every)
        await _sleep_until(slot)
        try:
            await run_tick(slot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _record(slot, "failed", f"{exc}")


def start_auto_refresh() -> None:
    global _task
    if _task is None and auto_enabled():
        _task = asyncio.create_task(_loop())


async def stop_auto_refresh() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


def auto_status() -> Dict[str, Any]:
    """What the Signals page shows about the timer."""
    every = get_settings().AUTO_REFRESH_MINUTES
    on = auto_enabled()
    return {
        "enabled": on,
        "every_minutes": every,
        "window": WINDOW_TEXT,
        "next_run": next_slot(datetime.now(IST), every).isoformat() if on else None,
        "last_run": dict(_last) or None,
    }
