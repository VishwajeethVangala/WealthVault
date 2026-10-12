"""Describe the latest BUY call of a strategy run, with the facts that justify it.

Both strategies already flag the signal bar in their per-bar series. This reads that flag and collects what was
true on the bar: for Swing V2.1 the UT Bot trigger, the trend filter and the protective stop; for the ATH
breakout the prior all-time high that was broken, the setup window and the 200-DMA. Nothing here recomputes a
signal, it only reports the bar the engine already chose, so the explanation always matches the call.
"""

from typing import Any, Dict, Optional


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Percent by which a is above b."""
    if a is None or not b:
        return None
    return round((a / b - 1.0) * 100.0, 2)


def swing_buy_call(result: Any, slope_lookback: int) -> Optional[Dict[str, Any]]:
    """Latest Swing V2.1 buy: signalled on a close, filled at the next open (or still queued)."""
    series = result.series
    idx = max((i for i, b in enumerate(series) if b.buy), default=None)
    if idx is None:
        return None
    sig = series[idx]
    slow_then = series[idx - slope_lookback].sma_slow if idx >= slope_lookback else None
    call: Dict[str, Any] = {
        "signal_date": sig.date,
        "signal_close": sig.close,
        "ut_stop": sig.ut_stop,
        "sma_fast": sig.sma_fast,
        "sma_slow": sig.sma_slow,
        "above_slow_pct": _pct(sig.close, sig.sma_slow),
        "fast_over_slow_pct": _pct(sig.sma_fast, sig.sma_slow),
        "slow_slope_pct": _pct(sig.sma_slow, slow_then),
        "slope_lookback": slope_lookback,
        "queued": idx == len(series) - 1,
        "entry_date": None,
        "entry_price": None,
        "stop": None,
    }
    if not call["queued"]:
        fill = series[idx + 1]
        trade = next((t for t in result.trades if t.entry_date == fill.date), None)
        call["entry_date"] = fill.date
        call["entry_price"] = trade.entry_price if trade else fill.open
        call["stop"] = fill.stop_level
        call["stop_pct"] = _pct(call["stop"], call["entry_price"]) if call["stop"] else None
    return call


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
