import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Eye, EyeOff, LogOut, Moon, RefreshCw, Sun } from 'lucide-react'
import { clearToken, fetchBrokerSessions, getStoredUser, triggerPortfolioSync } from '../utils/api'
import { PRIVACY_READY_PATHS, SHOW_THEME_TOGGLE } from '../utils/features'
import { Sidebar } from './Sidebar'
import { NAV_ITEMS, isNavActive } from './navItems'
import { GlobalFilters } from './GlobalFilters'
import { usePortfolio } from '../context/PortfolioContext'
import { useTheme } from '../context/ThemeContext'
import { usePrivacy } from '../context/PrivacyContext'
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
  const { holdings, refresh } = usePortfolio()
  const { theme, toggle } = useTheme()
  const { hidden, toggle: toggleHidden } = usePrivacy()

  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [isSyncing, setIsSyncing] = useState(false)
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
  // Portfolio filters do not apply to single-stock or broker pages
  // (Holdings has its own toolbar, built on the same URL filters)
  const hideGlobalFilters = path === '/brokers' || path === '/signals' || path === '/momentum' || path === '/strategy' || path === '/holdings'

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
    if (path === '/holdings') return { title: 'Holdings', sub: `Merged across ${sessions.length} ${sessions.length === 1 ? 'broker' : 'brokers'} · ${syncLine}` }
    if (path === '/brokers') return { title: 'Brokers', sub: 'Connect, sync and manage your broker accounts' }
    if (path === '/signals') return { title: 'Equity signals', sub: 'Momentum, Swing V2.1 and 200-DMA ATH breakout for every stock you hold' }
    if (path === '/momentum') return { title: 'Momentum', sub: 'Trend, returns and relative strength for one stock' }
    if (path === '/strategy') return { title: 'Strategies', sub: 'Rule-based backtests on daily candles' }
    return { title: 'Overview', sub: syncLine }
  }, [path, lastSync, connected, sessions.length])

  const handleSync = async () => {
    setIsSyncing(true)
    setSyncStatus(null)
    try {
      await triggerPortfolioSync()
      await Promise.all([refresh(), loadSessions()])
      setSyncStatus({ tone: 'ok', text: 'Synced' })
    } catch (err) {
      console.error('Sync failed:', err)
      setSyncStatus({ tone: 'bad', text: 'Sync failed' })
    } finally {
      setIsSyncing(false)
      setTimeout(() => setSyncStatus(null), 4000)
    }
  }

  const handleLogout = () => {
    clearToken()
    if (onLogout) onLogout()
    else window.location.reload()
  }

  return (
    <div className="app">
      <Sidebar holdingsCount={holdings.length} sessions={sessions} />

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
            {isSyncing ? 'Syncing…' : 'Sync all'}
          </button>

          {user && (
            <>
              <span className="avatar" title={user.name}>
                {user.picture ? <img src={user.picture} alt="" referrerPolicy="no-referrer" /> : user.name.charAt(0).toUpperCase()}
              </span>
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
