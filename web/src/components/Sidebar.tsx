import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { NAV_ITEMS, isNavActive, type NavItem } from './navItems'
import type { BrokerSessionInfo } from '../types'

const STATUS_DOT: Record<string, string> = {
  CONNECTED: 'var(--gain)',
  SYNCING: 'var(--accent)',
  AUTH_REQUIRED: 'var(--warn)',
  SESSION_EXPIRED: 'var(--warn)',
  DISCONNECTED: 'var(--text-3)',
  PROVIDER_ERROR: 'var(--loss)',
}

const STATUS_WORD: Record<string, string> = {
  CONNECTED: 'Connected',
  SYNCING: 'Syncing',
  AUTH_REQUIRED: 'Login needed',
  SESSION_EXPIRED: 'Session expired',
  DISCONNECTED: 'Off',
  PROVIDER_ERROR: 'Error',
}

interface SidebarProps {
  holdingsCount: number
  sessions: BrokerSessionInfo[]
}

export const Sidebar: React.FC<SidebarProps> = ({ holdingsCount, sessions }) => {
  const location = useLocation()
  const groups: NavItem['group'][] = ['Portfolio', 'Analysis']

  return (
    <aside className="side" aria-label="Primary">
      <NavLink to="/" className="brand" aria-label="WealthVault home">
        <span className="brand-mark">W</span>
        <span className="brand-name">WealthVault</span>
      </NavLink>

      {groups.map((group) => (
        <nav key={group} className="nav" aria-label={group}>
          <p className="nav-label">{group}</p>
          {NAV_ITEMS.filter((i) => i.group === group).map((item) => {
            const active = isNavActive(location.pathname, item.path)
            const Icon = item.icon
            return (
              <NavLink
                key={item.id}
                to={{ pathname: item.path, search: location.search }}
                className={active ? 'on' : undefined}
                aria-current={active ? 'page' : undefined}
                title={item.label}
              >
                <Icon size={18} strokeWidth={1.75} />
                <span className="nav-text">{item.label}</span>
                {item.id === 'holdings' && holdingsCount > 0 && <span className="count">{holdingsCount}</span>}
              </NavLink>
            )
          })}
        </nav>
      ))}

      <div className="side-foot">
        <span className="over" style={{ margin: 0 }}>
          Brokers
        </span>
        {sessions.length === 0 ? (
          <span>No brokers linked yet</span>
        ) : (
          sessions.map((s) => (
            <div key={s.connection_id} className="dotrow" title={`${s.display_name}: ${STATUS_WORD[s.status] ?? s.status}`}>
              <span className="dot" style={{ background: STATUS_DOT[s.status] ?? 'var(--text-3)' }} />
              <span>
                {s.display_name.split(' — ')[0]} · {STATUS_WORD[s.status] ?? s.status}
              </span>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
