"""SuperAI Magic Trend Strategy Engine.

Python port of the TradingView Pine Script "SuperAI Magic Trend [Fixed Sells]":
- Trend indicator: Supertrend(factor=3.0, atrPeriod=10).
  Direction < 0 is Bullish (Green cloud / support line).
  Direction > 0 is Bearish (Red cloud / resistance line).
- Filters:
  - ADX(14) > threshold (default 20.0): filters out sideways consolidation.
  - Volume > Volume SMA(20): ensures above-average institutional volume.
- Asymmetric Logic:
  - BUY (Hard to enter): Supertrend is bullish, within max_bars_after_flip of the flip,
    ADX > threshold, and Volume > Volume SMA. Only one buy per bullish cycle.
  - EXIT (Fast to exit): Supertrend flips to bearish (direction > 0). Instant risk cut,
    no filters required.
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.analytics.backtest import buy_hold_curve, summarize_backtest
from core.analytics.momentum import sma_series
from core.models import (
    StrategyStats,
    StrategyTrade,
    SupertrendBar,
    SupertrendParams,
    SupertrendResult,
    SupertrendStatus,
)

EXIT_SUPERTREND_BREAK = "Supertrend Bearish Flip"


def _date(candle: Dict[str, Any]) -> str:
    return str(candle["date"])[:10]


def _round(val: Optional[float], digits: int = 2) -> Optional[float]:
    return None if val is None else round(val, digits)


def _wilder_rma(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Wilder's Running Moving Average (Pine's ta.rma)."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period:
        return out
    # Seed with SMA of the first `period` values
    s = sum(values[:period])
    out[period - 1] = s / period
    prev = out[period - 1]
    for i in range(period, n):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def compute_supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    factor: float = 3.0,
) -> Tuple[List[Optional[float]], List[int]]:
    """Compute Pine-compatible Supertrend and Direction.

    Returns:
        (supertrend_values, direction_values)
        direction == -1 for Bullish (support), 1 for Bearish (resistance).
    """
    n = len(closes)
    st_out: List[Optional[float]] = [None] * n
    dir_out: List[int] = [1] * n

    if n < period:
        return st_out, dir_out

    # True range
    tr: List[float] = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    atr = _wilder_rma(tr, period)

    upper = 0.0
    lower = 0.0
    direction = 1

    for i in range(period - 1, n):
        curr_atr = atr[i]
        if curr_atr is None:
            continue

        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + factor * curr_atr
        basic_lower = hl2 - factor * curr_atr

        if i == period - 1:
            upper = basic_upper
            lower = basic_lower
            direction = -1 if closes[i] > upper else 1
            st_out[i] = lower if direction == -1 else upper
            dir_out[i] = direction
            continue

        prev_upper = upper
        prev_lower = lower
        prev_close = closes[i - 1]
        prev_dir = direction

        lower = basic_lower if (basic_lower > prev_lower or prev_close < prev_lower) else prev_lower
        upper = basic_upper if (basic_upper < prev_upper or prev_close > prev_upper) else prev_upper

        if prev_dir == 1:
            direction = -1 if closes[i] > prev_upper else 1
        else:
            direction = 1 if closes[i] < prev_lower else -1

        st_out[i] = lower if direction == -1 else upper
        dir_out[i] = direction

    return st_out, dir_out


def compute_adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    di_length: int = 14,
    adx_length: int = 14,
) -> List[Optional[float]]:
    """Compute ADX matching TradingView's ta.dmi(di_length, adx_length)."""
    n = len(closes)
    adx_out: List[Optional[float]] = [None] * n
    if n < max(di_length, adx_length) * 2:
        return adx_out

    tr: List[float] = [0.0] * n
    plus_dm: List[float] = [0.0] * n
    minus_dm: List[float] = [0.0] * n

    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    tr_rma = _wilder_rma(tr, di_length)
    plus_rma = _wilder_rma(plus_dm, di_length)
    minus_rma = _wilder_rma(minus_dm, di_length)

    dx: List[float] = [0.0] * n
    for i in range(n):
        t = tr_rma[i]
        p = plus_rma[i]
        m = minus_rma[i]
        if t is not None and p is not None and m is not None and t > 0:
            plus_di = 100.0 * p / t
            minus_di = 100.0 * m / t
            di_sum = plus_di + minus_di
            dx[i] = 100.0 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0.0

    # ADX is the RMA of DX
    # Find first valid index for DX
    start_dx = di_length - 1
    if start_dx < n:
        dx_valid = dx[start_dx:]
        adx_valid = _wilder_rma(dx_valid, adx_length)
        for j, val in enumerate(adx_valid):
            idx = start_dx + j
            if idx < n:
                adx_out[idx] = val

    return adx_out


def run_supertrend_strategy(
    instrument: str,
    candles: List[Dict[str, Any]],
    params: Optional[SupertrendParams] = None,
    name: Optional[str] = None,
    partial_bar_excluded: bool = False,
) -> SupertrendResult:
    """Run the SuperAI Magic Trend strategy over daily candles."""
    p = params or SupertrendParams()
    n = len(candles)
    warmup_needed = max(p.atr_period, p.vol_length, 30)
    if n <= warmup_needed:
        raise ValueError(
            f"Need more than {warmup_needed} daily candles for Supertrend analysis; got {n}."
        )

    dates = [_date(c) for c in candles]
    opens = [float(c.get("open") or c["close"]) for c in candles]
    closes = [float(c["close"]) for c in candles]
    highs = [float(c.get("high") or c["close"]) for c in candles]
    lows = [float(c.get("low") or c["close"]) for c in candles]
    volumes = [float(c.get("volume") or 0.0) for c in candles]

    st_series, dir_series = compute_supertrend(highs, lows, closes, period=p.atr_period, factor=p.factor)
    adx_series = compute_adx(highs, lows, closes, 14, 14)
    vol_sma_series = sma_series(volumes, p.vol_length)
    comm = p.commission_pct / 100.0

    buy_marks = [False] * n
    sell_marks = [False] * n
    in_position = [False] * n
    equity = [p.initial_capital] * n
    trades: List[StrategyTrade] = []

    cash = p.initial_capital
    qty = 0
    entry_price = 0.0
    entry_cost = 0.0
    entry_idx = -1
    has_bought_in_cycle = False
    flip_idx: Optional[int] = None

    for i in range(1, n):
        curr_dir = dir_series[i]
        prev_dir = dir_series[i - 1]

        # Check for direction flips
        flipped_bullish = curr_dir < 0 and prev_dir >= 0
        flipped_bearish = curr_dir > 0 and prev_dir <= 0

        if flipped_bullish:
            flip_idx = i
            has_bought_in_cycle = False
        elif curr_dir > 0:
            flip_idx = None
            has_bought_in_cycle = False

        # Entry logic
        pass_adx = not p.use_adx_filter or (
            adx_series[i] is not None and adx_series[i] >= p.adx_threshold
        )
        pass_vol = not p.use_vol_filter or (
            vol_sma_series[i] is not None and volumes[i] > vol_sma_series[i]
        )

        in_entry_window = False
        if curr_dir < 0 and flip_idx is not None:
            bars_since_flip = i - flip_idx
            in_entry_window = bars_since_flip < p.max_bars_after_flip

        can_buy = (
            dates[i] >= p.start_date
            and curr_dir < 0
            and not has_bought_in_cycle
            and in_entry_window
            and pass_adx
            and pass_vol
            and qty == 0
        )

        # Exit logic: Asymmetric (instant exit on bearish flip)
        can_exit = qty > 0 and (flipped_bearish or curr_dir > 0)

        if can_buy:
            buy_marks[i] = True
            has_bought_in_cycle = True
            shares = math.floor(p.capital_per_trade / closes[i])
            if shares > 0:
                entry_cost = shares * closes[i] * (1 + comm)
                cash -= entry_cost
                qty, entry_price, entry_idx = shares, closes[i], i

        elif can_exit:
            sell_marks[i] = True
            proceeds = qty * closes[i] * (1 - comm)
            pnl = proceeds - entry_cost
            trades.append(
                StrategyTrade(
                    entry_date=dates[entry_idx],
                    entry_price=round(entry_price, 2),
                    exit_date=dates[i],
                    exit_price=round(closes[i], 2),
                    exit_reason=EXIT_SUPERTREND_BREAK,
                    quantity=qty,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl / entry_cost * 100, 2) if entry_cost else 0.0,
                    bars_held=i - entry_idx,
                    is_open=False,
                )
            )
            cash += proceeds
            qty = 0

        in_position[i] = qty > 0
        equity[i] = cash + qty * closes[i]

    last = n - 1
    if qty > 0:
        unrealized = qty * closes[last] * (1 - comm) - entry_cost
        trades.append(
            StrategyTrade(
                entry_date=dates[entry_idx],
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

    # Tradable window
    first_dated = next((i for i, d in enumerate(dates) if d >= p.start_date), last)
    start = max(first_dated, warmup_needed)

    bh_curve, buy_hold_return = buy_hold_curve(closes, start, p.initial_capital, comm)
    stats = summarize_backtest(
        dates=dates,
        equity=equity,
        in_position=in_position,
        trades=trades,
        start=start,
        initial_capital=p.initial_capital,
        buy_hold_return_pct=buy_hold_return,
        signal_exit_reason=EXIT_SUPERTREND_BREAK,
    )

    # Status on latest bar
    last_dir = dir_series[last]
    last_st = st_series[last] or closes[last]
    last_adx = adx_series[last]
    last_vol = volumes[last]
    last_vol_sma = vol_sma_series[last]
    vol_ratio = (last_vol / last_vol_sma) if (last_vol_sma and last_vol_sma > 0) else None

    # Bars since flip
    bars_since_last_flip = (last - flip_idx) if (last_dir < 0 and flip_idx is not None) else None

    adx_display = f"{last_adx:.1f}" if last_adx is not None else "N/A"
    vol_display = f"{vol_ratio:.1f}x" if vol_ratio is not None else "N/A"

    common_status = dict(
        close=round(closes[last], 2),
        supertrend=round(last_st, 2),
        direction=last_dir,
        adx=_round(last_adx, 1),
        volume=last_vol,
        vol_sma=_round(last_vol_sma, 0),
        volume_ratio=_round(vol_ratio, 2),
        bars_since_flip=bars_since_last_flip,
    )

    if qty > 0:
        open_trade = trades[-1]
        if buy_marks[last]:
            headline = "BUY Signal Confirmed at Latest Close"
            detail = (
                f"Close ₹{closes[last]:,.2f} passed Supertrend support (₹{last_st:,.2f}), "
                f"ADX={adx_display} (>={p.adx_threshold}), and Volume={vol_display} average."
            )
        else:
            headline = "In Position (Bullish Trend)"
            detail = (
                f"Long since {open_trade.entry_date} at ₹{open_trade.entry_price:,.2f}. "
                f"Trailing stop at Supertrend support ₹{last_st:,.2f} "
                f"({((closes[last] / last_st) - 1) * 100:+.2f}% cushion)."
            )
        status = SupertrendStatus(
            state="IN_POSITION",
            headline=headline,
            detail=detail,
            last_signal="BUY" if buy_marks[last] else None,
            entry_date=open_trade.entry_date,
            entry_price=open_trade.entry_price,
            unrealized_pct=open_trade.pnl_pct,
            bars_held=open_trade.bars_held,
            **common_status,
        )
    else:
        if sell_marks[last]:
            headline = "EXIT Signal at Latest Close"
            detail = f"Supertrend broke red at ₹{last_st:,.2f}. Trend reversed to bearish."
            last_sig = "SELL"
        elif last_dir < 0:
            if has_bought_in_cycle:
                headline = "Cycle Trade Completed (Watching)"
                detail = "Already took a trade in this bullish cycle. Awaiting next reset."
                last_sig = None
            else:
                headline = "Bullish Cloud (Awaiting Filter Confirmation)"
                detail = (
                    f"Supertrend is green at ₹{last_st:,.2f} ({bars_since_last_flip} days into flip). "
                    f"Awaiting ADX >= {p.adx_threshold} (currently {adx_display}) "
                    f"and Volume > 20 SMA (currently {vol_display})."
                )
                last_sig = None
        else:
            headline = "Bearish Trend / No Setup"
            detail = f"Price is below Supertrend resistance ₹{last_st:,.2f}. Standing aside in cash."
            last_sig = None

        status = SupertrendStatus(
            state="FLAT",
            headline=headline,
            detail=detail,
            last_signal=last_sig,
            **common_status,
        )

    series = [
        SupertrendBar(
            date=dates[i],
            open=round(opens[i], 2),
            high=round(highs[i], 2),
            low=round(lows[i], 2),
            close=round(closes[i], 2),
            volume=volumes[i],
            supertrend=round(st_series[i] or closes[i], 2),
            direction=dir_series[i],
            adx=_round(adx_series[i], 1),
            vol_sma=_round(vol_sma_series[i], 0),
            buy=buy_marks[i],
            sell=sell_marks[i],
            equity=round(equity[i], 2),
            buy_hold=round(bh_curve[i], 2),
        )
        for i in range(start, n)
    ]

    return SupertrendResult(
        instrument=instrument,
        name=name,
        as_of=dates[last],
        params=p,
        history_start=dates[0],
        test_start=dates[start],
        test_end=dates[last],
        bars_tested=n - start,
        partial_bar_excluded=partial_bar_excluded,
        status=status,
        stats=stats,
        trades=trades,
        series=series,
    )
