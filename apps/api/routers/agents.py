"""FastAPI router for the WealthVault Agent Boardroom.

Provides endpoints to:
- Inspect boardroom agent profiles and real-time states
- Trigger an on-demand multi-agent deliberation cycle
- View active and historical action directives
- Mark directives closed ("ORDER_PLACED_AT_BROKER", "IGNORED", "SNOOZED")
- Inspect real-time debate timeline
- Fetch forensic due-diligence dossiers on demand
"""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.api.routers.accounts import get_current_user
from core.agents.boss import get_boss_ai_status
from core.agents.forensic_crawler import build_investigation_dossier, clean_display_name, clean_symbol
from core.agents.ground.contracts import GroundStockDossier
from core.agents.ground.ground_orchestrator import get_ground_swarm_orchestrator, is_pure_equity_stock
from core.agents.models import (
    AgentProfile,
    DirectiveCard,
    DirectiveStatus,
    InvestigationDossier,
    TimelineEvent,
)
from core.agents.orchestrator import get_orchestrator
from core.agents.storage import get_boardroom_storage
from storage.tables.repositories import HoldingsRepository

logger = logging.getLogger("wealthvault.api.agents")

router = APIRouter(prefix="/agents", tags=["Agent Boardroom"])


class DirectiveStatusUpdateRequest(BaseModel):
    status: DirectiveStatus
    user_comment: Optional[str] = Field(default=None, description="Optional note or reason for the action taken")


class BoardroomOverviewResponse(BaseModel):
    agents: List[AgentProfile]
    active_directives: List[DirectiveCard]
    historical_directives: List[DirectiveCard]
    timeline: List[TimelineEvent]
    ai_deliberation_status: str = "DELIBERATED_BY_GEMINI"
    ai_status_message: Optional[str] = None


@router.get(
    "/boardroom",
    response_model=BoardroomOverviewResponse,
    summary="Get Agent Boardroom Snapshot",
    description="Returns current statuses of all 3 tiers, active directives, and the real-time debate timeline."
)
async def get_boardroom_overview(
    current_user_id: str = Depends(get_current_user)
) -> BoardroomOverviewResponse:
    storage = get_boardroom_storage()
    orchestrator = get_orchestrator()

    all_active = storage.list_directives(status=DirectiveStatus.PENDING_REVIEW)
    all_historical = [
        d for d in storage.list_directives()
        if d.user_status != DirectiveStatus.PENDING_REVIEW
    ]

    # Strictly filter for pure Indian equities (no ETFs, US stocks, or unlisted shares)
    active = [
        d for d in all_active
        if not d.actions or is_pure_equity_stock(d.actions[0].symbol)
    ]
    historical = [
        d for d in all_historical
        if not d.actions or is_pure_equity_stock(d.actions[0].symbol)
    ]
    timeline = storage.get_timeline(limit=100)
    ai_info = get_boss_ai_status()

    return BoardroomOverviewResponse(
        agents=orchestrator.get_agent_profiles(),
        active_directives=active,
        historical_directives=historical,
        timeline=timeline,
        ai_deliberation_status=ai_info["status"],
        ai_status_message=ai_info["message"],
    )


@router.post(
    "/run",
    response_model=BoardroomOverviewResponse,
    summary="Trigger Boardroom Deliberation Cycle",
    description="Executes a full deliberation across Risk Officer, Reviewer, and Financial Planning Boss."
)
async def run_boardroom_review(
    current_user_id: str = Depends(get_current_user)
) -> BoardroomOverviewResponse:
    holdings_repo = HoldingsRepository()
    persisted_holdings = await holdings_repo.get_holdings(owner_id=current_user_id)

    # Convert Holding models to dicts for the agent engine
    raw_holdings = []
    total_val = 0.0
    for h in persisted_holdings:
        # Resolve symbol defensively across models and dicts
        symbol = (
            getattr(h, "instrument_symbol", None)
            or getattr(h, "symbol", None)
            or getattr(h, "tradingsymbol", None)
            or (h.get("instrument_symbol") if isinstance(h, dict) else None)
            or (h.get("symbol") if isinstance(h, dict) else None)
            or ""
        )
        if not symbol:
            continue

        raw_asset_class = str(getattr(h, "asset_class", "") or (h.get("asset_class", "") if isinstance(h, dict) else "") or "")
        if not is_pure_equity_stock(symbol, asset_class=raw_asset_class):
            continue

        qty = float(getattr(h, "quantity", 0.0) or (h.get("quantity", 0.0) if isinstance(h, dict) else 0.0) or 0.0)
        avg_price = float(getattr(h, "average_price", 0.0) or (h.get("average_price", 0.0) if isinstance(h, dict) else 0.0) or 0.0)
        cur_price = float(
            getattr(h, "current_price", None)
            or getattr(h, "last_price", None)
            or (h.get("current_price") if isinstance(h, dict) else None)
            or (h.get("last_price") if isinstance(h, dict) else None)
            or avg_price
            or 0.0
        )
        cur_val = float(
            getattr(h, "current_value", None)
            or (h.get("current_value") if isinstance(h, dict) else None)
            or (qty * cur_price)
            or 0.0
        )
        total_val += cur_val

        # Infer broker provider from connection_id or field
        conn_id = str(getattr(h, "connection_id", "") or (h.get("connection_id", "") if isinstance(h, dict) else "")).lower()
        if "zerodha" in conn_id or "kite" in conn_id:
            broker_name = "zerodha"
        elif "groww" in conn_id:
            broker_name = "groww"
        elif "indmoney" in conn_id:
            broker_name = "indmoney"
        else:
            broker_name = getattr(h, "broker", None) or (h.get("broker") if isinstance(h, dict) else None) or "portfolio"

        raw_holdings.append({
            "symbol": symbol,
            "instrument_symbol": symbol,
            "tradingsymbol": symbol,
            "broker": broker_name,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": cur_price,
            "current_value": cur_val
        })

    orchestrator = get_orchestrator()
    await orchestrator.run_review_cycle(
        holdings=raw_holdings,
        total_portfolio_value=total_val,
        benchmark_nifty_move_pct=0.0,
        trigger_source=f"USER_REQUEST ({current_user_id})",
        owner_id=current_user_id
    )

    storage = get_boardroom_storage()
    all_active = storage.list_directives(status=DirectiveStatus.PENDING_REVIEW)
    all_historical = [
        d for d in storage.list_directives()
        if d.user_status != DirectiveStatus.PENDING_REVIEW
    ]

    # Strictly filter for pure Indian equities (no ETFs, US stocks, or unlisted shares)
    active = [
        d for d in all_active
        if not d.actions or is_pure_equity_stock(d.actions[0].symbol)
    ]
    historical = [
        d for d in all_historical
        if not d.actions or is_pure_equity_stock(d.actions[0].symbol)
    ]
    timeline = storage.get_timeline(limit=100)
    ai_info = get_boss_ai_status()

    return BoardroomOverviewResponse(
        agents=orchestrator.get_agent_profiles(),
        active_directives=active,
        historical_directives=historical,
        timeline=timeline,
        ai_deliberation_status=ai_info["status"],
        ai_status_message=ai_info["message"],
    )


@router.post(
    "/directives/{directive_id}/status",
    response_model=DirectiveCard,
    summary="Update Directive Closure Status",
    description="Marks a directive as 'ORDER_PLACED_AT_BROKER', 'IGNORED', or 'SNOOZED'."
)
async def update_directive_status(
    directive_id: str,
    req: DirectiveStatusUpdateRequest,
    current_user_id: str = Depends(get_current_user)
) -> DirectiveCard:
    storage = get_boardroom_storage()
    updated = storage.update_directive_status(
        directive_id=directive_id,
        new_status=req.status,
        user_comment=req.user_comment
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directive '{directive_id}' not found."
        )
    return updated


@router.get(
    "/dossier/{symbol}",
    response_model=InvestigationDossier,
    summary="Get Forensic Due-Diligence Dossier for a Stock",
    description="Scrapes free public news and financials, computes causality and forensic risk score for any stock symbol."
)
async def get_stock_dossier(
    symbol: str,
    current_user_id: str = Depends(get_current_user)
) -> InvestigationDossier:
    clean_sym = clean_symbol(symbol)
    disp_name = clean_display_name(symbol)
    dossier = await build_investigation_dossier(clean_sym, company_name=disp_name)
    return dossier


# ==========================================
# Ground-Level Scout Swarm Endpoints
# ==========================================

class GroundSwarmOverviewResponse(BaseModel):
    dossiers: List[GroundStockDossier]
    status: Dict[str, Any]


@router.get(
    "/ground/dossiers",
    response_model=GroundSwarmOverviewResponse,
    summary="Get Ground-Level Intelligence Dossiers",
    description="Returns multidimensional ground scout reports (Risk, Tech, Pattern, Funda, News, Insider) for all holdings."
)
async def get_ground_dossiers(
    current_user_id: str = Depends(get_current_user)
) -> GroundSwarmOverviewResponse:
    swarm = get_ground_swarm_orchestrator()
    dossiers = swarm.get_all_dossiers()
    status_info = swarm.get_status()
    return GroundSwarmOverviewResponse(dossiers=dossiers, status=status_info)


@router.get(
    "/ground/status",
    summary="Get Live Ground Swarm Status",
    description="Returns live scanning state, active stock, and currently executing ground scout."
)
async def get_ground_status(
    current_user_id: str = Depends(get_current_user)
) -> Dict[str, Any]:
    swarm = get_ground_swarm_orchestrator()
    return swarm.get_status()


@router.post(
    "/ground/scan",
    summary="Trigger Sequential Ground Scout Scan",
    description="Initiates sequential ground scout execution across holdings with deliberate rate pacing."
)
async def trigger_ground_scan(
    inter_stock_delay: float = Query(default=3.0, ge=0.0, le=10.0, description="Pause in seconds between stocks"),
    current_user_id: str = Depends(get_current_user)
) -> Dict[str, Any]:
    repo = HoldingsRepository()
    persisted_holdings = await repo.get_holdings(owner_id=current_user_id)
    if not persisted_holdings:
        return {"status": "NO_HOLDINGS", "message": "No portfolio holdings found for user."}

    raw_holdings = []
    total_val = 0.0
    for h in persisted_holdings:
        symbol = (
            getattr(h, "instrument_symbol", None)
            or getattr(h, "symbol", None)
            or getattr(h, "tradingsymbol", None)
            or (h.get("instrument_symbol") if isinstance(h, dict) else None)
            or (h.get("symbol") if isinstance(h, dict) else None)
            or ""
        )
        if not symbol:
            continue

        raw_asset_class = str(getattr(h, "asset_class", "") or (h.get("asset_class", "") if isinstance(h, dict) else "") or "")
        if not is_pure_equity_stock(symbol, asset_class=raw_asset_class):
            continue
        
        name = getattr(h, "name", None) or (h.get("name") if isinstance(h, dict) else None) or ""
        asset_class = str(getattr(h, "asset_class", "") or (h.get("asset_class", "") if isinstance(h, dict) else ""))
        currency = str(getattr(h, "currency", "") or (h.get("currency", "") if isinstance(h, dict) else ""))
        if not is_pure_equity_stock(symbol, name=name, asset_class=asset_class, currency=currency):
            continue

        qty = float(getattr(h, "quantity", 0.0) or (h.get("quantity", 0.0) if isinstance(h, dict) else 0.0) or 0.0)
        avg_price = float(getattr(h, "average_price", 0.0) or (h.get("average_price", 0.0) if isinstance(h, dict) else 0.0) or 0.0)
        cur_price = float(
            getattr(h, "current_price", None)
            or getattr(h, "last_price", None)
            or (h.get("current_price") if isinstance(h, dict) else None)
            or (h.get("last_price") if isinstance(h, dict) else None)
            or avg_price
            or 0.0
        )
        cur_val = qty * cur_price
        total_val += cur_val
        raw_holdings.append({
            "symbol": symbol,
            "tradingsymbol": symbol,
            "name": name,
            "asset_class": asset_class,
            "currency": currency,
            "quantity": qty,
            "average_price": avg_price,
            "last_price": cur_price,
            "current_value": cur_val,
        })
    
    swarm = get_ground_swarm_orchestrator()
    if swarm.get_status().get("is_scanning"):
        return {"status": "ALREADY_RUNNING", "message": "Ground swarm is already executing a scan."}

    # Run in background task so API responds immediately
    import asyncio
    asyncio.create_task(
        swarm.run_swarm_cycle(
            holdings=raw_holdings,
            total_portfolio_value=total_val,
            owner_id=current_user_id,
            inter_stock_delay=inter_stock_delay
        )
    )

    return {
        "status": "INITIATED",
        "message": f"Ground scout scan initiated for {len(raw_holdings)} holdings with {inter_stock_delay}s deliberate pacing.",
        "holdings_count": len(raw_holdings)
    }


@router.get(
    "/ground/dossier/{symbol}",
    response_model=Optional[GroundStockDossier],
    summary="Get Ground Dossier for Single Stock"
)
async def get_single_ground_dossier(
    symbol: str,
    current_user_id: str = Depends(get_current_user)
) -> Optional[GroundStockDossier]:
    swarm = get_ground_swarm_orchestrator()
    dossier = swarm.get_dossier(symbol)
    if not dossier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ground dossier for '{symbol}' not found. Run a ground scan first."
        )
    return dossier

