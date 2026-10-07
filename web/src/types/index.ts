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
  tools_count: number
  holdings_count: number
  total_valuation: number
  last_latency_ms: number
  error_message?: string
  auth_url?: string
}

export interface ReauthRequest {
  api_key?: string
  totp_token?: string
  session_token?: string
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



