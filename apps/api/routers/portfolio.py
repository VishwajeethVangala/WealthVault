"""Portfolio Management, Sync, and Aggregation Router.

Provides endpoints for:
- GET /api/v1/portfolio/holdings: Real-time query of canonical holdings.
- POST /api/v1/portfolio/sync: Full orchestration pipeline (Live Fetch -> Blob Archive -> Normalize -> Table Upsert -> Snapshot Compute -> Snapshot Persist).
- GET /api/v1/portfolio/summary: Consolidated summary of latest snapshot, asset allocation, and connection statuses.
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from apps.api.routers.accounts import get_current_user
from core.market_data import get_market_data_service
from core.market_data.indmoney_client import IndmoneyAuthRequiredError, get_indmoney_mcp_client
from core.market_data.kite_client import get_kite_mcp_client
from core.market_data.user_client import get_user_kite_client
from core.models import (
    BrokerCatalogItem,
    BrokerDeleteResponse,
    BrokerSessionInfo,
    BrokerStatus,
    CreateBrokerConnectionRequest,
    CredentialField,
    CredentialSaveRequest,
    CredentialSaveResponse,
    Holding,
    MarketQuotesResponse,
    PortfolioSnapshot,
    PortfolioSummaryResponse,
    PortfolioSyncResponse,
    QuoteItem,
    ReauthRequest,
)
from core.portfolio.aggregation import PortfolioAggregationService
from core.portfolio.normalization import NormalizationService
from core.credentials import CredentialStoreError
from providers.brokers.angelone import AngelOneAuthRequiredError, AngelOneProvider
from providers.brokers.groww import GrowwAuthRequiredError, GrowwProvider
from providers.brokers.indmoney import IndmoneyProvider
from providers.brokers.zerodha import KiteAuthRequiredError, ZerodhaProvider
from storage.blobs.archive import archive_broker_payload, purge_broker_blobs
from storage.tables.repositories import (
    BrokerConnectionRepository,
    BrokerCredentialRepository,
    HoldingsRepository,
    SnapshotsRepository,
)

logger = logging.getLogger("wealthvault.api.portfolio")

# Comprehensive custodian metadata catalog for Indian & Global wealth management
BROKER_METADATA_CATALOG = {
    "zerodha": {
        "display_name": "Zerodha Kite Connect",
        "auth_type": "Daily Kite OAuth / Enctoken",
        "mcp_server_url": "https://mcp.kite.trade/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#e03a3c",
        "tag": "ZK",
        "supported": True,
        "description": "Direct Demat equity, F&O, and Coin mutual funds via Kite Connect MCP.",
    },
    "indmoney": {
        "display_name": "INDmoney Private Wealth",
        "auth_type": "Biometric OAuth2 Bearer",
        "mcp_server_url": "https://mcp.indmoney.com/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#4f46e5",
        "tag": "IND",
        "supported": True,
        "description": "Unified US tech equities, Indian stocks, NPS Tier 1, and fixed income bonds.",
    },
    "groww": {
        "display_name": "Groww",
        "auth_type": "Trade API key + daily approval",
        "mcp_server_url": "https://api.groww.in",
        "mcp_protocol": "REST (Groww Trade API)",
        "default_account_id": "",
        "color": "#00d09c",
        "tag": "GRW",
        "supported": True,
        "description": "Demat stock holdings via the Groww Trade API. Prices come from your Kite session.",
        "setup_url": "https://groww.in/trade-api/api-keys",
        "setup_steps": [
            "Subscribe to a Groww Trading API plan (the free plan is enough).",
            "Generate an API key and secret at groww.in/trade-api/api-keys.",
            "Approve the key there each day; Groww access tokens reset at 6 AM IST.",
        ],
        "credential_fields": [
            {"key": "api_key", "label": "API key", "secret": True, "required": True, "help": "From the Groww API keys page."},
            {"key": "api_secret", "label": "API secret", "secret": True, "required": False, "help": "Needed unless you give a TOTP secret."},
            {"key": "totp_secret", "label": "TOTP secret", "secret": True, "required": False, "help": "Alternative to the API secret (the base32 seed of your authenticator)."},
        ],
    },
    "upstox": {
        "display_name": "Upstox Pro",
        "auth_type": "Upstox API v2 OAuth",
        "mcp_server_url": "https://mcp.upstox.com/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#7b2cbf",
        "tag": "UPX",
        "supported": False,
        "coming_soon": True,
        "description": "Low-latency NSE/BSE equities, commodities, and derivatives.",
    },
    "angelone": {
        "display_name": "Angel One",
        "auth_type": "SmartAPI key + PIN + TOTP",
        "mcp_server_url": "https://apiconnect.angelone.in",
        "mcp_protocol": "REST (SmartAPI)",
        "default_account_id": "",
        "color": "#ff5722",
        "tag": "ANG",
        "supported": True,
        "description": "Demat holdings with live prices via Angel One SmartAPI.",
        "setup_url": "https://smartapi.angelone.in/",
        "setup_steps": [
            "Create a SmartAPI app at smartapi.angelone.in and copy its API key.",
            "Enable TOTP on your Angel One account and keep the base32 secret shown at setup.",
            "Enter your client code, PIN and TOTP secret below.",
        ],
        "credential_fields": [
            {"key": "api_key", "label": "SmartAPI key", "secret": True, "required": True, "help": "From your SmartAPI app."},
            {"key": "client_code", "label": "Client code", "secret": False, "required": True, "help": "Your Angel One login ID."},
            {"key": "pin", "label": "PIN / MPIN", "secret": True, "required": True, "help": "Your 4-digit login PIN."},
            {"key": "totp_secret", "label": "TOTP secret", "secret": True, "required": True, "help": "The base32 seed of your authenticator, not a 6-digit code."},
        ],
    },
    "dhan": {
        "display_name": "Dhan HQ",
        "auth_type": "DhanHQ Access Token",
        "mcp_server_url": "https://mcp.dhan.co/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#2563eb",
        "tag": "DHN",
        "supported": False,
        "coming_soon": True,
        "description": "Lightning-fast equity investing and SuperFast trading ledger.",
    },
    "icicidirect": {
        "display_name": "ICICI Direct Breeze",
        "auth_type": "Breeze API Session Key",
        "mcp_server_url": "https://mcp.icicidirect.com/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#ea580c",
        "tag": "ICI",
        "supported": False,
        "coming_soon": True,
        "description": "ICICI Securities 3-in-1 banking, equity, and sovereign gold bond ledger.",
    },
    "hdfcsky": {
        "display_name": "HDFC SKY",
        "auth_type": "HDFC Securities OAuth",
        "mcp_server_url": "https://mcp.hdfcsky.com/mcp",
        "mcp_protocol": "MCP Stdio / JSON-RPC v2.0",
        "color": "#0ea5e9",
        "tag": "SKY",
        "supported": False,
        "coming_soon": True,
        "description": "HDFC digital brokerage platform for multi-asset wealth management.",
    },
}

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])

# Brokers that authenticate with user-supplied API credentials stored (encrypted) in Azure
CREDENTIAL_BROKERS = {
    "groww": (GrowwProvider, GrowwAuthRequiredError),
    "angelone": (AngelOneProvider, AngelOneAuthRequiredError),
}


async def _pull_credential_broker(
    owner_id: str,
    conn: Any,
    sync_time: datetime,
    normalizer: NormalizationService,
    connections_repo: BrokerConnectionRepository,
) -> Optional[tuple]:
    """Fetch, archive and normalize holdings for a credential-based broker connection.

    Returns (holdings, blob_path), or None when the pull failed. The connection status is updated
    either way, so callers can keep the previously stored holdings on failure.
    """
    broker = conn.broker_name.lower().strip()
    provider_cls, auth_error_cls = CREDENTIAL_BROKERS[broker]
    provider = provider_cls(owner_id=owner_id, connection_id=conn.connection_id)
    try:
        raw = await provider.get_holdings()
        blob = await archive_broker_payload(
            owner_id=owner_id, connection_id=conn.connection_id, raw_data=raw, timestamp=sync_time
        )
        holdings = normalizer.normalize_holdings(
            raw_data=raw, broker_name=broker, owner_id=owner_id, connection_id=conn.connection_id
        )
        await connections_repo.update_status(
            owner_id=owner_id,
            connection_id=conn.connection_id,
            status=BrokerStatus.CONNECTED,
            last_sync_time=sync_time.isoformat(),
        )
        return holdings, blob
    except (auth_error_cls, CredentialStoreError) as exc:
        logger.warning("%s connection %s needs attention: %s", broker, conn.connection_id, exc)
        await connections_repo.update_status(
            owner_id=owner_id, connection_id=conn.connection_id, status=BrokerStatus.AUTH_REQUIRED
        )
    except Exception as exc:
        logger.error("%s connection %s sync failed: %s", broker, conn.connection_id, exc)
        await connections_repo.update_status(
            owner_id=owner_id, connection_id=conn.connection_id, status=BrokerStatus.PROVIDER_ERROR
        )
    return None


@router.get(
    "/holdings",
    response_model=List[Holding],
    status_code=status.HTTP_200_OK,
    summary="Get Normalized Portfolio Holdings with Live Market Quotes",
    description="Fetches holdings from Zerodha and INDmoney MCP providers, enriches with live market data quotes (LTP), and returns a unified canonical portfolio.",
)
async def get_portfolio_holdings(
    broker: str = Query(
        default="all",
        description="Filter broker provider ('all', 'zerodha', or 'indmoney')",
    ),
    connection_id: Optional[str] = Query(
        default=None,
        description="Optional connection identifier",
    ),
    refresh_live: bool = Query(
        default=True,
        description="Whether to enrich holdings with real-time market data quotes from MCP",
    ),
    current_user_id: str = Depends(get_current_user),
) -> List[Holding]:
    """Fetch and normalize unified holdings for the authenticated user, enriched with live MCP market quotes."""
    selected_broker = broker.lower().strip() if isinstance(broker, str) else "all"
    conn_id = str(connection_id) if connection_id and not hasattr(connection_id, "default") else None
    holdings_repo = HoldingsRepository()
    market_service = get_market_data_service()

    # If persisted holdings are present, filter and return
    persisted = await holdings_repo.get_holdings(owner_id=current_user_id)
    if persisted and not (refresh_live and selected_broker != "all" and not conn_id):
        filtered = persisted
        if conn_id:
            filtered = [h for h in persisted if h.connection_id.lower() == conn_id.lower()]
        elif selected_broker == "zerodha":
            filtered = [h for h in persisted if "zerodha" in h.connection_id.lower() or h.holding_id.startswith("hld_zk")]
        elif selected_broker == "indmoney":
            filtered = [h for h in persisted if "indmoney" in h.connection_id.lower() or h.holding_id.startswith("hld_ind")]

        if refresh_live:
            try:
                enriched, _ = await market_service.enrich_holdings_with_live_quotes(filtered, client=await get_user_kite_client(current_user_id))
                return enriched
            except Exception as quote_err:
                logger.warning("Market quote enrichment note for persisted holdings: %s", quote_err)
        return filtered

    normalizer = NormalizationService()
    unified_holdings: List[Holding] = []

    # 1. Fetch from Zerodha if requested
    if selected_broker in ("all", "zerodha"):
        zk_provider = ZerodhaProvider(connection_id=conn_id or "conn_zerodha_live")
        try:
            zk_raw = await zk_provider.get_holdings()
            zk_norm = normalizer.normalize_holdings(
                raw_data=zk_raw,
                broker_name="zerodha",
                owner_id=current_user_id,
                connection_id=conn_id or "conn_zerodha_live",
            )
            unified_holdings.extend(zk_norm)
        except Exception as exc:
            logger.error("Error fetching Zerodha holdings: %s", exc)

    # 2. Fetch from INDmoney if requested
    if selected_broker in ("all", "indmoney"):
        ind_provider = IndmoneyProvider(connection_id=conn_id or "conn_indmoney_live")
        try:
            ind_raw = await ind_provider.get_holdings()
            ind_norm = normalizer.normalize_holdings(
                raw_data=ind_raw,
                broker_name="indmoney",
                owner_id=current_user_id,
                connection_id=conn_id or "conn_indmoney_live",
            )
            unified_holdings.extend(ind_norm)
        except Exception as exc:
            logger.error("Error fetching INDmoney holdings: %s", exc)

    # 3. Enrich unified holdings with live market data quotes from MCP
    if refresh_live and unified_holdings:
        try:
            enriched, _ = await market_service.enrich_holdings_with_live_quotes(unified_holdings, client=await get_user_kite_client(current_user_id))
            return enriched
        except Exception as quote_err:
            logger.warning("Market quote enrichment note for live holdings: %s", quote_err)

    logger.info(
        "Returned %d unified holdings for user %s (broker filter: %s)",
        len(unified_holdings),
        current_user_id,
        selected_broker,
    )
    return unified_holdings


@router.get(
    "/quotes",
    response_model=MarketQuotesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Real-Time Market Quotes from MCP",
    description="Fetches live market data quotes (LTP, OHLC, net changes) directly from Kite MCP with in-memory TTL caching.",
)
async def get_market_quotes(
    instruments: str = Query(
        ...,
        description="Comma-separated instrument symbols in EXCHANGE:SYMBOL format (e.g. 'NSE:INFY,NSE:RELIANCE')",
    ),
    current_user_id: str = Depends(get_current_user),
) -> MarketQuotesResponse:
    """Fetch live market data quotes from MCP with TTL cache protection."""
    market_service = get_market_data_service()
    inst_list = [i.strip().upper() for i in instruments.split(",") if i.strip()]
    quotes_map, live_succeeded = await market_service.fetch_live_quotes(inst_list, client=await get_user_kite_client(current_user_id))
    freshness = "live" if live_succeeded else "cached"

    return MarketQuotesResponse(
        status="success",
        data_freshness=freshness,
        live_count=len(quotes_map) if live_succeeded else 0,
        cached_count=len(quotes_map) if not live_succeeded else 0,
        quotes=quotes_map,
    )


@router.post(
    "/sync",
    response_model=PortfolioSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Orchestrate Full Portfolio Synchronization",
    description=(
        "Fetches live holdings from Zerodha and INDmoney, archives raw JSON to Azure Blob Storage, "
        "normalizes holdings, batch upserts to Holdings Table, computes daily PortfolioSnapshot, "
        "persists to Snapshots Table, and updates broker sync timestamps."
    ),
)
async def sync_portfolio(
    current_user_id: str = Depends(get_current_user),
) -> PortfolioSyncResponse:
    """Execute end-to-end multi-broker sync, archiving, normalization, and snapshot computation."""
    sync_time = datetime.now(timezone.utc)
    normalizer = NormalizationService()
    aggregator = PortfolioAggregationService()
    holdings_repo = HoldingsRepository()
    snapshots_repo = SnapshotsRepository()
    connections_repo = BrokerConnectionRepository()

    all_holdings: List[Holding] = []
    archived_blob_paths: List[str] = []

    active_conns = await connections_repo.list_connections(owner_id=current_user_id)
    if not active_conns and not await connections_repo.is_tenant_initialized(owner_id=current_user_id):
        await get_broker_sessions(current_user_id=current_user_id)
        active_conns = await connections_repo.list_connections(owner_id=current_user_id)

    persisted_all = await holdings_repo.get_holdings(owner_id=current_user_id)

    # Sync each registered connection individually according to its custodian protocol
    for conn in active_conns:
        b_name = conn.broker_name.lower().strip()
        conn_id = conn.connection_id

        if b_name == "zerodha":
            zk_provider = ZerodhaProvider(connection_id=conn_id)
            try:
                zk_raw = await zk_provider.get_holdings()
                zk_blob = await archive_broker_payload(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    raw_data=zk_raw,
                    timestamp=sync_time,
                )
                archived_blob_paths.append(zk_blob)

                zk_normalized = normalizer.normalize_holdings(
                    raw_data=zk_raw,
                    broker_name="zerodha",
                    owner_id=current_user_id,
                    connection_id=conn_id,
                )
                all_holdings.extend(zk_normalized)

                await connections_repo.update_status(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    status=BrokerStatus.CONNECTED,
                    last_sync_time=sync_time.isoformat(),
                )
            except KiteAuthRequiredError as auth_exc:
                logger.warning("Zerodha connection %s requires authorization: %s", conn_id, auth_exc)
                await connections_repo.update_status(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    status=BrokerStatus.AUTH_REQUIRED,
                    last_sync_time=sync_time.isoformat(),
                )
                all_holdings.extend(h for h in persisted_all if h.connection_id == conn_id)
            except Exception as exc:
                logger.error("Zerodha connection %s sync failed during orchestration: %s", conn_id, exc)
                all_holdings.extend(h for h in persisted_all if h.connection_id == conn_id)

        elif b_name == "indmoney":
            ind_provider = IndmoneyProvider(connection_id=conn_id)
            try:
                ind_raw = await ind_provider.get_holdings()
                ind_blob = await archive_broker_payload(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    raw_data=ind_raw,
                    timestamp=sync_time,
                )
                archived_blob_paths.append(ind_blob)

                ind_normalized = normalizer.normalize_holdings(
                    raw_data=ind_raw,
                    broker_name="indmoney",
                    owner_id=current_user_id,
                    connection_id=conn_id,
                )
                all_holdings.extend(ind_normalized)

                await connections_repo.update_status(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    status=BrokerStatus.CONNECTED,
                    last_sync_time=sync_time.isoformat(),
                )
            except IndmoneyAuthRequiredError as auth_exc:
                logger.warning("INDmoney connection %s requires authorization: %s", conn_id, auth_exc)
                await connections_repo.update_status(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    status=BrokerStatus.AUTH_REQUIRED,
                    last_sync_time=sync_time.isoformat(),
                )
                all_holdings.extend(h for h in persisted_all if h.connection_id == conn_id)
            except Exception as exc:
                logger.error("INDmoney connection %s sync failed during orchestration: %s", conn_id, exc)
                await connections_repo.update_status(
                    owner_id=current_user_id,
                    connection_id=conn_id,
                    status=BrokerStatus.DISCONNECTED,
                    last_sync_time=sync_time.isoformat(),
                )
                all_holdings.extend(h for h in persisted_all if h.connection_id == conn_id)
        elif b_name in CREDENTIAL_BROKERS:
            pulled = await _pull_credential_broker(current_user_id, conn, sync_time, normalizer, connections_repo)
            if pulled is None:
                # Keep what we already had for this connection rather than dropping it
                all_holdings.extend(h for h in persisted_all if h.connection_id == conn_id)
            else:
                cred_holdings, cred_blob = pulled
                all_holdings.extend(cred_holdings)
                archived_blob_paths.append(cred_blob)
        else:
            # Preserve persisted holdings for other linked connections
            other_holdings = [h for h in persisted_all if h.connection_id == conn_id]
            all_holdings.extend(other_holdings)
            await connections_repo.update_status(
                owner_id=current_user_id,
                connection_id=conn_id,
                status=conn.status,
                last_sync_time=sync_time.isoformat(),
            )

    # --- 3. Live Market Quote Enrichment before snapshot calculation ---
    market_service = get_market_data_service()
    if all_holdings:
        try:
            all_holdings, _ = await market_service.enrich_holdings_with_live_quotes(all_holdings, client=await get_user_kite_client(current_user_id))
        except Exception as q_err:
            logger.warning("Quote enrichment during sync note: %s", q_err)

    # --- 4. Idempotent Holdings Update: Purge Stale Records and Batch Upsert ---
    upserted_count = await holdings_repo.replace_holdings(owner_id=current_user_id, holdings=all_holdings)

    # --- 5. Compute Daily Portfolio Snapshot ---
    as_of_date = sync_time.strftime("%Y-%m-%d")
    snapshot = aggregator.calculate_snapshot(
        owner_id=current_user_id,
        holdings=all_holdings,
        as_of_date=as_of_date,
    )

    # --- 6. Persist Snapshot to Snapshots Table ---
    saved_snapshot = await snapshots_repo.save_snapshot(snapshot)

    logger.info(
        "Orchestrated sync completed for user %s: %d holdings persisted, snapshot %s saved, %d blobs archived",
        current_user_id,
        upserted_count,
        saved_snapshot.snapshot_id,
        len(archived_blob_paths),
    )

    return PortfolioSyncResponse(
        status="success",
        synced_at=sync_time.isoformat(),
        holdings_upserted=upserted_count,
        archived_payloads=archived_blob_paths,
        snapshot=saved_snapshot,
    )


@router.get(
    "/summary",
    response_model=PortfolioSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Consolidated Portfolio Summary & Asset Allocation",
    description="Returns the latest computed portfolio snapshot, asset allocation breakdown, and connected broker statuses.",
)
async def get_portfolio_summary(
    current_user_id: str = Depends(get_current_user),
) -> PortfolioSummaryResponse:
    """Fetch latest portfolio snapshot and active broker connection statuses."""
    snapshots_repo = SnapshotsRepository()
    connections_repo = BrokerConnectionRepository()

    # 1. Fetch latest snapshot
    latest_snapshot = await snapshots_repo.get_latest_snapshot(owner_id=current_user_id)

    # Fallback to computing fresh snapshot if none exists
    if not latest_snapshot:
        holdings = await get_portfolio_holdings(broker="all", connection_id=None, current_user_id=current_user_id)
        aggregator = PortfolioAggregationService()
        latest_snapshot = aggregator.calculate_snapshot(
            owner_id=current_user_id,
            holdings=holdings,
            as_of_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        await snapshots_repo.save_snapshot(latest_snapshot)

    # 2. Fetch connection statuses
    connections = await connections_repo.list_connections(owner_id=current_user_id)

    return PortfolioSummaryResponse(
        owner_id=current_user_id,
        snapshot=latest_snapshot,
        connections=connections,
    )


@router.get(
    "/sessions",
    response_model=List[BrokerSessionInfo],
    status_code=status.HTTP_200_OK,
    summary="Get Broker MCP Sessions & Telemetry",
    description="Retrieves live Model Context Protocol (MCP) broker sessions, connection health, token expiry, and sync metrics.",
)
async def get_broker_sessions(
    current_user_id: str = Depends(get_current_user),
) -> List[BrokerSessionInfo]:
    """Return comprehensive telemetry for all connected broker MCP sessions."""
    connections_repo = BrokerConnectionRepository()
    holdings_repo = HoldingsRepository()
    credentials_repo = BrokerCredentialRepository()

    # Query or seed connections (only on first-time onboarding for this tenant)
    existing = await connections_repo.list_connections(owner_id=current_user_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    is_init = await connections_repo.is_tenant_initialized(owner_id=current_user_id)
    if not is_init:
        # New tenants start with no connections; brokers are added from the Brokers page
        await connections_repo.mark_tenant_initialized(owner_id=current_user_id)

    # Fetch holdings for metrics calculation
    holdings = await holdings_repo.get_holdings(owner_id=current_user_id)
    if not holdings:
        holdings = await get_portfolio_holdings(broker="all", connection_id=None, current_user_id=current_user_id)

    # Next daily Kite session expiry is 06:00 AM IST (00:30 UTC next day)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    kite_expiry = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if kite_expiry <= now:
        kite_expiry += timedelta(days=1)

    sessions: List[BrokerSessionInfo] = []

    for conn_obj in existing:
        b_name = conn_obj.broker_name.lower().strip()
        conn_id = conn_obj.connection_id

        # Isolate holdings strictly for this connection
        c_holdings = [
            h for h in holdings
            if h.connection_id == conn_id
            or (not h.connection_id and b_name == "zerodha" and conn_id == "conn_zerodha_live" and h.holding_id.startswith("hld_zk"))
            or (not h.connection_id and b_name == "indmoney" and conn_id == "conn_indmoney_live" and h.holding_id.startswith("hld_ind"))
        ]
        c_val = sum(h.current_value for h in c_holdings)

        if b_name == "zerodha":
            zk_provider = ZerodhaProvider(connection_id=conn_id)
            zk_status = conn_obj.status
            zk_auth_url: Optional[str] = None
            zk_account_id = conn_obj.account_id or ""

            if conn_obj.status in (BrokerStatus.SESSION_EXPIRED, BrokerStatus.DISCONNECTED):
                try:
                    zk_auth_url = await zk_provider.get_login_url()
                except Exception as exc:
                    logger.warning("Could not fetch Kite auth URL for %s: %s", conn_id, exc)
            else:
                try:
                    acct_status = await zk_provider.get_account_status()
                    if acct_status.get("status") == "auth_required":
                        zk_status = BrokerStatus.AUTH_REQUIRED
                        zk_auth_url = acct_status.get("auth_url")
                    elif acct_status.get("status") == "success":
                        zk_status = BrokerStatus.CONNECTED
                        if acct_status.get("data", {}).get("user_id"):
                            zk_account_id = acct_status["data"]["user_id"]
                except Exception as exc:
                    logger.warning("Zerodha status probe note for %s: %s", conn_id, exc)
                    zk_status = BrokerStatus.AUTH_REQUIRED
                    zk_auth_url = await zk_provider.get_login_url()

            if zk_status != BrokerStatus.CONNECTED and not zk_auth_url:
                try:
                    zk_auth_url = await zk_provider.get_login_url()
                except Exception:
                    pass

            zk_is_expired = zk_status in (BrokerStatus.SESSION_EXPIRED, BrokerStatus.AUTH_REQUIRED, BrokerStatus.DISCONNECTED)
            disp_name = f"Zerodha Kite Connect — {conn_obj.account_label}" if conn_obj.account_label else "Zerodha Kite Connect"

            sessions.append(
                BrokerSessionInfo(
                    connection_id=conn_id,
                    owner_id=current_user_id,
                    broker_name="zerodha",
                    display_name=disp_name,
                    status=zk_status,
                    last_sync_time=conn_obj.last_sync_time or now_iso,
                    account_id=zk_account_id,
                    account_label=conn_obj.account_label,
                    auth_type="Daily Kite OAuth / Enctoken",
                    session_expires_at=kite_expiry.isoformat(),
                    is_expired=zk_is_expired,
                    mcp_server_url="https://mcp.kite.trade/mcp",
                    mcp_protocol="MCP Stdio / JSON-RPC v2.0",
                    holdings_count=len(c_holdings),
                    total_valuation=c_val,
                    auth_url=zk_auth_url,
                )
            )
        elif b_name == "indmoney":
            ind_provider = IndmoneyProvider(connection_id=conn_id)
            ind_status = conn_obj.status
            ind_auth_url: Optional[str] = None
            ind_account_id = conn_obj.account_id or ""

            if conn_obj.status in (BrokerStatus.SESSION_EXPIRED, BrokerStatus.DISCONNECTED):
                try:
                    client = get_indmoney_mcp_client(connection_id=conn_id)
                    ind_auth_url = client.get_authorization_url()
                except Exception as exc:
                    logger.warning("Could not fetch INDmoney auth URL for %s: %s", conn_id, exc)
            else:
                try:
                    acct_status = await ind_provider.get_account_status()
                    if acct_status.get("status") == "auth_required":
                        ind_status = BrokerStatus.AUTH_REQUIRED
                        ind_auth_url = acct_status.get("auth_url")
                    elif acct_status.get("status") == "success":
                        ind_status = BrokerStatus.CONNECTED
                except Exception as exc:
                    logger.warning("INDmoney status probe note for %s: %s", conn_id, exc)
                    ind_status = BrokerStatus.AUTH_REQUIRED
                    ind_auth_url = ind_provider.client.get_authorization_url()

            if ind_status != BrokerStatus.CONNECTED and not ind_auth_url:
                ind_auth_url = get_indmoney_mcp_client(connection_id=conn_id).get_authorization_url()

            ind_is_expired = ind_status in (BrokerStatus.SESSION_EXPIRED, BrokerStatus.AUTH_REQUIRED, BrokerStatus.DISCONNECTED)
            disp_name = f"INDmoney Private Wealth — {conn_obj.account_label}" if conn_obj.account_label else "INDmoney Private Wealth"

            sessions.append(
                BrokerSessionInfo(
                    connection_id=conn_id,
                    owner_id=current_user_id,
                    broker_name="indmoney",
                    display_name=disp_name,
                    status=ind_status,
                    last_sync_time=conn_obj.last_sync_time or now_iso,
                    account_id=ind_account_id,
                    account_label=conn_obj.account_label,
                    auth_type="Biometric OAuth2 Bearer",
                    is_expired=ind_is_expired,
                    mcp_server_url="https://mcp.indmoney.com/mcp",
                    mcp_protocol="MCP Stdio / JSON-RPC v2.0",
                    holdings_count=len(c_holdings),
                    total_valuation=c_val,
                    auth_url=ind_auth_url,
                )
            )
        else:
            meta = BROKER_METADATA_CATALOG.get(
                b_name,
                {
                    "display_name": b_name.capitalize(),
                    "auth_type": "Custodian API / OAuth",
                    "mcp_server_url": f"https://mcp.{b_name}.com/mcp",
                    "mcp_protocol": "MCP JSON-RPC v2.0",
                                        "color": "#6366f1",
                    "tag": b_name[:3].upper(),
                },
            )
            disp_name = f"{meta.get('display_name', b_name.capitalize())} — {conn_obj.account_label}" if conn_obj.account_label else meta.get('display_name', b_name.capitalize())
            b_status = conn_obj.status
            saved_fields: List[str] = []
            if b_name in CREDENTIAL_BROKERS:
                saved_fields = await credentials_repo.get_fields_set(current_user_id, conn_id)
                if not saved_fields:
                    b_status = BrokerStatus.AUTH_REQUIRED
            b_is_expired = b_status in (BrokerStatus.SESSION_EXPIRED, BrokerStatus.AUTH_REQUIRED, BrokerStatus.DISCONNECTED)

            sessions.append(
                BrokerSessionInfo(
                    connection_id=conn_id,
                    owner_id=current_user_id,
                    broker_name=b_name,
                    display_name=disp_name,
                    status=b_status,
                    last_sync_time=conn_obj.last_sync_time or now_iso,
                    account_id=conn_obj.account_id or "",
                    account_label=conn_obj.account_label,
                    auth_type=meta.get("auth_type", "OAuth2 / API Key"),
                    is_expired=b_is_expired,
                    mcp_server_url=meta.get("mcp_server_url", f"https://mcp.{b_name}.com/mcp"),
                    mcp_protocol=meta.get("mcp_protocol", "MCP JSON-RPC v2.0"),
                    holdings_count=len(c_holdings),
                    total_valuation=c_val,
                    auth_url=meta.get("setup_url") if b_name in CREDENTIAL_BROKERS and b_status != BrokerStatus.CONNECTED else None,
                    credentials_saved=bool(saved_fields),
                )
            )

    return sessions


@router.post(
    "/sessions/{broker_name}/sync",
    response_model=BrokerSessionInfo,
    status_code=status.HTTP_200_OK,
    summary="Synchronize Single Broker Connection",
)
async def sync_single_broker(
    broker_name: str,
    current_user_id: str = Depends(get_current_user),
) -> BrokerSessionInfo:
    """Trigger targeted live sync for a single broker connection or custodian platform."""
    connections_repo = BrokerConnectionRepository()
    connections = await connections_repo.list_connections(owner_id=current_user_id)
    target_conn = next((c for c in connections if c.connection_id.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        target_conn = next((c for c in connections if c.broker_name.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{broker_name}' not found.")

    broker_clean = target_conn.broker_name.lower().strip()
    conn_id = target_conn.connection_id
    sync_time = datetime.now(timezone.utc)
    holdings_repo = HoldingsRepository()
    snapshots_repo = SnapshotsRepository()
    normalizer = NormalizationService()
    aggregator = PortfolioAggregationService()
    market_service = get_market_data_service()

    new_broker_holdings: List[Holding] = []

    # 1. Targeted live pull from requested broker connection
    if broker_clean == "zerodha":
        zk_provider = ZerodhaProvider(connection_id=conn_id)
        try:
            zk_raw = await zk_provider.get_holdings()
            await archive_broker_payload(
                owner_id=current_user_id,
                connection_id=conn_id,
                raw_data=zk_raw,
                timestamp=sync_time,
            )
            new_broker_holdings = normalizer.normalize_holdings(
                raw_data=zk_raw,
                broker_name="zerodha",
                owner_id=current_user_id,
                connection_id=conn_id,
            )
        except KiteAuthRequiredError as auth_exc:
            logger.warning("Zerodha connection %s sync requires authorization: %s", conn_id, auth_exc)
            await connections_repo.update_status(
                owner_id=current_user_id,
                connection_id=conn_id,
                status=BrokerStatus.AUTH_REQUIRED,
                last_sync_time=sync_time.isoformat(),
            )
            sessions = await get_broker_sessions(current_user_id=current_user_id)
            target = next((s for s in sessions if s.connection_id == conn_id), None)
            if target:
                target.auth_url = auth_exc.auth_url
                target.status = BrokerStatus.AUTH_REQUIRED
                return target
        except Exception as exc:
            logger.error("Zerodha connection %s sync failed: %s", conn_id, exc)
            await connections_repo.update_status(
                owner_id=current_user_id,
                connection_id=conn_id,
                status=BrokerStatus.PROVIDER_ERROR,
                last_sync_time=sync_time.isoformat(),
            )
            raise HTTPException(status_code=502, detail=f"Zerodha sync failed for {conn_id}: {exc}")
    elif broker_clean == "indmoney":
        ind_provider = IndmoneyProvider(connection_id=conn_id)
        try:
            ind_raw = await ind_provider.get_holdings()
            await archive_broker_payload(
                owner_id=current_user_id,
                connection_id=conn_id,
                raw_data=ind_raw,
                timestamp=sync_time,
            )
            new_broker_holdings = normalizer.normalize_holdings(
                raw_data=ind_raw,
                broker_name="indmoney",
                owner_id=current_user_id,
                connection_id=conn_id,
            )
        except IndmoneyAuthRequiredError as auth_exc:
            logger.warning("INDmoney connection %s sync requires authorization: %s", conn_id, auth_exc)
            await connections_repo.update_status(
                owner_id=current_user_id,
                connection_id=conn_id,
                status=BrokerStatus.AUTH_REQUIRED,
                last_sync_time=sync_time.isoformat(),
            )
            sessions = await get_broker_sessions(current_user_id=current_user_id)
            target = next((s for s in sessions if s.connection_id == conn_id), None)
            if target:
                target.auth_url = auth_exc.auth_url
                target.status = BrokerStatus.AUTH_REQUIRED
                return target
        except Exception as exc:
            logger.error("INDmoney connection %s sync failed: %s", conn_id, exc)
            await connections_repo.update_status(
                owner_id=current_user_id,
                connection_id=conn_id,
                status=BrokerStatus.DISCONNECTED,
                last_sync_time=sync_time.isoformat(),
            )
            raise HTTPException(
                status_code=502,
                detail=f"INDmoney server communication failure: {exc}",
            )
    elif broker_clean in CREDENTIAL_BROKERS:
        pulled = await _pull_credential_broker(current_user_id, target_conn, sync_time, normalizer, connections_repo)
        if pulled is None:
            sessions = await get_broker_sessions(current_user_id=current_user_id)
            target = next((s for s in sessions if s.connection_id == conn_id), None)
            if not target:
                raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
            return target
        new_broker_holdings, _blob = pulled
    elif broker_clean in BROKER_METADATA_CATALOG and BROKER_METADATA_CATALOG[broker_clean].get("supported", True):
        await connections_repo.update_status(
            owner_id=current_user_id,
            connection_id=conn_id,
            status=BrokerStatus.CONNECTED,
            last_sync_time=sync_time.isoformat(),
        )
        sessions = await get_broker_sessions(current_user_id=current_user_id)
        target = next((s for s in sessions if s.connection_id == conn_id), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
        return target
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported broker: {broker_name}")

    # 2. Enrich newly pulled holdings with live quotes
    if new_broker_holdings:
        try:
            new_broker_holdings, _ = await market_service.enrich_holdings_with_live_quotes(new_broker_holdings, client=await get_user_kite_client(current_user_id))
        except Exception as q_err:
            logger.warning("Single broker quote enrichment note: %s", q_err)

    # 3. Combine with other connections' persisted holdings and batch persist
    existing_holdings = await holdings_repo.get_holdings(owner_id=current_user_id)
    other_holdings = [
        h for h in existing_holdings
        if h.connection_id != conn_id
    ]
    combined_holdings = other_holdings + new_broker_holdings

    await holdings_repo.replace_holdings(owner_id=current_user_id, holdings=combined_holdings)

    # 4. Compute and save updated daily snapshot
    as_of_date = sync_time.strftime("%Y-%m-%d")
    snapshot = aggregator.calculate_snapshot(
        owner_id=current_user_id,
        holdings=combined_holdings,
        as_of_date=as_of_date,
    )
    await snapshots_repo.save_snapshot(snapshot)

    # 5. Update status to CONNECTED and record fresh sync time
    await connections_repo.update_status(
        owner_id=current_user_id,
        connection_id=conn_id,
        status=BrokerStatus.CONNECTED,
        last_sync_time=sync_time.isoformat(),
    )

    sessions = await get_broker_sessions(current_user_id=current_user_id)
    target = next((s for s in sessions if s.connection_id == conn_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
    return target


@router.post(
    "/sessions/{broker_name}/reauth",
    response_model=BrokerSessionInfo,
    status_code=status.HTTP_200_OK,
    summary="Re-authenticate Broker Session",
)
async def reauth_broker(
    broker_name: str,
    payload: Optional[ReauthRequest] = None,
    current_user_id: str = Depends(get_current_user),
) -> BrokerSessionInfo:
    """Re-authenticate an expired or invalid broker session."""
    connections_repo = BrokerConnectionRepository()
    connections = await connections_repo.list_connections(owner_id=current_user_id)
    target_conn = next((c for c in connections if c.connection_id.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        target_conn = next((c for c in connections if c.broker_name.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{broker_name}' not found.")

    sync_time = datetime.now(timezone.utc)
    await connections_repo.update_status(
        owner_id=current_user_id,
        connection_id=target_conn.connection_id,
        status=BrokerStatus.CONNECTED,
        last_sync_time=sync_time.isoformat(),
    )

    sessions = await get_broker_sessions(current_user_id=current_user_id)
    target = next((s for s in sessions if s.connection_id == target_conn.connection_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
    return target


@router.post(
    "/sessions/{broker_name}/expire",
    response_model=BrokerSessionInfo,
    status_code=status.HTTP_200_OK,
    summary="Simulate Session Expiry (Testing/Diagnostics)",
)
async def expire_broker(
    broker_name: str,
    current_user_id: str = Depends(get_current_user),
) -> BrokerSessionInfo:
    """Set broker session status to SESSION_EXPIRED for testing."""
    connections_repo = BrokerConnectionRepository()
    connections = await connections_repo.list_connections(owner_id=current_user_id)
    target_conn = next((c for c in connections if c.connection_id.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        target_conn = next((c for c in connections if c.broker_name.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{broker_name}' not found.")

    await connections_repo.update_status(
        owner_id=current_user_id,
        connection_id=target_conn.connection_id,
        status=BrokerStatus.SESSION_EXPIRED,
    )

    sessions = await get_broker_sessions(current_user_id=current_user_id)
    target = next((s for s in sessions if s.connection_id == target_conn.connection_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
    return target


@router.post(
    "/sessions/{broker_name}/disconnect",
    response_model=BrokerSessionInfo,
    status_code=status.HTTP_200_OK,
    summary="Disconnect Broker Session",
)
async def disconnect_broker(
    broker_name: str,
    current_user_id: str = Depends(get_current_user),
) -> BrokerSessionInfo:
    """Disconnect broker session."""
    connections_repo = BrokerConnectionRepository()
    connections = await connections_repo.list_connections(owner_id=current_user_id)
    target_conn = next((c for c in connections if c.connection_id.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        target_conn = next((c for c in connections if c.broker_name.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{broker_name}' not found.")

    await connections_repo.update_status(
        owner_id=current_user_id,
        connection_id=target_conn.connection_id,
        status=BrokerStatus.DISCONNECTED,
    )

    sessions = await get_broker_sessions(current_user_id=current_user_id)
    target = next((s for s in sessions if s.connection_id == target_conn.connection_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Broker {broker_name} not found.")
    return target


@router.get(
    "/oauth/indmoney/callback",
    response_class=HTMLResponse,
    summary="INDmoney OAuth 2.0 PKCE Callback",
    description="Receives OAuth 2.0 authorization code from INDmoney, exchanges for tokens, and persists session.",
)
async def indmoney_oauth_callback(
    code: Optional[str] = Query(None, description="Authorization code from INDmoney"),
    state: Optional[str] = Query(None, description="PKCE state token"),
    error: Optional[str] = Query(None, description="Error returned from INDmoney"),
    error_description: Optional[str] = Query(None, description="Error description"),
) -> HTMLResponse:
    """Handle INDmoney OAuth redirect and token exchange."""
    if error:
        logger.warning("INDmoney authorization returned error: %s (%s)", error, error_description)
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>INDmoney Authorization Failed</title></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh; background: #fef2f2;">
              <div style="background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; max-width: 480px;">
                <h2 style="color: #b91c1c; margin-bottom: 8px;">✕ INDmoney Authorization Failed</h2>
                <p style="color: #64748b; font-size: 14px;">{error}: {error_description or ''}</p>
                <p style="color: #94a3b8; font-size: 12px; margin-top: 16px;">You may close this tab and try again from WealthVault.</p>
              </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from INDmoney.")

    conn_id = "conn_indmoney_live"
    if state and "::" in state:
        conn_id = state.split("::")[0]

    client = get_indmoney_mcp_client(connection_id=conn_id)
    try:
        await client.exchange_code(code=code, state=state)
    except Exception as exc:
        logger.error("Failed to exchange INDmoney code for %s: %s", conn_id, exc)
        return HTMLResponse(
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>INDmoney Token Exchange Failed</title></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh; background: #fef2f2;">
              <div style="background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; max-width: 480px;">
                <h2 style="color: #b91c1c; margin-bottom: 8px;">✕ Token Exchange Error</h2>
                <p style="color: #64748b; font-size: 14px;">{exc}</p>
              </div>
            </body>
            </html>
            """,
            status_code=502,
        )

    return HTMLResponse(
        content="""
        <!DOCTYPE html>
        <html>
        <head><title>INDmoney Connected</title></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh; background: #f8fafc;">
          <div style="background: white; padding: 40px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); text-align: center; max-width: 480px;">
            <div style="width: 52px; height: 52px; border-radius: 50%; background: #ecfdf5; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 16px;">
              <span style="color: #059669; font-size: 28px; font-weight: bold;">✓</span>
            </div>
            <h2 style="color: #059669; margin-bottom: 8px; font-weight: 700; font-size: 20px;">INDmoney Connected Successfully!</h2>
            <p style="color: #64748b; font-size: 14px; line-height: 1.5;">Your WealthVault session is authenticated. You can now close this tab and click <b>Sync Now</b> in WealthVault to stream your US stocks, NPS, and bonds.</p>
            <script>
              if (window.opener) {
                try { window.opener.postMessage('indmoney_authorized', '*'); } catch(e) {}
              }
              setTimeout(() => { try { window.close(); } catch(e) {} }, 2500);
            </script>
          </div>
        </body>
        </html>
        """
    )


@router.get(
    "/brokers/catalog",
    response_model=List[BrokerCatalogItem],
    status_code=status.HTTP_200_OK,
    summary="Get Supported Broker Custodians Catalog",
    description="Returns list of all supported broker custodians with metadata, branding colors, and current connection status.",
)
async def get_broker_catalog(
    current_user_id: str = Depends(get_current_user),
) -> List[BrokerCatalogItem]:
    """Retrieve catalog of supported broker custodians and whether they are currently connected."""
    connections_repo = BrokerConnectionRepository()
    existing = await connections_repo.list_connections(owner_id=current_user_id)
    
    counts: Dict[str, int] = {}
    for c in existing:
        b_name = c.broker_name.lower().strip()
        counts[b_name] = counts.get(b_name, 0) + 1

    catalog_items: List[BrokerCatalogItem] = []
    for broker_key, meta in BROKER_METADATA_CATALOG.items():
        count = counts.get(broker_key, 0)
        catalog_items.append(
            BrokerCatalogItem(
                broker_name=broker_key,
                display_name=meta["display_name"],
                tag=meta["tag"],
                color=meta["color"],
                auth_type=meta["auth_type"],
                mcp_protocol=meta["mcp_protocol"],
                description=meta["description"],
                supported=meta.get("supported", True),
                coming_soon=meta.get("coming_soon", False),
                is_connected=count > 0,
                connected_count=count,
                credential_fields=[CredentialField(**f) for f in meta.get("credential_fields", [])],
                setup_url=meta.get("setup_url"),
                setup_steps=meta.get("setup_steps", []),
            )
        )
    return catalog_items


@router.post(
    "/connections",
    response_model=BrokerSessionInfo,
    status_code=status.HTTP_201_CREATED,
    summary="Connect or Link Broker Custodian",
    description="Connects a new broker custodian, initializes Azure Table connection record, and generates OAuth URL if needed.",
)
async def create_broker_connection(
    request: CreateBrokerConnectionRequest,
    current_user_id: str = Depends(get_current_user),
) -> BrokerSessionInfo:
    """Connect a new broker custodian for the authenticated user."""
    broker_clean = request.broker_name.lower().strip()
    catalog_meta = BROKER_METADATA_CATALOG.get(broker_clean)
    if not catalog_meta or not catalog_meta.get("supported", True):
        raise HTTPException(status_code=400, detail=f"{broker_clean or 'This broker'} is not available yet.")
    initial_status = BrokerStatus.AUTH_REQUIRED if broker_clean in CREDENTIAL_BROKERS else BrokerStatus.CONNECTED
    connections_repo = BrokerConnectionRepository()

    existing_all = await connections_repo.list_connections(owner_id=current_user_id)
    same_broker_conns = [c for c in existing_all if c.broker_name.lower() == broker_clean]

    conn_id = request.connection_id
    if not conn_id:
        default_conn_id = f"conn_{broker_clean}_live"
        existing_default = next((c for c in same_broker_conns if c.connection_id == default_conn_id), None)
        if existing_default:
            conn_id = f"conn_{broker_clean}_{uuid.uuid4().hex[:6]}"
        else:
            conn_id = default_conn_id

    now_iso = datetime.now(timezone.utc).isoformat()
    account_num = len(same_broker_conns) + 1
    
    account_label = request.account_label
    if not account_label:
        account_label = f"Account {account_num}" if len(same_broker_conns) > 0 else "Primary Account"

    default_meta = BROKER_METADATA_CATALOG.get(broker_clean, {})
    account_id = request.account_id or ""

    existing = await connections_repo.get_connection(owner_id=current_user_id, connection_id=conn_id)
    if not existing:
        await connections_repo.create_connection(
            owner_id=current_user_id,
            broker_name=broker_clean,
            connection_id=conn_id,
            status=initial_status,
            account_id=account_id,
            account_label=account_label,
        )
    else:
        await connections_repo.update_status(
            owner_id=current_user_id,
            connection_id=conn_id,
            status=initial_status,
            last_sync_time=now_iso,
            account_id=account_id,
            account_label=account_label,
        )

    sessions = await get_broker_sessions(current_user_id=current_user_id)
    target = next((s for s in sessions if s.connection_id == conn_id), None)
    if not target:
        meta = BROKER_METADATA_CATALOG.get(broker_clean, {})
        target = BrokerSessionInfo(
            connection_id=conn_id,
            owner_id=current_user_id,
            broker_name=broker_clean,
            display_name=f"{meta.get('display_name', broker_clean.capitalize())} — {account_label}",
            status=BrokerStatus.CONNECTED,
            last_sync_time=now_iso,
            account_id=account_id,
            account_label=account_label,
            auth_type=meta.get("auth_type", "OAuth2 / API Key"),
            is_expired=False,
            mcp_server_url=meta.get("mcp_server_url", f"https://mcp.{broker_clean}.com/mcp"),
            mcp_protocol=meta.get("mcp_protocol", "MCP JSON-RPC v2.0"),
            holdings_count=0,
            total_valuation=0.0,
            auth_url=None,
        )
    return target


async def _find_connection(owner_id: str, ref: str):
    connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    key = ref.lower().strip()
    return next((c for c in connections if c.connection_id.lower() == key), None) or next(
        (c for c in connections if c.broker_name.lower() == key), None
    )


@router.put(
    "/connections/{connection_ref}/credentials",
    response_model=CredentialSaveResponse,
    status_code=status.HTTP_200_OK,
    summary="Save Broker API Credentials",
    description=(
        "Stores the user's API credentials for a Groww or Angel One connection, encrypted in Azure Table Storage, "
        "then tests the login. Credentials are never returned."
    ),
)
async def save_broker_credentials(
    connection_ref: str,
    payload: CredentialSaveRequest,
    current_user_id: str = Depends(get_current_user),
) -> CredentialSaveResponse:
    conn = await _find_connection(current_user_id, connection_ref)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{connection_ref}' not found.")
    broker = conn.broker_name.lower().strip()
    if broker not in CREDENTIAL_BROKERS:
        raise HTTPException(status_code=400, detail=f"{broker} does not use API credentials.")

    meta = BROKER_METADATA_CATALOG[broker]
    allowed = {f["key"] for f in meta["credential_fields"]}
    unknown = set(payload.fields) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown credential fields: {', '.join(sorted(unknown))}.")
    given = {k: v.strip() for k, v in payload.fields.items() if v and v.strip()}
    missing = [f["label"] for f in meta["credential_fields"] if f["required"] and f["key"] not in given]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {', '.join(missing)}.")
    if broker == "groww" and not (given.get("api_secret") or given.get("totp_secret")):
        raise HTTPException(status_code=422, detail="Groww needs either the API secret or a TOTP secret.")

    repo = BrokerCredentialRepository()
    try:
        saved = await repo.save_credentials(current_user_id, conn.connection_id, given)
    except CredentialStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    provider_cls, _ = CREDENTIAL_BROKERS[broker]
    result = await provider_cls(owner_id=current_user_id, connection_id=conn.connection_id).get_account_status()
    ok = result.get("status") == "success"

    connections_repo = BrokerConnectionRepository()
    await connections_repo.update_status(
        owner_id=current_user_id,
        connection_id=conn.connection_id,
        status=BrokerStatus.CONNECTED if ok else BrokerStatus.AUTH_REQUIRED,
        account_id=given.get("client_code") if ok and given.get("client_code") else None,
    )
    return CredentialSaveResponse(
        saved_fields=saved,
        login_ok=ok,
        message="" if ok else str(result.get("message") or "The broker did not accept these credentials."),
        auth_url=result.get("auth_url"),
    )


@router.delete(
    "/connections/{connection_ref}/credentials",
    status_code=status.HTTP_200_OK,
    summary="Remove Stored Broker Credentials",
)
async def delete_broker_credentials(
    connection_ref: str,
    current_user_id: str = Depends(get_current_user),
) -> Dict[str, Any]:
    conn = await _find_connection(current_user_id, connection_ref)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{connection_ref}' not found.")
    removed = await BrokerCredentialRepository().delete_credentials(current_user_id, conn.connection_id)
    await BrokerConnectionRepository().update_status(
        owner_id=current_user_id, connection_id=conn.connection_id, status=BrokerStatus.AUTH_REQUIRED
    )
    return {"status": "success", "removed": removed}


@router.delete(
    "/connections/{broker_name}",
    response_model=BrokerDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete / Disconnect Broker Custodian Connection & Wipe All Associated Data",
    description="Removes a linked broker custodian connection, purges all associated holdings from Azure Tables, recomputes daily snapshot, and cleans up archived blobs.",
)
async def delete_broker_connection(
    broker_name: str,
    wipe_blobs: bool = Query(default=True, description="Whether to also permanently delete raw JSON payloads in blob storage"),
    current_user_id: str = Depends(get_current_user),
) -> BrokerDeleteResponse:
    """Delete a broker custodian connection and wipe all associated holdings & snapshot data."""
    connections_repo = BrokerConnectionRepository()
    holdings_repo = HoldingsRepository()
    snapshots_repo = SnapshotsRepository()
    aggregator = PortfolioAggregationService()

    connections = await connections_repo.list_connections(owner_id=current_user_id)
    target_conn = next((c for c in connections if c.connection_id.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        target_conn = next((c for c in connections if c.broker_name.lower() == broker_name.lower().strip()), None)
    if not target_conn:
        raise HTTPException(status_code=404, detail=f"Broker connection '{broker_name}' not found.")

    conn_id = target_conn.connection_id
    broker_clean = target_conn.broker_name.lower().strip()

    # 1. Delete connection entity from Azure Table
    await connections_repo.delete_connection(owner_id=current_user_id, connection_id=conn_id)
    if broker_clean in CREDENTIAL_BROKERS:
        await BrokerCredentialRepository().delete_credentials(current_user_id, conn_id)

    # 2. Purge all holdings belonging strictly to this connection
    purged_holdings = await holdings_repo.delete_holdings_by_connection(
        owner_id=current_user_id,
        connection_id=conn_id,
        broker_name=broker_clean,
    )

    # 3. Purge archived blobs if requested
    purged_blobs = 0
    if wipe_blobs:
        try:
            purged_blobs = await purge_broker_blobs(owner_id=current_user_id, connection_id=conn_id)
        except Exception as blob_err:
            logger.warning("Purging blobs note for %s: %s", conn_id, blob_err)

    # 4. Fetch remaining holdings and recompute portfolio snapshot
    remaining_holdings = await holdings_repo.get_holdings(owner_id=current_user_id)
    as_of_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_snapshot = aggregator.calculate_snapshot(
        owner_id=current_user_id,
        holdings=remaining_holdings,
        as_of_date=as_of_date,
    )
    await snapshots_repo.save_snapshot(new_snapshot)

    # 5. Invalidate client session / credentials in-memory for this specific connection
    if broker_clean == "zerodha":
        try:
            zk_client = get_kite_mcp_client(connection_id=conn_id)
            await zk_client.reset_session()
        except Exception as z_err:
            logger.debug("Zerodha session reset note: %s", z_err)
    elif broker_clean == "indmoney":
        try:
            ind_client = get_indmoney_mcp_client(connection_id=conn_id)
            ind_client.reset_tokens()
        except Exception as ind_err:
            logger.debug("INDmoney token reset note: %s", ind_err)

    logger.info(
        "Wiped broker connection %s (%s) for user %s: %d holdings purged, %d blobs purged, new total valuation: %.2f",
        conn_id,
        broker_clean,
        current_user_id,
        purged_holdings,
        purged_blobs,
        new_snapshot.total_current_value,
    )

    return BrokerDeleteResponse(
        status="success",
        broker_name=broker_clean,
        connection_id=conn_id,
        holdings_purged=purged_holdings,
        blobs_purged=purged_blobs,
        snapshot_updated=True,
        remaining_holdings_count=len(remaining_holdings),
        new_total_valuation=new_snapshot.total_current_value,
    )



