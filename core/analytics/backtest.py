"""Shared backtest statistics for strategy engines."""

from datetime import date
from typing import List, Optional, Sequence, Tuple

from core.models import StrategyStats, StrategyTrade


def buy_hold_curve(
    closes: Sequence[float],
    start: int,
    initial_capital: float,
    commission: float = 0.0,
) -> Tuple[List[float], float]:
    """Equity of buying at `closes[start]` and holding, plus the total return (%) to the last close."""
    cost = closes[start] * (1 + commission)
    curve = [initial_capital * c / cost for c in closes]
    total = (closes[-1] * (1 - commission) / cost - 1) * 100
    return curve, total


def summarize_backtest(
    dates: Sequence[str],
    equity: Sequence[float],
    in_position: Sequence[bool],
    trades: List[StrategyTrade],
    start: int,
    initial_capital: float,
    buy_hold_return_pct: float,
    signal_exit_reason: str,
    stop_exit_reason: Optional[str] = None,
) -> StrategyStats:
    """Performance summary over bars `start..end` (dates as YYYY-MM-DD)."""
    n = len(equity)
    last = n - 1
    final_equity = equity[last]

    years = max((date.fromisoformat(dates[last]) - date.fromisoformat(dates[start])).days / 365.25, 1e-9)
    cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100 if final_equity > 0 else -100.0

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

    return StrategyStats(
        initial_capital=initial_capital,
        final_equity=round(final_equity, 2),
        net_profit=round(final_equity - initial_capital, 2),
        net_profit_pct=round((final_equity / initial_capital - 1) * 100, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        buy_hold_return_pct=round(buy_hold_return_pct, 2),
        total_trades=len(closed),
        open_trade=bool(trades and trades[-1].is_open),
        win_rate_pct=round(len(wins) / len(closed) * 100, 1) if closed else None,
        avg_win_pct=round(sum(t.pnl_pct for t in wins) / len(wins), 2) if wins else None,
        avg_loss_pct=round(sum(t.pnl_pct for t in losses) / len(losses), 2) if losses else None,
        profit_factor=round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        avg_bars_held=round(sum(t.bars_held for t in closed) / len(closed), 1) if closed else None,
        exposure_pct=round(sum(in_position[start:]) / (n - start) * 100, 1),
        signal_exits=sum(1 for t in closed if t.exit_reason == signal_exit_reason),
        stop_exits=sum(1 for t in closed if stop_exit_reason and t.exit_reason == stop_exit_reason),
    )
