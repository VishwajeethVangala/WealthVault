"""Mutual funds are valued at the latest NAV AMFI has published, not at the (possibly days old) price Coin sends.

The scenario is the real one: on 26 Oct Coin priced UTI Silver ETF FoF at 26.065 (the 21 Oct NAV) while 23 Oct's
published NAV was 24.5344."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.market_data import mf_nav
from core.models import AssetClass, Holding

ISIN = "INF789F1AYL4"
SERIES = [("23-10-2026", 24.5344), ("22-10-2026", 25.3626), ("21-10-2026", 26.065), ("19-10-2026", 26.416)]


def run(coro):
    return asyncio.run(coro)


def fund(isin=ISIN, qty=274.642, avg=19.2969, price=26.065, **kw):
    return Holding(
        holding_id="h" + str(isin), owner_id="o", connection_id="conn_zerodha_live", instrument_symbol="UTI SILVER ETF FUND OF FUND - DIRECT PLAN",
        asset_class=AssetClass.MUTUAL_FUND, quantity=qty, average_price=avg, current_price=price, current_value=round(qty * price, 2),
        pnl=round(qty * (price - avg), 2), isin=isin, data_freshness="cached", **kw,
    )


def navs(mapping=None, series=None, history_error=None):
    """Patch the two NAV sources: ISIN -> scheme code, and the NAV history of a scheme."""
    mapping = {ISIN: "151731"} if mapping is None else mapping

    async def isin_map(http):
        return mapping

    async def history(http, code):
        if history_error:
            raise history_error
        return SERIES if series is None else series

    return patch.multiple(mf_nav, _isin_map=isin_map, _history=history)


def test_a_fund_is_valued_at_the_latest_published_nav():
    with navs():
        h = run(mf_nav.apply_latest_nav([fund()]))[0]
    assert h.current_price == 24.5344
    assert h.current_value == round(274.642 * 24.5344, 2)  # 6,738.20, not 7,159 at the stale 26.065
    assert h.pnl == round(h.current_value - 274.642 * 19.2969, 2)
    assert h.data_freshness == "live"
    assert h.last_price_updated_at == "2026-10-23"  # the NAV's own date, so a page can say what it is


def test_the_day_change_is_the_latest_nav_against_the_one_before_it():
    with navs():
        h = run(mf_nav.apply_latest_nav([fund()]))[0]
    pct = (24.5344 / 25.3626 - 1) * 100
    assert h.day_change_percentage == round(pct, 2)  # -3.27%
    assert h.day_pnl == round(h.current_value - 274.642 * 25.3626, 2)  # the units' value lost since the previous NAV
    assert h.day_pnl < 0


def test_the_whole_portfolio_total_moves_to_the_latest_nav():
    funds = [fund(), fund(isin="INF000B", qty=100, avg=10.0, price=12.0)]
    with navs(mapping={ISIN: "1", "INF000B": "2"}, series=SERIES):
        out = run(mf_nav.apply_latest_nav(funds))
    assert out[0].current_value == round(274.642 * 24.5344, 2)
    assert abs(24.5344 / 12.0 - 1) > mf_nav.MAX_NAV_GAP
    assert out[1].current_price == 12.0  # a published NAV twice the broker's price is a wrong match: the broker's stays
    assert out[1].current_value == 1200.0


def test_applying_it_twice_changes_nothing_more():
    with navs():
        once = run(mf_nav.apply_latest_nav([fund()]))[0].model_dump()
        twice = run(mf_nav.apply_latest_nav([fund()]))
        again = run(mf_nav.apply_latest_nav(twice))[0].model_dump()
    assert once == again


def test_a_fund_without_an_isin_or_a_scheme_match_keeps_the_brokers_price():
    stale = fund(isin=None)
    with navs():
        assert run(mf_nav.apply_latest_nav([stale]))[0].current_price == 26.065
    with navs(mapping={}):
        assert run(mf_nav.apply_latest_nav([fund()]))[0].current_price == 26.065


def test_when_the_nav_sources_fail_the_brokers_price_stays_and_nothing_raises():
    with navs(history_error=RuntimeError("down")):
        h = run(mf_nav.apply_latest_nav([fund()]))[0]
    assert (h.current_price, h.current_value, h.data_freshness) == (26.065, round(274.642 * 26.065, 2), "cached")

    async def broken(http):
        raise RuntimeError("AMFI is down")

    with patch.object(mf_nav, "_isin_map", broken):
        assert run(mf_nav.apply_latest_nav([fund()]))[0].current_price == 26.065


def test_a_nav_nowhere_near_the_brokers_price_is_not_taken_for_it():
    wrong_scheme = [("23-10-2026", 1500.0), ("22-10-2026", 1490.0)]
    with navs(series=wrong_scheme):
        h = run(mf_nav.apply_latest_nav([fund()]))[0]
    assert h.current_price == 26.065


def test_a_single_published_nav_still_values_the_fund_but_gives_no_day_change():
    with navs(series=[("23-10-2026", 24.5344)]):
        h = run(mf_nav.apply_latest_nav([fund()]))[0]
    assert h.current_price == 24.5344 and h.day_pnl is None


def test_only_mutual_funds_with_units_are_touched():
    equity = Holding(holding_id="e", owner_id="o", connection_id="c", instrument_symbol="INFY", asset_class=AssetClass.EQUITY, quantity=5, average_price=1, current_price=2, current_value=10, pnl=5, isin=ISIN)
    empty = fund(qty=0)
    with navs():
        out = run(mf_nav.apply_latest_nav([equity, empty]))
    assert out[0].current_price == 2 and out[1].current_price == 26.065


def test_mf_values_falls_back_to_the_day_change_from_the_brokers_nav():
    # the history has the broker's NAV and the one before, but the latest NAV step is skipped when it is far off
    with navs(series=[("23-10-2026", 1500.0), ("21-10-2026", 26.065), ("19-10-2026", 26.416)]):
        h = run(mf_nav.apply_mf_values([fund()]))[0]
    assert h.current_price == 26.065  # not revalued
    assert h.day_change_percentage == round((26.065 / 26.416 - 1) * 100, 2)  # but measured from its own NAV


def test_nav_dates_parse():
    assert mf_nav._nav_date("23-10-2026") == "2026-10-23"
    assert mf_nav._nav_date("garbage") is None


class FakeResp:
    def __init__(self, text="", status=200, data=None):
        self._text, self.status, self._data = text, status, data

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *e):
        return False


class FakeHttp:
    def __init__(self, resp):
        self.resp, self.calls = resp, 0

    def get(self, url, **k):
        self.calls += 1
        return self.resp


def reset_caches():
    mf_nav._amfi = None
    mf_nav._amfi_failed_at = -mf_nav.FAILURE_BACKOFF
    mf_nav._navs.clear()
    mf_nav._failed.clear()


def test_a_failed_amfi_download_is_not_retried_on_every_poll():
    reset_caches()
    http = FakeHttp(FakeResp(status=503))
    for _ in range(4):
        try:
            run(mf_nav._isin_map(http))
        except RuntimeError:
            pass
    assert http.calls == 1  # the next three polls waited out the backoff
    reset_caches()


def test_an_older_amfi_list_is_kept_when_a_refresh_fails():
    reset_caches()
    mf_nav._amfi = (time.monotonic() - mf_nav.AMFI_TTL - 1, {ISIN: "151731"})  # expired, but better than nothing
    assert run(mf_nav._isin_map(FakeHttp(FakeResp(status=500)))) == {ISIN: "151731"}
    reset_caches()


def test_simultaneous_reads_share_one_amfi_download():
    reset_caches()
    text = "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n151731;INF789F1AYL4;;UTI Silver;24.5344;23-Oct-2026\n"
    http = FakeHttp(FakeResp(text=text))

    async def many():
        return await asyncio.gather(*(mf_nav._isin_map(http) for _ in range(6)))

    results = run(many())
    assert http.calls == 1 and all(r == {ISIN: "151731"} for r in results)
    reset_caches()


def test_the_last_known_navs_are_used_when_a_refresh_fails():
    reset_caches()
    mf_nav._navs["151731"] = (time.monotonic() - mf_nav.NAV_TTL - 1, [("23-10-2026", 24.5344)])
    assert run(mf_nav._history(FakeHttp(FakeResp(status=500)), "151731")) == [("23-10-2026", 24.5344)]
    reset_caches()


def test_the_holdings_route_returns_funds_at_the_latest_nav():
    from apps.api.routers import portfolio

    stored = [fund()]
    repo = SimpleNamespace(get_holdings=AsyncMock(return_value=stored))
    svc = SimpleNamespace(enrich_holdings_with_live_quotes=AsyncMock(side_effect=lambda hs, client=None: (hs, "live")))
    with navs(), patch.object(portfolio, "HoldingsRepository", return_value=repo), patch.object(portfolio, "get_market_data_service", return_value=svc), \
            patch.object(portfolio, "get_user_kite_client", AsyncMock(return_value=None)), patch.object(portfolio, "overlay_indmoney_live", AsyncMock(side_effect=lambda o, hs: hs)):
        out = run(portfolio.get_portfolio_holdings(broker="all", connection_id=None, refresh_live=True, indmoney_live=False, current_user_id="o"))
    assert out[0].current_price == 24.5344
    assert out[0].current_value == round(274.642 * 24.5344, 2)
    with navs(), patch.object(portfolio, "HoldingsRepository", return_value=repo), patch.object(portfolio, "get_market_data_service", return_value=svc), \
            patch.object(portfolio, "get_user_kite_client", AsyncMock(return_value=None)):
        out = run(portfolio.get_portfolio_holdings(broker="all", connection_id=None, refresh_live=False, indmoney_live=False, current_user_id="o"))
    assert out[0].current_price == 24.5344  # also on the read that skips live quotes
