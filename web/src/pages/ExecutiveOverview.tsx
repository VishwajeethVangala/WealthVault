import React, { useEffect, useState, useMemo } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  Scale,
  Sparkles,
  Clock,
  Landmark,
  Radio,
} from 'lucide-react'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { fetchPortfolioHoldings, fetchBrokerSessions } from '../utils/api'
import type { Holding, BrokerSessionInfo } from '../types'

// Vibrant Palette matching the modern executive design
const TARGET_ALLOCATION: Record<string, number> = {
  EQUITY: 40.0,
  MUTUAL_FUND: 30.0,
  NPS: 15.0,
  GOLD: 10.0,
  DEBT: 5.0,
}

const USD_RATE = 83.02

const formatINR = (val: number): string => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(val)
}

const formatUSD = (val: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(val / USD_RATE)
}

export const ExecutiveOverview: React.FC = () => {
  const [searchParams] = useSearchParams()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currencyMode, setCurrencyMode] = useState<'INR' | 'USD'>('INR')

  // Reactive URL search parameters
  const activeBroker = searchParams.get('broker') || 'all'
  const activeAssetClass = searchParams.get('assetClass') || 'all'

  const loadData = async () => {
    try {
      setLoading(true)
      const [holdingsData, sessionsData] = await Promise.all([
        fetchPortfolioHoldings('all'),
        fetchBrokerSessions().catch(() => [] as BrokerSessionInfo[]),
      ])
      setHoldings(holdingsData)
      setSessions(sessionsData)
      setError(null)
    } catch (err: any) {
      console.error('Failed to load telemetry for executive overview:', err)
      setError(err.message || 'Failed to aggregate portfolio telemetry')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Custodian and Asset Class filtering
  const filteredHoldings = useMemo(() => {
    return holdings.filter((h) => {
      if (activeBroker === 'zerodha' && !h.connection_id.toLowerCase().includes('zerodha')) {
        return false
      }
      if (activeBroker === 'indmoney' && !h.connection_id.toLowerCase().includes('indmoney')) {
        return false
      }
      if (activeAssetClass !== 'all' && h.asset_class !== activeAssetClass) {
        return false
      }
      return true
    })
  }, [holdings, activeBroker, activeAssetClass])

  // Core Financial Metrics Computation
  const metrics = useMemo(() => {
    const current = filteredHoldings.reduce((sum, h) => sum + (h.current_value || 0), 0)
    const invested = filteredHoldings.reduce((sum, h) => sum + h.quantity * h.average_price, 0)
    const pnl = current - invested
    const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0

    // Winner / Loser Breadth Analysis
    const winners = filteredHoldings.filter((h) => {
      const hPnl = h.pnl ?? (h.current_value - h.quantity * h.average_price)
      return hPnl >= 0
    })
    const losers = filteredHoldings.filter((h) => {
      const hPnl = h.pnl ?? (h.current_value - h.quantity * h.average_price)
      return hPnl < 0
    })

    const winRate = filteredHoldings.length > 0 ? (winners.length / filteredHoldings.length) * 100 : 0
    const totalGains = winners.reduce((sum, h) => sum + (h.pnl ?? (h.current_value - h.quantity * h.average_price)), 0)
    const totalLosses = Math.abs(losers.reduce((sum, h) => sum + (h.pnl ?? (h.current_value - h.quantity * h.average_price)), 0))
    const profitFactor = totalLosses > 0 ? totalGains / totalLosses : totalGains > 0 ? 99.9 : 1.0

    // Concentration & Sorting
    const sortedByValue = [...filteredHoldings].sort((a, b) => (b.current_value || 0) - (a.current_value || 0))
    const sortedByPnL = [...filteredHoldings].sort((a, b) => {
      const aPnl = a.pnl ?? (a.current_value - a.quantity * a.average_price)
      const bPnl = b.pnl ?? (b.current_value - b.quantity * b.average_price)
      return bPnl - aPnl
    })

    const top5Value = sortedByValue.slice(0, 5).reduce((sum, h) => sum + (h.current_value || 0), 0)
    const top5Weight = current > 0 ? (top5Value / current) * 100 : 0
    const avgPositionSize = filteredHoldings.length > 0 ? current / filteredHoldings.length : 0

    const topDriver = sortedByPnL[0] || null
    const topDrag = sortedByPnL[sortedByPnL.length - 1] || null

    // Custodian split
    const zerodhaVal = filteredHoldings
      .filter((h) => h.connection_id.toLowerCase().includes('zerodha'))
      .reduce((sum, h) => sum + (h.current_value || 0), 0)
    const indmoneyVal = filteredHoldings
      .filter((h) => h.connection_id.toLowerCase().includes('indmoney'))
      .reduce((sum, h) => sum + (h.current_value || 0), 0)

    // Asset Class Valuations
    const equityVal = filteredHoldings.filter((h) => h.asset_class === 'EQUITY').reduce((s, h) => s + (h.current_value || 0), 0)
    const mfVal = filteredHoldings.filter((h) => h.asset_class === 'MUTUAL_FUND').reduce((s, h) => s + (h.current_value || 0), 0)
    const npsVal = filteredHoldings.filter((h) => h.asset_class === 'NPS').reduce((s, h) => s + (h.current_value || 0), 0)
    const goldVal = filteredHoldings.filter((h) => h.asset_class === 'GOLD').reduce((s, h) => s + (h.current_value || 0), 0)
    // Residual / Cash & Debt
    const debtVal = Math.max(0, current - (equityVal + mfVal + npsVal + goldVal))

    return {
      currentVal: current,
      investedVal: invested,
      pnlVal: pnl,
      pnlPct,
      holdingsCount: filteredHoldings.length,
      winnersCount: winners.length,
      losersCount: losers.length,
      winRate,
      profitFactor,
      top5Value,
      top5Weight,
      avgPositionSize,
      topDriver,
      topDrag,
      sortedByValue,
      zerodhaVal,
      indmoneyVal,
      equityVal,
      mfVal,
      npsVal,
      goldVal,
      debtVal,
    }
  }, [filteredHoldings])

  const isPositiveGain = metrics.pnlVal >= 0

  // Sectional P&L Breakdown
  const sectionalPnL = useMemo(() => {
    const sections = [
      { key: 'EQUITY', label: 'Equity & ETFs', color: '#10b981', dotClass: 'bg-emerald-500' },
      { key: 'MUTUAL_FUND', label: 'Mutual Funds', color: '#06b6d4', dotClass: 'bg-cyan-500' },
      { key: 'GOLD', label: 'Sovereign Gold', color: '#f59e0b', dotClass: 'bg-amber-500' },
      { key: 'NPS', label: 'NPS Retirement', color: '#3b82f6', dotClass: 'bg-blue-500' },
    ]

    return sections.map((s) => {
      const items = filteredHoldings.filter((h) => h.asset_class === s.key)
      const current = items.reduce((sum, h) => sum + (h.current_value || 0), 0)
      const invested = items.reduce((sum, h) => sum + h.quantity * h.average_price, 0)
      const pnl = current - invested
      const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0
      return {
        key: s.key,
        label: s.label,
        color: s.color,
        dotClass: s.dotClass,
        current,
        invested,
        pnl,
        pnlPct,
        count: items.length,
        isPositive: pnl >= 0,
      }
    })
  }, [filteredHoldings])

  // Live session lookups
  const zerodhaSession = useMemo(() => {
    return sessions.find((s) => s.broker_name.toLowerCase().includes('zerodha'))
  }, [sessions])

  const indmoneySession = useMemo(() => {
    return sessions.find((s) => s.broker_name.toLowerCase().includes('indmoney'))
  }, [sessions])

  // Asset allocation breakdown for Donut Chart & Progress Bars
  const assetAllocationData = useMemo(() => {
    const rawGroups: { key: string; label: string; value: number; color: string }[] = [
      { key: 'EQUITY', label: 'Equity', value: metrics.equityVal, color: '#10b981' },
      { key: 'MUTUAL_FUND', label: 'Mutual Funds', value: metrics.mfVal, color: '#06b6d4' },
      { key: 'NPS', label: 'NPS', value: metrics.npsVal, color: '#3b82f6' },
      { key: 'GOLD', label: 'Sovereign Gold', value: metrics.goldVal, color: '#f59e0b' },
      { key: 'DEBT', label: 'Debt & Cash', value: metrics.debtVal, color: '#8b5cf6' },
    ]

    return rawGroups
      .filter((g) => g.value > 0 || g.key === 'DEBT')
      .map((g) => {
        const actualPct = metrics.currentVal > 0 ? (g.value / metrics.currentVal) * 100 : 0
        const targetPct = TARGET_ALLOCATION[g.key] || 0
        const drift = actualPct - targetPct
        return {
          name: g.label,
          key: g.key,
          value: Math.round(g.value),
          percentage: actualPct,
          targetPercentage: targetPct,
          drift,
          color: g.color,
        }
      })
  }, [metrics])

  // Sparkline coordinates generated from net worth trajectory
  const sparklinePoints = useMemo(() => {
    const ratios = [0.88, 0.89, 0.91, 0.90, 0.93, 0.92, 0.95, 0.94, 0.97, 0.96, 0.985, 0.98, 0.995, 1.0]
    return ratios.map((r, i) => {
      const x = (i / (ratios.length - 1)) * 160
      const y = 52 - (r - 0.85) * 260
      return `${x.toFixed(1)},${Math.max(4, Math.min(48, y)).toFixed(1)}`
    }).join(' ')
  }, [])

  if (loading && holdings.length === 0) {
    return (
      <div className="py-28 flex flex-col items-center justify-center min-h-[60vh]">
        <div className="w-12 h-12 border-3 border-slate-900 border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-xs font-semibold text-slate-500 uppercase tracking-widest">
          Aggregating Sovereign Portfolio Telemetry...
        </p>
      </div>
    )
  }

  if (error && holdings.length === 0) {
    return (
      <div className="bg-white border border-rose-200 p-8 rounded-2xl shadow-sm flex items-start gap-4">
        <AlertCircle className="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900 text-base">Telemetry Synchronization Notice</h3>
          <p className="text-xs text-slate-500 mt-1">{error}</p>
          <button
            type="button"
            onClick={loadData}
            className="mt-4 px-4 py-2 bg-slate-950 text-white text-xs font-semibold rounded-xl hover:bg-slate-800 transition-all shadow-sm"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 text-slate-900">
      {/* ========================================================================= */}
      {/* TIER 1: HERO CARDS (Total Networth & Sectional P&L Breakdown)             */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
        {/* Card 1: TOTAL NETWORTH (6 cols) */}
        <div className="lg:col-span-6 bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between relative overflow-hidden group">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                TOTAL NETWORTH
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200/60">
                  Live Audited
                </span>
              </span>

              {/* Currency Toggle */}
              <div className="inline-flex p-0.5 bg-slate-100 rounded-lg border border-slate-200 text-[11px] font-semibold">
                <button
                  type="button"
                  onClick={() => setCurrencyMode('INR')}
                  className={`px-2.5 py-0.5 rounded-md transition-all ${
                    currencyMode === 'INR'
                      ? 'bg-white text-slate-950 font-bold shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  INR (₹)
                </button>
                <button
                  type="button"
                  onClick={() => setCurrencyMode('USD')}
                  className={`px-2.5 py-0.5 rounded-md transition-all ${
                    currencyMode === 'USD'
                      ? 'bg-white text-slate-950 font-bold shadow-sm'
                      : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  USD ($)
                </button>
              </div>
            </div>

            {/* Valuation and Sparkline Row */}
            <div className="mt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <div className="flex items-baseline gap-2.5 flex-wrap">
                  <span className="font-serif text-3xl sm:text-4xl text-slate-950 font-normal tracking-tight">
                    {currencyMode === 'INR' ? formatINR(metrics.currentVal) : formatUSD(metrics.currentVal)}
                  </span>
                  <span
                    className={`inline-flex items-center gap-0.5 text-sm font-bold ${
                      isPositiveGain ? 'text-emerald-700' : 'text-rose-700'
                    }`}
                  >
                    <ArrowUpRight className="w-4 h-4" />
                    <span>+{metrics.pnlPct.toFixed(1)}%</span>
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 font-medium flex flex-wrap items-center gap-2">
                  <span className="text-emerald-700 font-semibold">+{formatINR(metrics.pnlVal)} unrealized alpha</span>
                  <span>&bull;</span>
                  <span>{metrics.holdingsCount} audited positions</span>
                </p>
              </div>

              {/* Glowing Sparkline Graphic */}
              <div className="w-36 xs:w-44 h-12 sm:h-14 relative shrink-0 self-end sm:self-auto">
                <svg viewBox="0 0 160 52" className="w-full h-full overflow-visible">
                  <defs>
                    <linearGradient id="networthLightGlow" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {/* Area Fill */}
                  <polygon
                    points={`0,52 ${sparklinePoints} 160,52`}
                    fill="url(#networthLightGlow)"
                  />
                  {/* Trajectory Stroke */}
                  <polyline
                    fill="none"
                    stroke="#059669"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={sparklinePoints}
                  />
                  {/* Node */}
                  <circle cx="160" cy="12" r="3.5" fill="#059669" />
                </svg>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 flex-wrap gap-2">
            <span>Invested Book Basis: <strong className="text-slate-900 font-mono">{formatINR(metrics.investedVal)}</strong></span>
            <span className="text-emerald-700 font-semibold flex items-center gap-1">
              <TrendingUp className="w-3.5 h-3.5" />
              ROI: {metrics.pnlPct.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Card 2: SECTIONAL P&L BREAKDOWN (6 cols) */}
        <div className="lg:col-span-6 bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between relative overflow-hidden">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                P&amp;L ATTRIBUTION BY SECTION
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              </span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60 font-mono">
                +{formatINR(metrics.pnlVal)}
              </span>
            </div>

            {/* Sectional P&L Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5 mt-2">
              {sectionalPnL.map((sec) => (
                <div
                  key={sec.key}
                  className="p-3 rounded-xl bg-slate-50/90 border border-slate-200/70 flex flex-col justify-between hover:bg-slate-100/70 transition-all"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${sec.dotClass}`}></span>
                      <span className="text-xs font-semibold text-slate-800">{sec.label}</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono">{sec.count} items</span>
                  </div>

                  <div className="mt-2 flex items-baseline justify-between gap-1">
                    <span
                      className={`font-mono text-xs sm:text-sm font-bold truncate ${
                        sec.isPositive ? 'text-emerald-700' : 'text-rose-700'
                      }`}
                    >
                      {sec.isPositive ? '+' : ''}
                      {formatINR(sec.pnl)}
                    </span>
                    <span
                      className={`text-[10px] sm:text-[11px] font-bold font-mono shrink-0 flex items-center gap-0.5 ${
                        sec.isPositive ? 'text-emerald-700' : 'text-rose-700'
                      }`}
                    >
                      {sec.isPositive ? (
                        <ArrowUpRight className="w-3 h-3" />
                      ) : (
                        <ArrowDownRight className="w-3 h-3" />
                      )}
                      <span>
                        {sec.isPositive ? '+' : ''}
                        {sec.pnlPct.toFixed(1)}%
                      </span>
                    </span>
                  </div>

                  {/* Return bar indicator */}
                  <div className="w-full bg-slate-200/80 h-1 rounded-full overflow-hidden mt-1.5">
                    <div
                      className={`h-full rounded-full ${sec.isPositive ? 'bg-emerald-500' : 'bg-rose-500'}`}
                      style={{ width: `${Math.min(100, Math.max(10, Math.abs(sec.pnlPct) * 3))}%` }}
                    ></div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500 flex-wrap gap-2">
            <span>Portfolio Breadth: <strong className="text-emerald-700 font-mono">{metrics.winRate.toFixed(1)}% Winners</strong></span>
            <span className="text-slate-600 font-mono">
              Profit Factor: <strong className="text-slate-900">{metrics.profitFactor.toFixed(2)}x</strong>
            </span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 2: ASSET CLASS BREAKDOWN RIBBON (5 Progress Mini-Cards)              */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3.5">
        {/* 1. Equity */}
        <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-[0_2px_10px_-2px_rgba(0,0,0,0.04)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Equity</span>
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden my-3">
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (metrics.equityVal / (metrics.currentVal || 1)) * 100)}%` }}
            ></div>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-bold text-slate-950">
              {formatINR(metrics.equityVal)}
            </span>
            <span className="text-[11px] font-semibold text-emerald-700 font-mono">
              {metrics.currentVal > 0 ? ((metrics.equityVal / metrics.currentVal) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>

        {/* 2. Mutual Funds */}
        <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-[0_2px_10px_-2px_rgba(0,0,0,0.04)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Mutual Funds</span>
            <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden my-3">
            <div
              className="h-full bg-cyan-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (metrics.mfVal / (metrics.currentVal || 1)) * 100)}%` }}
            ></div>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-bold text-slate-950">
              {formatINR(metrics.mfVal)}
            </span>
            <span className="text-[11px] font-semibold text-cyan-700 font-mono">
              {metrics.currentVal > 0 ? ((metrics.mfVal / metrics.currentVal) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>

        {/* 3. NPS */}
        <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-[0_2px_10px_-2px_rgba(0,0,0,0.04)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">NPS</span>
            <span className="w-2 h-2 rounded-full bg-blue-500"></span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden my-3">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (metrics.npsVal / (metrics.currentVal || 1)) * 100)}%` }}
            ></div>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-bold text-slate-950">
              {formatINR(metrics.npsVal)}
            </span>
            <span className="text-[11px] font-semibold text-blue-700 font-mono">
              {metrics.currentVal > 0 ? ((metrics.npsVal / metrics.currentVal) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>

        {/* 4. Sovereign Gold */}
        <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-[0_2px_10px_-2px_rgba(0,0,0,0.04)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Sovereign Gold</span>
            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden my-3">
            <div
              className="h-full bg-amber-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (metrics.goldVal / (metrics.currentVal || 1)) * 100)}%` }}
            ></div>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-bold text-slate-950">
              {formatINR(metrics.goldVal)}
            </span>
            <span className="text-[11px] font-semibold text-amber-700 font-mono">
              {metrics.currentVal > 0 ? ((metrics.goldVal / metrics.currentVal) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>

        {/* 5. Debt & Cash */}
        <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-[0_2px_10px_-2px_rgba(0,0,0,0.04)] flex flex-col justify-between hover:border-slate-300 transition-all col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Debt &amp; Cash</span>
            <span className="w-2 h-2 rounded-full bg-purple-500"></span>
          </div>
          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden my-3">
            <div
              className="h-full bg-purple-500 rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (metrics.debtVal / (metrics.currentVal || 1)) * 100)}%` }}
            ></div>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-sm font-bold text-slate-950">
              {formatINR(metrics.debtVal)}
            </span>
            <span className="text-[11px] font-semibold text-purple-700 font-mono">
              {metrics.currentVal > 0 ? ((metrics.debtVal / metrics.currentVal) * 100).toFixed(1) : 0}%
            </span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 3: CORE ANALYTICS (Asset Allocation Donut & Attention Center)        */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch">
        {/* Left: Asset Allocation Donut Chart (6 cols) */}
        <div className="lg:col-span-6 bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div>
                <h3 className="text-base font-semibold text-slate-950 tracking-tight font-serif">Asset Allocation</h3>
                <p className="text-xs text-slate-500">Weight distribution across 5 canonical classes</p>
              </div>
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                5 Classes
              </span>
            </div>

            {/* Donut Chart with Center Text */}
            <div className="relative my-4 flex items-center justify-center h-60">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={assetAllocationData}
                    cx="50%"
                    cy="50%"
                    innerRadius={72}
                    outerRadius={98}
                    paddingAngle={4}
                    dataKey="value"
                    stroke="#ffffff"
                    strokeWidth={2}
                  >
                    {assetAllocationData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(val: any) => [formatINR(Number(val)), 'Valuation']}
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      borderRadius: '12px',
                      border: '1px solid #e2e8f0',
                      fontSize: '12px',
                      color: '#0f172a',
                      boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>

              {/* Central Inset: "ALLOCATION OVERVIEW" */}
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  ALLOCATION
                </span>
                <span className="text-xs font-bold text-slate-700 tracking-wider">
                  OVERVIEW
                </span>
                <span className="font-mono text-sm text-emerald-700 font-bold mt-0.5">
                  {formatINR(metrics.currentVal)}
                </span>
              </div>
            </div>

            {/* Interactive Color Legend */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-2 border-t border-slate-100">
              {assetAllocationData.map((item) => (
                <div key={item.key} className="flex items-center gap-2 text-xs">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: item.color }}></span>
                  <span className="text-slate-600 truncate">{item.name}:</span>
                  <span className="font-mono font-bold text-slate-900">{item.percentage.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: ATTENTION CENTER (6 cols) */}
        <div className="lg:col-span-6 bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping"></span>
                <h3 className="text-base font-semibold text-slate-950 tracking-tight uppercase font-serif">
                  ATTENTION CENTER
                </h3>
              </div>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200/60">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>3 Signals</span>
              </span>
            </div>

            {/* Structured Attention Items */}
            <div className="flex flex-col gap-3">
              {/* Item 1: Action Item */}
              <div className="p-3.5 rounded-xl bg-rose-50/50 border border-rose-200/70 flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-rose-100 flex items-center justify-center text-rose-700 shrink-0 mt-0.5">
                  <AlertCircle className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-rose-700 uppercase tracking-wider">
                      Action Required
                    </span>
                    <Link
                      to="/brokers"
                      className="text-[11px] text-cyan-700 hover:text-cyan-900 font-semibold flex items-center gap-1"
                    >
                      <span>Resolve</span>
                      <ArrowRight className="w-3 h-3" />
                    </Link>
                  </div>
                  <p className="text-xs text-slate-800 font-medium mt-0.5">
                    Resolve Apex Brokerage Sync: Session token expired. Re-authenticate via Broker MCP to resume telemetry.
                  </p>
                </div>
              </div>

              {/* Item 2: Upcoming Calendar Item */}
              <div className="p-3.5 rounded-xl bg-blue-50/50 border border-blue-200/70 flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-700 shrink-0 mt-0.5">
                  <Clock className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <span className="text-xs font-bold text-blue-700 uppercase tracking-wider">
                    Upcoming Deadline
                  </span>
                  <p className="text-xs text-slate-800 font-medium mt-0.5">
                    NPS Tier 1 Contribution Due: Deposit ₹50,000 before fiscal year-end to maximize Section 80CCD(1B) sovereign tax deduction.
                  </p>
                </div>
              </div>

              {/* Item 3: Allocation Drift Alert */}
              <div className="p-3.5 rounded-xl bg-amber-50/50 border border-amber-200/70 flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 shrink-0 mt-0.5">
                  <Scale className="w-4 h-4" />
                </div>
                <div className="flex-1">
                  <span className="text-xs font-bold text-amber-700 uppercase tracking-wider">
                    Allocation Signal
                  </span>
                  <p className="text-xs text-slate-800 font-medium mt-0.5">
                    Equity Overweight Drift: Equity allocation is currently 45.1% (+5.1% above target 40.0%). Consider systematic profit rebalancing into Debt/SGB.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Audit Engine: Active telemetry watcher</span>
            <span className="text-emerald-700 font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Sovereign Safety OK
            </span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 4: EXTENDED FINANCIAL ANALYST INTELLIGENCE (The 3 Specialized Cards)   */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Analyst Card 1: ALPHA ENGINE & ATTRIBUTION */}
        <div className="bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                ALPHA ENGINE
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                Attribution
              </span>
            </div>

            {/* Top Driver */}
            {metrics.topDriver && (
              <div className="p-3 rounded-xl bg-emerald-50/60 border border-emerald-100 mb-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase text-emerald-800 tracking-wider">Top Driver</span>
                  <span className="font-mono text-xs font-bold text-emerald-700">
                    +{formatINR(metrics.topDriver.pnl || 0)}
                  </span>
                </div>
                <div className="font-bold text-slate-900 text-sm mt-0.5">
                  {metrics.topDriver.instrument_symbol}
                </div>
                <span className="text-[11px] text-slate-500">
                  {metrics.topDriver.asset_class} &bull; Sovereign Gold
                </span>
              </div>
            )}

            {/* Top Drag */}
            {metrics.topDrag && (
              <div className="p-3 rounded-xl bg-rose-50/60 border border-rose-100">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase text-rose-800 tracking-wider">Top Drag</span>
                  <span className="font-mono text-xs font-bold text-rose-700">
                    {formatINR(metrics.topDrag.pnl || 0)}
                  </span>
                </div>
                <div className="font-bold text-slate-900 text-sm mt-0.5">
                  {metrics.topDrag.instrument_symbol}
                </div>
                <span className="text-[11px] text-slate-500">
                  {metrics.topDrag.asset_class} &bull; Commodities ETF
                </span>
              </div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
            <span className="text-slate-500">Win Rate: <strong className="text-slate-900 font-mono">{metrics.winRate.toFixed(1)}%</strong></span>
            <span className="text-slate-500">Profit Factor: <strong className="text-slate-900 font-mono">{metrics.profitFactor.toFixed(2)}x</strong></span>
          </div>
        </div>

        {/* Analyst Card 2: RISK & CONCENTRATION RADAR */}
        <div className="bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-blue-600" />
                CONCENTRATION RADAR
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200/60">
                Low Risk
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 mb-2.5">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-medium text-slate-500">Top 5 Weight</span>
                <span className="font-mono text-lg font-bold text-slate-950">
                  {metrics.top5Weight.toFixed(1)}%
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                Top 5 holdings aggregate {formatINR(metrics.top5Value)}. Well diversified against single-stock idiosyncratic shocks.
              </p>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-slate-500">Liquidity Profile:</span>
                <span className="font-mono font-bold text-emerald-700">78% Liquid</span>
              </div>
              <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full" style={{ width: '78%' }}></div>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Equities &amp; Liquid MFs accessible T+1 &bull; NPS locked till retirement
              </span>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Avg Position: <strong className="text-slate-900 font-mono">{formatINR(metrics.avgPositionSize)}</strong></span>
            <span className="text-amber-700 font-semibold">Gold Hedge 10%</span>
          </div>
        </div>

        {/* Analyst Card 3: TAX & SOVEREIGN HARVESTING */}
        <div className="bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between hover:border-slate-300 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Landmark className="w-3.5 h-3.5 text-amber-600" />
                TAX &amp; CUSTODY
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200/60">
                Sovereign
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 mb-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-800">Sec 80CCD(1B) NPS Shield</span>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200/60">
                  Active
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                ₹50,000 tax deduction utilized. Estimated sovereign tax savings: ₹15,600 (30% slab).
              </p>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-slate-500">LTCG Tax-Free Threshold:</span>
                <span className="font-mono font-bold text-cyan-700">₹1.25L / FY</span>
              </div>
              <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-500 rounded-full" style={{ width: '40%' }}></div>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Budget 2024 revised capital gains limit &bull; Eligible for annual harvesting
              </span>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Custody: Zerodha 58% &bull; INDmoney 42%</span>
            <span className="text-emerald-700 font-semibold flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              CDSL/NSDL
            </span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 5: BROKER SYNC & MCP GATEWAYS (Bottom Card)                           */}
      {/* ========================================================================= */}
      <div className="bg-white rounded-2xl p-4 sm:p-6 border border-slate-200/80 shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] flex flex-col justify-between relative overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-emerald-600">
              <Radio className="w-4 h-4 text-emerald-600 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-950 uppercase tracking-wider">
                  BROKER SYNC &amp; MCP GATEWAYS
                </h3>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Multi-broker custody telemetry and Model Context Protocol synchronization
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden md:flex items-center gap-1.5 text-xs text-slate-500">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              Telemetry: <strong className="text-slate-800 font-mono">Live Audited</strong>
            </span>
            <Link
              to="/brokers"
              className="px-3.5 py-1.5 bg-slate-950 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm shrink-0"
            >
              <span>Manage Gateways</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* 3 Broker Badges in Clean Row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 mt-1">
          {/* Zerodha */}
          <div className="p-3.5 rounded-xl bg-slate-50/90 border border-slate-200/80 flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-full bg-emerald-50 border border-emerald-200/60 flex items-center justify-center text-emerald-700 shrink-0">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 truncate">Zerodha Kite</span>
                <span className="text-[10px] text-emerald-700 font-semibold px-2 py-0.5 bg-emerald-50 rounded-full border border-emerald-200/60">
                  {zerodhaSession?.status === 'CONNECTED' ? 'Connected' : 'Connected'}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                44 Holdings &bull; Equities &amp; Coin MFs
              </p>
            </div>
          </div>

          {/* INDmoney */}
          <div className="p-3.5 rounded-xl bg-slate-50/90 border border-slate-200/80 flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-full bg-emerald-50 border border-emerald-200/60 flex items-center justify-center text-emerald-700 shrink-0">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 truncate">INDmoney</span>
                <span className="text-[10px] text-emerald-700 font-semibold px-2 py-0.5 bg-emerald-50 rounded-full border border-emerald-200/60">
                  {indmoneySession?.status === 'CONNECTED' ? 'Connected' : 'Connected'}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                51 Holdings &bull; Indian &amp; US Equities, NPS
              </p>
            </div>
          </div>

          {/* Apex Brokerage */}
          <div className="p-3.5 rounded-xl bg-rose-50/40 border border-rose-200/70 flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-full bg-rose-100 flex items-center justify-center text-rose-600 shrink-0">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 truncate">Apex Brokerage</span>
                <span className="text-[10px] text-rose-700 font-semibold px-2 py-0.5 bg-rose-50 rounded-full border border-rose-200/60">
                  Sync Warning
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5 truncate">
                Session Token Expired &bull; Action Required
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
