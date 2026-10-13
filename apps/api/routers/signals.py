"""Equity Signals Router.

- GET  /api/v1/analytics/signals?market=in|us          cached momentum / Swing V2.1 / ATH-breakout signals
- POST /api/v1/analytics/signals/refresh?market=in|us  recompute them in the background (progress comes from the GET)
- GET  /api/v1/analytics/signals/us-live               live USD prices for the caller's US stocks (INDmoney)
- POST /api/v1/analytics/signals/us-history/{ticker}   build or top up the stored history for any US ticker

Indian stocks use Kite candles. US stocks use the history stored in Azure (see core.market_data.us_history):
INDmoney for the recent year and for daily top-ups, with a validated one-time backfill for everything older.
Computing every stock takes a minute or two, so it runs as a background job and results are cached per stock.
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.routers.accounts import get_current_user
from core.analytics.equity_signals import MOMENTUM_LOOKBACK_DAYS, _no_partial, build_signal_row, compute_stock_signals, load_benchmark
from core.analytics.live_signals import live_india_rows, live_us_rows
from core.market_data.indmoney_client import IndmoneyAuthRequiredError
from core.market_data.kite_client import KiteAuthRequiredError
from core.market_data.service import MCPMarketDataService
from core.market_data.symbol_resolver import resolve_indmoney_symbols, split_indmoney_symbol
from core.market_data.us_history import UsHistoryError, ensure_history, get_candles, us_session_closed
from core.market_data.user_client import get_user_kite_client
from core.models import AssetClass, Holding
from providers.brokers.indmoney import IndmoneyProvider
from storage.tables.repositories import HoldingsRepository, SignalCacheRepository

logger = logging.getLogger("wealthvault.api.signals")

router = APIRouter(prefix="/analytics/signals", tags=["Equity Signals"])

CONCURRENCY = 2
US_BENCHMARK = "SPY"
US_TICK_SIZE = 0.01
US_LIVE_TTL_SECONDS = 10.0


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
_us_live_cache: Dict[str, Any] = {}


async def session_really_expired(client: Any) -> bool:
    """Kite words some throttling and per-stock failures like an expired login, so a login is only treated as
    gone when the profile check fails twice, a couple of seconds apart."""
    for attempt in range(2):
        try:
            await client.get_profile()
            return False
        except KiteAuthRequiredError:
            if attempt == 0:
                await asyncio.sleep(2.0)
        except Exception:
            return False
    return True


def _job_dict(job: Job) -> Dict[str, Any]:
    return asdict(job)


def _job_key(owner_id: str, market: str) -> str:
    return f"{owner_id}:{market}"


# --- symbol maps -----------------------------------------------------------------------------------------


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


def _us_ticker(symbol: str) -> str:
    """'NVDA (NVIDIA Corporation)' -> 'NVDA'."""
    return symbol.strip().split()[0].upper()


def _us_symbol_map(holdings: List[Holding]) -> Dict[str, str]:
    """Holding symbol -> 'US:TICKER', for US stock holdings."""
    return {h.instrument_symbol: f"US:{_us_ticker(h.instrument_symbol)}" for h in holdings if h.asset_class == AssetClass.US_STOCKS}


def _us_names(holdings: List[Holding]) -> Dict[str, str]:
    names: Dict[str, str] = {}
    for h in holdings:
        if h.asset_class != AssetClass.US_STOCKS:
            continue
        sym = h.instrument_symbol
        names[_us_ticker(sym)] = sym[sym.find("(") + 1 : sym.rfind(")")].strip() if "(" in sym and sym.endswith(")") else _us_ticker(sym)
    return names


def _indmoney_client(owner_id: str, holdings: List[Holding]) -> Any:
    conn_ids = sorted({h.connection_id for h in holdings if "indmoney" in (h.connection_id or "").lower()})
    if not conn_ids:
        raise HTTPException(status_code=409, detail="Connect INDmoney to analyse US stocks.")
    return IndmoneyProvider(connection_id=conn_ids[0], owner_id=owner_id).client


# --- refresh jobs ----------------------------------------------------------------------------------------


async def _run_job_in(owner_id: str, job: Job) -> None:
    cache = SignalCacheRepository()
    try:
        client = await get_user_kite_client(owner_id)
        holdings = await HoldingsRepository().get_holdings(owner_id=owner_id)
        symbols = sorted(set((await _equity_symbol_map(holdings, client)).values()))
        job.total = len(symbols)

        benchmark = None
        try:
            benchmark = await load_benchmark(client)
        except KiteAuthRequiredError:
            raise
        except Exception as exc:
            logger.warning("Benchmark unavailable for signals: %s", exc)

        sem = asyncio.Semaphore(CONCURRENCY)
        auth_error: List[KiteAuthRequiredError] = []
        retry: List[str] = []

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
                if await session_really_expired(client):
                    auth_error.append(exc)
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


async def _run_job_us(owner_id: str, job: Job) -> None:
    cache = SignalCacheRepository()
    try:
        holdings = await HoldingsRepository().get_holdings(owner_id=owner_id)
        client = _indmoney_client(owner_id, holdings)
        names = _us_names(holdings)
        tickers = sorted(names)
        job.total = len(tickers)

        # S&P 500 (SPY) is the momentum benchmark; it goes through the same stored-history process
        bench_info = await ensure_history(US_BENCHMARK, client)
        bench_all, _ = await get_candles(US_BENCHMARK)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=MOMENTUM_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        benchmark = [c for c in bench_all if c["date"] >= cutoff] if bench_info.count else None

        sem = asyncio.Semaphore(3)
        auth_error: List[IndmoneyAuthRequiredError] = []
        retry: List[str] = []

        async def attempt(ticker: str) -> bool:
            try:
                info = await ensure_history(ticker, client)
                candles, _meta = await get_candles(ticker)
                row = build_signal_row(
                    f"US:{ticker}",
                    {"name": names.get(ticker), "tick_size": US_TICK_SIZE},
                    candles,
                    benchmark,
                    benchmark_name="S&P 500 (SPY)",
                    drop_partial=_no_partial,
                    extra={"currency": "USD", "history_status": info.status, "history_note": info.note, "history_first": info.first_date},
                )
                if info.status != "complete":
                    # Without the full history the all-time high and the strategies' state are not trustworthy
                    for section in ("swing", "ath"):
                        row[section] = None
                        row["errors"][section] = f"History incomplete ({info.count} days); not shown rather than guessed"
                await cache.save(f"US:{ticker}", row)
                return True
            except IndmoneyAuthRequiredError as exc:
                auth_error.append(exc)
                return False
            except UsHistoryError as exc:
                logger.warning("US history failed for %s: %s", ticker, exc)
                return False
            except Exception as exc:
                logger.warning("US signals attempt failed for %s: %s", ticker, exc)
                return False

        async def one(ticker: str) -> None:
            async with sem:
                if auth_error:
                    return
                if await attempt(ticker):
                    job.done += 1
                else:
                    retry.append(ticker)

        await asyncio.gather(*(one(t) for t in tickers))
        for ticker in retry:
            if auth_error:
                break
            await asyncio.sleep(1.0)
            if not await attempt(ticker) and not auth_error:
                job.failed += 1
                await cache.save(
                    f"US:{ticker}",
                    {"instrument": f"US:{ticker}", "momentum": None, "swing": None, "ath": None, "errors": {"all": "Price history unavailable"}},
                )
            job.done += 1
        if auth_error:
            job.state = "error"
            job.message = "INDmoney needs authorization to fetch US price history."
            job.auth_url = auth_error[0].auth_url
        else:
            job.state = "done"
    except IndmoneyAuthRequiredError as exc:
        job.state = "error"
        job.message = "INDmoney needs authorization to fetch US price history."
        job.auth_url = exc.auth_url
    except HTTPException as exc:
        job.state = "error"
        job.message = str(exc.detail)
    except Exception as exc:
        logger.error("US signals refresh failed: %s", exc, exc_info=True)
        job.state = "error"
        job.message = f"Refresh failed: {exc}"
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()


# --- endpoints -------------------------------------------------------------------------------------------


@router.post("/refresh", status_code=status.HTTP_202_ACCEPTED, summary="Recompute equity signals in the background")
async def refresh_signals(
    market: str = Query("in", pattern="^(in|us)$"),
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    key = _job_key(current_user_id, market)
    job = _jobs.get(key)
    if job and job.state == "running":
        return _job_dict(job)
    job = Job(state="running", started_at=datetime.now(timezone.utc).isoformat())
    _jobs[key] = job
    runner = _run_job_us if market == "us" else _run_job_in
    task = asyncio.create_task(runner(current_user_id, job))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return _job_dict(job)


@router.get("", status_code=status.HTTP_200_OK, summary="Cached equity signals and refresh progress")
async def get_signals(
    market: str = Query("in", pattern="^(in|us)$"),
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    symbol_map = _us_symbol_map(holdings) if market == "us" else await _equity_symbol_map(holdings, None)  # cache-only
    signals = await SignalCacheRepository().get_many(list(set(symbol_map.values())))
    job = _jobs.get(_job_key(current_user_id, market)) or Job()
    return {"job": _job_dict(job), "symbol_map": symbol_map, "signals": signals}


async def _us_quotes(owner_id: str, holdings: List[Holding]) -> Dict[str, Any]:
    """Live INDmoney quotes for the owner's US stocks plus SPY (the benchmark), cached for a few seconds."""
    tickers = sorted({_us_ticker(h.instrument_symbol) for h in holdings if h.asset_class == AssetClass.US_STOCKS} | {US_BENCHMARK})
    cached = _us_live_cache.get(owner_id)
    if cached and time.monotonic() - cached[0] < US_LIVE_TTL_SECONDS:
        quotes = cached[1]
    else:
        client = _indmoney_client(owner_id, holdings)
        quotes: Dict[str, Any] = {}
        # INDmoney now and then drops part of a batch; anything missing gets one more try
        batches = [tickers[i : i + 10] for i in range(0, len(tickers), 10)]
        for attempt in range(2):
            if attempt == 1:
                missing = [t for t in tickers if t not in quotes]
                if not missing:
                    break
                await asyncio.sleep(0.5)
                batches = [missing[i : i + 10] for i in range(0, len(missing), 10)]
            for batch in batches:
                try:
                    resp = await client.call_tool("get_us_stocks_details", {"symbols": batch})
                except IndmoneyAuthRequiredError:
                    batches = []
                    break
                except Exception as exc:
                    logger.warning("US live quotes failed for %s: %s", batch, exc)
                    continue
                _collect_us_quotes(resp, batch, quotes)
        _us_live_cache[owner_id] = (time.monotonic(), quotes)
    return quotes


@router.get("/us-live", status_code=status.HTTP_200_OK, summary="Live USD prices for the caller's US stocks")
async def get_us_live(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    return {"quotes": await _us_quotes(current_user_id, holdings), "session_closed": us_session_closed()}


@router.get("/live", status_code=status.HTTP_200_OK, summary="Signals recomputed on the live price")
async def get_live_signals(
    market: str = Query("in", pattern="^(in|us)$"),
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """The cached rows rebuilt with today's bar made from the live quote. Rows that cannot be (history behind,
    no quote, session not open) are simply absent and the caller keeps the cached ones."""
    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    rows: Dict[str, Any] = {}
    try:
        if market == "us":
            symbol_map = _us_symbol_map(holdings)
            cached = await SignalCacheRepository().get_many(list(set(symbol_map.values())))
            quotes = await _us_quotes(current_user_id, holdings)
            rows = await live_us_rows(cached, quotes, _us_names(holdings), US_TICK_SIZE)
        else:
            symbol_map = await _equity_symbol_map(holdings, None)
            cached = await SignalCacheRepository().get_many(list(set(symbol_map.values())))
            rows = await live_india_rows(await get_user_kite_client(current_user_id), cached)
    except (KiteAuthRequiredError, IndmoneyAuthRequiredError, HTTPException) as exc:
        logger.info("Live signals unavailable: %s", getattr(exc, "detail", exc))
    except Exception as exc:
        logger.warning("Live signals failed: %s", exc, exc_info=True)
    return {"signals": rows, "live": bool(rows), "at": datetime.now(timezone.utc).isoformat()}


def _collect_us_quotes(resp: Any, batch: List[str], quotes: Dict[str, Any]) -> None:
    for t in batch:
        stats = ((resp or {}).get(t) or {}).get("entity_stats") if isinstance(resp, dict) else None
        if not stats or not stats.get("live_price"):
            continue
        quotes[t] = {
            "price": stats.get("live_price"),
            "day_change": stats.get("day_change"),
            "day_change_pct": stats.get("day_change_percentage"),
            "prev_close": stats.get("prev_close"),
            "ext_price": stats.get("ext_hr_live_price"),
            "ext_change_pct": stats.get("ext_hr_day_change_percentage"),
            "updated": stats.get("last_updated"),
        }


@router.post("/us-history/{ticker}", status_code=status.HTTP_200_OK, summary="Build or top up stored history for a US ticker")
async def build_us_history(
    ticker: str,
    rebuild: bool = Query(False, description="Discard the stored history and rebuild it"),
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    """The process for any new US stock: full history is fetched, validated and stored on first request."""
    holdings = await HoldingsRepository().get_holdings(owner_id=current_user_id)
    try:
        info = await ensure_history(ticker, _indmoney_client(current_user_id, holdings), force_rebuild=rebuild)
    except UsHistoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IndmoneyAuthRequiredError as exc:
        raise HTTPException(status_code=409, detail={"code": "INDMONEY_AUTH_REQUIRED", "auth_url": exc.auth_url})
    return asdict(info)
