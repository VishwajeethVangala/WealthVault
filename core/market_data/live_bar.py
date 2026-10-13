"""Treat the live price as today's daily candle.

The strategies and the momentum report run on daily candles. During the session the exchange's candle for
today is still forming, so instead of waiting for the close the live quote is folded into it: today's close
is the live price, its high and low stretch to include it. After the close the live price is the close, so
the same call gives the final bar. Nothing is stored; the bar is rebuilt from the quote on each request.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
ET = ZoneInfo("America/New_York")


def india_today(now: Optional[datetime] = None) -> Optional[str]:
    """Today's NSE date once the session has opened (09:15 IST, Mon-Fri); None before that or on weekends."""
    n = (now or datetime.now(IST)).astimezone(IST)
    if n.weekday() >= 5 or (n.hour, n.minute) < (9, 15):
        return None
    return n.strftime("%Y-%m-%d")


def us_today(now: Optional[datetime] = None) -> Optional[str]:
    """Today's US date once the regular session has opened (09:30 ET, Mon-Fri); None before that or on weekends."""
    n = (now or datetime.now(ET)).astimezone(ET)
    if n.weekday() >= 5 or (n.hour, n.minute) < (9, 30):
        return None
    return n.strftime("%Y-%m-%d")


def apply_live_quote(
    candles: List[Dict[str, Any]],
    today: Optional[str],
    price: Optional[float],
    open_: float = 0.0,
    high: float = 0.0,
    low: float = 0.0,
    volume: float = 0.0,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Return the candles with today's bar built from the live quote, and whether that was done.

    The input list is not modified. A quote that shows no trading today (a holiday echoing the last close)
    is ignored so the series does not gain a flat phantom bar.
    """
    if not candles or not today or not price or price <= 0:
        return candles, False
    last = candles[-1]
    last_date = str(last["date"])[:10]
    if last_date > today:
        return candles, False

    if last_date == today:
        bar = dict(last)
        bar["close"] = price
        bar["high"] = max(float(last["high"]), price, high or 0.0)
        bar["low"] = min(float(last["low"]), price, low or float("inf"))
        return candles[:-1] + [bar], True

    if open_ > 0:
        traded = (open_, high, low, price) != (last["open"], last["high"], last["low"], last["close"])
    else:
        traded = price != last["close"]
    if not traded:
        return candles, False
    start = open_ if open_ > 0 else price
    bar = {
        "date": today,
        "open": start,
        "high": max(start, price, high or 0.0),
        "low": min(start, price, low or float("inf")),
        "close": price,
        "volume": volume or 0.0,
    }
    return candles + [bar], True
