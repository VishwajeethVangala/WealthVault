import React, { useEffect, useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  TrendingUp,
  TrendingDown,
  Download,
  AlertCircle,
  X,
  Layers,
  RotateCcw,
  LayoutGrid,
  List,
} from 'lucide-react'
import { fetchPortfolioHoldings } from '../utils/api'
import type { Holding } from '../types'

const formatINR = (val: number): string => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(val)
}

export const HoldingsTable: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  type SortColumn = keyof Holding | 'invested_value'
  const [sortField, setSortField] = useState<SortColumn>('current_value')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [pnlFilter, setPnlFilter] = useState<'all' | 'gainers' | 'losers'>('all')
  const [pageSize, setPageSize] = useState<number>(50)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [viewMode, setViewMode] = useState<'auto' | 'table' | 'cards'>('auto')

  // URL-driven filter states
  const activeBroker = searchParams.get('broker') || 'all'
  const activeAssetClass = searchParams.get('assetClass') || 'all'

  const loadHoldings = async () => {
    try {
      setLoading(true)
      const data = await fetchPortfolioHoldings('all')
      setHoldings(data)
      setError(null)
    } catch (err: any) {
      console.error('Failed to load holdings:', err)
      setError(err.message || 'Failed to fetch portfolio holdings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHoldings()
  }, [])

  // 1. Custodian-scoped holdings
  const brokerScopedHoldings = useMemo(() => {
    return holdings.filter((h) => {
      if (activeBroker === 'zerodha' && !h.connection_id.toLowerCase().includes('zerodha')) {
        return false
      }
      if (activeBroker === 'indmoney' && !h.connection_id.toLowerCase().includes('indmoney')) {
        return false
      }
      return true
    })
  }, [holdings, activeBroker])


  // Broker counts
  const brokerCounts = useMemo(() => {
    return {
      all: holdings.length,
      zerodha: holdings.filter((h) => h.connection_id.toLowerCase().includes('zerodha')).length,
      indmoney: holdings.filter((h) => h.connection_id.toLowerCase().includes('indmoney')).length,
    }
  }, [holdings])

  // Category counts within active custodian scope
  const categoryCounts = useMemo(() => {
    return {
      all: brokerScopedHoldings.length,
      EQUITY: brokerScopedHoldings.filter(
        (h) =>
          h.asset_class === 'EQUITY' &&
          h.currency !== 'USD' &&
          !h.connection_id.toLowerCase().includes('us') &&
          !h.connection_id.toLowerCase().includes('alpaca') &&
          !['SNDK', 'AMZN', 'SPCX', 'LITE', 'DELL', 'MU', 'CRWD', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'META'].some((s) =>
            h.instrument_symbol.toUpperCase().includes(s)
          )
      ).length,
      MUTUAL_FUND: brokerScopedHoldings.filter(
        (h) => h.asset_class === 'MUTUAL_FUND' && !h.instrument_symbol.toUpperCase().includes('SGB')
      ).length,
      US_STOCKS: brokerScopedHoldings.filter(
        (h) =>
          h.asset_class === 'US_STOCKS' ||
          h.currency === 'USD' ||
          h.connection_id.toLowerCase().includes('us') ||
          h.connection_id.toLowerCase().includes('alpaca') ||
          ['SNDK', 'AMZN', 'SPCX', 'LITE', 'DELL', 'MU', 'CRWD', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'META'].some((s) =>
            h.instrument_symbol.toUpperCase().includes(s)
          )
      ).length,
      GOLD: brokerScopedHoldings.filter((h) => h.instrument_symbol.toUpperCase().includes('SGB')).length,
      NPS: brokerScopedHoldings.filter((h) => h.asset_class === 'NPS').length,
    }
  }, [brokerScopedHoldings])

  // 2. Fully filtered subset
  const filteredHoldings = useMemo(() => {
    return brokerScopedHoldings.filter((h) => {
      // Asset class filter
      if (activeAssetClass !== 'all') {
        if (activeAssetClass === 'US_STOCKS') {
          const isUs =
            h.asset_class === 'US_STOCKS' ||
            h.currency === 'USD' ||
            h.connection_id.toLowerCase().includes('us') ||
            h.connection_id.toLowerCase().includes('alpaca') ||
            ['SNDK', 'AMZN', 'SPCX', 'LITE', 'DELL', 'MU', 'CRWD', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'META'].some((s) =>
              h.instrument_symbol.toUpperCase().includes(s)
            )
          if (!isUs) return false
        } else if (activeAssetClass === 'GOLD') {
          const isSgb = h.instrument_symbol.toUpperCase().includes('SGB')
          if (!isSgb) return false
        } else if (activeAssetClass === 'DEBT') {
          const sym = h.instrument_symbol.toLowerCase()
          const isDebt =
            h.asset_class === 'DEBT' ||
            sym.includes('debt') ||
            sym.includes('liquid') ||
            sym.includes('bond') ||
            sym.includes('gilt') ||
            sym.includes('treasury') ||
            sym.includes('arbitrage') ||
            sym.includes('fd') ||
            sym.includes('cash') ||
            sym.includes('overnight')
          if (!isDebt) return false
        } else if (h.asset_class !== activeAssetClass) {
          return false
        }
      }

      // Gainers / Losers quick filter
      const investedCost = h.quantity * h.average_price
      const pnl = h.pnl ?? (h.current_value - investedCost)
      if (pnlFilter === 'gainers' && pnl < 0) return false
      if (pnlFilter === 'losers' && pnl >= 0) return false

      // Localized Search
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim()
        const symbolMatch = h.instrument_symbol.toLowerCase().includes(query)
        const idMatch = h.holding_id.toLowerCase().includes(query)
        const brokerMatch = h.connection_id.toLowerCase().includes(query)
        const classMatch = h.asset_class.toLowerCase().includes(query)
        if (!symbolMatch && !idMatch && !brokerMatch && !classMatch) return false
      }

      return true
    })
  }, [brokerScopedHoldings, activeAssetClass, pnlFilter, searchQuery])

  // 3. Dynamic Sorting
  const sortedHoldings = useMemo(() => {
    return [...filteredHoldings].sort((a, b) => {
      let aVal: any = a[sortField as keyof Holding] ?? 0
      let bVal: any = b[sortField as keyof Holding] ?? 0

      if (sortField === 'invested_value') {
        aVal = a.quantity * a.average_price
        bVal = b.quantity * b.average_price
      } else if (sortField === 'pnl') {
        aVal = a.pnl ?? (a.current_value - a.quantity * a.average_price)
        bVal = b.pnl ?? (b.current_value - b.quantity * b.average_price)
      } else if (typeof aVal === 'string') {
        aVal = (aVal as string).toLowerCase()
        bVal = ((bVal as string) || '').toLowerCase()
      }

      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1
      return 0
    })
  }, [filteredHoldings, sortField, sortOrder])

  // Paginated slice
  const paginatedHoldings = useMemo(() => {
    if (pageSize === 0) return sortedHoldings
    const start = (currentPage - 1) * pageSize
    return sortedHoldings.slice(start, start + pageSize)
  }, [sortedHoldings, currentPage, pageSize])

  const totalPages = pageSize > 0 ? Math.ceil(sortedHoldings.length / pageSize) : 1

  const handleSort = (field: SortColumn) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('desc')
    }
  }

  const renderSortIcon = (field: SortColumn) => {
    if (sortField !== field) {
      return <ArrowUpDown className="w-3.5 h-3.5 text-slate-300 group-hover:text-slate-900 transition-colors" />
    }
    return sortOrder === 'asc' ? (
      <ArrowUp className="w-3.5 h-3.5 text-slate-950 font-bold" />
    ) : (
      <ArrowDown className="w-3.5 h-3.5 text-slate-950 font-bold" />
    )
  }

  const handleBrokerSelect = (broker: string) => {
    const nextParams = new URLSearchParams(searchParams)
    if (broker === 'all') {
      nextParams.delete('broker')
    } else {
      nextParams.set('broker', broker)
    }
    setSearchParams(nextParams, { replace: true })
    setCurrentPage(1)
  }

  const handleCategorySelect = (category: string) => {
    const nextParams = new URLSearchParams(searchParams)
    if (category === 'all') {
      nextParams.delete('assetClass')
    } else {
      nextParams.set('assetClass', category)
    }
    setSearchParams(nextParams, { replace: true })
    setCurrentPage(1)
  }

  const handleClearAll = () => {
    setSearchQuery('')
    setPnlFilter('all')
    setSearchParams(new URLSearchParams(), { replace: true })
    setCurrentPage(1)
  }

  // Summary Metrics
  const filteredValuation = useMemo(
    () => filteredHoldings.reduce((sum, h) => sum + (h.current_value || 0), 0),
    [filteredHoldings]
  )
  const filteredInvested = useMemo(
    () => filteredHoldings.reduce((sum, h) => sum + h.quantity * h.average_price, 0),
    [filteredHoldings]
  )
  const filteredPnL = filteredValuation - filteredInvested
  const filteredPnLPct = filteredInvested > 0 ? (filteredPnL / filteredInvested) * 100 : 0
  const isPositiveGain = filteredPnL >= 0

  const exportCSV = () => {
    const headers = [
      'Symbol',
      'Asset Class',
      'Custodian',
      'Quantity',
      'Avg Price (INR)',
      'Current Price (INR)',
      'Investment Value (INR)',
      'Current Value (INR)',
      'Unrealized Gain (INR)',
      'Return (%)',
    ]
    const rows = sortedHoldings.map((h) => {
      const investedCost = h.quantity * h.average_price
      const pnl = h.pnl ?? (h.current_value - investedCost)
      const pnlPct = investedCost > 0 ? (pnl / investedCost) * 100 : 0
      return [
        `"${h.instrument_symbol}"`,
        h.asset_class,
        h.connection_id.includes('zerodha') ? 'Zerodha' : 'INDmoney',
        h.quantity,
        h.average_price.toFixed(2),
        (h.current_price || 0).toFixed(2),
        investedCost.toFixed(2),
        h.current_value.toFixed(2),
        pnl.toFixed(2),
        pnlPct.toFixed(2) + '%',
      ]
    })
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `wealthvault_holdings_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  if (loading && holdings.length === 0) {
    return (
      <div className="py-24 flex flex-col items-center justify-center min-h-[50vh]">
        <div className="w-10 h-10 border-3 border-slate-900 border-t-transparent rounded-full animate-spin"></div>
        <p className="mt-4 text-xs font-semibold text-slate-500 uppercase tracking-wider">
          Loading Canonical Portfolio Holdings...
        </p>
      </div>
    )
  }

  if (error && holdings.length === 0) {
    return (
      <div className="bg-white border border-rose-200 p-8 rounded-2xl shadow-sm flex items-start gap-4">
        <AlertCircle className="w-6 h-6 text-rose-600 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900 text-base">Holdings Ledger Connection Notice</h3>
          <p className="text-xs text-slate-500 mt-1">{error}</p>
          <button
            onClick={loadHoldings}
            className="mt-4 px-4 py-2 bg-slate-950 text-white text-xs font-semibold rounded-xl hover:bg-slate-800 transition-all shadow-sm"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* 1. Header KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Metric 1: Current Value */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Current Value
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] text-emerald-700 bg-emerald-50 font-bold border border-emerald-200/60">
              Live Audited
            </span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {formatINR(filteredValuation)}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 text-xs font-bold">
              {isPositiveGain ? (
                <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md flex items-center gap-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span>+{formatINR(filteredPnL)} (+{filteredPnLPct.toFixed(2)}%)</span>
                </span>
              ) : (
                <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded-md flex items-center gap-1">
                  <TrendingDown className="w-3.5 h-3.5" />
                  <span>{formatINR(filteredPnL)} ({filteredPnLPct.toFixed(2)}%)</span>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Metric 2: Investment Value */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Investment Value
            </span>
            <span className="text-xs text-slate-400 font-semibold">Cost Basis</span>
          </div>
          <div className="mt-3">
            <div className="font-serif text-3xl text-slate-950 tracking-tight font-normal">
              {formatINR(filteredInvested)}
            </div>
            <div className="text-xs text-slate-500 mt-1.5 font-medium">
              {sortedHoldings.length} of {holdings.length} positions active
            </div>
          </div>
        </div>

        {/* Metric 3: Active Composition */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Asset Mix
            </span>
            <span className="text-xs text-slate-400 font-semibold">Scope</span>
          </div>
          <div className="mt-2.5 flex flex-col gap-1 text-xs">
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="w-2 h-2 rounded-full bg-slate-900"></span> Stocks &amp; ETFs
              </span>
              <span className="font-semibold text-slate-900 font-mono">
                {categoryCounts.EQUITY} items
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="w-2 h-2 rounded-full bg-slate-600"></span> Mutual Funds
              </span>
              <span className="font-semibold text-slate-900 font-mono">
                {categoryCounts.MUTUAL_FUND} funds
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="w-2 h-2 rounded-full bg-slate-400"></span> Sovereign Gold
              </span>
              <span className="font-semibold text-slate-900 font-mono">
                {categoryCounts.GOLD} items
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="w-2 h-2 rounded-full bg-purple-600"></span> NPS Retirement
              </span>
              <span className="font-semibold text-slate-900 font-mono">
                {categoryCounts.NPS} items
              </span>
            </div>
          </div>
        </div>

        {/* Metric 4: Total P&L Return */}
        <div className="bg-white p-5 rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              Total P&amp;L Return
            </span>
            <span className={`text-xs font-bold px-2 py-0.5 rounded font-mono ${isPositiveGain ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
              {isPositiveGain ? '+' : ''}{filteredPnLPct.toFixed(2)}%
            </span>
          </div>
          <div className="mt-3">
            <div className={`font-serif text-3xl tracking-tight font-normal ${isPositiveGain ? 'text-emerald-700' : 'text-rose-700'}`}>
              {isPositiveGain ? '+' : ''}{formatINR(filteredPnL)}
            </div>
            <p className="text-[11px] text-slate-400 mt-1.5 leading-normal">
              Audited cumulative portfolio profit &amp; loss return.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Action Toolbar Above Ledger */}
      {/* 2. Action Toolbar Above Ledger */}
      <div className="flex flex-col gap-3 mt-1">
        {/* Row 1: Custodian Tabs + Asset Class Filter Tabs & Scope Count */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            {/* Custodian Segmented Control */}
            <div className="inline-flex items-center p-1 bg-slate-100/90 rounded-xl border border-slate-200/80 text-xs font-semibold shrink-0">
              {[
                { id: 'all', label: 'All Custodians', count: brokerCounts.all },
                { id: 'zerodha', label: 'Zerodha', count: brokerCounts.zerodha },
                { id: 'indmoney', label: 'INDmoney', count: brokerCounts.indmoney },
              ].map((b) => {
                const isSelected = activeBroker === b.id
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => handleBrokerSelect(b.id)}
                    className={`h-7 px-3 rounded-lg transition-all duration-150 flex items-center gap-1.5 shrink-0 ${
                      isSelected
                        ? 'bg-white text-slate-950 shadow-sm font-bold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <span className="whitespace-nowrap">{b.label}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono leading-none ${
                        isSelected ? 'bg-slate-100 text-slate-900 font-bold' : 'text-slate-400'
                      }`}
                    >
                      {b.count}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="h-5 w-px bg-slate-200 shrink-0 mx-1 hidden sm:block" />

            {/* Asset Class Filter Buttons */}
            {[
              { id: 'all', label: 'All', count: categoryCounts.all },
              { id: 'EQUITY', label: 'Equity', count: categoryCounts.EQUITY },
              { id: 'MUTUAL_FUND', label: 'Mutual Funds', count: categoryCounts.MUTUAL_FUND },
              { id: 'US_STOCKS', label: 'US Stocks', count: categoryCounts.US_STOCKS },
              { id: 'GOLD', label: 'Sovereign Gold', count: categoryCounts.GOLD },
              { id: 'NPS', label: 'NPS Retirement', count: categoryCounts.NPS },
            ].map((cat) => {
              const isSelected = activeAssetClass === cat.id
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => handleCategorySelect(cat.id)}
                  className={`h-9 px-3.5 rounded-xl text-xs font-semibold transition-all duration-150 select-none border flex items-center gap-2 shrink-0 ${
                    isSelected
                      ? 'bg-slate-950 text-white border-slate-950 shadow-sm'
                      : 'bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-50 border-slate-200/80 shadow-[0_1px_2px_rgba(0,0,0,0.03)]'
                  }`}
                >
                  <span className="whitespace-nowrap">{cat.label}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded-md text-[10px] font-mono font-bold leading-none ${
                      isSelected ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {cat.count}
                  </span>
                </button>
              )
            })}
          </div>

          {/* Quick Active Scope Metric on far right */}
          <div className="hidden lg:flex items-center gap-2 text-xs font-medium text-slate-500 shrink-0">
            <span className="font-semibold text-slate-900 font-mono">{filteredHoldings.length}</span>
            <span>of</span>
            <span className="font-semibold text-slate-900 font-mono">{brokerScopedHoldings.length}</span>
            <span>assets</span>
            {filteredHoldings.length !== brokerScopedHoldings.length && (
              <button
                type="button"
                onClick={handleClearAll}
                className="ml-1 text-slate-400 hover:text-rose-600 transition-colors flex items-center gap-1 font-semibold"
                title="Reset filters"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Search, Gainers/Losers Segmented Filter & Export CSV */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          {/* Left: Search Box & Gainers/Losers Toggle */}
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2.5">
            {/* Search Box */}
            <div className="relative flex items-center flex-1 sm:flex-initial">
              <Search className="w-4 h-4 absolute left-3 text-slate-400 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setCurrentPage(1)
                }}
                placeholder="Search ticker, scheme, custody..."
                className="w-full sm:w-64 md:w-72 h-9 pl-9 pr-8 bg-white text-slate-900 placeholder:text-slate-400 text-xs rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.03)] border border-slate-200/80 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900 transition-all font-medium"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery('')
                    setCurrentPage(1)
                  }}
                  className="absolute right-2.5 text-slate-400 hover:text-slate-600 transition-colors p-1"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Quick Gainers / Losers Segmented Filter */}
            <div className="h-9 inline-flex items-center p-1 bg-slate-100/90 rounded-xl border border-slate-200/80 text-xs font-semibold shrink-0">
              <button
                type="button"
                onClick={() => {
                  setPnlFilter('all')
                  setCurrentPage(1)
                }}
                className={`h-7 px-3 rounded-lg transition-all duration-150 flex items-center justify-center ${
                  pnlFilter === 'all'
                    ? 'bg-white text-slate-950 shadow-sm font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => {
                  setPnlFilter('gainers')
                  setCurrentPage(1)
                }}
                className={`h-7 px-3 rounded-lg transition-all duration-150 flex items-center justify-center ${
                  pnlFilter === 'gainers'
                    ? 'bg-white text-emerald-700 shadow-sm font-bold'
                    : 'text-slate-600 hover:text-emerald-700'
                }`}
              >
                Gainers (+)
              </button>
              <button
                type="button"
                onClick={() => {
                  setPnlFilter('losers')
                  setCurrentPage(1)
                }}
                className={`h-7 px-3 rounded-lg transition-all duration-150 flex items-center justify-center ${
                  pnlFilter === 'losers'
                    ? 'bg-white text-rose-700 shadow-sm font-bold'
                    : 'text-slate-600 hover:text-rose-700'
                }`}
              >
                Losers (-)
              </button>
            </div>
          </div>

          {/* Right: View Mode Switcher & Export CSV Button */}
          <div className="flex items-center justify-between sm:justify-end gap-2 w-full sm:w-auto shrink-0">
            {/* View Mode Switcher */}
            <div className="h-9 inline-flex items-center p-1 bg-slate-100/90 rounded-xl border border-slate-200/80 text-xs font-semibold">
              <button
                type="button"
                onClick={() => setViewMode('table')}
                className={`h-7 px-2.5 rounded-lg transition-all duration-150 flex items-center gap-1.5 ${
                  viewMode === 'table' || viewMode === 'auto'
                    ? 'bg-white text-slate-950 shadow-sm font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Table View (Tablet/Desktop)"
              >
                <List className="w-3.5 h-3.5" />
                <span className="text-[11px]">Table</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode('cards')}
                className={`h-7 px-2.5 rounded-lg transition-all duration-150 flex items-center gap-1.5 ${
                  viewMode === 'cards'
                    ? 'bg-white text-slate-950 shadow-sm font-bold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
                title="Card Feed View (Mobile/Tab)"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
                <span className="text-[11px]">Cards</span>
              </button>
            </div>

            <button
              type="button"
              onClick={exportCSV}
              className="h-9 px-3.5 bg-white hover:bg-slate-50 text-slate-700 hover:text-slate-950 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.03)] text-xs font-semibold flex items-center gap-2 border border-slate-200/80 transition-colors shrink-0"
              title="Export filtered holdings as CSV"
            >
              <Download className="w-3.5 h-3.5 text-slate-500" />
              <span className="hidden xs:inline">Export CSV</span>
            </button>
          </div>
        </div>
      </div>

      {/* 3. Primary Holdings Container (Mobile Cards + Tablet/Desktop Table) */}
      <div className="bg-white rounded-2xl shadow-[0_4px_20px_-4px_rgba(0,0,0,0.05)] border border-slate-200/80 overflow-hidden flex flex-col">
        {/* Mobile Sort Bar (shown on mobile or when cards mode is explicitly selected) */}
        <div
          className={`${
            viewMode === 'cards' ? 'flex' : 'flex md:hidden'
          } px-4 py-2.5 bg-slate-50/90 border-b border-slate-200/80 items-center justify-between text-xs text-slate-500`}
        >
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-slate-600">Sort:</span>
            <select
              value={`${sortField}_${sortOrder}`}
              onChange={(e) => {
                const [f, o] = e.target.value.split('_')
                setSortField(f as SortColumn)
                setSortOrder(o as 'asc' | 'desc')
              }}
              className="bg-white text-slate-800 font-semibold border border-slate-200 rounded-lg px-2 py-1 text-xs focus:outline-none shadow-sm"
            >
              <option value="current_value_desc">Current Value (High to Low)</option>
              <option value="current_value_asc">Current Value (Low to High)</option>
              <option value="invested_value_desc">Investment Value (High to Low)</option>
              <option value="invested_value_asc">Investment Value (Low to High)</option>
              <option value="pnl_desc">Gain (High to Low)</option>
              <option value="pnl_asc">Gain (Low to High)</option>
              <option value="instrument_symbol_asc">Symbol (A to Z)</option>
              <option value="quantity_desc">Units (High to Low)</option>
            </select>
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            {sortedHoldings.length} positions
          </span>
        </div>

        {/* ========================================================================= */}
        {/* A. MOBILE / COMPACT CARD FEED (Zero Horizontal Scrolling on Mobile)       */}
        {/* ========================================================================= */}
        <div
          className={`${
            viewMode === 'cards' ? 'block' : 'block md:hidden'
          } divide-y divide-slate-100`}
        >
          {paginatedHoldings.map((holding) => {
            const investedCost = holding.quantity * holding.average_price
            const pnl = holding.pnl ?? (holding.current_value - investedCost)
            const pnlPct = investedCost > 0 ? (pnl / investedCost) * 100 : 0
            const isPositive = pnl >= 0

            return (
              <div
                key={holding.holding_id}
                className="p-3.5 sm:p-4 bg-white hover:bg-slate-50/80 transition-colors flex flex-col gap-2.5"
              >
                {/* Row 1: Symbol & Valuation */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-bold text-slate-950 text-sm tracking-tight truncate">
                        {holding.instrument_symbol}
                      </span>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                          holding.asset_class === 'EQUITY'
                            ? 'bg-slate-100 text-slate-800'
                            : holding.asset_class === 'MUTUAL_FUND'
                            ? 'bg-cyan-50 text-cyan-800 border border-cyan-200/60'
                            : holding.asset_class === 'NPS'
                            ? 'bg-purple-50 text-purple-800 border border-purple-200/60'
                            : 'bg-amber-50 text-amber-800 border border-amber-200/60'
                        }`}
                      >
                        {holding.asset_class.replace('_', ' ')}
                      </span>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <span className="font-serif font-bold text-base text-slate-950 block">
                      {formatINR(holding.current_value)}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block">
                      Invested: {formatINR(investedCost)}
                    </span>
                  </div>
                </div>

                {/* Row 2: Custody, Units & PnL Badge */}
                <div className="pt-2 border-t border-slate-100/80 flex items-center justify-between gap-2 text-xs">
                  <div className="flex items-center gap-2 text-slate-600 min-w-0 truncate">
                    <span className="flex items-center gap-1 font-medium shrink-0">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          holding.connection_id.includes('zerodha')
                            ? 'bg-slate-900'
                            : 'bg-slate-500'
                        }`}
                      ></span>
                      <span className="text-xs text-slate-700 font-semibold">
                        {holding.connection_id.includes('zerodha') ? 'Zerodha' : 'INDmoney'}
                      </span>
                    </span>
                    <span className="text-slate-300">&bull;</span>
                    <span className="font-mono text-[11px] text-slate-600 truncate">
                      {holding.quantity.toLocaleString('en-IN', {
                        maximumFractionDigits: holding.asset_class === 'MUTUAL_FUND' ? 3 : 2,
                      })}{' '}
                      units @ {formatINR(holding.average_price)}
                    </span>
                  </div>

                  {/* PnL Badge */}
                  <div
                    className={`shrink-0 px-2.5 py-1 rounded-lg text-xs font-bold font-mono flex items-center gap-1 ${
                      isPositive
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200/60'
                        : 'bg-rose-50 text-rose-700 border border-rose-200/60'
                    }`}
                  >
                    {isPositive ? (
                      <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5 text-rose-600" />
                    )}
                    <span>
                      {isPositive ? '+' : ''}
                      {formatINR(pnl)}
                    </span>
                    <span className="text-[10px] font-semibold opacity-85">
                      ({isPositive ? '+' : ''}
                      {pnlPct.toFixed(1)}%)
                    </span>
                  </div>
                </div>
              </div>
            )
          })}

          {sortedHoldings.length === 0 && (
            <div className="py-12 px-4 text-center text-slate-500 flex flex-col items-center justify-center gap-2">
              <Layers className="w-8 h-8 text-slate-300" />
              <p className="text-sm font-semibold text-slate-800">
                No positions match active filters.
              </p>
              <button
                type="button"
                onClick={handleClearAll}
                className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-950 text-white text-xs font-semibold rounded-xl"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Clear Filters</span>
              </button>
            </div>
          )}
        </div>

        {/* ========================================================================= */}
        {/* B. TABLET & DESKTOP RESPONSIVE TABLE (Fits cleanly without blowout)        */}
        {/* ========================================================================= */}
        <div
          className={`${
            viewMode === 'cards' ? 'hidden' : 'hidden md:block'
          } overflow-x-auto w-full max-h-[640px] overflow-y-auto`}
        >
          <table className="w-full text-left border-collapse">
            <thead className="sticky top-0 z-20 bg-slate-50/95 backdrop-blur-md shadow-sm border-b border-slate-200 select-none">
              <tr className="text-slate-500 uppercase text-[11px] font-bold tracking-wider h-11">
                <th
                  onClick={() => handleSort('instrument_symbol')}
                  className="py-3 px-4 sm:px-5 text-left cursor-pointer hover:text-slate-900 transition-colors group"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Asset &amp; Symbol</span>
                    {renderSortIcon('instrument_symbol')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('asset_class')}
                  className="py-3 px-3 text-left cursor-pointer hover:text-slate-900 transition-colors group hidden sm:table-cell"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Asset Class</span>
                    {renderSortIcon('asset_class')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('connection_id')}
                  className="py-3 px-3 text-left cursor-pointer hover:text-slate-900 transition-colors group"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Custody</span>
                    {renderSortIcon('connection_id')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('quantity')}
                  className="py-3 px-3 text-right cursor-pointer hover:text-slate-900 transition-colors group hidden xl:table-cell"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Units</span>
                    {renderSortIcon('quantity')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('average_price')}
                  className="py-3 px-3 text-right cursor-pointer hover:text-slate-900 transition-colors group hidden xl:table-cell"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Avg Cost</span>
                    {renderSortIcon('average_price')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('current_price')}
                  className="py-3 px-3 text-right cursor-pointer hover:text-slate-900 transition-colors group hidden 2xl:table-cell"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Market Price</span>
                    {renderSortIcon('current_price')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('invested_value')}
                  className="py-3 px-3 sm:px-4 text-right cursor-pointer hover:text-slate-900 transition-colors group hidden md:table-cell"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Investment Value</span>
                    {renderSortIcon('invested_value')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('current_value')}
                  className="py-3 px-4 sm:px-5 text-right cursor-pointer hover:text-slate-900 transition-colors group"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Current Value</span>
                    {renderSortIcon('current_value')}
                  </div>
                </th>
                <th
                  onClick={() => handleSort('pnl')}
                  className="py-3 px-4 sm:px-5 text-right cursor-pointer hover:text-slate-900 transition-colors group"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Unrealized Gain</span>
                    {renderSortIcon('pnl')}
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {paginatedHoldings.map((holding) => {
                const investedCost = holding.quantity * holding.average_price
                const pnl = holding.pnl ?? (holding.current_value - investedCost)
                const pnlPct = investedCost > 0 ? (pnl / investedCost) * 100 : 0
                const isPositive = pnl >= 0

                return (
                  <tr
                    key={holding.holding_id}
                    className="hover:bg-slate-50/80 transition-colors group"
                  >
                    {/* Symbol */}
                    <td className="py-3.5 px-4 sm:px-5">
                      <div className="flex flex-col">
                        <span className="font-bold text-slate-900 text-sm group-hover:text-emerald-700 transition-colors">
                          {holding.instrument_symbol}
                        </span>
                        {/* Tablet secondary summary when Units / Avg Cost are hidden on < xl */}
                        <div className="flex xl:hidden items-center gap-1.5 text-[10px] text-slate-500 font-mono mt-0.5">
                          <span>
                            {holding.quantity.toLocaleString('en-IN', {
                              maximumFractionDigits:
                                holding.asset_class === 'MUTUAL_FUND' ? 3 : 2,
                            })}{' '}
                            units
                          </span>
                          <span>&bull;</span>
                          <span>Avg {formatINR(holding.average_price)}</span>
                        </div>
                      </div>
                    </td>

                    {/* Asset Class Badge */}
                    <td className="py-3.5 px-3 hidden sm:table-cell">
                      <span
                        className={`inline-flex items-center px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
                          holding.asset_class === 'EQUITY'
                            ? 'bg-slate-100 text-slate-800'
                            : holding.asset_class === 'MUTUAL_FUND'
                            ? 'bg-cyan-50 text-cyan-800 border border-cyan-200/60'
                            : holding.asset_class === 'NPS'
                            ? 'bg-purple-50 text-purple-800 border border-purple-200/60'
                            : 'bg-amber-50 text-amber-800 border border-amber-200/60'
                        }`}
                      >
                        {holding.asset_class.replace('_', ' ')}
                      </span>
                    </td>

                    {/* Custody */}
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            holding.connection_id.includes('zerodha')
                              ? 'bg-slate-900'
                              : 'bg-slate-500'
                          }`}
                        ></span>
                        <span className="text-xs text-slate-700 font-medium">
                          {holding.connection_id.includes('zerodha') ? 'Zerodha' : 'INDmoney'}
                        </span>
                      </div>
                    </td>

                    {/* Quantity */}
                    <td className="py-3.5 px-3 text-right font-medium text-slate-900 font-mono hidden xl:table-cell">
                      {holding.quantity.toLocaleString('en-IN', {
                        maximumFractionDigits: holding.asset_class === 'MUTUAL_FUND' ? 3 : 2,
                      })}
                    </td>

                    {/* Avg Price */}
                    <td className="py-3.5 px-3 text-right text-slate-600 font-mono hidden xl:table-cell">
                      {formatINR(holding.average_price)}
                    </td>

                    {/* Current Price */}
                    <td className="py-3.5 px-3 text-right text-slate-900 font-semibold font-mono hidden 2xl:table-cell">
                      {holding.current_price ? formatINR(holding.current_price) : '—'}
                    </td>

                    {/* Investment Value */}
                    <td className="py-3.5 px-3 sm:px-4 text-right font-mono text-slate-600 font-medium hidden md:table-cell">
                      {formatINR(investedCost)}
                    </td>

                    {/* Current Value */}
                    <td className="py-3.5 px-4 sm:px-5 text-right font-bold text-slate-900 font-mono text-sm">
                      {formatINR(holding.current_value)}
                    </td>

                    {/* Unrealized Gain */}
                    <td className="py-3.5 px-4 sm:px-5 text-right font-mono">
                      <div className="flex flex-col items-end">
                        <span
                          className={`font-bold text-xs flex items-center gap-0.5 ${
                            isPositive ? 'text-emerald-700' : 'text-rose-700'
                          }`}
                        >
                          {isPositive ? '+' : ''}
                          {formatINR(pnl)}
                        </span>
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                            isPositive
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-rose-50 text-rose-700'
                          }`}
                        >
                          {isPositive ? '+' : ''}
                          {pnlPct.toFixed(2)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}

              {sortedHoldings.length === 0 && (
                <tr>
                  <td colSpan={9} className="py-16 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center gap-2">
                      <Layers className="w-8 h-8 text-slate-300" />
                      <p className="text-sm font-semibold text-slate-800">
                        No positions match the active search or filter.
                      </p>
                      <p className="text-xs text-slate-400">
                        Try resetting your search query or switching to "All Assets".
                      </p>
                      <button
                        type="button"
                        onClick={handleClearAll}
                        className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 bg-slate-950 text-white text-xs font-semibold rounded-xl hover:bg-slate-800 transition-all shadow-sm"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Clear All Filters</span>
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer: Pagination & Page Size */}
        {sortedHoldings.length > 0 && (
          <div className="p-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
            <div className="flex items-center gap-2">
              <span>Showing</span>
              <span className="font-bold text-slate-900 font-mono">
                {paginatedHoldings.length}
              </span>
              <span>of</span>
              <span className="font-bold text-slate-900 font-mono">
                {sortedHoldings.length}
              </span>
              <span>positions</span>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span>Per page:</span>
                {[25, 50, 100].map((size) => (
                  <button
                    key={size}
                    onClick={() => {
                      setPageSize(size)
                      setCurrentPage(1)
                    }}
                    className={`px-2 py-1 rounded font-semibold transition-colors ${
                      pageSize === size
                        ? 'bg-slate-950 text-white'
                        : 'bg-slate-100 text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {size}
                  </button>
                ))}
              </div>

              {totalPages > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    disabled={currentPage === 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="px-2.5 py-1 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Prev
                  </button>
                  <span className="px-2 font-mono font-medium">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    disabled={currentPage === totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="px-2.5 py-1 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
