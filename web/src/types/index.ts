export type AssetClass = 'EQUITY' | 'MUTUAL_FUND' | 'GOLD' | 'NPS' | 'DEBT' | 'US_STOCKS'

export interface Holding {
  holding_id: string
  owner_id: string
  connection_id: string
  instrument_symbol: string
  asset_class: AssetClass
  quantity: number
  average_price: number
  current_value: number
  current_price?: number
  pnl?: number
  day_change?: number
  day_change_percentage?: number
  day_pnl?: number
  currency: string
  data_freshness?: 'live' | 'cached'
  last_price_updated_at?: string
}

export interface QuoteItem {
  instrument_token?: number
  last_price: number
  volume?: number
  average_price?: number
  ohlc?: {
    open?: number
    high?: number
    low?: number
    close?: number
  }
  net_change?: number
  lower_circuit_limit?: number
  upper_circuit_limit?: number
  last_trade_time?: string
  oi?: number
  timestamp?: string
}

export interface MarketQuotesResponse {
  quotes: Record<string, QuoteItem>
  source: string
  timestamp: string
}

export interface AssetAllocationMetric {
  absolute_value: number
  percentage_weight: number
}

export interface PortfolioSnapshot {
  snapshot_id: string
  owner_id: string
  as_of_date: string
  calculation_version: string
  total_current_value: number
  total_invested_value: number
  total_unrealized_pnl: number
  total_pnl_percentage: number
  asset_allocation: Record<string, AssetAllocationMetric>
  holdings_count: number
  created_at: string
}

export interface BrokerConnection {
  connection_id: string
  owner_id: string
  broker_name: string
  status: string
  last_sync_time?: string
}

export interface PortfolioSummary {
  owner_id: string
  snapshot: PortfolioSnapshot
  connections: BrokerConnection[]
}

export interface User {
  user_id: string
  email: string
  name: string
  picture?: string
  created_at?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

export type BrokerStatus =
  | 'CONNECTED'
  | 'SYNCING'
  | 'AUTH_REQUIRED'
  | 'SESSION_EXPIRED'
  | 'DISCONNECTED'
  | 'PROVIDER_ERROR'

export interface BrokerSessionInfo {
  connection_id: string
  owner_id: string
  broker_name: string
  display_name: string
  status: BrokerStatus
  last_sync_time?: string
  account_id: string
  account_label?: string
  auth_type: string
  session_expires_at?: string
  is_expired: boolean
  mcp_server_url: string
  mcp_protocol: string
  tools_count?: number | null
  holdings_count: number
  total_valuation: number
  last_latency_ms?: number | null
  error_message?: string
  auth_url?: string
  credentials_saved?: boolean
}

export interface CredentialSaveResponse {
  saved_fields: string[]
  login_ok: boolean
  message: string
  auth_url?: string | null
}

export interface ReauthRequest {
  api_key?: string
  totp_token?: string
  session_token?: string
}

export interface CredentialField {
  key: string
  label: string
  secret: boolean
  required: boolean
  help: string
}

export interface BrokerCatalogItem {
  broker_name: string
  display_name: string
  tag: string
  color: string
  auth_type: string
  mcp_protocol: string
  description: string
  supported: boolean
  is_connected: boolean
  connected_count?: number
  coming_soon?: boolean
  credential_fields: CredentialField[]
  setup_url?: string | null
  setup_steps: string[]
}

export interface CreateBrokerConnectionRequest {
  broker_name: string
  account_id?: string
  account_label?: string
  connection_id?: string
  custom_mcp_url?: string
}

export interface BrokerDeleteResponse {
  status: string
  broker_name: string
  connection_id?: string
  holdings_purged: number
  blobs_purged: number
  snapshot_updated: boolean
  remaining_holdings_count: number
  new_total_valuation: number
}

export interface TrendCheck {
  key: string
  label: string
  passed: boolean
  detail: string
}

export interface MomentumSeriesPoint {
  date: string
  close: number
  sma50: number | null
  sma200: number | null
}

export type ReturnWindow = '1M' | '3M' | '6M' | '12M' | '12-1'

// Percent fields are percent values (12.5 = 12.5%)
export interface MomentumAnalysis {
  instrument: string
  name: string | null
  as_of: string
  last_price: number
  candles_used: number
  live_bar?: boolean
  trend_score: number
  trend_max_score: number
  trend_verdict: string
  trend_checks: TrendCheck[]
  sma_20: number | null
  sma_50: number | null
  sma_200: number | null
  pct_from_sma50: number | null
  pct_from_sma200: number | null
  sma200_slope_pct: number | null
  cross_state: 'golden' | 'death' | null
  days_since_cross: number | null
  macd: number | null
  macd_signal: number | null
  macd_histogram: number | null
  returns: Partial<Record<ReturnWindow, number | null>>
  volatility_6m: number | null
  volatility_12m: number | null
  risk_adjusted_6m: number | null
  risk_adjusted_12m: number | null
  rsi_14: number | null
  high_52w: number | null
  low_52w: number | null
  pct_from_52w_high: number | null
  pct_from_52w_low: number | null
  benchmark: string
  relative_strength: Partial<Record<Exclude<ReturnWindow, '12-1'>, number | null>>
  series: MomentumSeriesPoint[]
}




export interface StrategyStats {
  initial_capital: number
  final_equity: number
  net_profit: number
  net_profit_pct: number
  cagr_pct: number
  max_drawdown_pct: number
  buy_hold_return_pct: number
  total_trades: number
  open_trade: boolean
  win_rate_pct: number | null
  avg_win_pct: number | null
  avg_loss_pct: number | null
  profit_factor: number | null
  avg_bars_held: number | null
  exposure_pct: number
  signal_exits: number
  stop_exits: number
}

export interface StrategyTrade {
  entry_date: string
  entry_price: number
  exit_date: string | null
  exit_price: number | null
  exit_reason: '200DMA BREAK' | 'OPEN'
  quantity: number
  pnl: number
  pnl_pct: number
  bars_held: number
  is_open: boolean
}

// "Below 200DMA -> ATH Break -> Hold till 200DMA Break" (see core/analytics/ath_breakout_strategy.py)
export interface AthBreakoutParams {
  dma_length: number
  window_bars: number
  capital_per_trade: number
  initial_capital: number
  start_date: string
  commission_pct: number
}

export interface AthBreakoutStatus {
  state: 'IN_POSITION' | 'FLAT'
  headline: string
  detail: string
  last_signal: 'BUY' | 'SELL' | null
  close: number
  dma: number | null
  prior_ath: number | null
  pct_to_ath: number | null
  days_since_below_dma: number | null
  in_window: boolean
  window_days_left: number | null
  pct_above_dma: number | null
  entry_date: string | null
  entry_price: number | null
  unrealized_pct: number | null
  bars_held: number | null
}

export interface AthBreakoutBar {
  date: string
  high: number
  close: number
  dma: number | null
  ath: number | null
  in_window: boolean
  buy: boolean
  sell: boolean
  equity: number
  buy_hold: number
}

export interface AthBreakoutResult {
  instrument: string
  name: string | null
  as_of: string
  params: AthBreakoutParams
  history_start: string
  test_start: string
  test_end: string
  bars_tested: number
  partial_bar_excluded: boolean
  live_bar?: boolean
  live_price?: number | null
  status: AthBreakoutStatus
  stats: StrategyStats
  trades: StrategyTrade[]
  series: AthBreakoutBar[]
}

export interface AthBreakoutOptions {
  start_date?: string
  dma_length?: number
  window_bars?: number
  capital_per_trade?: number
}

export interface SupertrendParams {
  atr_period: number
  factor: number
  use_adx_filter: boolean
  adx_threshold: number
  use_vol_filter: boolean
  vol_length: number
  max_bars_after_flip: number
  capital_per_trade: number
  initial_capital: number
  start_date: string
  commission_pct: number
}

export interface SupertrendStatus {
  state: 'IN_POSITION' | 'FLAT'
  headline: string
  detail: string
  last_signal: 'BUY' | 'SELL' | null
  close: number
  supertrend: number
  direction: number
  adx: number | null
  volume: number
  vol_sma: number | null
  volume_ratio: number | null
  bars_since_flip: number | null
  entry_date: string | null
  entry_price: number | null
  unrealized_pct: number | null
  bars_held: number | null
}

export interface SupertrendBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  supertrend: number
  direction: number
  adx: number | null
  vol_sma: number | null
  buy: boolean
  sell: boolean
  equity: number
  buy_hold: number
}

export interface SupertrendResult {
  instrument: string
  name: string | null
  as_of: string
  params: SupertrendParams
  history_start: string
  test_start: string
  test_end: string
  bars_tested: number
  partial_bar_excluded: boolean
  live_bar?: boolean
  live_price?: number | null
  status: SupertrendStatus
  stats: StrategyStats
  trades: StrategyTrade[]
  series: SupertrendBar[]
}

export interface SupertrendOptions {
  start_date?: string
  atr_period?: number
  factor?: number
  use_adx_filter?: boolean
  adx_threshold?: number
  use_vol_filter?: boolean
  vol_length?: number
  max_bars_after_flip?: number
  capital_per_trade?: number
}

export interface ScreenerRecommendation {
  symbol: string
  name: string
  close?: number
  volume?: number
  per_chg?: number
}

export interface ScreenerRecommendationsResponse {
  slug: string
  title: string
  fetched_at: string
  items: ScreenerRecommendation[]
  count: number
}

export interface TargetAllocation {
  owner_id: string
  targets: Record<string, number>
  updated_at?: string
}

// Equity signals (momentum, 200-DMA ATH breakout), computed per stock by the backend
export interface MomentumSignal {
  verdict: string
  score: number
  max: number
  last_price: number
  high_52w: number | null
  low_52w: number | null
  pct_from_52w_high: number | null
  range_pos: number | null
}

/** A closed trade: where the strategy said sell. */
export interface ExitCall {
  signal_date: string
  exit_date: string
  exit_price: number | null
  reason: string
  entry_date: string
  entry_price: number | null
  pnl_pct: number | null
  bars_held: number | null
}

export interface PendingSell {
  signal_date: string
  signal_close: number
  reason: string
  entry_date: string | null
  entry_price: number | null
}

export interface AthSignal {
  state: 'IN_POSITION' | 'FLAT'
  headline: string
  detail: string
  last_signal: 'BUY' | 'SELL' | null
  entry_date: string | null
  entry_price: number | null
  bars_held: number | null
  in_window: boolean
  window_days_left: number | null
  pct_to_ath: number | null
  pct_above_dma: number | null
  as_of: string
  call?: AthCall | null
  exits?: ExitCall[]
}

export interface StockSignals {
  instrument: string
  name?: string | null
  as_of?: string | null
  history_days?: number
  /** the most recent sessions (up to 7) for this stock, oldest first */
  last_sessions?: string[]
  /** present when the row was rebuilt on the live price: today's bar is unfinished until the close */
  live?: { price: number; date: string; at: string }
  live_date?: string
  momentum: MomentumSignal | null
  ath: AthSignal | null
  errors: Record<string, string>
  computed_at?: string
  currency?: string
  history_status?: 'complete' | 'partial'
  history_note?: string
  history_first?: string
}

export interface SignalsJob {
  state: 'idle' | 'running' | 'done' | 'error'
  total: number
  done: number
  failed: number
  started_at: string | null
  finished_at: string | null
  message: string | null
  auth_url: string | null
  /** where the stocks come from: on the Chartink list, held, and on both (counted once in `total`) */
  list_count?: number
  holdings_count?: number
  overlap?: number
  /** 'manual' (the button) or 'schedule' (the market-hours auto refresh) */
  trigger?: 'manual' | 'schedule'
}

export interface SignalsResponse {
  job: SignalsJob
  symbol_map: Record<string, string>
  signals: Record<string, StockSignals>
}

export interface UsLiveQuote {
  price: number
  day_change: number | null
  day_change_pct: number | null
  prev_close: number | null
  ext_price: number | null
  ext_change_pct: number | null
  updated: string | null
}

export interface UsLiveResponse {
  quotes: Record<string, UsLiveQuote>
  session_closed: boolean
}

// Stage 2 screener (stocks from a saved Chartink screener, with the same signals as Equity signals)
export interface Stage2Row {
  sr?: number
  nsecode: string
  name: string
  bsecode?: string
  close: number
  per_chg: number
  volume: number
  held: boolean
  is_new: boolean | null
  [extra: string]: unknown
}

export interface Stage2Response {
  job: SignalsJob
  list: {
    title: string
    date: string
    fetched_at: string
    url: string
    extra_columns: string[]
    previous_date: string | null
    rows: Stage2Row[]
    dropped: { nsecode: string; name?: string }[]
  } | null
  signals: Record<string, StockSignals>
  /** the market-hours auto refresh */
  auto?: AutoRefresh
}

export interface AutoRefresh {
  enabled: boolean
  every_minutes: number
  window: string
  next_run: string | null
  last_run: { slot: string; at: string; outcome: 'ran' | 'skipped' | 'failed'; message: string; users: number } | null
}

export interface Stage2LiveResponse {
  quotes: Record<string, { price: number; day_change_pct: number | null }>
}

export interface AthCall {
  signal_date: string
  entry_date: string
  entry_price: number
  close: number
  prior_ath: number | null
  above_ath_pct: number | null
  days_since_below_dma: number | null
  window_bars: number
  dma: number | null
  above_dma_pct: number | null
  queued: boolean
}

export interface WatchlistItem {
  symbol: string
  name: string
  notes: string
  target_price: number | null
  price_when_added: number | null
  added_at: string
  last_price: number | null
  pct_since_added: number | null
  trend_verdict: string | null
  trend_score: number | null
  signal_state: string | null
}

export interface WatchlistResponse {
  items: WatchlistItem[]
  count: number
}

// --- Agent Boardroom Types ---

export interface GuardrailCheck {
  guardrail_id: string
  name: string
  threshold: string
  mandate: string
  status: 'CHECKED_AND_ACTIVE' | 'WARNING' | 'PENDING'
  last_audit_result: string
  severity: 'CRITICAL' | 'HIGH' | 'NORMAL'
}

export interface AgentExecutionSummary {
  total_holdings_scanned?: number
  subordinate_reports_reviewed?: number
  executive_directives_issued?: number
  breached_holdings_count?: number
  deep_drawdown_count?: number
  concentration_violations_count?: number
  max_concentration_holding?: string | null
  max_concentration_pct?: number | null
  all_checks_verified?: boolean
  capital_freed_target_inr?: number
}

export interface AgentProfile {
  agent_id: string
  name: string
  title: string
  tier: 'DOMAIN_SPECIALIST' | 'FIDUCIARY_REVIEWER' | 'EXECUTIVE_BOSS'
  avatar_icon: string
  philosophy: string
  state: 'IDLE' | 'ANALYZING' | 'PROPOSAL_GENERATED' | 'WAITING_REVIEW' | 'REVISION_REQUESTED' | 'APPROVED' | 'SYNTHESIZED'
  current_task?: string | null
  last_run_at?: string | null
  monitored_metrics: string[]
  guardrails?: GuardrailCheck[]
  execution_summary?: AgentExecutionSummary
}

export interface ProposedAction {
  symbol: string
  display_name?: string | null
  broker: string
  action: 'CUT_LOSS' | 'TRAILING_TRIM' | 'REBALANCE' | 'PYRAMID_ADD' | 'HOLD_DEFENSE' | 'EXIT_ALL'
  quantity: number
  estimated_price: number
  trigger_reason: string
  suggested_stop_loss?: number | null
  target_price?: number | null
  order_type: string
  trend_verdict?: string | null
  holding_quantity?: number | null
  holding_avg_price?: number | null
  pnl_pct?: number | null
}

export interface NewsCatalyst {
  headline: string
  source: string
  published_at: string
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'
  category: string
  link?: string | null
}

export interface FundamentalVitals {
  market_cap_cr?: number | null
  pe_ratio?: number | null
  book_value?: number | null
  roce_pct?: number | null
  roe_pct?: number | null
  debt_to_equity?: number | null
  sales_growth_yoy_pct?: number | null
  net_profit_cr?: number | null
  promoter_holding_pct?: number | null
  promoter_pledged_pct?: number | null
  fii_dii_trend: string
  pros: string[]
  cons: string[]
}

export interface InvestigationDossier {
  symbol: string
  timestamp: string
  causality: 'SYSTEMIC_MARKET_BETA' | 'COMPANY_SPECIFIC' | 'SPECULATIVE_MANIPULATION'
  causality_explanation: string
  market_benchmark_delta: Record<string, number>
  recent_news: NewsCatalyst[]
  fundamental_vitals: FundamentalVitals
  technical_trend?: string | null
  trend_score?: number | null
  trend_max?: number | null
  volume_delivery_pct?: number | null
  purpose_of_move: string
  forensic_risk_score: number
}

export interface DirectiveCard {
  directive_id: string
  timestamp: string
  title: string
  display_name?: string | null
  trend_verdict?: string | null
  summary_thesis: string
  priority: 'CRITICAL' | 'HIGH' | 'NORMAL' | 'LOW'
  originating_subagents: string[]
  actions: ProposedAction[]
  review_verdict: string
  review_summary: string
  investigation_dossier?: InvestigationDossier | null
  user_status: 'PENDING_REVIEW' | 'ORDER_PLACED_AT_BROKER' | 'IGNORED' | 'SNOOZED' | 'SIMULATED'
  user_comment?: string | null
  resolved_at?: string | null
  holding_quantity?: number | null
  holding_avg_price?: number | null
  pnl_pct?: number | null
  ai_deliberated?: boolean
  ai_deliberation_status?: 'DELIBERATED_BY_GEMINI' | 'HELD_API_KEY_REQUIRED' | 'HELD_NETWORK_ERROR' | string
  ai_synthesis_notes?: string | null
}

export interface TimelineEvent {
  event_id: string
  timestamp: string
  agent_id: string
  agent_name: string
  event_type: string
  message: string
  proposal_id?: string | null
  directive_id?: string | null
  metadata: Record<string, unknown>
}

export interface BoardroomOverview {
  agents: AgentProfile[]
  active_directives: DirectiveCard[]
  historical_directives: DirectiveCard[]
  timeline: TimelineEvent[]
  ai_deliberation_status?: 'DELIBERATED_BY_GEMINI' | 'HELD_API_KEY_REQUIRED' | 'HELD_NETWORK_ERROR' | string
  ai_status_message?: string | null
}

// --- Ground-Level Scout Swarm Types ---

export interface RiskIntelReport {
  symbol: string
  current_price: number
  average_price: number
  quantity: number
  pnl_pct: number
  portfolio_weight_pct: number
  stop_loss_breach: boolean
  deep_drawdown_breach: boolean
  over_concentration: boolean
  broker_source: string
  status: string
  summary: string
  completed_at: string
}

export interface TechIntelReport {
  symbol: string
  current_price: number
  sma_50?: number | null
  sma_200?: number | null
  slope_200_sma?: number | null
  golden_cross?: boolean | null
  stage_verdict: string
  momentum_score: number
  momentum_max: number
  rs_score_vs_nifty?: number | null
  rs_rating_label?: 'OUTPERFORMING' | 'IN_LINE' | 'UNDERPERFORMING' | string | null
  market_regime?: 'BULL_MARKET' | 'NEUTRAL_CHOPPY' | 'BEAR_CORRECTION' | string | null
  nifty_trend_summary?: string | null
  status: string
  summary: string
  completed_at: string
}

export interface PatternIntelReport {
  symbol: string
  pattern_detected: boolean
  pattern_name?: string | null
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  confidence: number
  pivot_breakout_price?: number | null
  support_stop_price?: number | null
  pattern_stage?: string | null
  volume_surge_ratio?: number | null
  volume_dryup_confirmed?: boolean | null
  is_low_volume_trap?: boolean
  status: string
  summary: string
  completed_at: string
}

export interface FundaIntelReport {
  symbol: string
  is_etf: boolean
  market_cap_cr?: number | null
  pe_ratio?: number | null
  roce_pct?: number | null
  roe_pct?: number | null
  debt_to_equity?: number | null
  sales_growth_3y?: number | null
  promoter_holding_pct?: number | null
  promoter_pledged_pct?: number | null
  status: string
  summary: string
  completed_at: string
}

export interface NewsArticleItem {
  headline: string
  source: string
  published_at: string
  link?: string | null
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'
  confidence: number
  category: string
}

export interface NewsIntelReport {
  symbol: string
  articles_scanned: number
  positive_count: number
  negative_count: number
  neutral_count: number
  dominant_sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'
  sentiment_confidence: number
  material_threat: boolean
  threat_reasons: string[]
  articles: NewsArticleItem[]
  status: string
  summary: string
  completed_at: string
}

export interface BulkDealItem {
  date: string
  client_name: string
  buy_sell: 'BUY' | 'SELL'
  quantity: number
  price: number
  deal_type: 'BULK' | 'BLOCK'
  remarks?: string | null
}

export interface PITDisclosureItem {
  date: string
  person_name: string
  category_of_person: string
  transaction_type: 'BUY' | 'SELL' | 'PLEDGE' | 'REVOKE'
  quantity: number
  value_inr: number
}

export interface InsiderIntelReport {
  symbol: string
  is_etf: boolean
  bulk_deals: BulkDealItem[]
  block_deals: BulkDealItem[]
  pit_disclosures: PITDisclosureItem[]
  institutional_bias: 'ACCUMULATION' | 'DISTRIBUTION' | 'NEUTRAL' | 'NO_DEALS'
  promoter_bias: 'BUYING' | 'SELLING' | 'NEUTRAL' | 'NO_FILINGS'
  status: string
  summary: string
  completed_at: string
}

export interface GroundStockDossier {
  symbol: string
  company_name: string
  is_etf: boolean
  risk_report?: RiskIntelReport | null
  tech_report?: TechIntelReport | null
  pattern_report?: PatternIntelReport | null
  funda_report?: FundaIntelReport | null
  news_report?: NewsIntelReport | null
  insider_report?: InsiderIntelReport | null
  barrier_status: 'PENDING' | 'IN_PROGRESS' | 'READY_FOR_REVIEW' | 'QUARANTINED'
  completed_scouts: string[]
  required_scouts: string[]
  missing_scouts: string[]
  current_scout?: string | null
  last_updated: string
}

export interface GroundSwarmOverview {
  dossiers: GroundStockDossier[]
  status: {
    is_scanning: boolean
    current_stock?: string | null
    current_scout?: string | null
    total_dossiers: number
    ready_dossiers: number
    timestamp: string
  }
}



