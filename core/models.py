"""Domain and API schema models for WealthVault.

Defines the User identity entity, BrokerConnection session entity,
canonical financial models (Holding, Transaction, PortfolioSnapshot), and related schemas.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BrokerStatus(str, Enum):
    """Lifecycle and health status of a broker connection."""

    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    DISCONNECTED = "DISCONNECTED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class AssetClass(str, Enum):
    """Canonical asset classes supported by WealthVault."""

    EQUITY = "EQUITY"
    MUTUAL_FUND = "MUTUAL_FUND"
    GOLD = "GOLD"
    NPS = "NPS"
    US_STOCKS = "US_STOCKS"
    DEBT = "DEBT"



class TransactionType(str, Enum):
    """Direction of a financial order/trade transaction."""

    BUY = "BUY"
    SELL = "SELL"


class User(BaseModel):
    """User account entity stored in Table Storage.

    Represents a tenant boundary in WealthVault.
    """

    user_id: str = Field(..., description="Unique user identifier (derived from Google OAuth sub)")
    email: str = Field(..., description="User primary email address")
    name: str = Field(..., description="User display name")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 creation timestamp",
    )
    picture: Optional[str] = Field(default=None, description="User avatar image URL")


class BrokerConnection(BaseModel):
    """Broker connection entity stored in Table Storage.

    Enforces strict isolation:
    PartitionKey MUST strictly be owner_id (user_id).
    RowKey is connection_id.
    """

    connection_id: str = Field(..., description="Unique connection identifier (RowKey)")
    owner_id: str = Field(..., description="User ID of the connection owner (PartitionKey)")
    broker_name: str = Field(..., description="Broker service identifier (e.g., 'zerodha', 'indmoney')")
    status: BrokerStatus = Field(
        default=BrokerStatus.CONNECTED,
        description="Current synchronization and authentication status",
    )
    last_sync_time: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp of last successful sync",
    )


class Holding(BaseModel):
    """Canonical portfolio holding normalized across all broker formats."""

    holding_id: str = Field(..., description="Unique identifier for the holding")
    owner_id: str = Field(..., description="User ID of the tenant owner")
    connection_id: str = Field(..., description="Broker connection identifier source")
    instrument_symbol: str = Field(..., description="Normalized trading symbol or scheme name")
    asset_class: AssetClass = Field(..., description="Financial asset classification")
    quantity: float = Field(..., description="Number of shares or fund units held")
    average_price: float = Field(..., description="Average acquisition cost per unit")
    current_value: float = Field(..., description="Current total valuation of the holding")
    current_price: Optional[float] = Field(default=None, description="Latest market price or NAV")
    pnl: Optional[float] = Field(default=None, description="Total unrealized profit or loss")
    currency: str = Field(default="INR", description="Denomination currency code")


class Transaction(BaseModel):
    """Canonical investment transaction normalized across all broker formats."""

    transaction_id: str = Field(..., description="Unique transaction identifier")
    owner_id: str = Field(..., description="User ID of the tenant owner")
    connection_id: str = Field(..., description="Broker connection identifier source")
    instrument_symbol: str = Field(..., description="Normalized trading symbol or scheme name")
    asset_class: AssetClass = Field(..., description="Financial asset classification")
    trade_date: datetime = Field(..., description="Timestamp of trade execution or order fill")
    transaction_type: TransactionType = Field(..., description="BUY or SELL")
    quantity: float = Field(..., description="Number of shares or units transacted")
    price: float = Field(..., description="Execution price or NAV per unit")
    amount: float = Field(..., description="Total settlement amount (quantity * price)")
    currency: str = Field(default="INR", description="Denomination currency code")


class AssetAllocationItem(BaseModel):
    """Asset class allocation metrics."""

    asset_class: str = Field(..., description="Asset class identifier")
    absolute_value: float = Field(..., description="Aggregate valuation in INR")
    percentage_weight: float = Field(..., description="Portfolio allocation percentage (0 - 100)")


class PortfolioSnapshot(BaseModel):
    """Point-in-time consolidated portfolio valuation and allocation snapshot."""

    snapshot_id: str = Field(..., description="Unique snapshot identifier (e.g. snapshot_YYYY-MM-DD)")
    owner_id: str = Field(..., description="User ID of tenant owner (PartitionKey)")
    as_of_date: str = Field(..., description="Date of calculation (YYYY-MM-DD)")
    calculation_version: str = Field(default="v1", description="Calculation engine schema version")
    total_current_value: float = Field(..., description="Aggregate market valuation in INR")
    total_invested_value: float = Field(..., description="Aggregate cost basis/invested capital in INR")
    total_unrealized_pnl: float = Field(..., description="Aggregate unrealized profit or loss in INR")
    total_pnl_percentage: float = Field(..., description="Total return percentage")
    asset_allocation: Dict[str, Dict[str, float]] = Field(
        default_factory=dict,
        description="Asset allocation mapping asset class to percentage weight and absolute value",
    )
    holdings_count: int = Field(default=0, description="Total number of constituent holdings")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 creation timestamp",
    )


# --- API Request & Response Schemas ---

class GoogleAuthRequest(BaseModel):
    """Payload for Google OAuth ID token verification."""

    credential: str = Field(..., description="Google ID Token issued by Google Identity Services")


class TokenResponse(BaseModel):
    """Authentication response returning signed JWT and authenticated User profile."""

    access_token: str = Field(..., description="Signed internal JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme")
    user: User = Field(..., description="Authenticated user account details")


class BrokerConnectionCreate(BaseModel):
    """Payload to establish a new broker connection."""

    broker_name: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Target broker identifier (e.g., 'zerodha', 'indmoney')",
    )


class PortfolioSyncResponse(BaseModel):
    """Response returned upon completing an orchestrated portfolio sync."""

    status: str = Field(default="success", description="Overall sync status")
    synced_at: str = Field(..., description="ISO 8601 sync timestamp")
    holdings_upserted: int = Field(..., description="Total canonical holdings persisted")
    archived_payloads: List[str] = Field(..., description="Azure Blob Storage URIs of archived payloads")
    snapshot: PortfolioSnapshot = Field(..., description="Generated daily portfolio snapshot")


class PortfolioSummaryResponse(BaseModel):
    """Consolidated portfolio overview for dashboard rendering."""

    owner_id: str = Field(..., description="Tenant user ID")
    snapshot: PortfolioSnapshot = Field(..., description="Latest portfolio snapshot")
    connections: List[BrokerConnection] = Field(..., description="Active broker connection statuses")


class BrokerSessionInfo(BaseModel):
    """Rich telemetry and session state for a broker connection / MCP gateway."""

    connection_id: str = Field(..., description="Unique connection identifier")
    owner_id: str = Field(..., description="User ID of owner")
    broker_name: str = Field(..., description="Broker service (zerodha, indmoney)")
    display_name: str = Field(..., description="Display title for the broker")
    status: BrokerStatus = Field(..., description="Connection / session status")
    last_sync_time: Optional[str] = Field(default=None, description="ISO timestamp of last successful sync")
    account_id: str = Field(..., description="Broker user ID / client ID")
    auth_type: str = Field(..., description="Authentication protocol (e.g. Daily Kite TOTP, OAuth2 Bearer)")
    session_expires_at: Optional[str] = Field(default=None, description="When the current session token expires")
    is_expired: bool = Field(default=False, description="Whether session is expired")
    mcp_server_url: str = Field(..., description="MCP endpoint URL or stdio protocol")
    mcp_protocol: str = Field(default="MCP Stdio / JSON-RPC v2.0", description="Protocol format")
    tools_count: int = Field(default=0, description="Available MCP tools count")
    holdings_count: int = Field(default=0, description="Holdings currently synced from this broker")
    total_valuation: float = Field(default=0.0, description="Total INR valuation from this broker")
    last_latency_ms: int = Field(default=0, description="Roundtrip latency in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Detailed error message if degraded")


class ReauthRequest(BaseModel):
    """Payload for broker session re-authentication."""

    api_key: Optional[str] = Field(default=None, description="Optional broker API Key")
    totp_token: Optional[str] = Field(default=None, description="Optional TOTP / 2FA code")
    session_token: Optional[str] = Field(default=None, description="Optional raw session enctoken / bearer")

