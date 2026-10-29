"""Which ATH-breakout calls are worth a push, and what they say.

A call is "today's" when the strategy's own row says it fired on today's bar: an entry whose entry date is today, or a
trade closed today. The rows are rebuilt on the live price (core/analytics/live_signals.py), so this is the same
reading the Signals page shows with its "Live" tag. Wording stays neutral ("entry signal", "exit signal"): these are a
strategy's outputs, not advice.
"""

from typing import Any, Dict, List

MAX_NAMES = 4


def display_name(sid: str, row: Dict[str, Any]) -> str:
    """'RELIANCE' from 'NSE:RELIANCE', without a trade-for-trade suffix like '-BE'."""
    code = sid.split(":", 1)[-1].upper()
    for suffix in ("-BE", "-BZ", "-BL", "-IL"):
        if code.endswith(suffix):
            code = code[: -len(suffix)]
    return code


def ath_events(rows: Dict[str, Dict[str, Any]], today: str) -> List[Dict[str, str]]:
    """Entry and exit calls that fired today, from signal rows keyed by instrument id."""
    out: List[Dict[str, str]] = []
    for sid, row in rows.items():
        ath = row.get("ath") or {}
        name = display_name(sid, row)
        call = ath.get("call") or {}
        if ath.get("state") == "IN_POSITION" and call.get("entry_date") == today and ath.get("entry_date") == today:
            out.append({"sid": sid, "name": name, "side": "buy", "date": today})
        for e in ath.get("exits") or []:
            if e.get("exit_date") == today:
                out.append({"sid": sid, "name": name, "side": "sell", "date": today})
                break
    return sorted(out, key=lambda e: (e["side"] != "buy", e["name"]))


def event_key(kind: str, e: Dict[str, str]) -> str:
    """The unique key of a call for one person: kind ('h' holdings, 's' Stage 2), day, side and stock."""
    return f"{kind}|{e['date']}|{e['side']}|{e['sid']}"


def _word(side: str) -> str:
    return "entry" if side == "buy" else "exit"


def _list(events: List[Dict[str, str]]) -> str:
    named = [f"{e['name']} ({_word(e['side'])})" for e in events[:MAX_NAMES]]
    more = len(events) - MAX_NAMES
    return ", ".join(named) + (f" and {more} more" if more > 0 else "")


def call_message(kind: str, events: List[Dict[str, str]]) -> Dict[str, str]:
    """Title, bodies and the page to open for a group of calls fired at the same refresh."""
    holdings = kind == "h"
    n = len(events)
    if n == 1:
        e = events[0]
        what = "entry signal" if e["side"] == "buy" else "exit signal (closed under the 200-DMA)"
        body = f"{e['name']}: {what} on today's live price."
    else:
        body = f"{n} calls: {_list(events)}."
    return {
        "title": "ATH strategy · your holdings" if holdings else "ATH strategy · Stage 2 list",
        "body": body + " A strategy signal, not advice.",
        "body_masked": body + " A strategy signal, not advice.",
        # what the lock screen shows: no stock names
        "public_title": "ATH strategy update",
        "route": "holdings" if holdings else "signals",
    }


def reversed_message(events: List[Dict[str, str]]) -> Dict[str, str]:
    n = len(events)
    body = (
        f"{events[0]['name']}: the {_word(events[0]['side'])} signal from earlier today did not hold at the close."
        if n == 1
        else f"{n} calls from earlier today did not hold at the close: {_list(events)}."
    )
    return {
        "title": "ATH strategy · did not hold at the close",
        "body": body,
        "body_masked": body,
        "public_title": "ATH strategy update",
        "route": "signals",
    }
