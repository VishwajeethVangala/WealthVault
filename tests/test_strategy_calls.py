"""The call extractors must report the bar the engine flagged, not recompute anything."""

from types import SimpleNamespace as NS

from core.analytics.strategy_calls import ath_buy_call


def _bar(date, close=100.0, **kw):
    base = dict(date=date, open=close, close=close, sma_fast=None, sma_slow=None, ut_stop=None, stop_level=None, buy=False, dma=None, ath=None)
    base.update(kw)
    return NS(**base)


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


def test_exit_calls_report_closed_trades_newest_first():
    from core.analytics.strategy_calls import exit_calls

    trades = [
        NS(entry_date="2026-01-05", entry_price=90.0, exit_date="2026-01-20", exit_price=85.0, exit_reason="200-DMA BREAK", pnl_pct=-5.5, bars_held=10),
        NS(entry_date="2026-02-02", entry_price=100.0, exit_date="2026-02-06", exit_price=108.0, exit_reason="200-DMA BREAK", pnl_pct=8.0, bars_held=4),
        NS(entry_date="2026-02-07", entry_price=109.0, exit_date=None, exit_price=None, exit_reason="OPEN", pnl_pct=1.0, bars_held=0),
    ]
    out = exit_calls(NS(series=[], trades=trades))
    assert [e["exit_date"] for e in out] == ["2026-02-06", "2026-01-20"]  # open trade excluded, newest first
    assert out[0]["signal_date"] == "2026-02-06" and out[0]["exit_price"] == 108.0
