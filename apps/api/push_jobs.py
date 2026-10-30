"""Runs the push notifications inside the web app (see core/push/service.py for what each one is).

* after every scheduled refresh, today's new strategy calls go out (auto_refresh.run_tick calls `after_tick`)
* a small clock loop sends the Kite login reminder (08:45), the daily net worth (15:45), the US stocks look (21:00
  on weekdays) and the weekly net worth (Sunday 09:00)

Push is off when no Firebase key is configured, and the clock loop runs only where the auto refresh does (production
by default), so a laptop or a test never sends anything.
"""

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apps.api.routers.signals import _equity_symbol_map, _us_quotes, session_really_expired
from apps.api.routers.stage2 import _key_of
from core.analytics.live_signals import live_india_rows
from core.market_data.candle_store import get_india_candles
from core.market_data.history import NIFTY_50_SYMBOL, NIFTY_50_TOKEN
from core.market_data.service import get_market_data_service
from core.market_data.user_client import get_user_kite_client
from core.push import fcm
from core.push.service import Ports, notify_calls, send_kite_reminders, send_networth, send_us_digest
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
    held_info: Dict[str, Dict[str, Dict[str, float]]] = {}
    for owner in owners:
        holdings = await holdings_repo.get_holdings(owner_id=owner)
        symbol_map = await _equity_symbol_map(holdings, None)
        held_keys[owner] = {_key_of(inst) for inst in set(symbol_map.values())}
        held_info[owner] = _positions(holdings, symbol_map)
    result = screener[0] if screener else None
    stage2_keys = {_key_of(r["nsecode"]) for r in (result.rows if result else [])}
    wanted = set(stage2_keys).union(*held_keys.values())
    if not wanted:
        return
    cached = await SignalCacheRepository().get_many(list(wanted))
    live = await live_india_rows(live_clients[0][1], cached)
    rows = {k: live.get(k, row) for k, row in cached.items()}
    counts = await notify_calls(ports, today, rows, held_keys, stage2_keys, final=local.time() >= CLOSE, held_info=held_info)
    if any(counts.values()):
        logger.info("ATH call notifications at %s: %s", local.strftime("%H:%M"), counts)


def _positions(holdings: List[Any], symbol_map: Dict[str, str]) -> Dict[str, Dict[str, float]]:
    """The person's position in each stock they hold, by signal key: shares and the overall gain in percent."""
    totals: Dict[str, List[float]] = {}
    for h in holdings:
        inst = symbol_map.get(h.instrument_symbol)
        if not inst:
            continue
        row = totals.setdefault(_key_of(inst), [0.0, 0.0, 0.0])
        row[0] += h.quantity
        row[1] += h.quantity * h.average_price
        row[2] += h.current_value
    return {k: {"qty": q, "pnl_pct": round((cur / inv - 1) * 100.0, 1) if inv > 0 else None} for k, (q, inv, cur) in totals.items()}


async def _nifty_move(owner: str, since: Optional[str]) -> Optional[float]:
    """Nifty 50's move for the net worth comparison: today's change from its live quote, or (given a date) the change
    since then from the stored daily candles. None when it cannot be told, and the line is then left out."""
    if since is None:
        quotes, _ok = await get_market_data_service().fetch_live_quotes([NIFTY_50_SYMBOL.upper()], client=await get_user_kite_client(owner))
        q = quotes.get(NIFTY_50_SYMBOL.upper())
        return float(q.day_change_percentage) if q and q.day_change_percentage is not None else None
    candles, _meta = await get_india_candles(None, {"instrument_token": NIFTY_50_TOKEN, "id": NIFTY_50_SYMBOL}, allow_fetch=False)
    if not candles:
        return None
    last = candles[-1]
    if date.fromisoformat(str(last["date"])[:10]) < date.today() - timedelta(days=4):
        return None  # the stored candles are too old to compare with
    start = [c for c in candles if str(c["date"])[:10] <= since]
    if not start or not start[-1]["close"]:
        return None
    return round((last["close"] / start[-1]["close"] - 1) * 100.0, 2)


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
            logger.info("Daily net worth pushes sent: %d", await send_networth(ports, HoldingsRepository(), SnapshotsRepository(), today, weekly=False, nifty=_nifty_move))
    if weekday and time(21, 0) <= t < time(23, 0) and ("us", today) not in done:
        done.add(("us", today))
        logger.info("US stocks pushes sent: %d", await send_us_digest(ports, HoldingsRepository(), today, _us_quotes))
    if now.weekday() == 6 and time(9, 0) <= t < time(12, 0) and ("nw_w", today) not in done:
        done.add(("nw_w", today))
        logger.info("Weekly net worth pushes sent: %d", await send_networth(ports, HoldingsRepository(), SnapshotsRepository(), today, weekly=True, nifty=_nifty_move))


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
