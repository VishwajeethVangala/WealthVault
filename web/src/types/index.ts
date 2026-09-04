export type AssetClass = 'EQUITY' | 'MUTUAL_FUND' | 'GOLD' | 'NPS'

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
  currency: string
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
}

export interface ReauthRequest {
  api_key?: string
  totp_token?: string
  session_token?: string
}

