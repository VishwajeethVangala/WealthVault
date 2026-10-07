"""NSE Swing Momentum V2.1 strategy engine.

Python port of the TradingView Pine v5 strategy "NSE Swing Momentum V2.1 CLEAN":

1. Trend filter (bullish regime): close > 200-SMA, 50-SMA > 200-SMA, and the
   200-SMA above its value 20 bars ago.
2. Entry: UT Bot buy (close crosses above an ATR(10) x 1.0 trailing stop) while
   the regime is bullish and flat.
3. Exit: UT Bot sell AND close below the 20-EMA on the same bar, or a fixed
   protective stop at entry price - 2 x ATR(14) (set once, not trailed).

Execution mirrors Pine's broker emulator with process_orders_on_close=false:
signals are evaluated on the bar close and market orders fill at the next bar's
open; the protective stop is placed on the close of the fill bar and triggers
intrabar from the following bar, filling at the stop or at the open on a gap.
Commission is charged per side as a percent of trade value and slippage as a
fixed number of ticks against each fill.

Deviation from Pine: position size is whole shares bought with available cash at
the fill price (Pine sizes on the signal bar's close and may allow fractional or
over-sized fills).
"""

import math
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

from core.analytics.momentum import ema_series, sma_series
from core.models import (
    StrategyBar,
    StrategyStats,
    StrategyStatus,
    StrategyTrade,
    SwingStrategyParams,
    SwingStrategyResult,
    TrendCheck,
)

EXIT_SIGNAL = "UT + EMA20 SELL"
EXIT_STOP = "ATR STOP"


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[float]:
    """True range per bar; the first bar uses high - low (as Pine does)."""
    out: List[float] = []
    for i in range(len(closes)):
        if i == 0:
            out.append(highs[i] - lows[i])
        else:
            prev = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - prev), abs(lows[i] - prev)))
    return out


def rma_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Wilder's moving average (Pine ta.rma), seeded with the SMA of the first `period` values."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def atr_series(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> List[Optional[float]]:
    """Average True Range (Pine ta.atr)."""
    return rma_series(true_range(highs, lows, closes), period)


def ut_trailing_stop(closes: Sequence[float], atr: Sequence[Optional[float]], key: float) -> List[Optional[float]]:
    """UT Bot ATR trailing stop, matching the Pine recursion (na until ATR is available)."""
    stops: List[Optional[float]] = [None] * len(closes)
    for i, src in enumerate(closes):
        if atr[i] is None:
            continue
        loss = key * atr[i]
        prev = stops[i - 1] if i > 0 and stops[i - 1] is not None else 0.0
        src1 = closes[i - 1] if i > 0 else None
        if src1 is not None and src > prev and src1 > prev:
            stops[i] = max(prev, src - loss)
        elif src1 is not None and src < prev and src1 < prev:
            stops[i] = min(prev, src + loss)
        elif src > prev:
            stops[i] = src - loss
        else:
            stops[i] = src + loss
    return stops


def _crossover(a: Sequence[Optional[float]], b: Sequence[Optional[float]], i: int) -> bool:
    """Pine ta.crossover(a, b) at bar i."""
    if i == 0 or None in (a[i], b[i], a[i - 1], b[i - 1]):
        return False
    return a[i] > b[i] and a[i - 1] <= b[i - 1]


def _round(val: Optional[float], digits: int = 2) -> Optional[float]:
    return None if val is None else round(val, digits)


def _date(candle: Dict[str, Any]) -> str:
    return str(candle["date"])[:10]


def run_swing_strategy(
    instrument: str,
    candles: List[Dict[str, Any]],
    params: Optional[SwingStrategyParams] = None,
    tick_size: float = 0.05,
    name: Optional[str] = None,
    partial_bar_excluded: bool = False,
) -> SwingStrategyResult:
    """Run the V2.1 strategy over daily candles (sorted oldest-first) and build the full report."""
    p = params or SwingStrategyParams()
    warmup = p.slow_sma - 1 + p.slope_lookback
    if len(candles) <= warmup + 1:
        raise ValueError(
            f"Need more than {warmup + 1} daily candles for the {p.slow_sma}-SMA and its "
            f"{p.slope_lookback}-bar slope; got {len(candles)}."
        )

    closes = [float(c["close"]) for c in candles]
    opens = [float(c.get("open") or c["close"]) for c in candles]
    highs = [float(c.get("high") or c["close"]) for c in candles]
    lows = [float(c.get("low") or c["close"]) for c in candles]
    n = len(candles)

    # --- Indicators ---
    fast = sma_series(closes, p.fast_sma)
    slow = sma_series(closes, p.slow_sma)
    exit_ema = ema_series(closes, p.exit_ema)
    ut_stop = ut_trailing_stop(closes, atr_series(highs, lows, closes, p.ut_atr_period), p.ut_key)
    stop_atr = atr_series(highs, lows, closes, p.stop_atr_period)

    def regime_parts(i: int) -> Dict[str, Optional[bool]]:
        s, f = slow[i], fast[i]
        s_prev = slow[i - p.slope_lookback] if i >= p.slope_lookback else None
        return {
            "above_slow": None if s is None else closes[i] > s,
            "fast_above_slow": None if s is None or f is None else f > s,
            "slow_rising": None if s is None or s_prev is None else s > s_prev,
        }

    regime = [all(v is True for v in regime_parts(i).values()) for i in range(n)]
    ut_buy = [ut_stop[i] is not None and closes[i] > ut_stop[i] and _crossover(closes, ut_stop, i) for i in range(n)]
    ut_sell = [ut_stop[i] is not None and closes[i] < ut_stop[i] and _crossover(ut_stop, closes, i) for i in range(n)]
    confirmed_sell = [ut_sell[i] and exit_ema[i] is not None and closes[i] < exit_ema[i] for i in range(n)]

    # --- Bar-by-bar broker emulation ---
    comm = p.commission_pct / 100.0
    slip = p.slippage_ticks * tick_size
    cash = p.initial_capital
    qty = 0
    entry_price = 0.0
    entry_cost = 0.0
    entry_idx = -1
    long_stop: Optional[float] = None
    stop_active: Optional[float] = None
    pending: Optional[str] = None
    prev_pos = 0
    trades: List[StrategyTrade] = []
    equity: List[float] = [p.initial_capital] * n
    buy_marks = [False] * n
    sell_marks = [False] * n
    stop_marks = [False] * n
    stop_levels: List[Optional[float]] = [None] * n
    in_position = [False] * n

    def close_position(i: int, fill: float, reason: str) -> None:
        nonlocal cash, qty
        proceeds = qty * fill * (1 - comm)
        pnl = proceeds - entry_cost
        trades.append(
            StrategyTrade(
                entry_date=_date(candles[entry_idx]),
                entry_price=round(entry_price, 2),
                exit_date=_date(candles[i]),
                exit_price=round(fill, 2),
                exit_reason=reason,
                quantity=qty,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl / entry_cost * 100, 2) if entry_cost else 0.0,
                bars_held=i - entry_idx,
                is_open=False,
            )
        )
        cash += proceeds
        qty = 0

    for i in range(n):
        # 1. Market orders queued on the previous close fill at this bar's open
        if pending == "BUY" and qty == 0:
            fill = opens[i] + slip
            shares = math.floor(cash / (fill * (1 + comm)))
            if shares > 0:
                entry_cost = shares * fill * (1 + comm)
                cash -= entry_cost
                qty, entry_price, entry_idx = shares, fill, i
        elif pending == "SELL" and qty > 0:
            close_position(i, opens[i] - slip, EXIT_SIGNAL)
        pending = None

        # 2. Protective stop placed on an earlier close triggers intrabar (gap -> open)
        if qty > 0 and stop_active is not None and lows[i] <= stop_active:
            close_position(i, min(opens[i], stop_active) - slip, EXIT_STOP)
            stop_marks[i] = True

        # 3. Script logic on the bar close
        pos = qty
        if regime[i] and ut_buy[i] and pos == 0:
            pending = "BUY"
            buy_marks[i] = True
        if pos > 0 and prev_pos == 0:
            long_stop = entry_price - stop_atr[i] * p.stop_atr_mult if stop_atr[i] is not None else None
        if pos == 0:
            long_stop = None
        if confirmed_sell[i] and pos > 0:
            pending = "SELL"
            sell_marks[i] = True
        stop_active = long_stop if p.use_stop and pos > 0 else None
        stop_levels[i] = stop_active

        equity[i] = cash + qty * closes[i]
        in_position[i] = pos > 0
        prev_pos = pos

    last = n - 1
    if qty > 0:
        unrealized = qty * closes[last] * (1 - comm) - entry_cost
        trades.append(
            StrategyTrade(
                entry_date=_date(candles[entry_idx]),
                entry_price=round(entry_price, 2),
                exit_date=None,
                exit_price=None,
                exit_reason="OPEN",
                quantity=qty,
                pnl=round(unrealized, 2),
                pnl_pct=round(unrealized / entry_cost * 100, 2) if entry_cost else 0.0,
                bars_held=last - entry_idx,
                is_open=True,
            )
        )

    # --- Statistics over the tradable window (after indicator warm-up) ---
    start = warmup
    bh_shares_value = closes[start] * (1 + comm)
    bh_curve = [p.initial_capital * closes[i] / bh_shares_value for i in range(n)]
    buy_hold_return = (closes[last] * (1 - comm) / bh_shares_value - 1) * 100

    final_equity = equity[last]
    years = max((date.fromisoformat(_date(candles[last])) - date.fromisoformat(_date(candles[start]))).days / 365.25, 1e-9)
    cagr = ((final_equity / p.initial_capital) ** (1 / years) - 1) * 100 if final_equity > 0 else -100.0

    peak = equity[start]
    max_dd = 0.0
    for i in range(start, n):
        peak = max(peak, equity[i])
        if peak > 0:
            max_dd = min(max_dd, (equity[i] / peak - 1) * 100)

    closed = [t for t in trades if not t.is_open]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)

    stats = StrategyStats(
        initial_capital=p.initial_capital,
        final_equity=round(final_equity, 2),
        net_profit=round(final_equity - p.initial_capital, 2),
        net_profit_pct=round((final_equity / p.initial_capital - 1) * 100, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        buy_hold_return_pct=round(buy_hold_return, 2),
        total_trades=len(closed),
        open_trade=bool(trades and trades[-1].is_open),
        win_rate_pct=round(len(wins) / len(closed) * 100, 1) if closed else None,
        avg_win_pct=round(sum(t.pnl_pct for t in wins) / len(wins), 2) if wins else None,
        avg_loss_pct=round(sum(t.pnl_pct for t in losses) / len(losses), 2) if losses else None,
        profit_factor=round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        avg_bars_held=round(sum(t.bars_held for t in closed) / len(closed), 1) if closed else None,
        exposure_pct=round(sum(in_position[start:]) / (n - start) * 100, 1),
        signal_exits=sum(1 for t in closed if t.exit_reason == EXIT_SIGNAL),
        stop_exits=sum(1 for t in closed if t.exit_reason == EXIT_STOP),
    )

    # --- Current status on the latest bar ---
    parts = regime_parts(last)
    regime_checks = [
        TrendCheck(
            key="above_slow",
            label=f"Close above {p.slow_sma}-SMA",
            passed=bool(parts["above_slow"]),
            detail=f"₹{closes[last]:,.2f} vs ₹{slow[last]:,.2f}" if slow[last] else "",
        ),
        TrendCheck(
            key="fast_above_slow",
            label=f"{p.fast_sma}-SMA above {p.slow_sma}-SMA",
            passed=bool(parts["fast_above_slow"]),
            detail=f"₹{fast[last]:,.2f} vs ₹{slow[last]:,.2f}" if fast[last] and slow[last] else "",
        ),
        TrendCheck(
            key="slow_rising",
            label=f"{p.slow_sma}-SMA rising ({p.slope_lookback} bars)",
            passed=bool(parts["slow_rising"]),
            detail=(
                f"₹{slow[last]:,.2f} vs ₹{slow[last - p.slope_lookback]:,.2f}"
                if slow[last] and slow[last - p.slope_lookback]
                else ""
            ),
        ),
    ]

    ut_last = ut_stop[last]
    if qty > 0:
        open_trade = trades[-1]
        if pending == "SELL":
            headline = "SELL signal on the last close"
            detail = "UT Bot flipped down and the close is below the 20-EMA. The strategy exits at the next open."
        else:
            headline = "In position"
            stop_txt = f"protective stop ₹{long_stop:,.2f}" if p.use_stop and long_stop else "no protective stop"
            detail = (
                f"Long since {open_trade.entry_date} at ₹{open_trade.entry_price:,.2f}; {stop_txt}. "
                f"Exit needs a UT Bot flip below ₹{ut_last:,.2f} with a close under the 20-EMA (₹{exit_ema[last]:,.2f})."
            )
        status = StrategyStatus(
            state="IN_POSITION",
            headline=headline,
            detail=detail,
            regime_bullish=regime[last],
            regime_checks=regime_checks,
            pending_order=pending,
            entry_date=open_trade.entry_date,
            entry_price=open_trade.entry_price,
            stop_price=_round(long_stop) if p.use_stop else None,
            ut_stop=_round(ut_last),
            exit_ema=_round(exit_ema[last]),
            unrealized_pct=open_trade.pnl_pct,
            bars_held=open_trade.bars_held,
        )
    else:
        if pending == "BUY":
            headline = "BUY signal on the last close"
            detail = "Bullish regime and a UT Bot buy. The strategy enters at the next open."
        elif regime[last]:
            headline = "Bullish regime, waiting for entry"
            detail = (
                f"Trend filter passes. Entry needs the close to cross above the UT Bot stop (₹{ut_last:,.2f})."
                if ut_last is not None and closes[last] <= ut_last
                else "Trend filter passes, but price is already above the UT Bot stop; entry needs a fresh UT Bot buy cross."
            )
        else:
            failing = [c.label for c in regime_checks if not c.passed]
            headline = "No trade: regime not bullish"
            detail = "Waiting for the trend filter. Failing: " + "; ".join(failing) + "."
        status = StrategyStatus(
            state="FLAT",
            headline=headline,
            detail=detail,
            regime_bullish=regime[last],
            regime_checks=regime_checks,
            pending_order=pending,
            ut_stop=_round(ut_last),
            exit_ema=_round(exit_ema[last]),
        )

    # --- Chart series over the tradable window ---
    series = [
        StrategyBar(
            date=_date(candles[i]),
            open=round(opens[i], 2),
            high=round(highs[i], 2),
            low=round(lows[i], 2),
            close=round(closes[i], 2),
            sma_fast=_round(fast[i]),
            sma_slow=_round(slow[i]),
            exit_ema=_round(exit_ema[i]),
            ut_stop=_round(ut_stop[i]),
            regime=regime[i],
            buy=buy_marks[i],
            sell=sell_marks[i],
            stop_exit=stop_marks[i],
            stop_level=_round(stop_levels[i]),
            equity=round(equity[i], 2),
            buy_hold=round(bh_curve[i], 2),
        )
        for i in range(start, n)
    ]

    return SwingStrategyResult(
        instrument=instrument,
        name=name,
        as_of=_date(candles[last]),
        params=p,
        test_start=_date(candles[start]),
        test_end=_date(candles[last]),
        bars_tested=n - start,
        partial_bar_excluded=partial_bar_excluded,
        status=status,
        stats=stats,
        trades=trades,
        series=series,
    )
