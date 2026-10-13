"""Risk figures for the Indian equity part of a portfolio, from stored daily candles.

The portfolio is replayed at today's weights: each day's return is the weighted average of the day's returns of
the holdings that traded that day (weights renormalised over those). That answers "how would today's mix have
behaved", which is what beta, volatility and drawdown are meant to describe. Nothing here is a forecast.
"""

import math
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional, Tuple

TRADING_DAYS = 252
MIN_DAYS = 60


def daily_returns(candles: List[Dict[str, Any]]) -> Dict[str, float]:
    """{date: close-to-close return} for consecutive candles."""
    out: Dict[str, float] = {}
    prev: Optional[float] = None
    for c in candles:
        close = float(c["close"])
        if prev and prev > 0:
            out[str(c["date"])[:10]] = close / prev - 1.0
        prev = close
    return out


def _cov(a: List[float], b: List[float]) -> float:
    ma, mb = mean(a), mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / len(a)


def beta_of(stock: List[float], bench: List[float]) -> Optional[float]:
    var = pstdev(bench) ** 2 if len(bench) > 1 else 0.0
    return _cov(stock, bench) / var if var > 0 else None


def portfolio_risk(
    positions: List[Tuple[str, float, List[Dict[str, Any]]]],
    bench_candles: List[Dict[str, Any]],
    lookback: int = TRADING_DAYS,
) -> Optional[Dict[str, Any]]:
    """`positions` are (name, value in INR, candles). Returns None when there is too little history."""
    bench = daily_returns(bench_candles)
    rets = [(name, value, daily_returns(c)) for name, value, c in positions if value > 0 and len(c) > 2]
    if not bench or not rets:
        return None
    total_value = sum(v for _, v, _ in positions if v > 0)
    dates = sorted(bench)[-lookback:]

    port: List[float] = []
    bmk: List[float] = []
    used_dates: List[str] = []
    for d in dates:
        present = [(v, r[d]) for _, v, r in rets if d in r]
        weight = sum(v for v, _ in present)
        # a day counts only if holdings worth most of the covered value traded; otherwise it would be a thin sample
        if weight <= 0 or weight < 0.5 * sum(v for _, v, _ in rets):
            continue
        port.append(sum(v * x for v, x in present) / weight)
        bmk.append(bench[d])
        used_dates.append(d)
    if len(port) < MIN_DAYS:
        return None

    daily_sd = pstdev(port)
    bench_sd = pstdev(bmk)
    beta = _cov(port, bmk) / (bench_sd**2) if bench_sd > 0 else None
    corr = _cov(port, bmk) / (daily_sd * bench_sd) if daily_sd > 0 and bench_sd > 0 else None

    peak, worst_dd, level = 1.0, 0.0, 1.0
    for r in port:
        level *= 1 + r
        peak = max(peak, level)
        worst_dd = min(worst_dd, level / peak - 1)
    downside = pstdev([min(r, 0.0) for r in port])

    per_stock: List[Dict[str, Any]] = []
    for name, value, r in rets:
        common = [d for d in used_dates if d in r]
        if len(common) < MIN_DAYS:
            continue
        b = beta_of([r[d] for d in common], [bench[d] for d in common])
        if b is not None:
            per_stock.append({"name": name, "weight": value / total_value * 100, "beta": round(b, 2), "contribution": round(value / total_value * b, 3)})
    per_stock.sort(key=lambda s: s["contribution"], reverse=True)

    covered = sum(v for _, v, _ in rets)
    return {
        "days": len(port),
        "since": used_dates[0],
        "until": used_dates[-1],
        "beta": None if beta is None else round(beta, 2),
        "correlation": None if corr is None else round(corr, 2),
        "volatility_pct": round(daily_sd * math.sqrt(TRADING_DAYS) * 100, 1),
        "benchmark_volatility_pct": round(bench_sd * math.sqrt(TRADING_DAYS) * 100, 1),
        "downside_volatility_pct": round(downside * math.sqrt(TRADING_DAYS) * 100, 1),
        "var95_1d_pct": round(1.645 * daily_sd * 100, 2),
        "max_drawdown_pct": round(worst_dd * 100, 1),
        "best_day_pct": round(max(port) * 100, 2),
        "worst_day_pct": round(min(port) * 100, 2),
        "positive_days_pct": round(sum(1 for r in port if r > 0) / len(port) * 100, 0),
        "coverage_pct": round(covered / total_value * 100, 0) if total_value else 0,
        "stocks": len(rets),
        "high_beta": per_stock[:4],
    }
