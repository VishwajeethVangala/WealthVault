import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  Shield,
  LayoutDashboard,
  Layers,
  Radio,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Sparkles,
} from 'lucide-react'
import { clearToken, getStoredUser } from '../utils/api'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  onLogout?: () => void
  activeBrokerCount?: number
  mobileOpen?: boolean
  onCloseMobile?: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed,
  onToggle,
  onLogout,
  activeBrokerCount = 2,
  mobileOpen = false,
  onCloseMobile,
}) => {
  const location = useLocation()
  const user = getStoredUser()

  const navItems = [
    {
      id: 'overview',
      name: 'Executive Overview',
      shortName: 'Overview',
      path: '/',
      icon: LayoutDashboard,
      badge: 'Live',
    },
    {
      id: 'holdings',
      name: 'Holdings Ledger',
      shortName: 'Holdings',
      path: '/holdings',
      icon: Layers,
      badge: '96',
    },
    {
      id: 'brokers',
      name: 'Broker Sync',
      shortName: 'MCP Sync',
      path: '/brokers',
      icon: Radio,
      badge: `${activeBrokerCount} Live`,
      isLive: true,
    },
  ]

  const isCurrentActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/'
    }
    return location.pathname.startsWith(path)
  }

  const handleLogoutClick = () => {
    clearToken()
    if (onLogout) {
      onLogout()
    } else {
      window.location.reload()
    }
  }

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {mobileOpen && (
        <div
          onClick={onCloseMobile}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40 md:hidden transition-opacity duration-200"
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed top-0 left-0 bottom-0 z-50 md:z-40 bg-white/95 backdrop-blur-xl border-r border-slate-200/80 flex flex-col justify-between transition-all duration-300 ease-in-out shadow-[1px_0_10px_rgba(0,0,0,0.03)] ${
          mobileOpen ? 'translate-x-0 w-64 shadow-2xl' : '-translate-x-full md:translate-x-0'
        } ${collapsed ? 'md:w-20' : 'md:w-64'}`}
      >
        {/* 1. Header & Brand Section */}
        <div>
          <div className="h-16 px-4 flex items-center justify-between border-b border-slate-100">
            <Link
              to={{ pathname: '/', search: location.search }}
              onClick={() => onCloseMobile?.()}
              className={`flex items-center gap-3 overflow-hidden ${
                collapsed ? 'md:justify-center md:w-full' : ''
              }`}
              title="WealthVault Home"
            >
              <div className="w-10 h-10 rounded-xl bg-slate-950 flex items-center justify-center text-white shrink-0 shadow-sm transition-transform hover:scale-105">
                <Shield className="w-5 h-5 text-emerald-400" />
              </div>
              {(!collapsed || mobileOpen) && (
                <div className="flex flex-col truncate">
                  <span className="font-serif text-lg text-slate-950 font-semibold tracking-tight leading-none">
                    WealthVault
                  </span>
                  <span className="text-[10px] text-slate-500 font-medium tracking-wider uppercase mt-1">
                    Private Wealth
                  </span>
                </div>
              )}
            </Link>

            {/* Desktop Collapse Toggle */}
            {!collapsed && (
              <button
                onClick={onToggle}
                className="hidden md:flex p-1.5 rounded-lg text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-colors"
                title="Collapse Menu"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}

            {/* Mobile Close Button */}
            <button
              onClick={onCloseMobile}
              className="md:hidden p-2 -mr-1 text-slate-500 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors"
              title="Close Menu"
              aria-label="Close navigation"
            >
              <span className="text-sm font-bold">✕</span>
            </button>
          </div>

          {/* 2. Navigation Items */}
          <nav className="p-3 space-y-1.5 mt-2">
            {navItems.map((item) => {
              const active = isCurrentActive(item.path)
              const Icon = item.icon

              return (
                <Link
                  key={item.id}
                  to={{ pathname: item.path, search: location.search }}
                  onClick={() => onCloseMobile?.()}
                  title={collapsed ? `${item.name} (${item.badge})` : undefined}
                  className={`relative flex items-center rounded-xl transition-all duration-150 group ${
                    collapsed && !mobileOpen
                      ? 'md:justify-center md:h-12 md:w-full md:px-0 justify-between px-3.5 py-2.5 w-full'
                      : 'justify-between px-3.5 py-2.5 w-full'
                  } ${
                    active
                      ? 'bg-slate-950 text-white font-semibold shadow-sm'
                      : 'text-slate-600 hover:text-slate-950 hover:bg-slate-100/80 font-medium'
                  }`}
                >
                <div className={`flex items-center ${collapsed && !mobileOpen ? 'md:justify-center' : 'gap-3'}`}>
                  <Icon
                    className={`w-5 h-5 shrink-0 transition-colors ${
                      active
                        ? item.isLive
                          ? 'text-emerald-400'
                          : 'text-white'
                        : item.isLive
                        ? 'text-emerald-600 group-hover:text-emerald-700'
                        : 'text-slate-400 group-hover:text-slate-700'
                    }`}
                  />
                  {(!collapsed || mobileOpen) && (
                    <span className="text-xs truncate tracking-tight">{item.name}</span>
                  )}
                </div>

                {/* Right Badge / Live Indicator */}
                {(!collapsed || mobileOpen) && item.badge && (
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      active
                        ? 'bg-slate-800 text-slate-200'
                        : item.isLive
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {item.isLive && (
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    )}
                    <span>{item.badge}</span>
                  </span>
                )}

                {/* Floating Tooltip in Collapsed Mode */}
                {collapsed && !mobileOpen && (
                  <div className="absolute left-full ml-3 px-3 py-1.5 bg-slate-950 text-white text-xs font-semibold rounded-lg shadow-xl opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 whitespace-nowrap flex items-center gap-1.5">
                    <span>{item.name}</span>
                    {item.badge && (
                      <span className="px-1.5 py-0.5 bg-slate-800 rounded text-[10px] text-emerald-400 font-mono">
                        {item.badge}
                      </span>
                    )}
                  </div>
                )}
              </Link>
            )
          })}
        </nav>
      </div>

      {/* 3. Bottom Profile & Collapse Action */}
      <div className="p-3 border-t border-slate-100 flex flex-col gap-2">
        {/* Expand button when collapsed on desktop */}
        {collapsed && !mobileOpen && (
          <button
            onClick={onToggle}
            className="w-full h-10 flex items-center justify-center rounded-xl text-slate-400 hover:text-slate-900 hover:bg-slate-100 transition-colors"
            title="Expand Menu"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        )}

        {/* User Card */}
        {user && (
          <div
            className={`flex items-center rounded-xl bg-slate-50 border border-slate-200/60 p-2 ${
              collapsed && !mobileOpen ? 'justify-center' : 'justify-between'
            }`}
          >
            <div className="flex items-center gap-2.5 overflow-hidden">
              {user.picture ? (
                <img
                  src={user.picture}
                  alt={user.name}
                  className="w-8 h-8 rounded-full object-cover ring-1 ring-slate-200 shrink-0 shadow-sm"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-950 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-sm">
                  {user.name.charAt(0)}
                </div>
              )}
              {(!collapsed || mobileOpen) && (
                <div className="flex flex-col truncate text-left">
                  <span className="text-xs font-bold text-slate-900 truncate leading-tight">
                    {user.name}
                  </span>
                  <span className="text-[10px] text-slate-400 truncate">
                    {user.email || 'Sovereign Account'}
                  </span>
                </div>
              )}
            </div>

            {(!collapsed || mobileOpen) && (
              <button
                onClick={handleLogoutClick}
                className="p-1.5 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        )}

        {/* Architecture Pill */}
        {(!collapsed || mobileOpen) && (
          <div className="px-3 py-1.5 rounded-lg bg-emerald-50/70 border border-emerald-200/50 flex items-center justify-between text-[10px] font-semibold text-emerald-800">
            <span className="flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-emerald-600" />
              <span>MCP Protocol Mesh</span>
            </span>
            <span className="font-mono text-[9px] uppercase tracking-wider text-emerald-700 bg-emerald-100/70 px-1.5 py-0.5 rounded">
              Active
            </span>
          </div>
        )}
      </div>
    </aside>
    </>
  )
}
