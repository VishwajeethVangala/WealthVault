"""Which strategy calls (the ATH breakout) are worth a push, and what they say.

A call is "today's" when the strategy's own row says it fired on today's bar: an entry whose entry date is today, or a
trade closed today. The rows are rebuilt on the live price (core/analytics/live_signals.py), so this is the same
reading the Signals page shows with its "Live" tag. Wording stays neutral ("entry signal", "exit signal"): these are a
strategy's outputs, not advice.

Each message names the page to open in `route`: 'strategy:<instrument>' for a single call (the Strategy tab opens on
that stock), 'strategy' for a group. The numbers quoted are the stock's own prices, never the person's amounts; what the
person holds shows as a share count and a percentage, and the masked text leaves the share count out.
"""

from typing import Any, Dict, List, Optional

MAX_NAMES = 4

TITLE_HOLDINGS = "Strategy calls · your holdings"
TITLE_STAGE2 = "Strategy calls · Stage 2 list"
PUBLIC_TITLE = "Strategy calls update"


def display_name(sid: str, row: Dict[str, Any]) -> str:
    """'RELIANCE' from 'NSE:RELIANCE', without a trade-for-trade suffix like '-BE'."""
    code = sid.split(":", 1)[-1].upper()
    for suffix in ("-BE", "-BZ", "-BL", "-IL"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
    return code


def ath_events(rows: Dict[str, Dict[str, Any]], today: str) -> List[Dict[str, Any]]:
    """Entry and exit calls that fired today, from signal rows keyed by instrument id."""
    out: List[Dict[str, Any]] = []
    for sid, row in rows.items():
        ath = row.get("ath") or {}
        name = display_name(sid, row)
        call = ath.get("call") or {}
        if ath.get("state") == "IN_POSITION" and call.get("entry_date") == today and ath.get("entry_date") == today:
            out.append(
                {
                    "sid": sid, "name": name, "side": "buy", "date": today,
                    "price": call.get("close"), "ath": call.get("prior_ath"),
                    "above_ath_pct": call.get("above_ath_pct"), "above_dma_pct": call.get("above_dma_pct"),
                }
            )
        for e in ath.get("exits") or []:
            if e.get("exit_date") == today:
                out.append(
                    {
                        "sid": sid, "name": name, "side": "sell", "date": today,
                        "price": e.get("exit_price"), "entry_price": e.get("entry_price"), "pnl_pct": e.get("pnl_pct"),
                    }
                )
                break
    return sorted(out, key=lambda e: (e["side"] != "buy", e["name"]))


def event_key(kind: str, e: Dict[str, Any]) -> str:
    """The unique key of a call for one person: kind ('h' holdings, 's' Stage 2), day, side and stock."""
    return f"{kind}|{e['date']}|{e['side']}|{e['sid']}"


def _word(side: str) -> str:
    return "entry" if side == "buy" else "exit"


def _px(v: Any) -> str:
    return f"{float(v):,.2f}"


def _signed(v: Any) -> str:
    return f"{'+' if float(v) >= 0 else '−'}{abs(float(v)):.1f}%"


def _list(events: List[Dict[str, Any]]) -> str:
    named = [f"{e['name']} ({_word(e['side'])})" for e in events[:MAX_NAMES]]
    more = len(events) - MAX_NAMES
    return ", ".join(named) + (f" and {more} more" if more > 0 else "")


def _facts(e: Dict[str, Any]) -> str:
    """The numbers behind one call, from what the strategy row carries (empty when it carries none)."""
    if e.get("price") is None:
        return ""
    if e["side"] == "buy":
        text = f"price {_px(e['price'])}"
        if e.get("ath") is not None and e.get("above_ath_pct") is not None:
            text += f", {float(e['above_ath_pct']):.2f}% above its prior ATH {_px(e['ath'])}"
        if e.get("above_dma_pct") is not None:
            text += f", {float(e['above_dma_pct']):.1f}% above the 200-DMA"
        return text
    text = f"closed under the 200-DMA at {_px(e['price'])}"
    if e.get("entry_price") is not None and e.get("pnl_pct") is not None:
        text += f"; the trade from {_px(e['entry_price'])} is {_signed(e['pnl_pct'])}"
    return text


def _held_line(held: Optional[Dict[str, Any]], masked: bool) -> str:
    """'You hold 40 shares, +18% overall.' from the person's own position in the stock (the share count is left out when masked)."""
    if not held:
        return ""
    pnl = held.get("pnl_pct")
    overall = f", {_signed(pnl)} overall" if pnl is not None else ""
    if masked:
        return f"You hold this stock{overall}."
    qty = held.get("qty")
    shares = f"{qty:g} share{'s' if qty != 1 else ''}" if qty else "this stock"
    return f"You hold {shares}{overall}."


def call_message(kind: str, events: List[Dict[str, Any]], held: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Title, bodies and the page to open for a group of calls fired at the same refresh.

    `held` maps the stock's key to the person's position in it ({'qty', 'pnl_pct'}); used for holdings calls."""
    holdings = kind == "h"
    n = len(events)
    held = held or {}
    if n == 1:
        e = events[0]
        what = "entry signal" if e["side"] == "buy" else "exit signal"
        facts = _facts(e)
        first = f"{e['name']}: {what} on today's live price." if e["side"] == "buy" else f"{e['name']}: {what}."
        lines = [first + (f" {facts[0].upper() + facts[1:]}." if facts else "")]
        mine = _held_line(held.get(e["sid"]), masked=False)
        mine_masked = _held_line(held.get(e["sid"]), masked=True)
        tail = "A strategy signal, not advice."
        body = "\n".join(lines + ([mine] if mine else []) + [tail])
        masked = "\n".join(lines + ([mine_masked] if mine_masked else []) + [tail])
        route = f"strategy:{e['sid']}"
        actions = [{"label": "Open strategy", "route": route}]
    else:
        lines = [f"{n} calls: {_list(events)}."]
        for e in events[:MAX_NAMES]:
            facts = _facts(e)
            if facts:
                lines.append(f"{e['name']}: {facts}")
        body = masked = "\n".join(lines + ["A strategy signal, not advice."])
        route = "strategy"
        actions = [{"label": "Open strategy", "route": "strategy"}]
    if holdings:
        actions.append({"label": "Holdings", "route": "holdings"})
    sells = sum(1 for e in events if e["side"] == "sell")
    return {
        "title": TITLE_HOLDINGS if holdings else TITLE_STAGE2,
        "body": body,
        "body_masked": masked,
        # what the lock screen shows: no stock names
        "public_title": PUBLIC_TITLE,
        "route": route,
        "extra": {"tone": "down" if sells == n else "up" if sells == 0 else "flat", "actions": actions},
    }


def reversed_message(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(events)
    body = (
        f"{events[0]['name']}: the {_word(events[0]['side'])} signal from earlier today did not hold at the close."
        if n == 1
        else f"{n} calls from earlier today did not hold at the close: {_list(events)}."
    )
    route = f"strategy:{events[0]['sid']}" if n == 1 and events[0].get("sid") else "strategy"
    return {
        "title": "Strategy calls · did not hold at the close",
        "body": body,
        "body_masked": body,
        "public_title": PUBLIC_TITLE,
        "route": route,
        "extra": {"tone": "flat", "actions": [{"label": "Open strategy", "route": route}]},
    }
