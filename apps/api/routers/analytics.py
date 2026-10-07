"""Market Analytics Router.

Provides endpoints for:
- GET /api/v1/analytics/momentum: Momentum report (trend, returns, RSI, 52W range,
  relative strength) for a single stock computed from Kite daily candles.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.routers.accounts import get_current_user
from core.analytics import analyze_momentum
from core.market_data.history import (
    NIFTY_50_SYMBOL,
    NIFTY_50_TOKEN,
    InstrumentNotFoundError,
    get_history_service,
)
from core.market_data.kite_client import KiteAuthRequiredError, KiteMCPClient, get_kite_mcp_client
from core.models import BrokerStatus, MomentumAnalysis
from storage.tables.repositories import BrokerConnectionRepository

logger = logging.getLogger("wealthvault.api.analytics")

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# Minimum daily candles for a useful report (50-DMA + MACD); longer windows show as unavailable
MIN_CANDLES = 50


async def _get_user_kite_client(owner_id: str) -> KiteMCPClient:
    """Use the caller's own Zerodha connection for market data, falling back to the default client."""
    connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    zerodha = [c for c in connections if c.broker_name.lower().strip() == "zerodha"]
    preferred = next((c for c in zerodha if c.status == BrokerStatus.CONNECTED), None) or (zerodha[0] if zerodha else None)
    return get_kite_mcp_client(preferred.connection_id) if preferred else get_kite_mcp_client()


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
    history = get_history_service()
    client = await _get_user_kite_client(current_user_id)

    try:
        instrument = await history.resolve_instrument(client, symbol)
        candles = await history.get_daily_candles(client, int(instrument["instrument_token"]))

        benchmark_candles: Optional[list] = None
        if int(instrument["instrument_token"]) != NIFTY_50_TOKEN:
            try:
                benchmark_candles = await history.get_daily_candles(client, NIFTY_50_TOKEN)
            except KiteAuthRequiredError:
                raise
            except Exception as exc:
                logger.warning("Benchmark candles unavailable, skipping relative strength: %s", exc)
    except InstrumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except KiteAuthRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "KITE_AUTH_REQUIRED",
                "message": "Historical prices come from Zerodha Kite, which needs today's login.",
                "auth_url": exc.auth_url,
            },
        )
    except Exception as exc:
        logger.error("Momentum data fetch failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch price history from Kite: {exc}",
        )

    if len(candles) < MIN_CANDLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only {len(candles)} days of price history available for {symbol}; at least {MIN_CANDLES} are needed.",
        )

    qualified = str(instrument.get("id") or f"{instrument.get('exchange')}:{instrument.get('tradingsymbol')}")
    return analyze_momentum(
        instrument=qualified,
        candles=candles,
        benchmark_candles=benchmark_candles,
        benchmark_name=NIFTY_50_SYMBOL.split(":", 1)[1],
        name=instrument.get("name"),
    )
