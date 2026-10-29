"""Stage 2 Router.

Takes the stock list from a saved Chartink screener (the Stage 2 trend template) and runs every stock through
the same momentum / ATH-breakout signals as the Equity signals page.

- GET  /api/v1/analytics/stage2          the stored list, what changed since the previous day, cached signals
- POST /api/v1/analytics/stage2/refresh  re-read Chartink, then recompute signals (list + Indian holdings) in the background
- GET  /api/v1/analytics/stage2/live     live Kite prices for the listed stocks

Signals are cached per stock exactly like Equity signals, so a stock that is also in the portfolio is not computed twice.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.routers.accounts import get_current_user
from apps.api.routers.signals import Job, _equity_symbol_map, _job_dict, session_really_expired
from core.analytics.equity_signals import MOMENTUM_LOOKBACK_DAYS, compute_stock_signals, load_benchmark
from core.analytics.live_signals import live_india_rows
from core.market_data.history import NIFTY_50_TOKEN, get_history_service
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.service import get_market_data_service
from core.market_data.user_client import get_user_kite_client
from core.screeners.chartink import ScreenerError, ScreenerResult, fetch_screener
from storage.tables.repositories import HoldingsRepository, ScreenerSnapshotRepository, SignalCacheRepository

logger = logging.getLogger("wealthvault.api.stage2")

router = APIRouter(prefix="/analytics/stage2", tags=["Stage 2"])

SLUG = "copy-stage-2-trend-template-949"
CONCURRENCY = 2
RESUME_MINUTES = 30

_jobs: Dict[str, Job] = {}
_tasks: set = set()


def _code_key(nsecode: str) -> str:
    return f"NSE:{nsecode.upper()}"


def _key_of(symbol: str) -> str:
    """Cache key of a stock given either a bare Chartink code ('INFY') or an exchange id ('NSE:INFY')."""
    return symbol.upper() if ":" in symbol else _code_key(symbol)


async def read_screener() -> Tuple[Optional[ScreenerResult], Optional[str]]:
    """The Chartink list, or why it could not be read."""
    try:
        result = await fetch_screener(SLUG)
    except ScreenerError as exc:
        return None, str(exc)
    if not result.rows:
        return None, "The Chartink screener returned no stocks right now."
    return result, None


def resume_point(previous: Optional[Job]) -> Optional[datetime]:
    """A run started soon after an interrupted one (Kite login lapsed, server restarted mid-run) keeps the rows that
    run already computed; any other run recomputes everything."""
    if previous is None or previous.state != "error" or not previous.started_at or not previous.finished_at:
        return None
    try:
        started = datetime.fromisoformat(previous.started_at)
        finished = datetime.fromisoformat(previous.finished_at)
    except ValueError:
        return None
    return started if datetime.now(timezone.utc) - finished <= timedelta(minutes=RESUME_MINUTES) else None


async def _run_job(
    owner_id: str,
    job: Job,
    fresh_since: Optional[datetime] = None,
    screener: Optional[Tuple[Optional[ScreenerResult], Optional[str]]] = None,
) -> None:
    """One refresh for the whole Signals page: re-read the Chartink list, then compute signals for every stock on it
    AND every Indian stock the user holds (a stock that is both is computed once).

    `fresh_since`: rows computed after this moment are kept as they are (a resumed run, or a scheduled run that has
    already done them for another user). `screener`: a list already read for this run, so it is read once."""
    cache = SignalCacheRepository()
    snapshots = ScreenerSnapshotRepository()
    try:
        result, chartink_error = screener if screener is not None else await read_screener()

        if result:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await snapshots.save(
                SLUG,
                today,
                {"title": result.title, "fetched_at": result.fetched_at, "extra_columns": result.extra_columns, "rows": result.rows},
            )

        client = await get_user_kite_client(owner_id)

        # cache key -> what to hand compute_stock_signals; the list first, then holdings that are not on it
        work: Dict[str, str] = {}
        for r in (result.rows if result else []):
            work.setdefault(_key_of(r["nsecode"]), r["nsecode"])
        list_keys = set(work)
        holdings = await HoldingsRepository().get_holdings(owner_id=owner_id)
        held_keys = set()
        for inst in sorted(set((await _equity_symbol_map(holdings, client)).values())):
            held_keys.add(_key_of(inst))
            work.setdefault(_key_of(inst), inst)
        job.list_count, job.holdings_count, job.overlap = len(list_keys), len(held_keys), len(list_keys & held_keys)

        if not work:
            job.state = "error"
            job.message = chartink_error or "There are no stocks to analyse yet."
            return
        job.total = len(work)

        benchmark = None
        try:
            benchmark = await load_benchmark(client)
        except KiteAuthRequiredError:
            raise
        except Exception as exc:
            logger.warning("Benchmark unavailable for signals: %s", exc)

        fresh_keys = set()
        if fresh_since is not None:
            for key, cached in (await cache.get_many(list(work))).items():
                try:
                    computed = datetime.fromisoformat(cached.get("computed_at", ""))
                except ValueError:
                    continue
                if computed >= fresh_since and not cached.get("errors", {}).get("all"):
                    fresh_keys.add(key)
        job.done = len(fresh_keys)
        todo = [k for k in work if k not in fresh_keys]

        sem = asyncio.Semaphore(CONCURRENCY)
        auth_error: List[KiteAuthRequiredError] = []
        retry: List[str] = []

        async def attempt(key: str) -> bool:
            try:
                row = await compute_stock_signals(client, work[key], benchmark)
                await cache.save(row["instrument"], row)
                if row["instrument"].upper() != key:
                    await cache.save(key, row)  # alias, so lookups by Chartink code or holding symbol always hit
                return True
            except KiteAuthRequiredError as exc:
                # Kite reports some per-stock failures like an expired login; confirm before stopping the run
                if await session_really_expired(client):
                    auth_error.append(exc)
                return False
            except Exception as exc:
                logger.warning("Signals failed for %s: %s", key, exc)
                return False

        async def one(key: str) -> None:
            async with sem:
                if auth_error:
                    return
                if await attempt(key):
                    job.done += 1
                else:
                    retry.append(key)

        await asyncio.gather(*(one(k) for k in todo))

        for key in retry:
            if auth_error:
                break
            await asyncio.sleep(1.0)
            if not await attempt(key) and not auth_error:
                job.failed += 1
                await cache.save(
                    key,
                    {"instrument": key, "momentum": None, "ath": None, "errors": {"all": "Price history unavailable"}},
                )
            job.done += 1

        if auth_error:
            job.state = "error"
            job.message = "Kite needs today's login to fetch price history."
            job.auth_url = auth_error[0].auth_url
        elif chartink_error:
            job.state = "error"
            job.message = f"{chartink_error} Your holdings were refreshed."
        else:
            job.state = "done"
    except KiteAuthRequiredError as exc:
        job.state = "error"
        job.message = "Kite needs today's login to fetch price history."
        job.auth_url = exc.auth_url
    except Exception as exc:
        logger.error("Signals refresh failed: %s", exc, exc_info=True)
        job.state = "error"
        job.message = f"Refresh failed: {exc}"
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED, summary="Re-read the Chartink screener and recompute signals for it and for the user's holdings")
async def refresh_stage2(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    previous = _jobs.get(current_user_id)
    if previous and previous.state == "running":
        return _job_dict(previous)
    job = Job(state="running", started_at=datetime.now(timezone.utc).isoformat())
    _jobs[current_user_id] = job
    task = asyncio.create_task(_run_job(current_user_id, job, fresh_since=resume_point(previous)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _job_dict(job)


@router.get("", status_code=status.HTTP_200_OK, summary="Stage 2 list, daily changes and cached signals")
async def get_stage2(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    latest, previous = await ScreenerSnapshotRepository().latest_two(SLUG)
    job = _jobs.get(current_user_id) or Job()
    from apps.api.auto_refresh import auto_status

    if latest is None:
        return {"job": _job_dict(job), "list": None, "signals": {}, "auto": auto_status()}

    day, snap = latest
    rows: List[Dict[str, Any]] = snap.get("rows", [])
    prev_codes = {r["nsecode"] for r in previous[1].get("rows", [])} if previous else None
    cur_codes = {r["nsecode"] for r in rows}

    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    held_ids = set((await _equity_symbol_map(holdings, None)).values())

    for r in rows:
        r["held"] = _code_key(r["nsecode"]) in held_ids
        r["is_new"] = None if prev_codes is None else r["nsecode"] not in prev_codes

    dropped = (
        [{"nsecode": r["nsecode"], "name": r.get("name")} for r in previous[1].get("rows", []) if r["nsecode"] not in cur_codes]
        if previous
        else []
    )
    signals = await SignalCacheRepository().get_many([_code_key(r["nsecode"]) for r in rows])
    return {
        "job": _job_dict(job),
        "list": {
            "title": snap.get("title"),
            "date": day,
            "fetched_at": snap.get("fetched_at"),
            "url": f"https://chartink.com/screener/{SLUG}",
            "extra_columns": snap.get("extra_columns", []),
            "previous_date": previous[0] if previous else None,
            "rows": rows,
            "dropped": dropped,
        },
        "signals": {k.split(":", 1)[1]: v for k, v in signals.items()},
        "auto": auto_status(),
    }


@router.get("/live-signals", status_code=status.HTTP_200_OK, summary="Stage 2 signals recomputed on the live price")
async def get_stage2_live_signals(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    latest, _ = await ScreenerSnapshotRepository().latest_two(SLUG)
    if latest is None:
        return {"signals": {}, "live": False, "reason": "no_signals"}
    codes = [r["nsecode"] for r in latest[1].get("rows", [])]
    cached = await SignalCacheRepository().get_many([_code_key(c) for c in codes])
    rows: Dict[str, Any] = {}
    reason = "ok"
    try:
        kite = await get_user_kite_client(current_user_id)
        live = await live_india_rows(kite, cached)
        rows = {k.split(":", 1)[1]: v for k, v in live.items()}
        if not rows and not kite.is_authenticated:
            reason = "login"  # the quote call flips this flag when the daily Kite session has lapsed
    except KiteAuthRequiredError as exc:
        logger.info("Live Stage 2 signals unavailable: %s", exc)
        reason = "login"
    except Exception as exc:
        logger.warning("Live Stage 2 signals failed: %s", exc, exc_info=True)
        reason = "error"
    if not rows and reason == "ok":
        reason = "no_prices" if cached else "no_signals"
    return {"signals": rows, "live": bool(rows), "reason": "ok" if rows else reason, "at": datetime.now(timezone.utc).isoformat()}


@router.get("/live", status_code=status.HTTP_200_OK, summary="Live Kite prices for the Stage 2 stocks")
async def get_stage2_live(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    latest, _ = await ScreenerSnapshotRepository().latest_two(SLUG)
    if latest is None:
        return {"quotes": {}}
    codes = [r["nsecode"] for r in latest[1].get("rows", [])]
    # Stocks in the exchange's trade-for-trade series are listed as e.g. NSE:MTARTECH-BE, so prefer the id the
    # signals run resolved for each stock and fall back to NSE:<code>
    cached = await SignalCacheRepository().get_many([_code_key(c) for c in codes])
    ids = {c: (cached.get(_code_key(c)) or {}).get("instrument") or _code_key(c) for c in codes}
    client = await get_user_kite_client(current_user_id)
    quotes_map, ok = await get_market_data_service().fetch_live_quotes(sorted(set(ids.values())), client=client)
    out: Dict[str, Any] = {}
    for c in codes:
        q = quotes_map.get(ids[c].upper())
        if q and q.last_price and q.last_price > 0:
            out[c] = {"price": q.last_price, "day_change_pct": q.day_change_percentage}
    return {"quotes": out, "live": ok}
