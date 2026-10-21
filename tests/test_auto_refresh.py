"""The market-hours auto refresh: when it runs, whom it runs for, and when it stands down."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from apps.api import auto_refresh as ar
from apps.api.routers import stage2
from apps.api.routers.signals import Job

IST = ar.IST


def at(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST)


def test_a_trading_day_runs_from_the_open_to_the_close_every_15_minutes():
    day = at(2026, 10, 21, 0, 0).date()  # a Wednesday
    times = [t.strftime("%H:%M") for t in ar.slots(day, 15)]
    assert times[0] == "09:15" and times[-1] == "15:30"
    assert len(times) == 26
    assert "15:45" not in times and "09:00" not in times


def test_next_run_never_falls_outside_market_hours_or_on_a_weekend():
    assert ar.next_slot(at(2026, 10, 21, 8, 0), 15) == at(2026, 10, 21, 9, 15)  # before the open
    assert ar.next_slot(at(2026, 10, 21, 9, 15), 15) == at(2026, 10, 21, 9, 30)  # strictly after a run time
    assert ar.next_slot(at(2026, 10, 21, 12, 7), 15) == at(2026, 10, 21, 12, 15)
    assert ar.next_slot(at(2026, 10, 21, 15, 30, 1), 15) == at(2026, 10, 22, 9, 15)  # after the close: next morning
    assert ar.next_slot(at(2026, 10, 23, 15, 31), 15) == at(2026, 10, 26, 9, 15)  # Friday evening: Monday
    assert ar.next_slot(at(2026, 10, 24, 11, 0), 15) == at(2026, 10, 26, 9, 15)  # Saturday


def test_logged_in_kite_users_are_found_from_their_session_files(tmp_path):
    def put(name, **data):
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")

    put("kite_session_google_1__conn_zerodha_live.json", is_authenticated=True, owner_id="google_1")
    put("kite_session_google_2__conn_zerodha_live.json", is_authenticated=True)  # older file: owner from the name
    put("kite_session_google_3__conn_zerodha_live.json", is_authenticated=False, owner_id="google_3")
    put("kite_session.json", is_authenticated=True)  # the old single-user file belongs to nobody
    with patch.object(ar, "data_dir", return_value=tmp_path):
        assert ar.kite_owners() == ["google_1", "google_2"]


def _tick(live, traded=True, running=None):
    runs = []

    async def fake_run(owner, job, fresh_since=None, screener=None):
        runs.append((owner, job.trigger, fresh_since, screener))
        job.state = "done"

    stage2._jobs.clear()
    for owner in running or []:
        stage2._jobs[owner] = Job(state="running")
    read = AsyncMock(return_value=("LIST", None))
    with patch.object(ar, "_live_clients", AsyncMock(return_value=[(o, object()) for o in live])), \
            patch.object(ar, "traded_today", AsyncMock(return_value=traded)), \
            patch.object(ar, "read_screener", read), patch.object(ar, "_run_job", fake_run):
        asyncio.run(ar.run_tick(at(2026, 10, 21, 10, 0)))
    stage2._jobs.clear()
    return runs, read.await_count, dict(ar._last)


def test_each_logged_in_user_is_refreshed_once_with_one_chartink_read():
    runs, reads, last = _tick(["google_1", "google_2"])
    assert [r[0] for r in runs] == ["google_1", "google_2"]
    assert reads == 1 and all(r[3] == ("LIST", None) for r in runs)
    assert all(r[1] == "schedule" for r in runs)
    assert runs[0][2] == runs[1][2]  # one start time, so the second user's run keeps what the first computed
    assert last["outcome"] == "ran" and last["users"] == 2


def test_a_user_whose_own_refresh_is_running_is_left_alone():
    runs, _, _ = _tick(["google_1", "google_2"], running=["google_1"])
    assert [r[0] for r in runs] == ["google_2"]


def test_nothing_runs_without_a_kite_login_or_on_a_market_holiday():
    runs, reads, last = _tick([])
    assert runs == [] and reads == 0 and last["outcome"] == "skipped"
    runs, reads, last = _tick(["google_1"], traded=False)
    assert runs == [] and reads == 0 and "not trading" in last["message"]


def test_a_manual_refresh_resumes_only_after_an_interrupted_run():
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat()  # noqa: E731
    assert stage2.resume_point(None) is None
    assert stage2.resume_point(Job(state="done", started_at=iso(now - timedelta(minutes=5)), finished_at=iso(now))) is None
    interrupted = Job(state="error", started_at=iso(now - timedelta(minutes=5)), finished_at=iso(now - timedelta(minutes=1)))
    assert stage2.resume_point(interrupted) == now - timedelta(minutes=5)
    stale = Job(state="error", started_at=iso(now - timedelta(hours=3)), finished_at=iso(now - timedelta(hours=2)))
    assert stage2.resume_point(stale) is None


def test_on_in_production_off_elsewhere_unless_set():
    def settings(env, flag):
        return SimpleNamespace(is_production=env, AUTO_REFRESH_ENABLED=flag, AUTO_REFRESH_MINUTES=15)

    with patch.object(ar, "get_settings", return_value=settings(True, None)):
        assert ar.auto_enabled() is True
    with patch.object(ar, "get_settings", return_value=settings(False, None)):
        assert ar.auto_enabled() is False
        assert ar.auto_status()["next_run"] is None
    with patch.object(ar, "get_settings", return_value=settings(True, False)):
        assert ar.auto_enabled() is False


def test_a_holiday_is_told_from_nifty_showing_no_trade_today():
    last = {"date": "2026-10-20", "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 1}

    def traded(quote):
        svc = SimpleNamespace(fetch_live_quotes=AsyncMock(return_value=({ar.NIFTY_50_SYMBOL.upper(): quote} if quote else {}, True)))
        with patch.object(ar, "get_market_data_service", return_value=svc), \
                patch.object(ar, "get_india_candles", AsyncMock(return_value=([last], {}))):
            return asyncio.run(ar.traded_today(object(), "2026-10-21"))

    echo = SimpleNamespace(last_price=105.0, open_price=100.0, high_price=110.0, low_price=95.0)  # yesterday's bar repeated
    moving = SimpleNamespace(last_price=106.0, open_price=105.5, high_price=106.5, low_price=104.0)
    assert traded(echo) is False
    assert traded(moving) is True
    assert traded(None) is None
