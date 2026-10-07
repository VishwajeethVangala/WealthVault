"""Stock Momentum Analytics Engine.

Pure functions computing momentum measures from a series of daily candles:
- Trend / moving averages (primary verdict): 20/50/200-DMA, golden/death cross,
  200-DMA slope, MACD (12, 26, 9).
- Price momentum: 1M / 3M / 6M / 12M rate of change and 12-1 momentum.
- Risk-adjusted momentum: return divided by annualized volatility (6M, 12M).
- RSI (14, Wilder smoothing).
- 52-week high / low proximity.
- Relative strength versus a benchmark index (e.g. NIFTY 50).

All percentages are returned as percent values (12.5 means 12.5%).
"""

import math
from typing import Any, Dict, List, Optional, Sequence

from core.models import MomentumAnalysis, MomentumSeriesPoint, TrendCheck

# Trading-day lookbacks
DAYS_1M = 21
DAYS_3M = 63
DAYS_6M = 126
DAYS_12M = 252
TRADING_DAYS_PER_YEAR = 252
SLOPE_LOOKBACK = 20
CHART_POINTS = 252


def sma_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Simple moving average aligned to input (None until enough data)."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema_series(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Exponential moving average seeded with the SMA of the first `period` values."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * alpha + prev * (1 - alpha)
        out[i] = prev
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    """Latest MACD line, signal line, and histogram."""
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow) if f is not None and s is not None]
    signal_line = ema_series(macd_line, signal)
    if not macd_line or signal_line[-1] is None:
        return {"macd": None, "signal": None, "histogram": None}
    return {
        "macd": macd_line[-1],
        "signal": signal_line[-1],
        "histogram": macd_line[-1] - signal_line[-1],
    }


def rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index using Wilder's smoothing."""
    if len(closes) <= period:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(c, 0.0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0.0) for c in changes[:period]) / period
    for c in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(c, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-c, 0.0)) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def rate_of_change(closes: Sequence[float], days: int, skip_recent: int = 0) -> Optional[float]:
    """Percent return over `days` trading days, optionally ending `skip_recent` days ago."""
    end = len(closes) - 1 - skip_recent
    start = len(closes) - 1 - days
    if start < 0 or end <= start or closes[start] <= 0:
        return None
    return (closes[end] / closes[start] - 1.0) * 100.0


def annualized_volatility(closes: Sequence[float], days: int) -> Optional[float]:
    """Annualized standard deviation of daily log returns over the last `days` days, in percent."""
    if len(closes) <= days:
        return None
    window = closes[-(days + 1):]
    returns = [math.log(window[i] / window[i - 1]) for i in range(1, len(window)) if window[i - 1] > 0 and window[i] > 0]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0


def last_cross(fast: Sequence[Optional[float]], slow: Sequence[Optional[float]]) -> Dict[str, Optional[Any]]:
    """Current fast/slow MA relationship and trading days since it last flipped."""
    diffs = [(i, f - s) for i, (f, s) in enumerate(zip(fast, slow)) if f is not None and s is not None]
    if not diffs:
        return {"state": None, "days_since": None}
    last_idx, last_diff = diffs[-1]
    state = "golden" if last_diff > 0 else "death"
    for (i, d), (_, prev_d) in zip(reversed(diffs), reversed(diffs[:-1])):
        if (d > 0) != (prev_d > 0):
            return {"state": state, "days_since": last_idx - i}
    return {"state": state, "days_since": None}


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1.0) * 100.0


def _round(val: Optional[float], digits: int = 2) -> Optional[float]:
    return None if val is None else round(val, digits)


def _ratio(ret: Optional[float], vol: Optional[float]) -> Optional[float]:
    if ret is None or vol is None or vol == 0:
        return None
    return ret / vol


TREND_VERDICTS = {
    5: "Strong Uptrend",
    4: "Uptrend",
    3: "Neutral",
    2: "Neutral",
    1: "Downtrend",
    0: "Strong Downtrend",
}


def analyze_momentum(
    instrument: str,
    candles: List[Dict[str, Any]],
    benchmark_candles: Optional[List[Dict[str, Any]]] = None,
    benchmark_name: str = "NIFTY 50",
    name: Optional[str] = None,
) -> MomentumAnalysis:
    """Compute the full momentum report for one instrument.

    Args:
        instrument: Exchange-qualified symbol (e.g. 'NSE:INFY').
        candles: Daily candles sorted oldest-first with keys date, close, and optionally high/low.
        benchmark_candles: Daily candles of the benchmark index for relative strength.
        benchmark_name: Display name of the benchmark.
        name: Company / instrument display name.
    """
    if len(candles) < 2:
        raise ValueError("Not enough price history to compute momentum.")

    closes = [float(c["close"]) for c in candles]
    highs = [float(c.get("high") or c["close"]) for c in candles]
    lows = [float(c.get("low") or c["close"]) for c in candles]
    last_price = closes[-1]

    sma20 = sma_series(closes, 20)
    sma50 = sma_series(closes, 50)
    sma200 = sma_series(closes, 200)
    s20, s50, s200 = sma20[-1], sma50[-1], sma200[-1]
    s200_prev = sma200[-1 - SLOPE_LOOKBACK] if len(sma200) > SLOPE_LOOKBACK else None
    sma200_slope = _pct(s200, s200_prev)
    cross = last_cross(sma50, sma200)
    macd_vals = macd(closes)

    # --- Trend checklist (primary verdict) ---
    checks: List[TrendCheck] = []

    def add_check(key: str, label: str, passed: Optional[bool], detail: str) -> None:
        if passed is not None:
            checks.append(TrendCheck(key=key, label=label, passed=passed, detail=detail))

    add_check(
        "above_50dma",
        "Price above 50-DMA",
        None if s50 is None else last_price > s50,
        f"{_pct(last_price, s50):+.2f}% vs 50-DMA" if s50 else "",
    )
    add_check(
        "above_200dma",
        "Price above 200-DMA",
        None if s200 is None else last_price > s200,
        f"{_pct(last_price, s200):+.2f}% vs 200-DMA" if s200 else "",
    )
    add_check(
        "golden_cross",
        "50-DMA above 200-DMA",
        None if cross["state"] is None else cross["state"] == "golden",
        (
            f"{'Golden' if cross['state'] == 'golden' else 'Death'} cross"
            + (f", {cross['days_since']} trading days ago" if cross["days_since"] is not None else "")
        )
        if cross["state"]
        else "",
    )
    add_check(
        "rising_200dma",
        "200-DMA rising",
        None if sma200_slope is None else sma200_slope > 0,
        f"{sma200_slope:+.2f}% over {SLOPE_LOOKBACK} trading days" if sma200_slope is not None else "",
    )
    add_check(
        "macd_bullish",
        "MACD above signal line",
        None if macd_vals["histogram"] is None else macd_vals["histogram"] > 0,
        f"Histogram {macd_vals['histogram']:+.2f}" if macd_vals["histogram"] is not None else "",
    )

    trend_score = sum(1 for c in checks if c.passed)
    trend_max = len(checks)
    # Scale to a 0-5 verdict when some checks were unavailable (short history)
    scaled = round(trend_score * 5 / trend_max) if trend_max else 0
    verdict = TREND_VERDICTS[scaled] if trend_max else "Insufficient Data"

    # --- Price momentum ---
    returns = {
        "1M": _round(rate_of_change(closes, DAYS_1M)),
        "3M": _round(rate_of_change(closes, DAYS_3M)),
        "6M": _round(rate_of_change(closes, DAYS_6M)),
        "12M": _round(rate_of_change(closes, DAYS_12M)),
        "12-1": _round(rate_of_change(closes, DAYS_12M, skip_recent=DAYS_1M)),
    }

    vol_6m = annualized_volatility(closes, DAYS_6M)
    vol_12m = annualized_volatility(closes, DAYS_12M)
    risk_adj_6m = _ratio(rate_of_change(closes, DAYS_6M), vol_6m)
    risk_adj_12m = _ratio(rate_of_change(closes, DAYS_12M), vol_12m)

    # --- 52-week range ---
    window = min(DAYS_12M, len(closes))
    high_52w = max(highs[-window:])
    low_52w = min(lows[-window:])

    # --- Relative strength vs benchmark (aligned by date) ---
    relative_strength: Dict[str, Optional[float]] = {}
    if benchmark_candles:
        bench_by_date = {str(c["date"])[:10]: float(c["close"]) for c in benchmark_candles}
        aligned = [(closes[i], bench_by_date[str(c["date"])[:10]]) for i, c in enumerate(candles) if str(c["date"])[:10] in bench_by_date]
        stock_aligned = [a for a, _ in aligned]
        bench_aligned = [b for _, b in aligned]
        for label, days in (("1M", DAYS_1M), ("3M", DAYS_3M), ("6M", DAYS_6M), ("12M", DAYS_12M)):
            s_ret = rate_of_change(stock_aligned, days)
            b_ret = rate_of_change(bench_aligned, days)
            relative_strength[label] = _round(s_ret - b_ret) if s_ret is not None and b_ret is not None else None

    # --- Chart series (last year) ---
    start = max(0, len(candles) - CHART_POINTS)
    series = [
        MomentumSeriesPoint(
            date=str(candles[i]["date"])[:10],
            close=round(closes[i], 2),
            sma50=_round(sma50[i]),
            sma200=_round(sma200[i]),
        )
        for i in range(start, len(candles))
    ]

    rsi_val = rsi(closes)

    return MomentumAnalysis(
        instrument=instrument,
        name=name,
        as_of=str(candles[-1]["date"])[:10],
        last_price=round(last_price, 2),
        candles_used=len(candles),
        trend_score=trend_score,
        trend_max_score=trend_max,
        trend_verdict=verdict,
        trend_checks=checks,
        sma_20=_round(s20),
        sma_50=_round(s50),
        sma_200=_round(s200),
        pct_from_sma50=_round(_pct(last_price, s50)),
        pct_from_sma200=_round(_pct(last_price, s200)),
        sma200_slope_pct=_round(sma200_slope),
        cross_state=cross["state"],
        days_since_cross=cross["days_since"],
        macd=_round(macd_vals["macd"]),
        macd_signal=_round(macd_vals["signal"]),
        macd_histogram=_round(macd_vals["histogram"]),
        returns=returns,
        volatility_6m=_round(vol_6m),
        volatility_12m=_round(vol_12m),
        risk_adjusted_6m=_round(risk_adj_6m),
        risk_adjusted_12m=_round(risk_adj_12m),
        rsi_14=_round(rsi_val),
        high_52w=round(high_52w, 2),
        low_52w=round(low_52w, 2),
        pct_from_52w_high=_round(_pct(last_price, high_52w)),
        pct_from_52w_low=_round(_pct(last_price, low_52w)),
        benchmark=benchmark_name,
        relative_strength=relative_strength,
        series=series,
    )
