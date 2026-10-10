import type React from 'react'
import { Activity, CandlestickChart, LayoutDashboard, Layers, Link2, Radar } from 'lucide-react'

export interface NavItem {
  id: string
  label: string
  short: string
  path: string
  icon: React.ComponentType<{ className?: string; strokeWidth?: number; size?: number }>
  group: 'Portfolio' | 'Analysis'
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', short: 'Overview', path: '/', icon: LayoutDashboard, group: 'Portfolio' },
  { id: 'holdings', label: 'Holdings', short: 'Holdings', path: '/holdings', icon: Layers, group: 'Portfolio' },
  { id: 'brokers', label: 'Brokers', short: 'Brokers', path: '/brokers', icon: Link2, group: 'Portfolio' },
  { id: 'signals', label: 'Equity signals', short: 'Signals', path: '/signals', icon: Radar, group: 'Analysis' },
  { id: 'momentum', label: 'Momentum', short: 'Momentum', path: '/momentum', icon: Activity, group: 'Analysis' },
  { id: 'strategy', label: 'Strategies', short: 'Strategy', path: '/strategy', icon: CandlestickChart, group: 'Analysis' },
]

export const isNavActive = (pathname: string, path: string) => (path === '/' ? pathname === '/' : pathname.startsWith(path))
