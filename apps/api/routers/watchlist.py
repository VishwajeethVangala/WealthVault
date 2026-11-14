"""Watchlist Router.

Manages user-tracked radar stocks for momentum analysis, strategy backtests, and signals.
Persisted in Azure Table Storage under each user's own partition ('watchlist' table).

- GET    /api/v1/watchlist          List watched symbols (enriched with latest cached signals)
- POST   /api/v1/watchlist          Add or update a symbol in the watchlist
- DELETE /api/v1/watchlist/{symbol}  Remove a symbol from the watchlist
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from apps.api.routers.accounts import get_current_user
from core.analytics.equity_signals import compute_stock_signals, load_benchmark
from core.market_data.history import normalize_symbol
from core.market_data.service import get_market_data_service
from core.market_data.user_client import get_user_kite_client
from storage.tables.repositories import SignalCacheRepository, WatchlistRepository

logger = logging.getLogger("wealthvault.api.watchlist")

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


class WatchlistItem(BaseModel):
    symbol: str
    name: str
    notes: Optional[str] = ""
    target_price: Optional[float] = None
    price_when_added: Optional[float] = None
    added_at: str
    # Enriched fields from signal cache
    last_price: Optional[float] = None
    pct_since_added: Optional[float] = None
    trend_verdict: Optional[str] = None
    trend_score: Optional[int] = None
    signal_state: Optional[str] = None


class WatchlistResponse(BaseModel):
    items: List[WatchlistItem]
    count: int


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol, e.g. INFY, NSE:TATAMOTORS, BSE:500209")
    name: Optional[str] = Field(default=None, max_length=128, description="Company name or friendly alias")
    notes: Optional[str] = Field(default=None, max_length=500, description="Notes on why you are watching")
    target_price: Optional[float] = Field(default=None, ge=0, description="Target entry price alert level")
    price_when_added: Optional[float] = Field(default=None, ge=0, description="Reference price when added")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        clean = v.strip().upper()
        if not clean:
            raise ValueError("Symbol cannot be empty.")
        return normalize_symbol(clean)


@router.get(
    "",
    response_model=WatchlistResponse,
    status_code=status.HTTP_200_OK,
    summary="List Watchlist",
    description="Returns all symbols on the caller's watchlist, newest first, enriched with cached signals.",
)
async def list_watchlist(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    repo = WatchlistRepository()
    cache = SignalCacheRepository()
    try:
        items = await repo.list_items(owner_id=current_user_id)
        if not items:
            return {"items": [], "count": 0}

        # Enrich with signals from SignalCacheRepository
        symbols = [it["symbol"] for it in items]
        cached_signals = await cache.get_many(symbols)

        enriched: List[Dict[str, Any]] = []
        for it in items:
            sym = it["symbol"]
            row = dict(it)
            sig = cached_signals.get(sym)

            # Try ticker-only key if exchange-prefixed was not found
            if not sig and ":" in sym:
                sig = cached_signals.get(sym.split(":")[-1])

            if sig and isinstance(sig, dict):
                mom = sig.get("momentum") or {}
                ath = sig.get("ath") or {}
                swing = sig.get("swing") or {}

                last_price = mom.get("last_price") or sig.get("live_price") or (ath.get("entry_price") if ath else None)
                row["last_price"] = last_price
                row["trend_verdict"] = mom.get("trend_verdict") or mom.get("verdict")
                row["trend_score"] = mom.get("trend_score") or mom.get("score")
                row["signal_state"] = ath.get("state") or swing.get("state")

                added_p = it.get("price_when_added")
                if added_p and last_price and added_p > 0:
                    row["pct_since_added"] = round((last_price - added_p) / added_p * 100, 2)

            enriched.append(row)

        # Enrich missing prices with live market quotes if Kite is connected
        missing_price_syms = [r["symbol"] for r in enriched if r.get("last_price") is None]
        if missing_price_syms:
            try:
                client = await get_user_kite_client(current_user_id)
                quotes_map, _ = await get_market_data_service().fetch_live_quotes(missing_price_syms, client=client)
                for row in enriched:
                    if row.get("last_price") is None:
                        sym = row["symbol"]
                        q = quotes_map.get(sym.upper()) or quotes_map.get(sym.split(":")[-1])
                        if q and q.last_price:
                            row["last_price"] = q.last_price
                            if not row.get("price_when_added"):
                                row["price_when_added"] = q.last_price
                                row["pct_since_added"] = 0.0
                            elif row.get("price_when_added"):
                                row["pct_since_added"] = round((q.last_price - row["price_when_added"]) / row["price_when_added"] * 100, 2)
            except Exception as exc:
                logger.debug("Live quote enrichment skipped: %s", exc)

        return {"items": enriched, "count": len(enriched)}
    finally:
        await repo.close()
        await cache.close()


@router.post(
    "/refresh",
    response_model=WatchlistResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh Watchlist Signals",
    description="Recomputes momentum trend verdicts and ATH breakout signals for all stocks on the caller's watchlist.",
)
async def refresh_watchlist(
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    repo = WatchlistRepository()
    cache = SignalCacheRepository()
    try:
        items = await repo.list_items(owner_id=current_user_id)
        if not items:
            return {"items": [], "count": 0}

        symbols = [it["symbol"] for it in items]
        try:
            client = await get_user_kite_client(current_user_id)
            benchmark = await load_benchmark(client)
            for sym in symbols:
                try:
                    row = await compute_stock_signals(client, sym, benchmark)
                    await cache.save(row["instrument"], row)
                    if row["instrument"] != sym:
                        await cache.save(sym, row)
                except Exception as exc:
                    logger.warning("Could not compute signal for watchlist %s: %s", sym, exc)
        except Exception as client_exc:
            logger.warning("Could not get Kite client for watchlist refresh: %s", client_exc)

        return await list_watchlist(current_user_id=current_user_id)
    finally:
        await repo.close()
        await cache.close()


@router.post(
    "",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add to Watchlist",
    description="Adds or updates a symbol in the caller's watchlist, resolving company name if available.",
)
async def add_to_watchlist(
    payload: WatchlistAddRequest,
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    repo = WatchlistRepository()
    cache = SignalCacheRepository()
    symbol = payload.symbol
    name = payload.name
    price_when_added = payload.price_when_added

    # If company name or price was not provided, attempt to pull from cached signal or Kite lookup
    sig = None
    if not name or not name.strip() or price_when_added is None:
        try:
            cached = await cache.get_many([symbol])
            sig = cached.get(symbol)
            if sig:
                if (not name or not name.strip()) and sig.get("name"):
                    name = str(sig["name"])
                if price_when_added is None:
                    mom = sig.get("momentum") or {}
                    if mom.get("last_price"):
                        price_when_added = float(mom["last_price"])
        except Exception as exc:
            logger.debug("Cache lookup for %s skipped: %s", symbol, exc)

    # Pre-compute signal if not yet cached, to immediately populate momentum and ATH breakout
    if not sig:
        try:
            client = await get_user_kite_client(current_user_id)
            benchmark = await load_benchmark(client)
            sig = await compute_stock_signals(client, symbol, benchmark)
            await cache.save(sig["instrument"], sig)
            if sig["instrument"] != symbol:
                await cache.save(symbol, sig)
            if (not name or not name.strip()) and sig.get("name"):
                name = str(sig["name"])
            if price_when_added is None:
                mom = sig.get("momentum") or {}
                if mom.get("last_price"):
                    price_when_added = float(mom["last_price"])
        except Exception as exc:
            logger.debug("Signal pre-compute note for %s: %s", symbol, exc)

    # Fallback price quote if price_when_added is still missing
    if price_when_added is None:
        try:
            client = await get_user_kite_client(current_user_id)
            quotes_map, _ = await get_market_data_service().fetch_live_quotes([symbol], client=client)
            q = quotes_map.get(symbol.upper()) or quotes_map.get(symbol.split(":")[-1])
            if q and q.last_price:
                price_when_added = float(q.last_price)
        except Exception:
            pass

    if not name or not name.strip():
        try:
            client = await get_user_kite_client(current_user_id)
            results = await client.search_instruments(symbol)
            exact = next((r for r in results if str(r.get("id", "")).upper() == symbol), None)
            if exact and exact.get("name"):
                name = str(exact["name"])
        except Exception as exc:
            logger.debug("Could not resolve name for %s: %s", symbol, exc)
            name = symbol.split(":")[-1]

    try:
        item = await repo.add_item(
            owner_id=current_user_id,
            symbol=symbol,
            name=name,
            notes=payload.notes,
            target_price=payload.target_price,
            price_when_added=price_when_added,
        )
        logger.info("User %s added %s to watchlist", current_user_id, symbol)
        return item
    finally:
        await repo.close()
        await cache.close()


@router.delete(
    "/{symbol:path}",
    status_code=status.HTTP_200_OK,
    summary="Remove from Watchlist",
    description="Removes a symbol from the caller's watchlist.",
)
async def remove_from_watchlist(
    symbol: str,
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    repo = WatchlistRepository()
    clean_sym = normalize_symbol(symbol.strip().upper())
    try:
        removed = await repo.remove_item(owner_id=current_user_id, symbol=clean_sym)
        logger.info("User %s removed %s from watchlist (deleted=%s)", current_user_id, clean_sym, removed)
        return {"status": "removed", "symbol": clean_sym, "success": removed}
    finally:
        await repo.close()
