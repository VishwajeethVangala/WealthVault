"""200-DMA -> ATH Breakout strategy engine.

Python port of the TradingView Pine v5 strategy
"Below 200DMA -> ATH Break -> Hold till 200DMA Break":

- Setup: the stock closed below its 200-DMA within the last 200 trading days.
- Entry: the close breaks above the prior all-time high (highest high of all
  earlier bars), while flat and on/after the backtest start date. Buys
  floor(capital_per_trade / close) shares.
- Exit: a close below the 200-DMA.

Execution mirrors Pine's process_orders_on_close=true: entries and exits fill at
the close of the signal bar. Capital per trade is fixed (no compounding) and
commission defaults to zero, as in the script.

The all-time high is only as good as the history supplied: callers should pass
the instrument's full daily history (see HistoricalDataService.get_full_daily_history).
"""

import math
from typing import Any, Dict, List, Optional

from core.analytics.backtest import buy_hold_curve, summarize_backtest
from core.analytics.momentum import sma_series
from core.models import (
    AthBreakoutBar,
    AthBreakoutParams,
    AthBreakoutResult,
    AthBreakoutStatus,
    StrategyTrade,
)

EXIT_DMA_BREAK = "200DMA BREAK"
NO_BELOW_DMA = 10000  # Pine: barsSinceBelow200 when no close below the DMA has occurred yet


def _date(candle: Dict[str, Any]) -> str:
    return str(candle["date"])[:10]


def _round(val: Optional[float], digits: int = 2) -> Optional[float]:
    return None if val is None else round(val, digits)


def run_ath_breakout_strategy(
    instrument: str,
    candles: List[Dict[str, Any]],
    params: Optional[AthBreakoutParams] = None,
    name: Optional[str] = None,
    partial_bar_excluded: bool = False,
) -> AthBreakoutResult:
    """Run the strategy over daily candles (sorted oldest-first, ideally full history)."""
    p = params or AthBreakoutParams()
    n = len(candles)
    if n <= p.dma_length:
        raise ValueError(f"Need more than {p.dma_length} daily candles for the {p.dma_length}-DMA; got {n}.")

    dates = [_date(c) for c in candles]
    closes = [float(c["close"]) for c in candles]
    highs = [float(c.get("high") or c["close"]) for c in candles]
    dma = sma_series(closes, p.dma_length)
    comm = p.commission_pct / 100.0

    ath_series: List[Optional[float]] = [None] * n
    prior_ath_series: List[Optional[float]] = [None] * n
    bars_since_below: List[int] = [NO_BELOW_DMA] * n
    in_window = [False] * n
    buy_marks = [False] * n
    sell_marks = [False] * n
    in_position = [False] * n
    equity = [p.initial_capital] * n
    trades: List[StrategyTrade] = []

    ath: Optional[float] = None
    last_below: Optional[int] = None
    cash = p.initial_capital
    qty = 0
    entry_price = 0.0
    entry_cost = 0.0
    entry_idx = -1

    for i in range(n):
        prior_ath = ath
        ath = highs[i] if ath is None else max(ath, highs[i])
        ath_series[i] = ath
        prior_ath_series[i] = prior_ath

        if dma[i] is not None and closes[i] < dma[i]:
            last_below = i
        bars_since_below[i] = i - last_below if last_below is not None else NO_BELOW_DMA
        in_window[i] = bars_since_below[i] <= p.window_bars

        pos = qty
        ath_break = prior_ath is not None and closes[i] > prior_ath
        entry = dates[i] >= p.start_date and in_window[i] and ath_break and pos == 0
        exit_ = pos > 0 and dma[i] is not None and closes[i] < dma[i]

        # process_orders_on_close: both fill at this bar's close
        if entry:
            buy_marks[i] = True
            shares = math.floor(p.capital_per_trade / closes[i])
            if shares > 0:
                entry_cost = shares * closes[i] * (1 + comm)
                cash -= entry_cost
                qty, entry_price, entry_idx = shares, closes[i], i
        if exit_:
            sell_marks[i] = True
            proceeds = qty * closes[i] * (1 - comm)
            pnl = proceeds - entry_cost
            trades.append(
                StrategyTrade(
                    entry_date=dates[entry_idx],
                    entry_price=round(entry_price, 2),
                    exit_date=dates[i],
                    exit_price=round(closes[i], 2),
                    exit_reason=EXIT_DMA_BREAK,
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

    # Tradable window: on/after the start date and once the DMA exists
    first_dated = next((i for i, d in enumerate(dates) if d >= p.start_date), last)
    start = max(first_dated, p.dma_length - 1)

    bh_curve, buy_hold_return = buy_hold_curve(closes, start, p.initial_capital, comm)
    stats = summarize_backtest(
        dates=dates,
        equity=equity,
        in_position=in_position,
        trades=trades,
        start=start,
        initial_capital=p.initial_capital,
        buy_hold_return_pct=buy_hold_return,
        signal_exit_reason=EXIT_DMA_BREAK,
    )

    # --- Current status on the latest bar ---
    close_last = closes[last]
    dma_last = dma[last]
    prior_ath_last = prior_ath_series[last]
    since = bars_since_below[last]
    days_since = None if since == NO_BELOW_DMA else since
    window_left = p.window_bars - since if in_window[last] else None
    pct_to_ath = (prior_ath_last / close_last - 1) * 100 if prior_ath_last else None
    pct_above_dma = (close_last / dma_last - 1) * 100 if dma_last else None

    common = dict(
        close=round(close_last, 2),
        dma=_round(dma_last),
        prior_ath=_round(prior_ath_last),
        pct_to_ath=_round(pct_to_ath),
        days_since_below_dma=days_since,
        in_window=in_window[last],
        window_days_left=window_left,
        pct_above_dma=_round(pct_above_dma),
    )

    if qty > 0:
        open_trade = trades[-1]
        if buy_marks[last]:
            headline = "Bought at the latest close"
            detail = (
                f"Close ₹{close_last:,.2f} broke the prior all-time high of ₹{prior_ath_last:,.2f} within "
                f"{since} trading days of a close below the {p.dma_length}-DMA."
            )
        else:
            headline = "In position"
            detail = (
                f"Long since {open_trade.entry_date} at ₹{open_trade.entry_price:,.2f}. "
                f"Holding until a close below the {p.dma_length}-DMA (now ₹{dma_last:,.2f}, "
                f"{pct_above_dma:+.2f}% away)."
            )
        status = AthBreakoutStatus(
            state="IN_POSITION",
            headline=headline,
            detail=detail,
            last_signal="BUY" if buy_marks[last] else None,
            entry_date=open_trade.entry_date,
            entry_price=open_trade.entry_price,
            unrealized_pct=open_trade.pnl_pct,
            bars_held=open_trade.bars_held,
            **common,
        )
    else:
        if sell_marks[last]:
            headline = "Sold at the latest close"
            detail = f"Close ₹{close_last:,.2f} fell below the {p.dma_length}-DMA (₹{dma_last:,.2f})."
        elif in_window[last]:
            headline = "Setup active: watching for an ATH breakout"
            detail = (
                f"Last close below the {p.dma_length}-DMA was {since} trading days ago, so an ATH break counts for "
                f"{window_left} more days. Entry needs a close above ₹{prior_ath_last:,.2f} "
                f"({pct_to_ath:+.2f}% from here)."
            )
        else:
            headline = "No setup"
            detail = (
                f"No close below the {p.dma_length}-DMA in the last {p.window_bars} trading days"
                + (f" (last one {since} days ago)" if days_since is not None else "")
                + ". A new setup starts the next time it closes below the DMA."
            )
        status = AthBreakoutStatus(
            state="FLAT",
            headline=headline,
            detail=detail,
            last_signal="SELL" if sell_marks[last] else None,
            **common,
        )

    series = [
        AthBreakoutBar(
            date=dates[i],
            high=round(highs[i], 2),
            close=round(closes[i], 2),
            dma=_round(dma[i]),
            ath=_round(ath_series[i]),
            in_window=in_window[i],
            buy=buy_marks[i],
            sell=sell_marks[i],
            equity=round(equity[i], 2),
            buy_hold=round(bh_curve[i], 2),
        )
        for i in range(start, n)
    ]

    return AthBreakoutResult(
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
