"""Data models and schemas for WealthVault's Multi-Level Agent Hierarchy."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AgentTier(str, Enum):
    """Hierarchy tier within the Agent Boardroom."""
    DOMAIN_SPECIALIST = "DOMAIN_SPECIALIST"  # Tier 1 (e.g. Risk Officer, Signal Scout)
    FIDUCIARY_REVIEWER = "FIDUCIARY_REVIEWER" # Tier 2 (Reviewer / Gatekeeper)
    EXECUTIVE_BOSS = "EXECUTIVE_BOSS"        # Tier 3 (Financial Planning Agent)


class AgentState(str, Enum):
    """Lifecycle state of an autonomous agent."""
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    PROPOSAL_GENERATED = "PROPOSAL_GENERATED"
    WAITING_REVIEW = "WAITING_REVIEW"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    APPROVED = "APPROVED"
    SYNTHESIZED = "SYNTHESIZED"


class ProposalActionType(str, Enum):
    """Type of financial action proposed by a subagent."""
    CUT_LOSS = "CUT_LOSS"
    TRAILING_TRIM = "TRAILING_TRIM"
    REBALANCE = "REBALANCE"
    PYRAMID_ADD = "PYRAMID_ADD"
    HOLD_DEFENSE = "HOLD_DEFENSE"
    EXIT_ALL = "EXIT_ALL"


class PolicyCheckStatus(str, Enum):
    """Evaluation status of a specific fiduciary rule."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class MoveCausality(str, Enum):
    """Decomposition of why a stock is dropping or rising."""
    SYSTEMIC_MARKET_BETA = "SYSTEMIC_MARKET_BETA"          # Move is explained by Nifty/Sector drop
    COMPANY_SPECIFIC = "COMPANY_SPECIFIC"                  # Idiosyncratic earnings/news/management catalyst
    SPECULATIVE_MANIPULATION = "SPECULATIVE_MANIPULATION"  # High volume pump with low delivery & no news


class DirectivePriority(str, Enum):
    """Urgency level of a directive presented to the user."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class DirectiveStatus(str, Enum):
    """User interaction and closure state of an action directive."""
    PENDING_REVIEW = "PENDING_REVIEW"
    ORDER_PLACED_AT_BROKER = "ORDER_PLACED_AT_BROKER"
    IGNORED = "IGNORED"
    SNOOZED = "SNOOZED"
    SIMULATED = "SIMULATED"


class ProposedAction(BaseModel):
    """Single order or allocation movement recommendation."""
    symbol: str
    display_name: Optional[str] = None
    broker: str
    action: ProposalActionType
    quantity: int
    estimated_price: float
    trigger_reason: str
    suggested_stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    order_type: str = "LIMIT"
    trend_verdict: Optional[str] = None
    holding_quantity: Optional[int] = None
    holding_avg_price: Optional[float] = None
    pnl_pct: Optional[float] = None


class WorkProposal(BaseModel):
    """Structured thesis and recommendation produced by a Tier 1 Sub-Agent."""
    proposal_id: str
    source_agent_id: str
    source_agent_name: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    urgency: DirectivePriority = DirectivePriority.NORMAL
    thesis: str
    underlying_metrics: Dict[str, Any] = Field(default_factory=dict)
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    revision_round: int = 0


class NewsCatalyst(BaseModel):
    """News or announcement item scraped from free public feeds."""
    headline: str
    source: str
    published_at: str
    age_days: Optional[int] = None
    age_label: Optional[str] = None  # e.g. "Today", "2d ago", "1w ago"
    sentiment: str = "NEUTRAL"  # POSITIVE, NEGATIVE, NEUTRAL
    category: str = "GENERAL"   # EARNINGS, REGULATORY, ORDER_WIN, MANAGEMENT, GENERAL
    link: Optional[str] = None
    summary_content: Optional[str] = None  # Full content / article description / snippet


class FundamentalVitals(BaseModel):
    """Key fundamental health and balance sheet metrics from free public sources."""
    market_cap_cr: Optional[float] = None
    pe_ratio: Optional[float] = None
    book_value: Optional[float] = None
    roce_pct: Optional[float] = None
    roe_pct: Optional[float] = None
    debt_to_equity: Optional[float] = None
    sales_growth_yoy_pct: Optional[float] = None
    net_profit_cr: Optional[float] = None
    promoter_holding_pct: Optional[float] = None
    promoter_pledged_pct: Optional[float] = None
    fii_dii_trend: str = "STABLE"  # ACCUMULATING, STABLE, DUMPING
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)


class InvestigationDossier(BaseModel):
    """Forensic due-diligence package compiled by Tier 2 Reviewer Agent."""
    symbol: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    causality: MoveCausality
    causality_explanation: str
    market_benchmark_delta: Dict[str, float] = Field(default_factory=dict)
    recent_news: List[NewsCatalyst] = Field(default_factory=list)
    fundamental_vitals: FundamentalVitals = Field(default_factory=FundamentalVitals)
    technical_trend: Optional[str] = None  # Genuine technical momentum verdict (e.g. "Neutral (2/5)")
    trend_score: Optional[int] = None
    trend_max: Optional[int] = None
    volume_delivery_pct: Optional[float] = None
    purpose_of_move: str
    forensic_risk_score: int = Field(default=0, ge=0, le=100)  # 0 = pristine, 100 = toxic/hazardous


class PolicyCheckResult(BaseModel):
    """Result of checking a specific fiduciary or risk policy rule."""
    rule_id: str
    rule_name: str
    status: PolicyCheckStatus
    threshold_checked: str
    observation: str


class ReviewEvaluation(BaseModel):
    """Audit evaluation issued by the Tier 2 Reviewer Agent."""
    evaluation_id: str
    proposal_id: str
    reviewer_agent_id: str = "fiduciary_reviewer"
    verdict: str  # "APPROVED" | "REVISION_REQUIRED" | "REJECTED"
    passed_rules_count: int = 0
    total_rules_count: int = 0
    rule_checks: List[PolicyCheckResult] = Field(default_factory=list)
    critique_and_feedback: Optional[str] = None
    suggested_adjustments: Optional[Dict[str, Any]] = None
    investigation_dossier: Optional[InvestigationDossier] = None


class DirectiveCard(BaseModel):
    """Executive decision card presented to the user with actionable closure pills."""
    directive_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    title: str
    display_name: Optional[str] = None
    trend_verdict: Optional[str] = None
    summary_thesis: str
    priority: DirectivePriority = DirectivePriority.NORMAL
    originating_subagents: List[str] = Field(default_factory=list)
    actions: List[ProposedAction] = Field(default_factory=list)
    review_verdict: str = "APPROVED"
    review_summary: str = ""
    investigation_dossier: Optional[InvestigationDossier] = None
    user_status: DirectiveStatus = DirectiveStatus.PENDING_REVIEW
    user_comment: Optional[str] = None
    resolved_at: Optional[str] = None
    holding_quantity: Optional[int] = None
    holding_avg_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    ai_deliberated: bool = False
    ai_deliberation_status: str = "DELIBERATED_BY_GEMINI"
    ai_synthesis_notes: Optional[str] = None


class TimelineEvent(BaseModel):
    """Single debate or workflow event recorded on the blackboard."""
    event_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_id: str
    agent_name: str
    event_type: str  # PROPOSAL, POLICY_CHECK, REVISION_NOTE, APPROVAL, DIRECTIVE_ISSUED, USER_ACTION
    message: str
    proposal_id: Optional[str] = None
    directive_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GuardrailCheck(BaseModel):
    """Specific risk rule or fiduciary guardrail monitored by an agent."""
    guardrail_id: str
    name: str
    threshold: str
    mandate: str
    status: str = "CHECKED_AND_ACTIVE"  # CHECKED_AND_ACTIVE, WARNING, PENDING
    last_audit_result: str
    severity: str = "HIGH"  # CRITICAL, HIGH, NORMAL


class AgentExecutionSummary(BaseModel):
    """Quantitative diagnostics from the agent's latest audit run."""
    total_holdings_scanned: int = 0
    subordinate_reports_reviewed: int = 0
    executive_directives_issued: int = 0
    breached_holdings_count: int = 0
    deep_drawdown_count: int = 0
    concentration_violations_count: int = 0
    max_concentration_holding: Optional[str] = None
    max_concentration_pct: Optional[float] = None
    all_checks_verified: bool = True
    capital_freed_target_inr: float = 0.0


class AgentProfile(BaseModel):
    """Agent identity, role, and current state in the boardroom."""
    agent_id: str
    name: str
    title: str
    tier: AgentTier
    avatar_icon: str
    philosophy: str
    state: AgentState = AgentState.IDLE
    current_task: Optional[str] = None
    last_run_at: Optional[str] = None
    monitored_metrics: List[str] = Field(default_factory=list)
    guardrails: List[GuardrailCheck] = Field(default_factory=list)
    execution_summary: Optional[AgentExecutionSummary] = None
