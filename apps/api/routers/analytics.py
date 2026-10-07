"""Market Analytics Router.

Provides endpoints for:
- GET /api/v1/analytics/momentum: Momentum report (trend, returns, RSI, 52W range,
  relative strength) for a single stock computed from Kite daily candles.
- GET /api/v1/analytics/strategy/swing-v21: NSE Swing Momentum V2.1 strategy status,
  signals, and backtest for a single stock.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.routers.accounts import get_current_user
from core.analytics import analyze_momentum
from core.analytics.swing_strategy import run_swing_strategy
from core.market_data.history import (
    MAX_LOOKBACK_DAYS,
    NIFTY_50_SYMBOL,
    NIFTY_50_TOKEN,
    InstrumentNotFoundError,
    drop_incomplete_today,
    get_history_service,
)
from core.market_data.kite_client import KiteAuthRequiredError, KiteMCPClient, get_kite_mcp_client
from core.models import BrokerStatus, MomentumAnalysis, SwingStrategyParams, SwingStrategyResult
from storage.tables.repositories import BrokerConnectionRepository

logger = logging.getLogger("wealthvault.api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Minimum daily candles for a useful report (50-DMA + MACD); longer windows show as unavailable
MIN_CANDLES = 50

# Extra calendar days fetched ahead of the backtest window for the 200-SMA + slope warm-up
STRATEGY_WARMUP_DAYS = 330


async def _get_user_kite_client(owner_id: str) -> KiteMCPClient:
    """Use the caller's own Zerodha connection for market data, falling back to the default client."""
    connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    zerodha = [c for c in connections if c.broker_name.lower().strip() == "zerodha"]
    preferred = next((c for c in zerodha if c.status == BrokerStatus.CONNECTED), None) or (zerodha[0] if zerodha else None)
    return get_kite_mcp_client(preferred.connection_id) if preferred else get_kite_mcp_client()


def _kite_auth_exception(exc: KiteAuthRequiredError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "KITE_AUTH_REQUIRED",
            "message": "Historical prices come from Zerodha Kite, which needs today's login.",
            "auth_url": exc.auth_url,
        },
    )


async def _load_candles(
    owner_id: str,
    symbol: str,
    lookback_days: int,
    with_benchmark: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """Resolve the symbol and fetch daily candles (and optionally NIFTY 50), mapping errors to HTTP."""
    history = get_history_service()
    client = await _get_user_kite_client(owner_id)

    try:
        instrument = await history.resolve_instrument(client, symbol)
        token = int(instrument["instrument_token"])
        candles = await history.get_daily_candles(client, token, lookback_days)

        benchmark_candles: Optional[List[Dict[str, Any]]] = None
        if with_benchmark and token != NIFTY_50_TOKEN:
            try:
                benchmark_candles = await history.get_daily_candles(client, NIFTY_50_TOKEN, lookback_days)
            except KiteAuthRequiredError:
                raise
            except Exception as exc:
                logger.warning("Benchmark candles unavailable, skipping relative strength: %s", exc)
    except InstrumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except KiteAuthRequiredError as exc:
        raise _kite_auth_exception(exc)
    except Exception as exc:
        logger.error("Price history fetch failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch price history from Kite: {exc}",
        )

    return instrument, candles, benchmark_candles


def _qualified_symbol(instrument: Dict[str, Any]) -> str:
    return str(instrument.get("id") or f"{instrument.get('exchange')}:{instrument.get('tradingsymbol')}")


@router.get(
    "/momentum",
    response_model=MomentumAnalysis,
    status_code=status.HTTP_200_OK,
    summary="Compute Stock Momentum",
    description=(
        "Fetches ~1 year of daily candles from Kite MCP and computes moving-average trend "
        "(50/200-DMA, golden cross, 200-DMA slope, MACD), 1M-12M returns, risk-adjusted momentum, "
        "RSI(14), 52-week range, and relative strength versus NIFTY 50."
    ),
)
async def get_momentum(
    symbol: str = Query(..., min_length=1, max_length=40, description="Symbol, e.g. 'INFY' or 'NSE:INFY'"),
    current_user_id: str = Depends(get_current_user),
) -> MomentumAnalysis:
    """Compute the momentum report for a single instrument."""
    instrument, candles, benchmark_candles = await _load_candles(
        current_user_id, symbol, lookback_days=400, with_benchmark=True
    )

    if len(candles) < MIN_CANDLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only {len(candles)} days of price history available for {symbol}; at least {MIN_CANDLES} are needed.",
        )

    return analyze_momentum(
        instrument=_qualified_symbol(instrument),
        candles=candles,
        benchmark_candles=benchmark_candles,
        benchmark_name=NIFTY_50_SYMBOL.split(":", 1)[1],
        name=instrument.get("name"),
    )


@router.get(
    "/strategy/swing-v21",
    response_model=SwingStrategyResult,
    status_code=status.HTTP_200_OK,
    summary="NSE Swing Momentum V2.1 Strategy",
    description=(
        "Runs the NSE Swing Momentum V2.1 strategy (50/200-SMA trend filter, UT Bot entry, "
        "UT + 20-EMA exit, ATR protective stop) on Kite daily candles and returns the current "
        "status, per-bar signals, trade list, and backtest statistics. Today's unfinished candle "
        "is excluded during market hours so signals do not change intraday."
    ),
)
async def get_swing_strategy(
    symbol: str = Query(..., min_length=1, max_length=40, description="Symbol, e.g. 'INFY' or 'NSE:INFY'"),
    years: int = Query(default=5, ge=1, le=5, description="Backtest length in years (Kite allows ~4.5Y after warm-up)"),
    ut_key: float = Query(default=1.0, gt=0, le=10, description="UT Bot key value"),
    ut_atr_period: int = Query(default=10, ge=1, le=100, description="UT Bot ATR period"),
    use_stop: bool = Query(default=True, description="Use the ATR protective stop"),
    stop_atr_mult: float = Query(default=2.0, gt=0, le=10, description="Protective stop ATR multiplier"),
    current_user_id: str = Depends(get_current_user),
) -> SwingStrategyResult:
    """Compute status, signals, and backtest for the V2.1 swing strategy."""
    params = SwingStrategyParams(
        ut_key=ut_key,
        ut_atr_period=ut_atr_period,
        use_stop=use_stop,
        stop_atr_mult=stop_atr_mult,
    )
    lookback = min(MAX_LOOKBACK_DAYS, years * 365 + STRATEGY_WARMUP_DAYS)
    instrument, candles, _ = await _load_candles(current_user_id, symbol, lookback_days=lookback)
    candles, partial_dropped = drop_incomplete_today(candles)

    tick = float(instrument.get("tick_size") or 0.05)
    try:
        return run_swing_strategy(
            instrument=_qualified_symbol(instrument),
            candles=candles,
            params=params,
            tick_size=tick,
            name=instrument.get("name"),
            partial_bar_excluded=partial_dropped,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
