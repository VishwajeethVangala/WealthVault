"""What gets sent, to whom, and when.

Four kinds of notification, each switchable per person:
  holdings_ath    ATH entry/exit calls on stocks the person holds (only that person), on the live price, at the refresh
                  that sees them, once per stock and direction per day, with a follow-up if a call did not hold at the close
  stage2_ath      the same calls for the Chartink Stage 2 list, to everyone (a stock someone holds is theirs, not repeated)
  networth_daily  after the close on trading days
  networth_weekly Sunday morning
  kite_login      morning reminder on trading days when Kite needs today's login

The push message holds only a type and an id; the text lives in the notifications table and the phone fetches it.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set
from zoneinfo import ZoneInfo

from core.push import fcm
from core.push.calls import ath_events, call_message, event_key, reversed_message
from storage.tables.repositories import (
    DeviceTokenRepository,
    NotificationPrefsRepository,
    NotificationRepository,
    PushSentRepository,
)

logger = logging.getLogger("wealthvault.push")
IST = ZoneInfo("Asia/Kolkata")


@dataclass
class Ports:
    """The storage and sender the service uses; tests hand in fakes."""

    devices: Any = field(default_factory=DeviceTokenRepository)
    prefs: Any = field(default_factory=NotificationPrefsRepository)
    notes: Any = field(default_factory=NotificationRepository)
    sent: Any = field(default_factory=PushSentRepository)
    sender: Any = field(default_factory=fcm.get_sender)


def inr(value: float) -> str:
    """Rupees with Indian digit grouping: 1234567.8 -> ₹12,34,568."""
    sign = "−" if value < 0 else ""
    n = f"{abs(round(value)):d}"
    if len(n) > 3:
        head, tail = n[:-3], n[-3:]
        groups: List[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        n = ",".join(groups + [tail])
    return f"{sign}₹{n}"


def pct(value: float) -> str:
    return f"{'+' if value >= 0 else '−'}{abs(value):.2f}%"


async def send_to_user(
    ports: Ports,
    owner_id: str,
    kind: str,
    pref_key: Optional[str],
    msg: Dict[str, str],
) -> int:
    """Store the text and push its id to each of the person's phones. Returns how many phones accepted it."""
    if ports.sender is None:
        return 0
    if pref_key and not (await ports.prefs.get(owner_id)).get(pref_key, True):
        return 0
    tokens = await ports.devices.tokens(owner_id)
    if not tokens:
        return 0
    nid = await ports.notes.create(
        owner_id, kind, msg["title"], msg["body"], msg.get("body_masked", msg["body"]), msg["public_title"], msg.get("route", "overview")
    )
    delivered = 0
    for token in tokens:
        result = await ports.sender.send(token, {"type": kind, "id": nid})
        if result == fcm.OK:
            delivered += 1
        elif result == fcm.UNREGISTERED:
            await ports.devices.remove(owner_id, token)
    return delivered


# --- ATH calls -------------------------------------------------------------------------------------------------


async def notify_calls(
    ports: Ports,
    today: str,
    rows: Dict[str, Dict[str, Any]],
    held_keys: Dict[str, Set[str]],
    stage2_keys: Iterable[str],
    final: bool = False,
) -> Dict[str, int]:
    """Send today's new ATH calls.

    `rows` are live signal rows by cache key; `held_keys` maps each person to the keys of stocks they hold;
    `stage2_keys` are the keys on the Chartink list. `final` marks the closing refresh, which also follows up on
    calls that no longer stand. Returns counts for the log."""
    counts = {"holdings": 0, "stage2": 0, "reversed": 0}
    stage2 = {k: rows[k] for k in stage2_keys if k in rows}
    stage2_events = ath_events(stage2, today)
    for owner in await ports.devices.owners():
        prefs = await ports.prefs.get(owner)
        mine = held_keys.get(owner, set())
        held_events = ath_events({k: rows[k] for k in mine if k in rows}, today)
        plans = []
        if prefs.get("holdings_ath", True):
            plans.append(("h", "holdings_ath", held_events))
        if prefs.get("stage2_ath", True):
            plans.append(("s", "stage2_ath", [e for e in stage2_events if e["sid"] not in mine and _alias(e["sid"]) not in mine]))
        for kind, pref_key, events in plans:
            fresh = [e for e in events if not await ports.sent.has(owner, event_key(kind, e))]
            if fresh and await send_to_user(ports, owner, "ath_" + kind, pref_key, call_message(kind, fresh)):
                for e in fresh:
                    await ports.sent.mark(owner, event_key(kind, e), sid=e["sid"], side=e["side"], kind=kind)
                counts["holdings" if kind == "h" else "stage2"] += 1
            if final:
                counts["reversed"] += await _follow_up(ports, owner, kind, pref_key, today, events)
    return counts


def _alias(sid: str) -> str:
    return sid.upper()


async def _follow_up(ports: Ports, owner: str, kind: str, pref_key: str, today: str, standing: List[Dict[str, str]]) -> int:
    """At the close: tell the person about calls sent today that no longer stand."""
    keys_now = {event_key(kind, e) for e in standing}
    gone = []
    for row in await ports.sent.with_prefix(owner, f"{kind}|{today}|"):
        if row.get("status") == "sent" and row["RowKey"] not in keys_now:
            gone.append({"sid": row.get("sid", ""), "name": (row.get("sid", "").split(":", 1)[-1]).upper(), "side": row.get("side", "buy"), "date": today, "_key": row["RowKey"]})
    if not gone:
        return 0
    if await send_to_user(ports, owner, "ath_reversed", pref_key, reversed_message(gone)):
        for g in gone:
            await ports.sent.mark(owner, g["_key"], sid=g["sid"], side=g["side"], kind=kind, status="reversed")
        return 1
    return 0


# --- net worth ---------------------------------------------------------------------------------------------------


def day_totals(holdings: List[Any]) -> Dict[str, Any]:
    total = sum(h.current_value for h in holdings)
    day = sum((h.day_pnl or 0.0) for h in holdings)
    prev = total - day
    return {"total": total, "day": day, "day_pct": (day / prev * 100.0) if prev > 0 else None}


def networth_daily_message(t: Dict[str, Any], as_of: Optional[str] = None) -> Dict[str, str]:
    mood = pct(t["day_pct"]) if t["day_pct"] is not None else "no day change reported"
    note = f" Based on data from {as_of}." if as_of else ""
    return {
        "title": "Net worth · today",
        "body": f"{inr(t['total'])} · today {mood} ({inr(t['day'])}).{note}",
        "body_masked": f"Today {mood}.{note}",
        "public_title": "Your daily net worth update is ready",
        "route": "overview",
    }


def networth_weekly_message(total: float, then: float, then_date: str) -> Dict[str, str]:
    change = total - then
    change_pct = (change / then * 100.0) if then > 0 else None
    mood = pct(change_pct) if change_pct is not None else ""
    return {
        "title": "Net worth · this week",
        "body": f"{inr(total)}, {mood} ({inr(change)}) since {then_date}.".replace(" ,", ""),
        "body_masked": f"{mood} since {then_date}.".strip(),
        "public_title": "Your weekly net worth update is ready",
        "route": "overview",
    }


async def send_networth(
    ports: Ports,
    holdings_repo: Any,
    snapshots_repo: Any,
    today: date,
    weekly: bool,
) -> int:
    """The daily or weekly net worth push, once per person per day (or week)."""
    sent = 0
    pref_key = "networth_weekly" if weekly else "networth_daily"
    key = f"nw_w|{today.isocalendar().year}-W{today.isocalendar().week:02d}" if weekly else f"nw_d|{today.isoformat()}"
    for owner in await ports.devices.owners():
        if await ports.sent.has(owner, key):
            continue
        holdings = await holdings_repo.get_holdings(owner_id=owner)
        if not holdings or sum(h.current_value for h in holdings) <= 0:
            continue
        t = day_totals(holdings)
        if weekly:
            target = (today - timedelta(days=7)).isoformat()
            older = [s for s in await snapshots_repo.list_snapshots(owner, limit=40) if s.as_of_date <= target]
            if not older:
                continue  # no snapshot a week old yet
            then = max(older, key=lambda s: s.as_of_date)
            msg = networth_weekly_message(t["total"], then.total_current_value, then.as_of_date)
        else:
            msg = networth_daily_message(t)
        if await send_to_user(ports, owner, "networth_weekly" if weekly else "networth_daily", pref_key, msg):
            await ports.sent.mark(owner, key)
            sent += 1
    return sent


# --- Kite login reminder -------------------------------------------------------------------------------------------


async def send_kite_reminders(ports: Ports, today: date, needs_login) -> int:
    """`needs_login(owner)` is an async check that is True when the person has Kite but no login for today."""
    sent = 0
    key = f"kite|{today.isoformat()}"
    for owner in await ports.devices.owners():
        if await ports.sent.has(owner, key) or not (await ports.prefs.get(owner)).get("kite_login", True):
            continue
        try:
            if not await needs_login(owner):
                continue
        except Exception as exc:
            logger.warning("Kite login check failed for %s: %s", owner, exc)
            continue
        msg = {
            "title": "Kite needs today's login",
            "body": "Log in to Zerodha (Kite) so live prices and ATH calls keep working today.",
            "body_masked": "Log in to Zerodha (Kite) so live prices and ATH calls keep working today.",
            "public_title": "Kite needs today's login",
            "route": "brokers",
        }
        if await send_to_user(ports, owner, "kite_login", "kite_login", msg):
            await ports.sent.mark(owner, key)
            sent += 1
    return sent


async def send_test(ports: Ports, owner_id: str) -> int:
    """A test notification to the person's own phones, ignoring their switches."""
    msg = {
        "title": "WealthVault notifications work",
        "body": "This is a test. Your net worth and calls will arrive like this.",
        "body_masked": "This is a test. Your net worth and calls will arrive like this.",
        "public_title": "WealthVault test notification",
        "route": "overview",
    }
    return await send_to_user(ports, owner_id, "test", None, msg)
