"""What gets sent, to whom, and when.

Kinds of notification, each switchable per person (the app calls the ATH ones "Strategy calls"):
  holdings_ath    strategy entry/exit calls on stocks the person holds (only that person), on the live price, at the refresh
                  that sees them, once per stock and direction per day, with a follow-up if a call did not hold at the close
  stage2_ath      the same calls for the Chartink Stage 2 list, to everyone (a stock someone holds is theirs, not repeated)
  networth_daily  after the close on trading days
  networth_weekly Sunday morning
  us_stocks       a mid-session look at the person's US stocks (21:00 IST) on US trading days
  kite_login      morning reminder on trading days when Kite needs today's login

The push message holds only a type and an id; the text lives in the notifications table and the phone fetches it.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set
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
        owner_id, kind, msg["title"], msg["body"], msg.get("body_masked", msg["body"]), msg["public_title"], msg.get("route", "overview"),
        json.dumps(msg["extra"], separators=(",", ":")) if msg.get("extra") else "",
    )
    delivered = 0
    for token in tokens:
        result = await ports.sender.send(token, {"type": kind, "id": nid})
        if result == fcm.OK:
            delivered += 1
        elif result == fcm.UNREGISTERED:
            await ports.devices.remove(owner_id, token)
    return delivered


# --- strategy calls -------------------------------------------------------------------------------------------------


async def notify_calls(
    ports: Ports,
    today: str,
    rows: Dict[str, Dict[str, Any]],
    held_keys: Dict[str, Set[str]],
    stage2_keys: Iterable[str],
    final: bool = False,
    held_info: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> Dict[str, int]:
    """Send today's new ATH calls.

    `rows` are live signal rows by cache key; `held_keys` maps each person to the keys of stocks they hold;
    `held_info` gives each person's position in them ({'qty', 'pnl_pct'}), for the "You hold..." line;
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
            if fresh and await send_to_user(ports, owner, "ath_" + kind, pref_key, call_message(kind, fresh, (held_info or {}).get(owner))):
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

CLASS_NAME = {"EQUITY": "Stocks", "US_STOCKS": "US", "MUTUAL_FUND": "MF", "NPS": "NPS", "GOLD": "Gold", "DEBT": "Debt"}
CLASS_ORDER = ["EQUITY", "US_STOCKS", "MUTUAL_FUND", "NPS", "GOLD", "DEBT"]
STOCK_CLASSES = ("EQUITY", "US_STOCKS")


def _arrow(v: float) -> str:
    return "▲" if v >= 0 else "▼"


def _tone(v: Optional[float]) -> str:
    return "flat" if v is None or abs(v) < 0.005 else "up" if v > 0 else "down"


def _class_key(h: Any) -> str:
    c = getattr(h, "asset_class", "")
    return str(getattr(c, "value", c) or "")


def _short(sym: str) -> str:
    """'RELIANCE' from 'RELIANCE' / 'NVDA (NVIDIA Corporation)'; the broker's own suffixes are dropped."""
    code = (sym or "").strip().split()[0].upper() if (sym or "").strip() else ""
    for suffix in ("-BE", "-BZ", "-BL", "-IL"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
    return code


def day_totals(holdings: List[Any]) -> Dict[str, Any]:
    total = sum(h.current_value for h in holdings)
    day = sum((h.day_pnl or 0.0) for h in holdings)
    prev = total - day
    return {"total": total, "day": day, "day_pct": (day / prev * 100.0) if prev > 0 else None}


def day_detail(holdings: List[Any]) -> Dict[str, Any]:
    """What drove the day: the best and the worst stock, each class's move, and how many stocks fell."""
    movers = []
    for h in holdings:
        pct_ = getattr(h, "day_change_percentage", None)
        if _class_key(h) in STOCK_CLASSES and pct_ is not None and (getattr(h, "current_value", 0) or 0) > 0:
            movers.append((_short(getattr(h, "instrument_symbol", "")), float(pct_)))
    by_class: Dict[str, List[float]] = {}
    for h in holdings:
        if getattr(h, "day_pnl", None) is None:
            continue
        cls = _class_key(h)
        row = by_class.setdefault(cls, [0.0, 0.0])
        row[0] += h.current_value
        row[1] += h.day_pnl
    classes = []
    for cls in CLASS_ORDER:
        if cls in by_class:
            cur, day = by_class[cls]
            prev = cur - day
            if prev > 0 and cls in CLASS_NAME:
                classes.append((CLASS_NAME[cls], day / prev * 100.0))
    best = max(movers, key=lambda m: m[1], default=None)
    worst = min(movers, key=lambda m: m[1], default=None)
    return {
        "best": best if best and best[1] > 0 else None,
        "drag": worst if worst and worst[1] < 0 else None,
        "classes": classes,
        "down": sum(1 for _n, v in movers if v < 0),
        "stocks": len(movers),
    }


def _mood(day_pct: Optional[float], detail: Dict[str, Any]) -> str:
    if day_pct is None:
        return ""
    if day_pct >= 1.5:
        return "A strong day."
    if day_pct >= 0.5:
        return "A good day."
    if day_pct > -0.5:
        return "Quiet day, a small " + ("win." if day_pct >= 0 else "dip.")
    if day_pct > -1.5:
        return "A soft day."
    if detail.get("stocks") and detail.get("down"):
        return f"Rough one: {detail['down']} of {detail['stocks']} stocks down."
    return "A rough day."


def _versus(own: float, nifty: Optional[float]) -> str:
    if nifty is None:
        return ""
    gap = own - nifty
    verdict = f"you beat it by {abs(gap):.2f}%" if gap > 0.004 else f"you lagged by {abs(gap):.2f}%" if gap < -0.004 else "level with it"
    return f"Nifty {_arrow(nifty)} {abs(nifty):.2f}% ({verdict})."


def networth_daily_message(
    t: Dict[str, Any], as_of: Optional[str] = None, detail: Optional[Dict[str, Any]] = None, nifty: Optional[float] = None
) -> Dict[str, Any]:
    day_pct = t["day_pct"]
    mood = pct(day_pct) if day_pct is not None else "no day change reported"
    detail = detail or {}
    rest: List[str] = []
    if day_pct is not None and nifty is not None:
        rest.append(_versus(day_pct, nifty))
    moves = []
    if detail.get("best"):
        moves.append(f"Best: {detail['best'][0]} {pct(detail['best'][1])}")
    if detail.get("drag"):
        moves.append(f"Drag: {detail['drag'][0]} {pct(detail['drag'][1])}")
    if moves:
        rest.append("   ".join(moves))
    if detail.get("classes"):
        rest.append("  ".join(f"{name} {_arrow(v)}{abs(v):.1f}%" for name, v in detail["classes"]))
    line = _mood(day_pct, detail)
    if line:
        rest.append(line)
    if as_of:
        rest.append(f"Based on data from {as_of}.")
    head = f"{inr(t['total'])} · today {mood} ({inr(t['day'])})"
    head_masked = f"Today {mood}" + (f" · {_versus(day_pct, nifty).rstrip('.').replace('(', '· ').replace(')', '')}" if day_pct is not None and nifty is not None else "")
    arrow = f" {_arrow(day_pct)} {abs(day_pct):.2f}%" if day_pct is not None else ""
    return {
        "title": f"Net worth · today{arrow}",
        "body": "\n".join([head + "."] + rest),
        "body_masked": "\n".join([head_masked + "."] + rest),
        "public_title": "Your daily net worth update is ready",
        "route": "overview",
        "extra": {"tone": _tone(day_pct), "actions": [{"label": "Holdings", "route": "holdings"}, {"label": "Overview", "route": "overview"}]},
    }


def networth_weekly_message(
    total: float, then: float, then_date: str, series: Optional[List[float]] = None, nifty: Optional[float] = None
) -> Dict[str, Any]:
    change = total - then
    change_pct = (change / then * 100.0) if then > 0 else None
    mood = pct(change_pct) if change_pct is not None else ""
    rest: List[str] = []
    if change_pct is not None and nifty is not None:
        rest.append(_versus(change_pct, nifty).replace("Nifty", "Nifty this week", 1))
    extra: Dict[str, Any] = {"tone": _tone(change_pct), "actions": [{"label": "Overview", "route": "overview"}, {"label": "Holdings", "route": "holdings"}]}
    if series and len(series) >= 3:
        extra["series"] = series
    arrow = f" {_arrow(change_pct)} {abs(change_pct):.2f}%" if change_pct is not None else ""
    return {
        "title": f"Net worth · this week{arrow}",
        "body": "\n".join([f"{inr(total)}, {mood} ({inr(change)}) since {then_date}.".replace(" ,", "")] + rest),
        "body_masked": "\n".join([f"{mood} since {then_date}.".strip()] + rest),
        "public_title": "Your weekly net worth update is ready",
        "route": "overview",
        "extra": extra,
    }


def _index_series(snaps: List[Any], total: float, since: str) -> List[float]:
    """The week's net worth as a line indexed to 100 (so it shows the shape and no amounts): snapshots from the
    reference day on, then today's value."""
    values = [float(s.total_current_value) for s in sorted(snaps, key=lambda s: s.as_of_date) if s.as_of_date >= since]
    values.append(float(total))
    base = values[0]
    return [round(v / base * 100.0, 2) for v in values] if base > 0 else []


# `nifty(owner, since)` -> Nifty 50's move: today's change when `since` is None, else the change since that date
NiftyMove = Callable[[str, Optional[str]], Awaitable[Optional[float]]]


async def send_networth(
    ports: Ports,
    holdings_repo: Any,
    snapshots_repo: Any,
    today: date,
    weekly: bool,
    nifty: Optional[NiftyMove] = None,
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
            snaps = await snapshots_repo.list_snapshots(owner, limit=40)
            older = [s for s in snaps if s.as_of_date <= target]
            if not older:
                continue  # no snapshot a week old yet
            then = max(older, key=lambda s: s.as_of_date)
            move = await _nifty_move(nifty, owner, then.as_of_date)
            msg = networth_weekly_message(t["total"], then.total_current_value, then.as_of_date, _index_series(snaps, t["total"], then.as_of_date), move)
        else:
            msg = networth_daily_message(t, detail=day_detail(holdings), nifty=await _nifty_move(nifty, owner, None))
        if await send_to_user(ports, owner, "networth_weekly" if weekly else "networth_daily", pref_key, msg):
            await ports.sent.mark(owner, key)
            sent += 1
    return sent


async def _nifty_move(nifty: Optional[NiftyMove], owner: str, since: Optional[str]) -> Optional[float]:
    """Nifty's move for the comparison line; the line is left out whenever it cannot be had."""
    if nifty is None:
        return None
    try:
        return await nifty(owner, since)
    except Exception as exc:
        logger.warning("Nifty move unavailable: %s", exc)
        return None


# --- US stocks digest -----------------------------------------------------------------------------------------------


def us_digest_message(rows: List[Dict[str, Any]], spy_pct: Optional[float]) -> Dict[str, Any]:
    """How the person's US stocks look right now. `rows` hold each stock's ticker, today's % move and its weight (value);
    the amount is an estimate from the stored values and the live move, and the masked text leaves it out."""
    total = sum(r["value"] for r in rows)
    move = sum(r["value"] * r["pct"] for r in rows) / total if total > 0 else 0.0
    amount = sum(r["value"] - r["value"] / (1 + r["pct"] / 100.0) for r in rows)
    up = sum(1 for r in rows if r["pct"] > 0)
    head = f"{_arrow(move)} {abs(move):.2f}% so far today"
    rest: List[str] = []
    if spy_pct is not None:
        gap = move - spy_pct
        verdict = f"you're ahead by {abs(gap):.2f}%" if gap > 0.004 else f"you're behind by {abs(gap):.2f}%" if gap < -0.004 else "level with it"
        rest.append(f"S&P 500 (SPY) {_arrow(spy_pct)} {abs(spy_pct):.2f}% ({verdict}).")
    best = max(rows, key=lambda r: r["pct"])
    worst = min(rows, key=lambda r: r["pct"])
    moves = []
    if best["pct"] > 0:
        moves.append(f"Best: {best['ticker']} {pct(best['pct'])}")
    if worst["pct"] < 0:
        moves.append(f"Drag: {worst['ticker']} {pct(worst['pct'])}")
    if moves:
        rest.append("   ".join(moves))
    rest.append(f"{up} of {len(rows)} stock{'s' if len(rows) != 1 else ''} up. The US session is still open.")
    return {
        "title": f"US stocks · so far today {_arrow(move)} {abs(move):.2f}%",
        "body": "\n".join([f"{head} (about {inr(amount)})."] + rest),
        "body_masked": "\n".join([head + "."] + rest),
        "public_title": "Your US stocks update is ready",
        "route": "holdings",
        "extra": {"tone": _tone(move), "actions": [{"label": "Holdings", "route": "holdings"}, {"label": "Signals", "route": "signals"}]},
    }


# `quotes(owner, holdings)` -> {ticker: {'day_change_pct': ...}} including 'SPY' when available
UsQuotes = Callable[[str, List[Any]], Awaitable[Dict[str, Any]]]


async def send_us_digest(ports: Ports, holdings_repo: Any, today: date, quotes: UsQuotes) -> int:
    """The US stocks push on a US trading day, once per person per day, from live prices."""
    sent = 0
    key = f"us|{today.isoformat()}"
    for owner in await ports.devices.owners():
        if await ports.sent.has(owner, key) or not (await ports.prefs.get(owner)).get("us_stocks", True):
            continue
        holdings = [h for h in await holdings_repo.get_holdings(owner_id=owner) if _class_key(h) == "US_STOCKS" and (h.current_value or 0) > 0]
        if not holdings:
            continue
        try:
            q = await quotes(owner, holdings)
        except Exception as exc:
            logger.warning("US quotes unavailable for %s: %s", owner, exc)
            continue
        rows = []
        for h in holdings:
            ticker = _short(h.instrument_symbol)
            move = (q.get(ticker) or {}).get("day_change_pct")
            if move is not None:
                rows.append({"ticker": ticker, "pct": float(move), "value": float(h.current_value)})
        spy = (q.get("SPY") or {}).get("day_change_pct")
        if not rows or all(r["pct"] == 0 for r in rows) and not spy:
            continue  # nothing priced, or the US market is shut today
        if await send_to_user(ports, owner, "us_digest", "us_stocks", us_digest_message(rows, float(spy) if spy is not None else None)):
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
            "body": "Log in to Zerodha (Kite) so live prices and strategy calls keep working today.",
            "body_masked": "Log in to Zerodha (Kite) so live prices and strategy calls keep working today.",
            "public_title": "Kite needs today's login",
            "route": "brokers",
            "extra": {"tone": "flat", "actions": [{"label": "Log in to Kite", "route": "brokers"}]},
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
