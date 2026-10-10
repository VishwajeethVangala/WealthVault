"""Equity Signals Router.

- GET  /api/v1/analytics/signals          cached momentum / Swing V2.1 / ATH-breakout signals for the caller's stocks
- POST /api/v1/analytics/signals/refresh  recompute them in the background (progress is returned by the GET)

Computing every stock takes a minute or two (Kite history is rate limited), so it runs as a background job
and results are cached per stock in Azure Table Storage.
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status

from apps.api.routers.accounts import get_current_user
from core.analytics.equity_signals import MOMENTUM_LOOKBACK_DAYS, compute_stock_signals
from core.market_data.history import NIFTY_50_TOKEN, get_history_service
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.service import MCPMarketDataService
from core.market_data.symbol_resolver import resolve_indmoney_symbols, split_indmoney_symbol
from core.market_data.user_client import get_user_kite_client
from core.models import AssetClass, Holding
from storage.tables.repositories import HoldingsRepository, SignalCacheRepository

logger = logging.getLogger("wealthvault.api.signals")

router = APIRouter(prefix="/analytics/signals", tags=["Equity Signals"])

CONCURRENCY = 2


@dataclass
class Job:
    state: str = "idle"  # idle | running | done | error
    total: int = 0
    done: int = 0
    failed: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    message: Optional[str] = None
    auth_url: Optional[str] = None


_jobs: Dict[str, Job] = {}
# Strong references so a running refresh task is not garbage collected
_tasks: set = set()


async def _equity_symbol_map(holdings: List[Holding], client: Optional[Any]) -> Dict[str, str]:
    """Holding symbol -> Kite instrument id, for Indian equity holdings only."""
    equity = [h for h in holdings if h.asset_class == AssetClass.EQUITY]
    mapping: Dict[str, str] = {}
    indmoney: List[str] = []
    for h in equity:
        if split_indmoney_symbol(h.instrument_symbol):
            indmoney.append(h.instrument_symbol)
            continue
        inst = MCPMarketDataService.format_instrument(h.instrument_symbol, h.asset_class)
        if inst:
            mapping[h.instrument_symbol] = inst
    mapping.update(await resolve_indmoney_symbols(indmoney, client))
    return mapping


def _job_dict(job: Job) -> Dict[str, Any]:
    return asdict(job)


async def _run_job(owner_id: str, job: Job) -> None:
    cache = SignalCacheRepository()
    try:
        client = await get_user_kite_client(owner_id)
        holdings = await HoldingsRepository().get_holdings(owner_id=owner_id)
        symbols = sorted(set((await _equity_symbol_map(holdings, client)).values()))
        job.total = len(symbols)

        history = get_history_service()
        benchmark = None
        try:
            benchmark = await history.get_daily_candles(client, NIFTY_50_TOKEN, MOMENTUM_LOOKBACK_DAYS)
        except KiteAuthRequiredError:
            raise
        except Exception as exc:
            logger.warning("Benchmark unavailable for signals: %s", exc)

        sem = asyncio.Semaphore(CONCURRENCY)
        auth_error: List[KiteAuthRequiredError] = []

        async def attempt(symbol: str) -> bool:
            """Compute and cache one stock. False means it failed and is worth retrying."""
            try:
                row = await compute_stock_signals(client, symbol, benchmark)
                await cache.save(row["instrument"], row)
                if row["instrument"] != symbol:
                    await cache.save(symbol, row)
                return True
            except KiteAuthRequiredError as exc:
                # Kite reports some per-stock failures the same way as an expired login, so confirm
                # the session is really gone before stopping the whole run.
                try:
                    await client.get_profile()
                except KiteAuthRequiredError:
                    auth_error.append(exc)
                except Exception:
                    pass
                return False
            except Exception as exc:
                logger.warning("Signals attempt failed for %s: %s", symbol, exc)
                return False

        async def one(symbol: str) -> None:
            async with sem:
                if auth_error:
                    return
                if await attempt(symbol):
                    job.done += 1
                else:
                    retry.append(symbol)

        retry: List[str] = []
        await asyncio.gather(*(one(s) for s in symbols))

        # Kite throttles under load and answers some calls with errors; retry the failures one at a time
        for symbol in retry:
            if auth_error:
                break
            await asyncio.sleep(1.0)
            ok = await attempt(symbol)
            if not ok and not auth_error:
                job.failed += 1
                await cache.save(
                    symbol,
                    {"instrument": symbol, "momentum": None, "swing": None, "ath": None, "errors": {"all": "Price history unavailable"}},
                )
            job.done += 1
        if auth_error:
            job.state = "error"
            job.message = "Kite needs today's login to fetch price history."
            job.auth_url = auth_error[0].auth_url
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


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED, summary="Recompute equity signals in the background")
async def refresh_signals(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    job = _jobs.get(current_user_id)
    if job and job.state == "running":
        return _job_dict(job)
    job = Job(state="running", started_at=datetime.now(timezone.utc).isoformat())
    _jobs[current_user_id] = job
    task = asyncio.create_task(_run_job(current_user_id, job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _job_dict(job)


@router.get("", status_code=status.HTTP_200_OK, summary="Cached equity signals and refresh progress")
async def get_signals(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    symbol_map = await _equity_symbol_map(holdings, None)  # cache-only, no network
    signals = await SignalCacheRepository().get_many(list(set(symbol_map.values())))
    job = _jobs.get(current_user_id) or Job()
    return {"job": _job_dict(job), "symbol_map": symbol_map, "signals": signals}
