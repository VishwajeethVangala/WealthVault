import type { LiveSignalsResponse } from '../components/signals/useLiveSignals'
import type { SignalsJob, SignalsResponse, Stage2LiveResponse, Stage2Response, UsLiveResponse, CredentialSaveResponse, TargetAllocation, AuthResponse, BrokerCatalogItem, BrokerDeleteResponse, BrokerSessionInfo, CreateBrokerConnectionRequest, Holding, MarketQuotesResponse, MomentumAnalysis, PortfolioSummary, ReauthRequest, SwingStrategyOptions, SwingStrategyResult, User, AthBreakoutOptions, AthBreakoutResult } from '../types'

const TOKEN_KEY = 'wv_token'
const USER_KEY = 'wv_user'

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export const getStoredUser = (): User | null => {
  const data = localStorage.getItem(USER_KEY)
  if (!data) return null
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

export const setStoredUser = (user: User) => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

// Error carrying HTTP status and the parsed FastAPI `detail` field
export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(options.headers || {})

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(endpoint, {
    ...options,
    headers,
  })

  if (!response.ok) {
    if (response.status === 401) {
      console.warn('Session unauthorized or expired')
    }
    const errorBody = await response.text()
    let detail: unknown = undefined
    try {
      detail = JSON.parse(errorBody)?.detail
    } catch {
      // Non-JSON error body
    }
    throw new ApiError(`API Error ${response.status}: ${errorBody || response.statusText}`, response.status, detail)
  }

  return response.json()
}

// Fetch Public Auth Config
export async function fetchAuthConfig(): Promise<{ google_client_id: string; environment: string; support_email?: string }> {
  return fetchApi<{ google_client_id: string; environment: string; support_email?: string }>('/api/v1/auth/config')
}

// Erase the signed-in user's profile and every piece of data held for them
export async function deleteAccount(): Promise<void> {
  await fetchApi('/api/v1/auth/account', { method: 'DELETE', body: JSON.stringify({ confirm: 'DELETE' }) })
}

// Verify Session Validity with Backend
export async function verifySession(): Promise<User | null> {
  const token = getToken()
  if (!token) return null
  try {
    const user = await fetchApi<User>('/api/v1/accounts/me')
    setStoredUser(user)
    return user
  } catch {
    clearToken()
    return null
  }
}

// Google OAuth Login
export async function authenticateWithGoogle(credential: string): Promise<AuthResponse> {
  const data = await fetchApi<AuthResponse>('/api/v1/auth/google', {
    method: 'POST',
    body: JSON.stringify({ credential }),
  })

  setToken(data.access_token)
  setStoredUser(data.user)
  return data
}

// Portfolio API Calls
export async function fetchPortfolioSummary(): Promise<PortfolioSummary> {
  return fetchApi<PortfolioSummary>('/api/v1/portfolio/summary')
}

export async function fetchPortfolioHoldings(broker = 'all', opts: { indmoneyLive?: boolean } = {}): Promise<Holding[]> {
  const params = new URLSearchParams()
  if (broker !== 'all') params.set('broker', broker)
  if (opts.indmoneyLive) params.set('indmoney_live', 'true')
  const query = params.toString() ? `?${params.toString()}` : ''
  return fetchApi<Holding[]>(`/api/v1/portfolio/holdings${query}`)
}

export async function triggerPortfolioSync(): Promise<any> {
  return fetchApi('/api/v1/portfolio/sync', {
    method: 'POST',
  })
}

export async function fetchMarketQuotes(instruments: string[]): Promise<MarketQuotesResponse> {
  const query = instruments.length > 0 ? `?instruments=${encodeURIComponent(instruments.join(','))}` : ''
  return fetchApi<MarketQuotesResponse>(`/api/v1/portfolio/quotes${query}`)
}

// Broker Session & MCP Telemetry API Calls
export async function fetchBrokerSessions(): Promise<BrokerSessionInfo[]> {
  return fetchApi<BrokerSessionInfo[]>('/api/v1/portfolio/sessions')
}

export async function syncBroker(connectionIdOrBroker: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(connectionIdOrBroker)}/sync`, {
    method: 'POST',
  })
}

export async function reauthBroker(connectionIdOrBroker: string, data?: ReauthRequest): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(connectionIdOrBroker)}/reauth`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  })
}

export async function expireBroker(connectionIdOrBroker: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(connectionIdOrBroker)}/expire`, {
    method: 'POST',
  })
}

export async function disconnectBroker(connectionIdOrBroker: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(connectionIdOrBroker)}/disconnect`, {
    method: 'POST',
  })
}

export async function fetchBrokerCatalog(): Promise<BrokerCatalogItem[]> {
  return fetchApi<BrokerCatalogItem[]>('/api/v1/portfolio/brokers/catalog')
}

export async function addBrokerConnection(data: CreateBrokerConnectionRequest): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>('/api/v1/portfolio/connections', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteBrokerConnection(connectionIdOrBroker: string, wipeBlobs = true): Promise<BrokerDeleteResponse> {
  return fetchApi<BrokerDeleteResponse>(`/api/v1/portfolio/connections/${encodeURIComponent(connectionIdOrBroker)}?wipe_blobs=${wipeBlobs}`, {
    method: 'DELETE',
  })
}



// Market Analytics API Calls
export async function fetchMomentum(symbol: string): Promise<MomentumAnalysis> {
  return fetchApi<MomentumAnalysis>(`/api/v1/analytics/momentum?symbol=${encodeURIComponent(symbol)}`)
}

export async function fetchSwingStrategy(symbol: string, options: SwingStrategyOptions = {}): Promise<SwingStrategyResult> {
  const params = new URLSearchParams({ symbol })
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value))
  })
  return fetchApi<SwingStrategyResult>(`/api/v1/analytics/strategy/swing-v21?${params.toString()}`)
}

export async function fetchAthBreakoutStrategy(symbol: string, options: AthBreakoutOptions = {}): Promise<AthBreakoutResult> {
  const params = new URLSearchParams({ symbol })
  Object.entries(options).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value))
  })
  return fetchApi<AthBreakoutResult>(`/api/v1/analytics/strategy/ath-breakout?${params.toString()}`)
}

// Target allocation (stored per user in Azure Table Storage)
export async function fetchTargets(): Promise<TargetAllocation> {
  return fetchApi<TargetAllocation>('/api/v1/portfolio/targets')
}

export async function saveTargets(targets: Record<string, number>): Promise<TargetAllocation> {
  return fetchApi<TargetAllocation>('/api/v1/portfolio/targets', {
    method: 'PUT',
    body: JSON.stringify({ targets }),
  })
}

// Broker API credentials (Groww, Angel One). Values are write-only: the backend never returns them.
export async function saveBrokerCredentials(connectionRef: string, fields: Record<string, string>): Promise<CredentialSaveResponse> {
  return fetchApi<CredentialSaveResponse>(`/api/v1/portfolio/connections/${encodeURIComponent(connectionRef)}/credentials`, {
    method: 'PUT',
    body: JSON.stringify({ fields }),
  })
}

// Daily portfolio value history (from the snapshots every sync stores)
export interface HistoryPoint {
  date: string
  value: number
  invested: number
  /** value of each asset class that day, keyed by class name */
  classes?: Record<string, number>
}

export async function fetchHistory(days = 365): Promise<HistoryPoint[]> {
  return fetchApi<HistoryPoint[]>(`/api/v1/portfolio/history?days=${days}`)
}

// Equity signals
export async function fetchSignals(market: 'in' | 'us' = 'in'): Promise<SignalsResponse> {
  return fetchApi<SignalsResponse>(`/api/v1/analytics/signals?market=${market}`)
}

export async function fetchLiveSignals(market: 'in' | 'us' = 'in'): Promise<LiveSignalsResponse> {
  return fetchApi<LiveSignalsResponse>(`/api/v1/analytics/signals/live?market=${market}`)
}

export async function fetchStage2LiveSignals(): Promise<LiveSignalsResponse> {
  return fetchApi<LiveSignalsResponse>('/api/v1/analytics/stage2/live-signals')
}

export interface PortfolioRisk {
  days: number; since: string; until: string; beta: number | null; correlation: number | null
  volatility_pct: number; benchmark_volatility_pct: number; downside_volatility_pct: number; var95_1d_pct: number
  max_drawdown_pct: number; best_day_pct: number; worst_day_pct: number; positive_days_pct: number
  coverage_pct: number; stocks: number; high_beta: { name: string; weight: number; beta: number; contribution: number }[]
}

export interface PortfolioRiskResponse { risk: PortfolioRisk | null; equity_value: number; measured_stocks: number; total_stocks: number; ready: boolean }

export async function fetchPortfolioRisk(): Promise<PortfolioRiskResponse> {
  return fetchApi<PortfolioRiskResponse>('/api/v1/analytics/signals/risk')
}

export async function fetchSymbolMap(): Promise<{ in: Record<string, string>; us: Record<string, string> }> {
  return fetchApi('/api/v1/analytics/signals/symbol-map')
}

export async function fetchUsLive(): Promise<UsLiveResponse> {
  return fetchApi<UsLiveResponse>('/api/v1/analytics/signals/us-live')
}

export async function refreshSignals(market: 'in' | 'us' = 'in'): Promise<SignalsJob> {
  return fetchApi<SignalsJob>(`/api/v1/analytics/signals/refresh?market=${market}`, { method: 'POST' })
}

// Stage 2 screener
export async function fetchStage2(): Promise<Stage2Response> {
  return fetchApi<Stage2Response>('/api/v1/analytics/stage2')
}

export async function refreshStage2(): Promise<SignalsJob> {
  return fetchApi<SignalsJob>('/api/v1/analytics/stage2/refresh', { method: 'POST' })
}

export async function fetchStage2Live(): Promise<Stage2LiveResponse> {
  return fetchApi<Stage2LiveResponse>('/api/v1/analytics/stage2/live')
}
