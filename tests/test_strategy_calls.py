"""The call extractors must report the bar the engine flagged, not recompute anything."""

from types import SimpleNamespace as NS

from core.analytics.strategy_calls import ath_buy_call, swing_buy_call


def _bar(date, close=100.0, **kw):
    base = dict(date=date, open=close, close=close, sma_fast=None, sma_slow=None, ut_stop=None, stop_level=None, buy=False, dma=None, ath=None)
    base.update(kw)
    return NS(**base)


def test_swing_buy_filled_at_next_open_uses_the_trade_price_and_stop():
    series = [_bar(f"2026-01-{d:02d}", 100 + d, sma_slow=50.0 + d) for d in range(1, 30)]
    series[24] = _bar("2026-01-25", 125.0, buy=True, ut_stop=120.0, sma_fast=110.0, sma_slow=75.0)
    series[25] = _bar("2026-01-26", 126.0, open=124.0, stop_level=108.0)
    result = NS(series=series, trades=[NS(entry_date="2026-01-26", entry_price=124.2)])

    call = swing_buy_call(result, slope_lookback=20)

    assert call["signal_date"] == "2026-01-25" and call["signal_close"] == 125.0
    assert call["entry_date"] == "2026-01-26" and call["entry_price"] == 124.2  # the trade's price, slippage included
    assert call["stop"] == 108.0 and not call["queued"]
    assert call["ut_stop"] == 120.0 and call["above_slow_pct"] == round((125 / 75 - 1) * 100, 2)
    assert call["slow_slope_pct"] is not None


def test_swing_buy_on_the_last_bar_is_queued_with_no_fill_yet():
    series = [_bar("2026-01-01"), _bar("2026-01-02", 130.0, buy=True, ut_stop=125.0)]
    call = swing_buy_call(NS(series=series, trades=[]), slope_lookback=20)
    assert call["queued"] and call["entry_date"] is None and call["entry_price"] is None


def test_swing_without_any_buy_has_no_call():
    assert swing_buy_call(NS(series=[_bar("2026-01-01")], trades=[]), 20) is None


def test_ath_buy_reports_the_broken_high_and_days_since_the_dma_break():
    series = [
        _bar("2026-01-01", 90.0, dma=100.0, ath=120.0),  # closed below the DMA
        _bar("2026-01-02", 95.0, dma=99.0, ath=120.0),  # still below
        _bar("2026-01-03", 105.0, dma=99.0, ath=120.0),
        _bar("2026-01-04", 125.0, dma=99.0, ath=125.0, buy=True),  # breaks the 120 high
    ]
    call = ath_buy_call(NS(series=series, trades=[NS(entry_date="2026-01-04", entry_price=125.0)]), window_bars=200)

    assert call["prior_ath"] == 120.0
    assert call["above_ath_pct"] == round((125 / 120 - 1) * 100, 2)
    assert call["days_since_below_dma"] == 2  # last close under the DMA was two bars earlier
    assert call["entry_date"] == "2026-01-04" and call["entry_price"] == 125.0


def test_exit_calls_report_the_signal_bar_and_the_fill_for_a_swing_sell():
    from core.analytics.strategy_calls import exit_calls, swing_pending_sell

    series = [_bar(f"2026-02-{d:02d}") for d in range(1, 8)]
    trades = [
        NS(entry_date="2026-01-05", entry_price=90.0, exit_date="2026-01-20", exit_price=85.0, exit_reason="ATR STOP", pnl_pct=-5.5, bars_held=10),
        NS(entry_date="2026-02-02", entry_price=100.0, exit_date="2026-02-06", exit_price=108.0, exit_reason="UT + EMA20 SELL", pnl_pct=8.0, bars_held=4),
        NS(entry_date="2026-02-07", entry_price=109.0, exit_date=None, exit_price=None, exit_reason="OPEN", pnl_pct=1.0, bars_held=0),
    ]
    out = exit_calls(NS(series=series, trades=trades))
    assert [e["exit_date"] for e in out] == ["2026-02-06", "2026-01-20"]  # open trade excluded, newest first
    assert out[0]["signal_date"] == "2026-02-05" and out[0]["exit_price"] == 108.0  # sold at the next open
    assert out[1]["signal_date"] == "2026-01-20"  # a stop fills intrabar on its own day

    queued = swing_pending_sell(NS(series=series, status=NS(pending_order="SELL", entry_date="2026-02-02", entry_price=100.0)))
    assert queued["signal_date"] == "2026-02-07"
    assert swing_pending_sell(NS(series=series, status=NS(pending_order=None))) is None
