"""Data Contracts for Ground-Level Intelligence Scouts and Dossiers."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ScoutStatus(BaseModel):
    """Execution status and metadata for a scout."""
    scout_id: str
    scout_name: str
    state: Literal["IDLE", "RUNNING", "COMPLETED", "FAILED", "BYPASSED"] = "IDLE"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class RiskIntelReport(BaseModel):
    """Risk Scout findings for portfolio allocation and drawdown boundaries."""
    symbol: str
    current_price: float = 0.0
    average_price: float = 0.0
    quantity: int = 0
    pnl_pct: float = 0.0
    portfolio_weight_pct: float = 0.0
    stop_loss_breach: bool = False
    deep_drawdown_breach: bool = False
    over_concentration: bool = False
    broker_source: str = "Unknown"
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    summary: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TechIntelReport(BaseModel):
    """Technical Scout findings: Moving averages, stage analysis, momentum, and market regime."""
    symbol: str
    current_price: float = 0.0
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    slope_200_sma: Optional[float] = None
    golden_cross: Optional[bool] = None
    stage_verdict: str = "Stage 1: Base / Consolidation"
    momentum_score: int = 0
    momentum_max: int = 5
    rs_score_vs_nifty: Optional[float] = None
    rs_rating_label: Optional[str] = None  # "OUTPERFORMING", "IN_LINE", "UNDERPERFORMING"
    market_regime: Optional[str] = None  # "BULL_MARKET", "NEUTRAL_CHOPPY", "BEAR_CORRECTION"
    nifty_trend_summary: Optional[str] = None
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    summary: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PatternIntelReport(BaseModel):
    """Pattern Finder Scout findings: Classical geometric chart formations with volume signature verification."""
    symbol: str
    pattern_detected: bool = False
    pattern_name: Optional[str] = None  # "Ascending Triangle", "Volatility Contraction (VCP)", "Cup & Handle", "Double Bottom", etc.
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    confidence: int = 0  # 0 to 100
    pivot_breakout_price: Optional[float] = None
    support_stop_price: Optional[float] = None
    pattern_stage: Optional[str] = None  # "FORMING", "NEAR_PIVOT", "CONFIRMED_BREAKOUT", "FAILED"
    volume_surge_ratio: Optional[float] = None  # Volume vs 20-day average volume (e.g., 2.1x)
    volume_dryup_confirmed: Optional[bool] = None  # True if volume dried up during base/handle
    is_low_volume_trap: bool = False  # True if breakout attempted on < 1.0x average volume
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    summary: str = "No distinct classical chart pattern detected."
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FundaIntelReport(BaseModel):
    """Fundamental Solvency Scout findings: Balance sheet & profitability vitals."""
    symbol: str
    is_etf: bool = False
    market_cap_cr: Optional[float] = None
    pe_ratio: Optional[float] = None
    roce_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    debt_to_equity: Optional[float] = None
    sales_growth_3y: Optional[float] = None
    promoter_holding_pct: Optional[float] = None
    promoter_pledged_pct: Optional[float] = None
    status: Literal["COMPLETED", "FAILED", "BYPASSED_ETF"] = "COMPLETED"
    summary: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NewsArticleItem(BaseModel):
    headline: str
    source: str = "News"
    published_at: str = ""
    age_days: Optional[int] = None
    age_label: Optional[str] = None  # e.g. "Today", "2d ago", "1w ago"
    link: Optional[str] = None
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = "NEUTRAL"
    confidence: float = 0.5
    category: str = "GENERAL"
    summary_content: Optional[str] = None  # Full content / article description / snippet


class NewsIntelReport(BaseModel):
    """Forensic News Scout findings: Google News RSS + Local FinBERT NLP classification."""
    symbol: str
    articles_scanned: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    dominant_sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = "NEUTRAL"
    sentiment_confidence: float = 0.0
    material_threat: bool = False
    threat_reasons: List[str] = Field(default_factory=list)
    latest_article_age_days: Optional[int] = None
    is_wire_quiet: bool = False  # True when no articles within 45 days
    articles: List[NewsArticleItem] = Field(default_factory=list)
    status: Literal["COMPLETED", "FAILED"] = "COMPLETED"
    summary: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BulkDealItem(BaseModel):
    date: str
    client_name: str
    buy_sell: Literal["BUY", "SELL"]
    quantity: int
    price: float
    deal_type: Literal["BULK", "BLOCK"]
    remarks: Optional[str] = None


class PITDisclosureItem(BaseModel):
    date: str
    person_name: str
    category_of_person: str
    transaction_type: Literal["BUY", "SELL", "PLEDGE", "REVOKE"]
    quantity: int
    value_inr: float


class InsiderIntelReport(BaseModel):
    """Insider & Bulk Deals Scout findings: SEBI PIT Disclosures & Institutional Block Trades."""
    symbol: str
    is_etf: bool = False
    bulk_deals: List[BulkDealItem] = Field(default_factory=list)
    block_deals: List[BulkDealItem] = Field(default_factory=list)
    pit_disclosures: List[PITDisclosureItem] = Field(default_factory=list)
    institutional_bias: Literal["ACCUMULATION", "DISTRIBUTION", "NEUTRAL", "NO_DEALS"] = "NO_DEALS"
    promoter_bias: Literal["BUYING", "SELLING", "NEUTRAL", "NO_FILINGS"] = "NO_FILINGS"
    status: Literal["COMPLETED", "FAILED", "BYPASSED_ETF"] = "COMPLETED"
    summary: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GroundStockDossier(BaseModel):
    """Unified dossier aggregating the 6 Ground Scout intelligence reports for a single stock."""
    symbol: str
    company_name: str = ""
    is_etf: bool = False
    
    # Reports from the 6 ground scouts
    risk_report: Optional[RiskIntelReport] = None
    tech_report: Optional[TechIntelReport] = None
    pattern_report: Optional[PatternIntelReport] = None
    funda_report: Optional[FundaIntelReport] = None
    news_report: Optional[NewsIntelReport] = None
    insider_report: Optional[InsiderIntelReport] = None
    
    # Barrier gate status
    barrier_status: Literal["PENDING", "IN_PROGRESS", "READY_FOR_REVIEW", "QUARANTINED"] = "PENDING"
    completed_scouts: List[str] = Field(default_factory=list)
    required_scouts: List[str] = Field(default_factory=list)
    missing_scouts: List[str] = Field(default_factory=list)
    current_scout: Optional[str] = None
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def update_barrier(self) -> None:
        """Evaluate if all required scouts have completed their reports."""
        all_scouts = ["risk", "tech", "pattern", "news"]
        if not self.is_etf:
            all_scouts.extend(["funda", "insider"])
        
        self.required_scouts = all_scouts
        
        completed = []
        if self.risk_report and self.risk_report.status in ("COMPLETED", "FAILED"):
            completed.append("risk")
        if self.tech_report and self.tech_report.status in ("COMPLETED", "FAILED"):
            completed.append("tech")
        if self.pattern_report and self.pattern_report.status in ("COMPLETED", "FAILED"):
            completed.append("pattern")
        if self.news_report and self.news_report.status in ("COMPLETED", "FAILED"):
            completed.append("news")
        if not self.is_etf:
            if self.funda_report and self.funda_report.status in ("COMPLETED", "FAILED", "BYPASSED_ETF"):
                completed.append("funda")
            if self.insider_report and self.insider_report.status in ("COMPLETED", "FAILED", "BYPASSED_ETF"):
                completed.append("insider")
        
        self.completed_scouts = completed
        missing = [s for s in self.required_scouts if s not in completed]
        self.missing_scouts = missing
        
        if not missing:
            self.barrier_status = "READY_FOR_REVIEW"
        elif completed:
            self.barrier_status = "IN_PROGRESS"
        else:
            self.barrier_status = "PENDING"
        self.last_updated = datetime.now(timezone.utc).isoformat()
