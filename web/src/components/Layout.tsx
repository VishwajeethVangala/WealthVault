import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { Eye, EyeOff, LogOut, Moon, RefreshCw, Sun } from 'lucide-react'
import { clearToken, fetchBrokerSessions, getStoredUser, syncBroker } from '../utils/api'
import { PRIVACY_READY_PATHS, SHOW_THEME_TOGGLE } from '../utils/features'
import { trackScreen } from '../utils/analytics'
import { AnalyticsBanner } from './AnalyticsConsent'
import { Sidebar } from './Sidebar'
import { NAV_ITEMS, isNavActive } from './navItems'
import { GlobalFilters } from './GlobalFilters'
import { usePortfolio } from '../context/PortfolioContext'
import { useTheme } from '../context/ThemeContext'
import { usePrivacy } from '../context/PrivacyContext'
import { buildInstruments } from './holdings/holdingsModel'
import type { BrokerSessionInfo } from '../types'

interface LayoutProps {
  children: React.ReactNode
  onLogout?: () => void
}

const formatClock = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }) : null

export const Layout: React.FC<LayoutProps> = ({ children, onLogout }) => {
  const location = useLocation()
  const user = getStoredUser()
  const { holdings, refresh, lastRefreshedAt, dataFreshness } = usePortfolio()
  const { theme, toggle } = useTheme()
  const { hidden, toggle: toggleHidden } = usePrivacy()

  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncProgress, setSyncProgress] = useState('')
  const [syncStatus, setSyncStatus] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await fetchBrokerSessions())
    } catch (err) {
      console.warn('Could not load broker sessions for the shell:', err)
    }
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  const path = location.pathname

  useEffect(() => {
    trackScreen(path)
  }, [path])
  // Portfolio filters do not apply to single-stock or broker pages
  // (Holdings has its own toolbar, built on the same URL filters)
  const hideGlobalFilters = path === '/brokers' || path === '/signals' || path === '/momentum' || path === '/strategy' || path === '/holdings' || path === '/account'

  const connected = sessions.filter((s) => s.status === 'CONNECTED').length
  const lastSync = useMemo(
    () => sessions.map((s) => s.last_sync_time).filter(Boolean).sort().pop() ?? null,
    [sessions],
  )

  const heading = useMemo(() => {
    const syncLine = lastSync
      ? `Synced ${formatClock(lastSync)} · ${connected} of ${sessions.length} brokers`
      : sessions.length > 0
      ? `${connected} of ${sessions.length} brokers connected`
      : 'No brokers linked yet'
    const priceLine = lastRefreshedAt
      ? ` · Prices ${dataFreshness === 'live' ? 'live' : 'stored'}, updated ${lastRefreshedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}`
      : ''
    if (path === '/holdings') return { title: 'Holdings', sub: `Merged across ${sessions.length} ${sessions.length === 1 ? 'broker' : 'brokers'} · ${syncLine}${priceLine}` }
    if (path === '/brokers') return { title: 'Brokers', sub: 'Connect, sync and manage your broker accounts' }
    if (path === '/signals') return { title: 'Signals', sub: 'Momentum and 200-DMA ATH breakout for the stocks you hold and your Chartink Stage 2 list' }
    if (path === '/momentum') return { title: 'Momentum', sub: 'Trend, returns and relative strength for one stock' }
    if (path === '/strategy') return { title: 'ATH Strategy', sub: 'The 200-DMA to all-time-high breakout: signal and backtest on daily candles' }
    if (path === '/account') return { title: 'Account', sub: 'Your sign-in, privacy and data' }
    return { title: 'Overview', sub: syncLine }
  }, [path, lastSync, connected, sessions.length, lastRefreshedAt, dataFreshness])

  // "Sync all" runs each broker's own Sync, one after another (they all rewrite the stored holdings, so not in parallel),
  // so it behaves exactly like the Sync button on a broker card and says which brokers need a login or failed.
  const handleSync = async () => {
    setIsSyncing(true)
    setSyncStatus(null)
    let issues = 0
    try {
      const list = await fetchBrokerSessions()
      setSessions(list)
      const problems: string[] = []
      let ok = 0
      for (let i = 0; i < list.length; i++) {
        const name = list[i].display_name.split(' — ')[0]
        setSyncProgress(`Syncing ${i + 1} of ${list.length}…`)
        try {
          const updated = await syncBroker(list[i].connection_id)
          if (updated.status === 'CONNECTED') ok++
          else problems.push(`${name} ${['AUTH_REQUIRED', 'SESSION_EXPIRED'].includes(updated.status) ? 'needs a login' : 'could not sync'}`)
        } catch {
          problems.push(`${name} failed`)
        }
      }
      await Promise.all([refresh(), loadSessions()])
      issues = problems.length
      setSyncStatus(
        list.length === 0
          ? { tone: 'bad', text: 'No brokers linked yet' }
          : problems.length === 0
            ? { tone: 'ok', text: list.length === 1 ? 'Synced' : `Synced all ${list.length} brokers` }
            : { tone: 'bad', text: `Synced ${ok} of ${list.length} · ${problems.join(', ')}` },
      )
    } catch (err) {
      console.error('Sync failed:', err)
      issues = 1
      setSyncStatus({ tone: 'bad', text: 'Sync failed' })
    } finally {
      setIsSyncing(false)
      setSyncProgress('')
      setTimeout(() => setSyncStatus(null), issues > 0 ? 12000 : 4000)
    }
  }

  // one holding per instrument, as the Holdings page counts them (a stock held with two brokers is one holding)
  const holdingsCount = useMemo(() => buildInstruments(holdings).length, [holdings])

  const handleLogout = () => {
    clearToken()
    if (onLogout) onLogout()
    else window.location.reload()
  }

  return (
    <div className="app">
      <Sidebar holdingsCount={holdingsCount} sessions={sessions} />

      <div className="main">
        <header className="topbar">
          <div className="grow">
            <h1 className="h1">{heading.title}</h1>
            <p className="sub num">{heading.sub}</p>
          </div>

          {syncStatus && (
            <span className={`badge ${syncStatus.tone === 'ok' ? 'ok' : 'bad'}`} role="status">
              <i />
              {syncStatus.text}
            </span>
          )}

          {PRIVACY_READY_PATHS.includes(path) && (
            <button
              className="btn btn-ghost btn-icon"
              type="button"
              onClick={toggleHidden}
              aria-label={hidden ? 'Show amounts' : 'Hide amounts'}
              aria-pressed={hidden}
            >
              {hidden ? <EyeOff size={18} strokeWidth={1.75} /> : <Eye size={18} strokeWidth={1.75} />}
            </button>
          )}

          {SHOW_THEME_TOGGLE && (
            <button className="btn btn-ghost btn-icon" type="button" onClick={toggle} aria-label="Toggle dark mode">
              {theme === 'dark' ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
            </button>
          )}

          <button className="btn btn-primary" type="button" onClick={handleSync} disabled={isSyncing}>
            <RefreshCw size={16} strokeWidth={1.75} className={isSyncing ? 'animate-spin' : ''} />
            {isSyncing ? syncProgress || 'Syncing…' : 'Sync all'}
          </button>

          {user && (
            <>
              <Link to="/account" className="avatar" title={`${user.name} · Account`} aria-label="Account">
                {user.picture ? <img src={user.picture} alt="" referrerPolicy="no-referrer" /> : user.name.charAt(0).toUpperCase()}
              </Link>
              <button className="btn btn-ghost btn-icon" type="button" onClick={handleLogout} aria-label="Sign out" title="Sign out">
                <LogOut size={18} strokeWidth={1.75} />
              </button>
            </>
          )}
        </header>

        {!hideGlobalFilters && (
          <div style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}>
            <GlobalFilters />
          </div>
        )}

        <main className="page">{children}</main>
        <AnalyticsBanner />
      </div>

      <nav className="tabbar" aria-label="Mobile">
        {NAV_ITEMS.map((item) => {
          const active = isNavActive(path, item.path)
          const Icon = item.icon
          return (
            <NavLink
              key={item.id}
              to={{ pathname: item.path, search: location.search }}
              className={active ? 'tab on' : 'tab'}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={20} strokeWidth={1.75} />
              {item.short}
            </NavLink>
          )
        })}
      </nav>
    </div>
  )
}
