import type { AuthResponse, BrokerCatalogItem, BrokerSessionInfo, CreateBrokerConnectionRequest, Holding, MarketQuotesResponse, PortfolioSummary, ReauthRequest, User } from '../types'

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
    throw new Error(`API Error ${response.status}: ${errorBody || response.statusText}`)
  }

  return response.json()
}

// Fetch Public Auth Config
export async function fetchAuthConfig(): Promise<{ google_client_id: string; environment: string }> {
  return fetchApi<{ google_client_id: string; environment: string }>('/api/v1/auth/config')
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

export async function fetchPortfolioHoldings(broker = 'all'): Promise<Holding[]> {
  const query = broker !== 'all' ? `?broker=${encodeURIComponent(broker)}` : ''
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

export async function syncBroker(brokerName: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(brokerName)}/sync`, {
    method: 'POST',
  })
}

export async function reauthBroker(brokerName: string, data?: ReauthRequest): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(brokerName)}/reauth`, {
    method: 'POST',
    body: JSON.stringify(data || {}),
  })
}

export async function expireBroker(brokerName: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(brokerName)}/expire`, {
    method: 'POST',
  })
}

export async function disconnectBroker(brokerName: string): Promise<BrokerSessionInfo> {
  return fetchApi<BrokerSessionInfo>(`/api/v1/portfolio/sessions/${encodeURIComponent(brokerName)}/disconnect`, {
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

export async function deleteBrokerConnection(brokerName: string): Promise<any> {
  return fetchApi(`/api/v1/portfolio/connections/${encodeURIComponent(brokerName)}`, {
    method: 'DELETE',
  })
}


