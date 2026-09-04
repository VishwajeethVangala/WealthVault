import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  RefreshCw,
  CheckCircle2,
  LogOut,
  SlidersHorizontal,
  RotateCcw,
  Radio,
  Menu,
} from 'lucide-react'
import { clearToken, getStoredUser, triggerPortfolioSync } from '../utils/api'
import { useSearchParams } from 'react-router-dom'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  children: React.ReactNode
  onLogout?: () => void
}

export const Layout: React.FC<LayoutProps> = ({ children, onLogout }) => {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const user = getStoredUser()

  // Persistent sidebar collapsed state (for tablet/desktop)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    return localStorage.getItem('wv_sidebar_collapsed') === 'true'
  })

  // Mobile drawer state
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  const toggleSidebar = () => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('wv_sidebar_collapsed', String(next))
      return next
    })
  }

  const [isSyncing, setIsSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState<string | null>(null)

  // Active filter params
  const activeBroker = searchParams.get('broker') || 'all'
  const activeAssetClass = searchParams.get('assetClass') || 'all'
  const activeRange = searchParams.get('range') || '200D'

  const hasActiveFilters =
    activeBroker !== 'all' || activeAssetClass !== 'all' || activeRange !== '200D'

  const isBrokerSyncPage = location.pathname === '/brokers'
  const isHoldingsPage = location.pathname === '/holdings'

  const updateParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === 'all' && key !== 'range') {
      next.delete(key)
    } else if (key === 'range' && value === '200D') {
      next.delete('range')
    } else {
      next.set(key, value)
    }
    setSearchParams(next, { replace: true })
  }

  const handleResetFilters = () => {
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  // Top-right global sync trigger
  const handleSync = async () => {
    setIsSyncing(true)
    setSyncStatus('Syncing live broker feeds...')
    try {
      await triggerPortfolioSync()
      setSyncStatus('Feeds synchronized!')
      setTimeout(() => setSyncStatus(null), 3500)
    } catch (err: any) {
      setSyncStatus('Sync error')
      console.error('Sync failed:', err)
      setTimeout(() => setSyncStatus(null), 4000)
    } finally {
      setIsSyncing(false)
    }
  }

  const handleLogout = () => {
    clearToken()
    if (onLogout) {
      onLogout()
    } else {
      window.location.reload()
    }
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-900 font-sans antialiased flex flex-col selection:bg-slate-900 selection:text-white">
      {/* 1. Collapsible Left Menu Sidebar with Mobile Drawer */}
      <Sidebar
        collapsed={isSidebarCollapsed}
        onToggle={toggleSidebar}
        onLogout={handleLogout}
        activeBrokerCount={2}
        mobileOpen={isMobileMenuOpen}
        onCloseMobile={() => setIsMobileMenuOpen(false)}
      />

      {/* 2. Top Navigation Header (Full width on mobile, offset on md+) */}
      <header
        className={`fixed top-0 right-0 z-30 bg-white/85 backdrop-blur-xl border-b border-slate-200/80 shadow-[0_1px_3px_rgba(0,0,0,0.03)] transition-all duration-300 left-0 ${
          isSidebarCollapsed ? 'md:left-20' : 'md:left-64'
        }`}
      >
        <div className="h-16 px-3 sm:px-6 lg:px-8 flex items-center justify-between gap-3 sm:gap-4">
          {/* Left: Hamburger Trigger (Mobile) & Section Context */}
          <div className="flex items-center gap-2.5 sm:gap-6 min-w-0">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden p-2 -ml-1 text-slate-700 hover:text-slate-950 rounded-xl hover:bg-slate-100 transition-colors focus:outline-none shrink-0"
              aria-label="Open Navigation Menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <h2 className="font-serif text-base sm:text-lg text-slate-950 font-semibold tracking-tight truncate">
              {location.pathname === '/brokers'
                ? 'Broker MCP Sync & Gateways'
                : location.pathname === '/holdings'
                ? 'Holdings Ledger'
                : 'Executive Portfolio'}
            </h2>
          </div>

          {/* Right: Preserved "Sync Brokers" Button, Live Pill & User Profile */}
          <div className="flex items-center gap-3">
            {/* Live Feed Status Pill */}
            <div className="hidden lg:flex items-center gap-2 px-3 py-1 bg-emerald-50 text-emerald-700 rounded-full border border-emerald-200/60 text-[11px] font-semibold">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-600"></span>
              </span>
              <span>Audited Live Feed</span>
            </div>

            {/* Sync Brokers Button (PRESERVED ON TOP RIGHT) */}
            <button
              onClick={handleSync}
              disabled={isSyncing}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 bg-slate-950 hover:bg-slate-800 text-white font-medium text-xs rounded-xl shadow-sm hover:shadow transition-all duration-150 disabled:opacity-50 active:scale-95"
              title="Trigger orchestrated live multi-broker sync"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin text-emerald-400' : ''}`} />
              <span>{isSyncing ? 'Syncing...' : 'Sync Brokers'}</span>
            </button>

            {syncStatus && (
              <span className="hidden sm:inline-flex items-center gap-1.5 text-xs text-emerald-700 font-semibold bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                {syncStatus}
              </span>
            )}

            {/* Profile Avatar & Sign Out */}
            {user ? (
              <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                {user.picture ? (
                  <img
                    src={user.picture}
                    alt={user.name}
                    className="w-8 h-8 rounded-full object-cover ring-1 ring-slate-200 shadow-sm"
                  />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-xs shadow-sm">
                    {user.name.charAt(0)}
                  </div>
                )}
                <div className="hidden xl:flex flex-col text-left">
                  <span className="text-xs font-semibold text-slate-900 leading-tight truncate max-w-[120px]">
                    {user.name}
                  </span>
                  <span className="text-[10px] text-slate-500 font-medium">
                    Sovereign Account
                  </span>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition-colors ml-1"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : null}
          </div>
        </div>

        {/* 3. Sub-Header: Filter Bar (Visible on Executive Overview only to prevent duplication) */}
        {!isBrokerSyncPage && !isHoldingsPage && (
          <div className="h-11 bg-slate-50/80 border-t border-slate-200/70 px-4 sm:px-6 lg:px-8">
            <div className="h-full flex items-center justify-between gap-4">
              {/* Filter Pills with hidden scrollbar and whitespace-nowrap */}
              <div className="flex items-center gap-2 overflow-x-auto py-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                <span className="hidden sm:flex items-center gap-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider mr-1 whitespace-nowrap shrink-0">
                  <SlidersHorizontal className="w-3 h-3" />
                  <span>Filter:</span>
                </span>

                {/* Custodian Segmented Filter */}
                <div className="inline-flex p-0.5 bg-slate-200/70 rounded-lg text-xs font-medium shrink-0">
                  {[
                    { id: 'all', label: 'All Custodians' },
                    { id: 'zerodha', label: 'Zerodha' },
                    { id: 'indmoney', label: 'INDmoney' },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => updateParam('broker', item.id)}
                      className={`px-3 py-1 rounded-md transition-all text-xs whitespace-nowrap shrink-0 ${
                        activeBroker === item.id
                          ? 'bg-white text-slate-900 font-semibold shadow-sm'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>

                {/* Asset Class Filter */}
                <div className="inline-flex p-0.5 bg-slate-200/70 rounded-lg text-xs font-medium shrink-0">
                  {[
                    { id: 'all', label: 'All Assets' },
                    { id: 'EQUITY', label: 'Stocks & ETFs' },
                    { id: 'MUTUAL_FUND', label: 'Mutual Funds' },
                    { id: 'GOLD', label: 'Sovereign Gold' },
                    { id: 'NPS', label: 'NPS Retirement' },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => updateParam('assetClass', item.id)}
                      className={`px-3 py-1 rounded-md transition-all text-xs whitespace-nowrap shrink-0 ${
                        activeAssetClass === item.id
                          ? 'bg-white text-slate-900 font-semibold shadow-sm'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>

                {/* Reset Action */}
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={handleResetFilters}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-100/60 rounded-md transition-colors ml-1 whitespace-nowrap shrink-0"
                    title="Reset all filters"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Reset</span>
                  </button>
                )}
              </div>

              {/* Quick Link to Broker Sync in Filter Strip */}
              <Link
                to={{ pathname: '/brokers', search: location.search }}
                className="hidden xl:inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors whitespace-nowrap shrink-0"
              >
                <Radio className="w-3 h-3 text-emerald-600 animate-pulse" />
                <span>2 Active MCP Feeds</span>
              </Link>
            </div>
          </div>
        )}
      </header>

      {/* 4. Main Content Area Offset by Sidebar Width (0 on mobile, 20/64 on md+) */}
      <main
        className={`flex-1 transition-all duration-300 pb-16 px-3 sm:px-6 lg:px-8 max-w-7xl w-full mx-auto ml-0 ${
          isSidebarCollapsed ? 'md:ml-20' : 'md:ml-64'
        } ${isBrokerSyncPage || isHoldingsPage ? 'pt-20 sm:pt-24' : 'pt-28 sm:pt-32'}`}
      >
        {children}
      </main>

      {/* 5. Modern Footer Offset by Sidebar Width */}
      <footer
        className={`border-t border-slate-200 bg-white/70 py-6 mt-auto transition-all duration-300 ml-0 ${
          isSidebarCollapsed ? 'md:ml-20' : 'md:ml-64'
        }`}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <span className="font-serif font-medium text-slate-800">WealthVault</span>
            <span>&bull; Sovereign Institutional Portfolio Engine</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
