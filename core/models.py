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
    account_id: Optional[str] = Field(
        default=None,
        description="Client or Account ID (e.g. SRK113, HUF101)",
    )
    account_label: Optional[str] = Field(
        default=None,
        description="User-defined account label/alias (e.g. 'Personal Demat', 'Family HUF')",
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
    day_pnl: Optional[float] = Field(default=None, description="1-day unrealized profit or loss")
    day_change_percentage: Optional[float] = Field(default=None, description="1-day price percentage change")
    data_freshness: str = Field(default="live", description="'live' if refreshed via MCP, 'cached' if fallback")
    last_price_updated_at: Optional[str] = Field(default=None, description="ISO timestamp of last quote update")
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
    account_label: Optional[str] = Field(default=None, description="User-defined account label / alias")
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
    auth_url: Optional[str] = Field(default=None, description="Interactive login / OAuth authorization URL if AUTH_REQUIRED")


class CreateBrokerConnectionRequest(BaseModel):
    """Payload for creating or linking a new broker custodian connection."""

    broker_name: str = Field(..., description="Broker key name (e.g. zerodha, indmoney, groww, upstox)")
    account_id: Optional[str] = Field(default=None, description="Optional custom client / account identifier")
    account_label: Optional[str] = Field(default=None, description="Optional user-defined account label / alias")
    connection_id: Optional[str] = Field(default=None, description="Optional custom connection identifier")
    custom_mcp_url: Optional[str] = Field(default=None, description="Optional custom MCP endpoint URL")


class BrokerCatalogItem(BaseModel):
    """Metadata describing an available broker custodian integration."""

    broker_name: str
    display_name: str
    tag: str
    color: str
    auth_type: str
    mcp_protocol: str
    description: str
    supported: bool = True
    is_connected: bool = False
    connected_count: int = 0


class ReauthRequest(BaseModel):
    """Payload for broker session re-authentication."""

    api_key: Optional[str] = Field(default=None, description="Optional broker API Key")
    totp_token: Optional[str] = Field(default=None, description="Optional TOTP / 2FA code")
    session_token: Optional[str] = Field(default=None, description="Optional raw session enctoken / bearer")


class QuoteItem(BaseModel):
    """Real-time market quote payload from Market Data Provider (MCP)."""

    instrument: str = Field(..., description="Instrument identifier (e.g. 'NSE:INFY')")
    last_price: float = Field(..., description="Last Traded Price (LTP)")
    day_change: Optional[float] = Field(default=None, description="Net price change today")
    day_change_percentage: Optional[float] = Field(default=None, description="Percentage change today")
    open_price: Optional[float] = Field(default=None, description="Day opening price")
    high_price: Optional[float] = Field(default=None, description="Day high price")
    low_price: Optional[float] = Field(default=None, description="Day low price")
    close_price: Optional[float] = Field(default=None, description="Previous day close price")
    timestamp: Optional[str] = Field(default=None, description="Quote timestamp")


class MarketQuotesResponse(BaseModel):
    """Batch market quotes response with caching and quota metadata."""

    status: str = Field(default="success", description="Status code")
    data_freshness: str = Field(default="live", description="'live' or 'cached'")
    cached_count: int = Field(default=0, description="Count of quotes served from TTL cache")
    live_count: int = Field(default=0, description="Count of quotes fetched live from MCP")
    quotes: Dict[str, QuoteItem] = Field(default_factory=dict, description="Map of instrument identifier to quote")


class BrokerDeleteResponse(BaseModel):
    """Result of removing a broker connection and wiping associated data."""

    status: str = Field(default="success", description="Status indicator")
    broker_name: str = Field(..., description="Target broker platform name")
    connection_id: Optional[str] = Field(default=None, description="Identifier of the deleted connection")
    holdings_purged: int = Field(default=0, description="Count of purged holding entities")
    blobs_purged: int = Field(default=0, description="Count of deleted raw blob payloads")
    snapshot_updated: bool = Field(default=True, description="Whether daily snapshot was recomputed")
    remaining_holdings_count: int = Field(default=0, description="Count of remaining holdings across other brokers")
    new_total_valuation: float = Field(default=0.0, description="Updated portfolio total valuation in INR")


# --- Momentum Analytics Schemas ---

class TrendCheck(BaseModel):
    """Single pass/fail rule in the moving-average trend checklist."""

    key: str = Field(..., description="Rule identifier (e.g. 'above_200dma')")
    label: str = Field(..., description="Human-readable rule name")
    passed: bool = Field(..., description="Whether the rule currently holds")
    detail: str = Field(default="", description="Supporting value for the rule")


class MomentumSeriesPoint(BaseModel):
    """Daily close with moving averages for charting."""

    date: str = Field(..., description="Trading date (YYYY-MM-DD)")
    close: float = Field(..., description="Closing price")
    sma50: Optional[float] = Field(default=None, description="50-day simple moving average")
    sma200: Optional[float] = Field(default=None, description="200-day simple moving average")


class MomentumAnalysis(BaseModel):
    """Momentum report for a single instrument. Percent fields are percent values (12.5 = 12.5%)."""

    instrument: str = Field(..., description="Exchange-qualified symbol (e.g. 'NSE:INFY')")
    name: Optional[str] = Field(default=None, description="Instrument display name")
    as_of: str = Field(..., description="Date of the latest candle (YYYY-MM-DD)")
    last_price: float = Field(..., description="Latest close / last traded price")
    candles_used: int = Field(..., description="Number of daily candles analysed")

    # Trend / moving averages (primary verdict)
    trend_score: int = Field(..., description="Number of trend rules passed")
    trend_max_score: int = Field(..., description="Number of trend rules evaluated")
    trend_verdict: str = Field(..., description="Overall trend classification")
    trend_checks: List[TrendCheck] = Field(default_factory=list, description="Trend checklist results")
    sma_20: Optional[float] = Field(default=None, description="20-day SMA")
    sma_50: Optional[float] = Field(default=None, description="50-day SMA")
    sma_200: Optional[float] = Field(default=None, description="200-day SMA")
    pct_from_sma50: Optional[float] = Field(default=None, description="Price distance from 50-DMA (%)")
    pct_from_sma200: Optional[float] = Field(default=None, description="Price distance from 200-DMA (%)")
    sma200_slope_pct: Optional[float] = Field(default=None, description="200-DMA change over last 20 trading days (%)")
    cross_state: Optional[str] = Field(default=None, description="'golden' if 50-DMA > 200-DMA, else 'death'")
    days_since_cross: Optional[int] = Field(default=None, description="Trading days since the last 50/200 cross")
    macd: Optional[float] = Field(default=None, description="MACD line (12, 26)")
    macd_signal: Optional[float] = Field(default=None, description="MACD signal line (9)")
    macd_histogram: Optional[float] = Field(default=None, description="MACD minus signal")

    # Price momentum
    returns: Dict[str, Optional[float]] = Field(default_factory=dict, description="Returns by window: 1M, 3M, 6M, 12M, 12-1 (%)")
    volatility_6m: Optional[float] = Field(default=None, description="Annualized 6M volatility (%)")
    volatility_12m: Optional[float] = Field(default=None, description="Annualized 12M volatility (%)")
    risk_adjusted_6m: Optional[float] = Field(default=None, description="6M return / 6M volatility")
    risk_adjusted_12m: Optional[float] = Field(default=None, description="12M return / 12M volatility")

    # Oscillator & range
    rsi_14: Optional[float] = Field(default=None, description="14-day RSI")
    high_52w: Optional[float] = Field(default=None, description="52-week high")
    low_52w: Optional[float] = Field(default=None, description="52-week low")
    pct_from_52w_high: Optional[float] = Field(default=None, description="Distance from 52-week high (%)")
    pct_from_52w_low: Optional[float] = Field(default=None, description="Distance from 52-week low (%)")

    # Relative strength
    benchmark: str = Field(default="NIFTY 50", description="Benchmark index for relative strength")
    relative_strength: Dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="Stock return minus benchmark return by window (percentage points)",
    )

    series: List[MomentumSeriesPoint] = Field(default_factory=list, description="Last year of closes with 50/200-DMA")





# --- Swing Strategy (NSE Swing Momentum V2.1) Schemas ---

class SwingStrategyParams(BaseModel):
    """Inputs of the NSE Swing Momentum V2.1 strategy (defaults match the Pine script)."""

    fast_sma: int = Field(default=50, ge=1, description="Fast SMA length")
    slow_sma: int = Field(default=200, ge=1, description="Slow SMA length")
    slope_lookback: int = Field(default=20, ge=1, description="Slow SMA slope lookback (bars)")
    ut_key: float = Field(default=1.0, gt=0, description="UT Bot key value (ATR multiple)")
    ut_atr_period: int = Field(default=10, ge=1, description="UT Bot ATR period")
    exit_ema: int = Field(default=20, ge=1, description="Exit confirmation EMA length")
    use_stop: bool = Field(default=True, description="Use the ATR protective stop")
    stop_atr_period: int = Field(default=14, ge=1, description="Protective stop ATR period")
    stop_atr_mult: float = Field(default=2.0, gt=0, description="Protective stop ATR multiplier")
    initial_capital: float = Field(default=100000.0, gt=0, description="Starting capital in INR")
    commission_pct: float = Field(default=0.10, ge=0, description="Commission per side (% of trade value)")
    slippage_ticks: int = Field(default=1, ge=0, description="Slippage per fill in ticks")


class StrategyTrade(BaseModel):
    """One round-trip trade from the backtest (open trades are marked to the last close)."""

    entry_date: str
    entry_price: float
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: str = Field(..., description="'UT + EMA20 SELL', 'ATR STOP' or 'OPEN'")
    quantity: int
    pnl: float = Field(..., description="Net P&L in INR after commission")
    pnl_pct: float = Field(..., description="Net P&L as % of entry cost")
    bars_held: int
    is_open: bool = False


class StrategyStats(BaseModel):
    """Backtest performance summary over the tradable window."""

    initial_capital: float
    final_equity: float
    net_profit: float
    net_profit_pct: float
    cagr_pct: float
    max_drawdown_pct: float = Field(..., description="Largest peak-to-trough equity decline (negative %)")
    buy_hold_return_pct: float
    total_trades: int = Field(..., description="Closed trades")
    open_trade: bool
    win_rate_pct: Optional[float] = None
    avg_win_pct: Optional[float] = None
    avg_loss_pct: Optional[float] = None
    profit_factor: Optional[float] = Field(default=None, description="Gross profit / gross loss (None if no losses)")
    avg_bars_held: Optional[float] = None
    exposure_pct: float = Field(..., description="% of bars spent in a position")
    signal_exits: int
    stop_exits: int


class StrategyStatus(BaseModel):
    """Where the strategy stands on the latest bar."""

    state: str = Field(..., description="'IN_POSITION' or 'FLAT'")
    headline: str
    detail: str
    regime_bullish: bool
    regime_checks: List[TrendCheck] = Field(default_factory=list)
    pending_order: Optional[str] = Field(default=None, description="'BUY' or 'SELL' queued for the next open")
    entry_date: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    ut_stop: Optional[float] = None
    exit_ema: Optional[float] = None
    unrealized_pct: Optional[float] = None
    bars_held: Optional[int] = None


class StrategyBar(BaseModel):
    """Per-bar indicator values, signals, and equity for charting."""

    date: str
    open: float
    high: float
    low: float
    close: float
    sma_fast: Optional[float] = None
    sma_slow: Optional[float] = None
    exit_ema: Optional[float] = None
    ut_stop: Optional[float] = None
    regime: bool = False
    buy: bool = Field(default=False, description="BUY signal on this close (fills next open)")
    sell: bool = Field(default=False, description="UT + EMA20 SELL signal on this close (fills next open)")
    stop_exit: bool = Field(default=False, description="Protective stop filled during this bar")
    stop_level: Optional[float] = None
    equity: float
    buy_hold: float


class SwingStrategyResult(BaseModel):
    """Full NSE Swing Momentum V2.1 report for one instrument."""

    instrument: str
    name: Optional[str] = None
    as_of: str
    params: SwingStrategyParams
    test_start: str = Field(..., description="First bar after indicator warm-up")
    test_end: str
    bars_tested: int
    partial_bar_excluded: bool = Field(default=False, description="Today's unfinished candle was dropped")
    status: StrategyStatus
    stats: StrategyStats
    trades: List[StrategyTrade] = Field(default_factory=list)
    series: List[StrategyBar] = Field(default_factory=list)
