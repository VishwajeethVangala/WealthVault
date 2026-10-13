"""Beta, volatility and drawdown must come out right on series where the answer is known."""

import random
from datetime import date, timedelta

from core.analytics.portfolio_risk import beta_of, daily_returns, portfolio_risk


def _series(returns, start=100.0, first=date(2025, 1, 1)):
    out, p, d = [], start, first
    out.append({"date": d.isoformat(), "close": p})
    for r in returns:
        d += timedelta(days=1)
        p *= 1 + r
        out.append({"date": d.isoformat(), "close": p})
    return out


def _bench(n=300, seed=3):
    random.seed(seed)
    return [random.uniform(-0.01, 0.011) for _ in range(n)]


def test_a_stock_moving_twice_the_index_has_beta_two():
    b = _bench()
    stock = [2 * r for r in b]
    assert abs(beta_of(stock, b) - 2.0) < 1e-9


def test_portfolio_that_is_the_index_has_beta_one_and_no_extra_volatility():
    b = _bench()
    bench = _series(b, 20000)
    out = portfolio_risk([("INDEXFUND", 100000.0, _series(b, 50))], bench)
    assert out["beta"] == 1.0 and out["correlation"] == 1.0
    assert abs(out["volatility_pct"] - out["benchmark_volatility_pct"]) < 0.1
    assert out["coverage_pct"] == 100 and out["stocks"] == 1


def test_weights_blend_betas_and_drawdown_is_measured_from_the_peak():
    b = _bench()
    bench = _series(b, 20000)
    out = portfolio_risk([("HIGH", 50000.0, _series([2 * r for r in b], 100)), ("LOW", 50000.0, _series([0.0 for _ in b], 100))], bench)
    assert abs(out["beta"] - 1.0) < 0.05  # half at beta 2, half at beta 0
    assert out["max_drawdown_pct"] <= 0 and out["worst_day_pct"] < 0 < out["best_day_pct"]
    assert out["high_beta"][0]["name"] == "HIGH"


def test_too_little_history_gives_no_numbers_rather_than_noise():
    b = _bench(30)
    assert portfolio_risk([("X", 1000.0, _series(b))], _series(b, 20000)) is None
    assert daily_returns([{"date": "2025-01-01", "close": 10}]) == {}
