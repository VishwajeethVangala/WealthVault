"""Runs the push notifications inside the web app (see core/push/service.py for what each one is).

* after every scheduled refresh, today's new ATH calls go out (auto_refresh.run_tick calls `after_tick`)
* a small clock loop sends the Kite login reminder (08:45), the daily net worth (15:45) and the weekly one (Sunday 09:00)

Push is off when no Firebase key is configured, and the clock loop runs only where the auto refresh does (production
by default), so a laptop or a test never sends anything.
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apps.api.routers.signals import _equity_symbol_map, session_really_expired
from apps.api.routers.stage2 import _key_of
from core.analytics.live_signals import live_india_rows
from core.market_data.user_client import get_user_kite_client
from core.push import fcm
from core.push.service import Ports, notify_calls, send_kite_reminders, send_networth
from storage.tables.repositories import (
    BrokerConnectionRepository,
    HoldingsRepository,
    SignalCacheRepository,
    SnapshotsRepository,
)

logger = logging.getLogger("wealthvault.api.push_jobs")
IST = ZoneInfo("Asia/Kolkata")
CLOSE = time(15, 30)

_task: Optional[asyncio.Task] = None


def push_ready() -> bool:
    return fcm.get_sender() is not None


async def after_tick(slot: datetime, live_clients: List[Tuple[str, Any]], screener: Tuple[Any, Optional[str]]) -> None:
    """After a scheduled refresh: send each person's new ATH calls (holdings) and the Stage 2 calls (everyone)."""
    if not push_ready() or not live_clients:
        return
    ports = Ports()
    owners = await ports.devices.owners()
    if not owners:
        return
    local = slot.astimezone(IST)
    today = local.date().isoformat()
    holdings_repo = HoldingsRepository()
    held_keys: Dict[str, set] = {}
    for owner in owners:
        holdings = await holdings_repo.get_holdings(owner_id=owner)
        held_keys[owner] = {_key_of(inst) for inst in set((await _equity_symbol_map(holdings, None)).values())}
    result = screener[0] if screener else None
    stage2_keys = {_key_of(r["nsecode"]) for r in (result.rows if result else [])}
    wanted = set(stage2_keys).union(*held_keys.values())
    if not wanted:
        return
    cached = await SignalCacheRepository().get_many(list(wanted))
    live = await live_india_rows(live_clients[0][1], cached)
    rows = {k: live.get(k, row) for k, row in cached.items()}
    counts = await notify_calls(ports, today, rows, held_keys, stage2_keys, final=local.time() >= CLOSE)
    if any(counts.values()):
        logger.info("ATH call notifications at %s: %s", local.strftime("%H:%M"), counts)


def _market_closed(today: str) -> bool:
    """True when today's auto refresh found that the exchange is not trading (a market holiday)."""
    from apps.api import auto_refresh

    last = auto_refresh._last
    return bool(last.get("outcome") == "skipped" and "not trading" in str(last.get("message", "")) and str(last.get("slot", "")).startswith(today))


async def _kite_needs_login(owner: str) -> bool:
    conns = await BrokerConnectionRepository().list_connections(owner)
    if not any(str(getattr(c.broker_name, "value", c.broker_name)).lower() == "zerodha" for c in conns):
        return False
    return await session_really_expired(await get_user_kite_client(owner))


async def run_clock(now: datetime, done: set) -> None:
    """Start whichever timed push is due. Each runs once a day however often this is called."""
    today = now.date()
    t = now.time()
    ports = Ports()
    weekday = now.weekday() < 5
    if weekday and time(8, 45) <= t < time(9, 30) and ("kite", today) not in done:
        done.add(("kite", today))
        logger.info("Kite login reminders sent: %d", await send_kite_reminders(ports, today, _kite_needs_login))
    if weekday and time(15, 45) <= t < time(17, 0) and ("nw_d", today) not in done:
        done.add(("nw_d", today))
        if not _market_closed(today.isoformat()):
            logger.info("Daily net worth pushes sent: %d", await send_networth(ports, HoldingsRepository(), SnapshotsRepository(), today, weekly=False))
    if now.weekday() == 6 and time(9, 0) <= t < time(12, 0) and ("nw_w", today) not in done:
        done.add(("nw_w", today))
        logger.info("Weekly net worth pushes sent: %d", await send_networth(ports, HoldingsRepository(), SnapshotsRepository(), today, weekly=True))


async def _loop() -> None:
    done: set = set()
    logger.info("Push notifications on")
    while True:
        await asyncio.sleep(30)
        try:
            await run_clock(datetime.now(IST), done)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Push clock failed: %s", exc, exc_info=True)


def start_push_jobs() -> None:
    global _task
    from apps.api.auto_refresh import auto_enabled

    if _task is None and auto_enabled() and push_ready():
        _task = asyncio.create_task(_loop())


async def stop_push_jobs() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
