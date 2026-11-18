import type React from 'react'
import { Activity, CandlestickChart, Crown, LayoutDashboard, Layers, Link2, Radar, Star } from 'lucide-react'

export interface NavItem {
  id: string
  label: string
  short: string
  path: string
  icon: React.ComponentType<{ className?: string; strokeWidth?: number; size?: number }>
  group: 'Portfolio' | 'Analysis'
  badge?: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', short: 'Overview', path: '/', icon: LayoutDashboard, group: 'Portfolio' },
  { id: 'holdings', label: 'Holdings', short: 'Holdings', path: '/holdings', icon: Layers, group: 'Portfolio' },
  { id: 'watchlist', label: 'Watchlist', short: 'Watchlist', path: '/watchlist', icon: Star, group: 'Portfolio' },
  { id: 'brokers', label: 'Brokers', short: 'Brokers', path: '/brokers', icon: Link2, group: 'Portfolio' },
  { id: 'boardroom', label: 'Review', short: 'Review', path: '/boardroom', icon: Crown, group: 'Analysis', badge: 'Beta' },
  { id: 'signals', label: 'Signals', short: 'Signals', path: '/signals', icon: Radar, group: 'Analysis' },
  { id: 'momentum', label: 'Momentum', short: 'Momentum', path: '/momentum', icon: Activity, group: 'Analysis' },
  { id: 'strategy', label: 'Strategies', short: 'Strategies', path: '/strategy', icon: CandlestickChart, group: 'Analysis' },
]

export const isNavActive = (pathname: string, path: string) => (path === '/' ? pathname === '/' : pathname.startsWith(path))
