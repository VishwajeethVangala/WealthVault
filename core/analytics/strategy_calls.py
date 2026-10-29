"""Describe the latest BUY call of a strategy run, with the facts that justify it.

The strategy already flags the signal bar in its per-bar series. This reads that flag and collects what was
true on the bar: for the ATH
breakout the prior all-time high that was broken, the setup window and the 200-DMA. Nothing here recomputes a
signal, it only reports the bar the engine already chose, so the explanation always matches the call.
"""

from typing import Any, Dict, List, Optional


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Percent by which a is above b."""
    if a is None or not b:
        return None
    return round((a / b - 1.0) * 100.0, 2)


def ath_buy_call(result: Any, window_bars: int) -> Optional[Dict[str, Any]]:
    """Latest ATH-breakout buy: the close broke the prior all-time high and the order fills at that close."""
    series = result.series
    idx = max((i for i, b in enumerate(series) if b.buy), default=None)
    if idx is None or idx == 0:
        return None
    bar = series[idx]
    prior_ath = series[idx - 1].ath
    # trading days since the last close below the 200-DMA; the break only counts inside the window after it
    below = next((idx - j for j in range(idx - 1, -1, -1) if series[j].dma and series[j].close < series[j].dma), None)
    trade = next((t for t in result.trades if t.entry_date == bar.date), None)
    return {
        "signal_date": bar.date,
        "entry_date": bar.date,
        "entry_price": trade.entry_price if trade else bar.close,
        "close": bar.close,
        "prior_ath": prior_ath,
        "above_ath_pct": _pct(bar.close, prior_ath),
        "days_since_below_dma": below,
        "window_bars": window_bars,
        "dma": bar.dma,
        "above_dma_pct": _pct(bar.close, bar.dma),
        "queued": False,
    }


def exit_calls(result: Any, keep: int = 4) -> List[Dict[str, Any]]:
    """The most recent closed trades, newest first: where the strategy said SELL and at what price.

    The ATH breakout sells at the close that broke the 200-DMA.
    """
    out: List[Dict[str, Any]] = []
    for t in reversed([t for t in result.trades if t.exit_date]):
        signal_date = t.exit_date
        out.append(
            {
                "signal_date": signal_date,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "reason": t.exit_reason,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "pnl_pct": t.pnl_pct,
                "bars_held": t.bars_held,
            }
        )
        if len(out) >= keep:
            break
    return out
