"""The live-signals endpoints say WHY rows are not live, so the page can show the right chip."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.api.routers import stage2


def _call(kite_authenticated: bool, live_rows: dict, cached: dict):
    kite = SimpleNamespace(is_authenticated=kite_authenticated)
    snapshot = (("2026-10-13", {"rows": [{"nsecode": "ABB"}]}), None)
    with patch.object(stage2, "ScreenerSnapshotRepository") as snaps, patch.object(stage2, "SignalCacheRepository") as cache, patch.object(
        stage2, "get_user_kite_client", AsyncMock(return_value=kite)
    ), patch.object(stage2, "live_india_rows", AsyncMock(return_value=live_rows)):
        snaps.return_value.latest_two = AsyncMock(return_value=snapshot)
        cache.return_value.get_many = AsyncMock(return_value=cached)
        return asyncio.run(stage2.get_stage2_live_signals(current_user_id="u1"))


def test_rows_present_is_live():
    out = _call(True, {"NSE:ABB": {"live": True}}, {"NSE:ABB": {}})
    assert out["live"] is True and out["reason"] == "ok"


def test_lapsed_kite_login_is_reported():
    out = _call(False, {}, {"NSE:ABB": {}})
    assert out["live"] is False and out["reason"] == "login"


def test_logged_in_but_nothing_to_price_is_no_prices():
    out = _call(True, {}, {"NSE:ABB": {}})
    assert out["live"] is False and out["reason"] == "no_prices"


def test_nothing_computed_yet_is_no_signals():
    out = _call(True, {}, {})
    assert out["live"] is False and out["reason"] == "no_signals"
