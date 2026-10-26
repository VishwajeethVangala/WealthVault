"""One-pass signal bundle for a stock: momentum verdict, Swing V2.1 status and ATH-breakout status.

The three analyses share the same daily candles, so the history is fetched once per stock and sliced
for each. Each section fails independently (for example a recent listing has too little history for
the 200-day rules) and reports why instead of failing the whole row.
"""

import asyncio
import json
import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.analytics import analyze_momentum
from core.analytics.ath_breakout_strategy import run_ath_breakout_strategy
from core.analytics.strategy_calls import ath_buy_call, exit_calls, swing_buy_call, swing_pending_sell
from core.analytics.swing_strategy import run_swing_strategy
from core.market_data.candle_store import get_india_candles
from core.market_data.indmoney_market import get_user_indmoney_client
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.history import (
    MAX_LOOKBACK_DAYS,
    InstrumentNotFoundError,
    NIFTY_50_SYMBOL,
    NIFTY_50_TOKEN,
    drop_incomplete_today,
    get_history_service,
    normalize_symbol,
)
from core.models import AthBreakoutParams, SwingStrategyParams
from storage.tables.repositories import SignalCacheRepository

logger = logging.getLogger("wealthvault.analytics.equity_signals")

MIN_MOMENTUM_CANDLES = 50
MOMENTUM_LOOKBACK_DAYS = 400
SWING_YEARS = 5
STRATEGY_WARMUP_DAYS = 330
SESSIONS_KEPT = 7  # most recent sessions listed per row, for the buy and sell call windows


def _since(candles: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [c for c in candles if str(c["date"])[:10] >= cutoff]


def _no_partial(candles: List[Dict[str, Any]]):
    """US candles are only stored after the session closes, so nothing needs dropping."""
    return candles, False


def _momentum_section(instrument_id: str, instrument: Dict[str, Any], candles, benchmark, benchmark_name: str) -> Dict[str, Any]:
    recent = _since(candles, MOMENTUM_LOOKBACK_DAYS)
    if len(recent) < MIN_MOMENTUM_CANDLES:
        raise ValueError(f"Only {len(recent)} days of history")
    m = analyze_momentum(
        instrument=instrument_id,
        candles=recent,
        benchmark_candles=benchmark,
        benchmark_name=benchmark_name,
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


def _swing_section(instrument_id: str, instrument: Dict[str, Any], candles, drop_partial) -> Dict[str, Any]:
    lookback = min(MAX_LOOKBACK_DAYS, SWING_YEARS * 365 + STRATEGY_WARMUP_DAYS)
    use, partial = drop_partial(_since(candles, lookback))
    params = SwingStrategyParams()
    r = run_swing_strategy(
        instrument=instrument_id,
        candles=use,
        params=params,
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
        "call": swing_buy_call(r, params.slope_lookback),
        "exits": exit_calls(r),
        "pending_sell": swing_pending_sell(r),
    }


def _ath_section(instrument_id: str, instrument: Dict[str, Any], candles, drop_partial) -> Dict[str, Any]:
    use, partial = drop_partial(candles)
    params = AthBreakoutParams()
    r = run_ath_breakout_strategy(
        instrument=instrument_id,
        candles=use,
        params=params,
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
        "call": ath_buy_call(r, params.window_bars),
        "exits": exit_calls(r),
    }


def build_signal_row(
    instrument_id: str,
    instrument: Dict[str, Any],
    candles: List[Dict[str, Any]],
    benchmark: Optional[List[Dict[str, Any]]],
    benchmark_name: str = NIFTY_50_SYMBOL.split(":", 1)[1],
    drop_partial=drop_incomplete_today,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the signal row for one stock from candles that are already loaded."""
    row: Dict[str, Any] = {
        "instrument": instrument_id,
        "name": instrument.get("name"),
        "as_of": str(candles[-1]["date"])[:10] if candles else None,
        "history_days": len(candles),
        # the two most recent completed sessions, so pages can ask "what happened in the last 2 sessions"
        "last_sessions": [str(c["date"])[:10] for c in drop_partial(candles)[0][-SESSIONS_KEPT:]],
        "momentum": None,
        "swing": None,
        "ath": None,
        "errors": {},
    }
    if extra:
        row.update(extra)
    for key, build in (
        ("momentum", lambda: _momentum_section(instrument_id, instrument, candles, benchmark, benchmark_name)),
        ("swing", lambda: _swing_section(instrument_id, instrument, candles, drop_partial)),
        ("ath", lambda: _ath_section(instrument_id, instrument, candles, drop_partial)),
    ):
        try:
            row[key] = build()
        except ValueError as exc:
            row["errors"][key] = str(exc) or "Not enough history"
        except Exception as exc:  # one broken section must not drop the others
            logger.warning("%s signal failed for %s: %s", key, instrument_id, exc)
            row["errors"][key] = "Could not compute"
    return row


_STORED_TTL_SECONDS = 300.0
_stored: Dict[str, Dict[str, Any]] = {}
_stored_at = -_STORED_TTL_SECONDS


async def _stored_instrument(symbol: str) -> Optional[Dict[str, Any]]:
    """The instrument of a stock whose signals were computed before (token and tick size are kept on its row).

    Lets a refresh run without Kite's instrument search; the table is read once for all stocks, not per stock."""
    global _stored_at
    qualified = normalize_symbol(symbol)
    if time.monotonic() - _stored_at >= _STORED_TTL_SECONDS:
        repo = SignalCacheRepository()
        found: Dict[str, Dict[str, Any]] = {}
        for r in await repo.query_entities(user_id=repo.PARTITION):
            try:
                row = json.loads(r.get("payload") or "{}")
            except ValueError:
                continue
            if row.get("token") and row.get("instrument"):
                inst = {"id": row["instrument"], "instrument_token": row["token"], "tick_size": row.get("tick_size"), "name": row.get("name")}
                found[str(row["instrument"]).upper()] = inst
                found.setdefault(str(r.get("RowKey", "")).upper(), inst)
        _stored.clear()
        _stored.update(found)
        _stored_at = time.monotonic()
    return _stored.get(qualified.upper())


async def compute_stock_signals(client: Any, symbol: str, benchmark: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Indian stocks: fetch history from Kite once and build the full signal row.

    With Kite's login lapsed and INDmoney connected, a stock already known (token stored) is topped up from INDmoney
    instead. One never seen before needs Kite for its first full history, which is a per-stock failure, not an
    expired login."""
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
        except KiteAuthRequiredError:
            if await get_user_indmoney_client(getattr(client, "owner_id", None)) is None:
                raise
            instrument = await _stored_instrument(symbol) or {}
            if not instrument:
                raise ValueError("Needs a Kite login for its first price history")
            break
    instrument_id = str(instrument.get("id") or f"{instrument.get('exchange')}:{instrument.get('tradingsymbol')}")
    # stored finished candles, topped up from Kite when behind; the live price is folded in at read time
    candles, _meta = await get_india_candles(client, instrument)
    if not candles:
        raise ValueError("Price history unavailable")
    return build_signal_row(
        instrument_id,
        instrument,
        candles,
        benchmark,
        extra={"token": int(instrument["instrument_token"]), "tick_size": instrument.get("tick_size")},
    )


async def load_benchmark(client: Any) -> Optional[List[Dict[str, Any]]]:
    """NIFTY 50 candles for the relative-strength reading, from the same store as the stocks."""
    nifty = {"instrument_token": NIFTY_50_TOKEN, "id": NIFTY_50_SYMBOL, "tick_size": 0.05}
    candles, _meta = await get_india_candles(client, nifty)
    return _since(candles, MOMENTUM_LOOKBACK_DAYS) or None
