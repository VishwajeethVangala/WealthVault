"""One-pass signal bundle for a stock: momentum verdict, Swing V2.1 status and ATH-breakout status.

The three analyses share the same daily candles, so the history is fetched once per stock and sliced
for each. Each section fails independently (for example a recent listing has too little history for
the 200-day rules) and reports why instead of failing the whole row.
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.analytics import analyze_momentum
from core.analytics.ath_breakout_strategy import run_ath_breakout_strategy
from core.analytics.swing_strategy import run_swing_strategy
from core.market_data.history import (
    MAX_LOOKBACK_DAYS,
    InstrumentNotFoundError,
    NIFTY_50_SYMBOL,
    drop_incomplete_today,
    get_history_service,
)
from core.models import AthBreakoutParams, SwingStrategyParams

logger = logging.getLogger("wealthvault.analytics.equity_signals")

MIN_MOMENTUM_CANDLES = 50
MOMENTUM_LOOKBACK_DAYS = 400
SWING_YEARS = 5
STRATEGY_WARMUP_DAYS = 330


def _since(candles: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [c for c in candles if str(c["date"])[:10] >= cutoff]


def _momentum_section(instrument_id: str, instrument: Dict[str, Any], candles, benchmark) -> Dict[str, Any]:
    recent = _since(candles, MOMENTUM_LOOKBACK_DAYS)
    if len(recent) < MIN_MOMENTUM_CANDLES:
        raise ValueError(f"Only {len(recent)} days of history")
    m = analyze_momentum(
        instrument=instrument_id,
        candles=recent,
        benchmark_candles=benchmark,
        benchmark_name=NIFTY_50_SYMBOL.split(":", 1)[1],
        name=instrument.get("name"),
    )
    hi, lo = m.high_52w, m.low_52w
    range_pos = ((m.last_price - lo) / (hi - lo) * 100) if hi is not None and lo is not None and hi > lo else None
    return {
        "verdict": m.trend_verdict,
        "score": m.trend_score,
        "max": m.trend_max_score,
        "last_price": m.last_price,
        "high_52w": hi,
        "low_52w": lo,
        "pct_from_52w_high": m.pct_from_52w_high,
        "range_pos": range_pos,
        "checks": [{"label": c.label, "passed": c.passed} for c in m.trend_checks],
    }


def _swing_section(instrument_id: str, instrument: Dict[str, Any], candles) -> Dict[str, Any]:
    lookback = min(MAX_LOOKBACK_DAYS, SWING_YEARS * 365 + STRATEGY_WARMUP_DAYS)
    use, partial = drop_incomplete_today(_since(candles, lookback))
    r = run_swing_strategy(
        instrument=instrument_id,
        candles=use,
        params=SwingStrategyParams(),
        tick_size=float(instrument.get("tick_size") or 0.05),
        name=instrument.get("name"),
        partial_bar_excluded=partial,
    )
    s = r.status
    return {
        "state": s.state,
        "headline": s.headline,
        "detail": s.detail,
        "pending_order": s.pending_order,
        "entry_date": s.entry_date,
        "entry_price": s.entry_price,
        "stop_price": s.stop_price,
        "bars_held": s.bars_held,
        "regime_bullish": s.regime_bullish,
        "as_of": r.as_of,
    }


def _ath_section(instrument_id: str, instrument: Dict[str, Any], candles) -> Dict[str, Any]:
    use, partial = drop_incomplete_today(candles)
    r = run_ath_breakout_strategy(
        instrument=instrument_id,
        candles=use,
        params=AthBreakoutParams(),
        name=instrument.get("name"),
        partial_bar_excluded=partial,
    )
    s = r.status
    return {
        "state": s.state,
        "headline": s.headline,
        "detail": s.detail,
        "last_signal": s.last_signal,
        "entry_date": s.entry_date,
        "entry_price": s.entry_price,
        "bars_held": s.bars_held,
        "in_window": s.in_window,
        "window_days_left": s.window_days_left,
        "pct_to_ath": s.pct_to_ath,
        "pct_above_dma": s.pct_above_dma,
        "as_of": r.as_of,
    }


async def compute_stock_signals(client: Any, symbol: str, benchmark: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Fetch history once and build the full signal row for one stock."""
    history = get_history_service()
    instrument: Dict[str, Any] = {}
    for attempt in range(3):
        try:
            instrument = await history.resolve_instrument(client, symbol)
            break
        except InstrumentNotFoundError:
            # Kite's search occasionally comes back empty under load; a stock that exists resolves on retry
            if attempt == 2:
                raise
            await asyncio.sleep(1.0 * (attempt + 1))
    token = int(instrument["instrument_token"])
    instrument_id = str(instrument.get("id") or f"{instrument.get('exchange')}:{instrument.get('tradingsymbol')}")
    candles = await history.get_full_daily_history(client, token, earliest=instrument.get("listing_date") or None)

    row: Dict[str, Any] = {
        "instrument": instrument_id,
        "name": instrument.get("name"),
        "as_of": str(candles[-1]["date"])[:10] if candles else None,
        "history_days": len(candles),
        "momentum": None,
        "swing": None,
        "ath": None,
        "errors": {},
    }
    for key, build in (
        ("momentum", lambda: _momentum_section(instrument_id, instrument, candles, benchmark)),
        ("swing", lambda: _swing_section(instrument_id, instrument, candles)),
        ("ath", lambda: _ath_section(instrument_id, instrument, candles)),
    ):
        try:
            row[key] = build()
        except ValueError as exc:
            row["errors"][key] = str(exc) or "Not enough history"
        except Exception as exc:  # one broken section must not drop the others
            logger.warning("%s signal failed for %s: %s", key, symbol, exc)
            row["errors"][key] = "Could not compute"
    return row
