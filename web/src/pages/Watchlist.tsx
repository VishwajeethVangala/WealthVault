import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  CandlestickChart,
  Plus,
  RefreshCw,
  Search,
  Star,
  Target,
  Trash2,
  TrendingUp,
} from 'lucide-react'
import {
  addToWatchlist,
  fetchWatchlist,
  refreshWatchlist,
  removeFromWatchlist,
  searchStocks,
  type StockSuggestion,
} from '../utils/api'
import { formatDay, formatINR, formatPct, signedTone } from '../utils/format'
import type { WatchlistItem } from '../types'

type FilterKind = 'all' | 'bullish' | 'bearish' | 'setup'
type SortBy = 'recent' | 'score' | 'gain' | 'alpha'

const QUICK_STARTS = [
  { symbol: 'NSE:RELIANCE', name: 'Reliance Industries Limited' },
  { symbol: 'NSE:TCS', name: 'Tata Consultancy Services' },
  { symbol: 'NSE:HDFCBANK', name: 'HDFC Bank Limited' },
  { symbol: 'NSE:INFY', name: 'Infosys Limited' },
  { symbol: 'NSE:ICICIBANK', name: 'ICICI Bank Limited' },
  { symbol: 'NSE:TATAMOTORS', name: 'Tata Motors Limited' },
]

export const Watchlist: React.FC = () => {
  const [items, setItems] = useState<WatchlistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<{ msg: string; tone: 'ok' | 'bad' } | null>(null)

  // Add stock form state
  const [inputSymbol, setInputSymbol] = useState('')
  const [inputName, setInputName] = useState('')
  const [inputNotes, setInputNotes] = useState('')
  const [inputTarget, setInputTarget] = useState('')
  const [adding, setAdding] = useState(false)

  // Suggestions for add stock
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([])
  const [openSuggestions, setOpenSuggestions] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(-1)
  const typed = useRef(false)

  // Filters & sorting
  const [searchQuery, setSearchQuery] = useState('')
  const [filter, setFilter] = useState<FilterKind>('all')
  const [sortBy, setSortBy] = useState<SortBy>('recent')

  const showToast = (msg: string, tone: 'ok' | 'bad' = 'ok') => {
    setToast({ msg, tone })
    window.setTimeout(() => setToast(null), 3500)
  }

  const loadData = useCallback(async (isSilent = false) => {
    if (!isSilent) setLoading(true)
    setError(null)
    try {
      const res = await fetchWatchlist()
      setItems(res.items || [])
    } catch (err: any) {
      console.error('Failed to load watchlist:', err)
      setError(err?.message || 'Could not load your watchlist.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const res = await refreshWatchlist()
      setItems(res.items || [])
      showToast('Recalculated momentum and signals for all watchlist stocks')
    } catch (err: any) {
      console.error('Watchlist refresh error:', err)
      showToast('Could not refresh signals: ' + (err?.message || 'Error'), 'bad')
      await loadData(true)
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [loadData])

  // Autocomplete debounce
  useEffect(() => {
    const q = inputSymbol.trim()
    if (!typed.current || q.length < 2 || /^[A-Z]+:/i.test(q)) {
      setSuggestions([])
      return
    }
    let stale = false
    const t = window.setTimeout(() => {
      searchStocks(q)
        .then((list) => {
          if (stale) return
          setSuggestions(list)
          setActiveSuggestion(-1)
          setOpenSuggestions(true)
        })
        .catch(() => {
          if (stale) return
          setSuggestions([])
        })
    }, 200)
    return () => {
      stale = true
      window.clearTimeout(t)
    }
  }, [inputSymbol])

  const chooseSuggestion = (s: StockSuggestion) => {
    typed.current = false
    setInputSymbol(s.symbol)
    setInputName(s.name)
    setSuggestions([])
    setOpenSuggestions(false)
  }

  const handleAdd = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const cleanSym = inputSymbol.trim().toUpperCase()
    if (!cleanSym || adding) return

    setAdding(true)
    const targetPriceNum = inputTarget ? parseFloat(inputTarget) : undefined

    // Optimistic item
    const optItem: WatchlistItem = {
      symbol: cleanSym.includes(':') ? cleanSym : `NSE:${cleanSym}`,
      name: inputName.trim() || cleanSym.split(':').pop()!,
      notes: inputNotes.trim(),
      target_price: targetPriceNum ?? null,
      price_when_added: null,
      added_at: new Date().toISOString(),
      last_price: null,
      pct_since_added: null,
      trend_verdict: null,
      trend_score: null,
      signal_state: null,
    }

    setItems((prev) => [optItem, ...prev.filter((it) => it.symbol !== optItem.symbol)])
    showToast(`Added ${optItem.symbol} to watchlist`)
    setInputSymbol('')
    setInputName('')
    setInputNotes('')
    setInputTarget('')

    try {
      await addToWatchlist(cleanSym, {
        name: inputName.trim() || undefined,
        notes: inputNotes.trim() || undefined,
        target_price: targetPriceNum,
      })
      await loadData(true)
    } catch (err: any) {
      console.error('Failed to add to watchlist:', err)
      showToast(err?.message || 'Failed to save to server', 'bad')
      await loadData(true)
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (symbol: string) => {
    const target = items.find((it) => it.symbol === symbol)
    // Optimistic removal
    setItems((prev) => prev.filter((it) => it.symbol !== symbol))
    showToast(`Removed ${target?.name || symbol} from watchlist`)

    try {
      await removeFromWatchlist(symbol)
      await loadData(true)
    } catch (err: any) {
      console.error('Failed to remove from watchlist:', err)
      showToast(err?.message || 'Failed to remove', 'bad')
      await loadData(true)
    }
  }

  // Filtered & Sorted items
  const visibleItems = useMemo(() => {
    let res = [...items]

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      res = res.filter(
        (it) => it.symbol.toLowerCase().includes(q) || it.name.toLowerCase().includes(q) || (it.notes && it.notes.toLowerCase().includes(q))
      )
    }

    if (filter === 'bullish') {
      res = res.filter((it) => (it.trend_score ?? 0) >= 4 || it.trend_verdict?.toLowerCase().includes('bull'))
    } else if (filter === 'bearish') {
      res = res.filter((it) => (it.trend_score ?? 5) <= 2 || it.trend_verdict?.toLowerCase().includes('bear'))
    } else if (filter === 'setup') {
      res = res.filter((it) => it.signal_state === 'IN_POSITION' || it.signal_state === 'SETUP_ACTIVE' || it.signal_state?.includes('TRADE'))
    }

    res.sort((a, b) => {
      if (sortBy === 'score') return (b.trend_score ?? -1) - (a.trend_score ?? -1)
      if (sortBy === 'gain') return (b.pct_since_added ?? -999) - (a.pct_since_added ?? -999)
      if (sortBy === 'alpha') return a.symbol.localeCompare(b.symbol)
      return new Date(b.added_at).getTime() - new Date(a.added_at).getTime()
    })

    return res
  }, [items, searchQuery, filter, sortBy])

  // Summary calculations
  const stats = useMemo(() => {
    const total = items.length
    const bullish = items.filter((it) => (it.trend_score ?? 0) >= 4).length
    const inSetups = items.filter((it) => it.signal_state === 'IN_POSITION' || it.signal_state === 'SETUP_ACTIVE').length
    const withGains = items.filter((it) => it.pct_since_added != null)
    const avgGain = withGains.length > 0 ? withGains.reduce((acc, it) => acc + (it.pct_since_added || 0), 0) / withGains.length : null
    return { total, bullish, inSetups, avgGain }
  }, [items])

  return (
    <div className="page-in max-w-7xl mx-auto flex flex-col gap-6">
      {/* Toast message */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-2xl shadow-xl border text-xs font-semibold backdrop-blur-md transition-all ${
            toast.tone === 'ok'
              ? 'bg-wv-surface/90 text-wv-text border-amber-500/40 shadow-amber-500/10'
              : 'bg-wv-surface/90 text-rose-500 border-rose-500/40 shadow-rose-500/10'
          }`}
        >
          <Star className={`w-4 h-4 ${toast.tone === 'ok' ? 'fill-amber-500 text-amber-500' : 'text-rose-500'}`} />
          <span>{toast.msg}</span>
        </div>
      )}

      {/* Error alert banner if fetch failed */}
      {error && (
        <div className="bg-wv-loss-weak border border-wv-loss rounded-2xl p-4 flex items-center gap-3 text-xs text-wv-loss">
          <AlertCircle className="w-5 h-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Top Controls: Compact KPIs & Refresh Action */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 flex-1">
          <div className="bg-wv-surface border border-wv-border rounded-xl px-3 py-2 shadow-xs flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Tracked</span>
              <span className="text-base font-bold font-mono text-wv-text leading-tight">{stats.total} stocks</span>
            </div>
            <Star className="w-4 h-4 text-amber-500/60" />
          </div>

          <div className="bg-wv-surface border border-wv-border rounded-xl px-3 py-2 shadow-xs flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Bullish</span>
              <span className="text-base font-bold font-mono text-wv-gain leading-tight">{stats.bullish}</span>
            </div>
            <TrendingUp className="w-4 h-4 text-wv-gain/60" />
          </div>

          <div className="bg-wv-surface border border-wv-border rounded-xl px-3 py-2 shadow-xs flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">ATH Setups</span>
              <span className="text-base font-bold font-mono text-wv-accent leading-tight">{stats.inSetups}</span>
            </div>
            <CandlestickChart className="w-4 h-4 text-wv-accent/60" />
          </div>

          <div className="bg-wv-surface border border-wv-border rounded-xl px-3 py-2 shadow-xs flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Avg Gain</span>
              <span className={`text-base font-bold font-mono leading-tight ${signedTone(stats.avgGain)}`}>
                {stats.avgGain != null ? formatPct(stats.avgGain) : '0.00%'}
              </span>
            </div>
            <Activity className="w-4 h-4 text-wv-text-3/60" />
          </div>
        </div>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border border-wv-border bg-wv-surface text-wv-text-2 hover:text-wv-text hover:border-wv-border-strong shrink-0 transition-colors shadow-xs active:scale-95"
          title="Scan and compute momentum & ATH breakout signals for all watchlist stocks"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-amber-500' : 'text-wv-text-3'}`} />
          <span>{refreshing ? 'Scanning…' : 'Refresh Signals'}</span>
        </button>
      </div>

      {/* Sleek Compact Add Stock Toolbar */}
      <div className="bg-wv-surface border border-wv-border rounded-xl p-2.5 shadow-xs">
        <form onSubmit={handleAdd} className="flex flex-col sm:flex-row items-stretch gap-2">
          {/* Symbol input with suggestions */}
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-wv-text-3 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={inputSymbol}
              onChange={(e) => {
                typed.current = true
                setInputSymbol(e.target.value)
              }}
              onFocus={() => setOpenSuggestions(true)}
              onBlur={() => window.setTimeout(() => setOpenSuggestions(false), 200)}
              placeholder="Add stock to radar (e.g. TCS, RELIANCE, BSE:500209)…"
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-wv-border bg-wv-surface-2 focus:bg-wv-surface focus:outline-none focus:ring-1 focus:ring-amber-500 font-mono uppercase placeholder:normal-case placeholder:font-sans"
            />
            {openSuggestions && suggestions.length > 0 && (
              <ul
                role="listbox"
                className="absolute z-30 left-0 right-0 top-full mt-1 max-h-56 overflow-auto rounded-xl border border-wv-border bg-wv-surface shadow-xl py-1 text-xs"
              >
                {suggestions.map((s, idx) => (
                  <li
                    key={s.symbol}
                    role="option"
                    aria-selected={idx === activeSuggestion}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      chooseSuggestion(s)
                    }}
                    className={`flex items-baseline gap-2.5 px-3 py-2 cursor-pointer hover:bg-wv-surface-2 transition-colors ${
                      idx === activeSuggestion ? 'bg-wv-surface-2' : ''
                    }`}
                  >
                    <span className="font-mono text-xs font-bold text-amber-500 shrink-0">{s.symbol}</span>
                    <span className="text-[11px] text-wv-text-2 truncate">{s.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Notes input */}
          <div className="w-full sm:w-48">
            <input
              value={inputNotes}
              onChange={(e) => setInputNotes(e.target.value)}
              placeholder="Notes (optional)"
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-wv-border bg-wv-surface-2 focus:bg-wv-surface focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>

          {/* Target Price input */}
          <div className="w-full sm:w-28">
            <input
              type="number"
              step="any"
              value={inputTarget}
              onChange={(e) => setInputTarget(e.target.value)}
              placeholder="Target ₹"
              className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-wv-border bg-wv-surface-2 focus:bg-wv-surface focus:outline-none focus:ring-1 focus:ring-amber-500 font-mono"
            />
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={adding || !inputSymbol.trim()}
            className="inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 bg-amber-500 text-black text-xs font-bold rounded-lg hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-xs shrink-0 active:scale-95"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{adding ? 'Adding…' : 'Add Stock'}</span>
          </button>
        </form>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* Segmented Filter Pills */}
        <div className="flex items-center gap-1.5 p-1 bg-wv-surface-2 border border-wv-border rounded-xl self-start overflow-x-auto max-w-full">
          {(
            [
              ['all', 'All Stocks'],
              ['bullish', 'Bullish'],
              ['bearish', 'Bearish'],
              ['setup', 'In Setup / Trade'],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setFilter(k)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors shrink-0 ${
                filter === k ? 'bg-wv-surface text-wv-text shadow-sm' : 'text-wv-text-3 hover:text-wv-text'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto w-full sm:w-auto">
          {/* Quick search input */}
          <div className="relative flex-1 sm:w-48">
            <Search className="w-3.5 h-3.5 text-wv-text-3 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter list…"
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-wv-border bg-wv-surface focus:outline-none focus:ring-1 focus:ring-amber-500 text-wv-text"
            />
          </div>

          {/* Sort dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortBy)}
            className="px-3 py-1.5 text-xs rounded-xl border border-wv-border bg-wv-surface text-wv-text focus:outline-none focus:ring-1 focus:ring-amber-500"
          >
            <option value="recent">Recently Added</option>
            <option value="score">Highest Momentum</option>
            <option value="gain">Best % Since Added</option>
            <option value="alpha">Symbol (A-Z)</option>
          </select>
        </div>
      </div>

      {/* Main Table / Empty State */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="mt-3 text-xs font-medium text-wv-text-3">Loading your watchlist…</p>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="bg-wv-surface border border-dashed border-wv-border rounded-2xl p-10 text-center flex flex-col items-center">
          <div className="w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-500 mb-3">
            <Star className="w-6 h-6" />
          </div>
          <h3 className="font-serif text-lg font-semibold text-wv-text">
            {items.length === 0 ? 'Your Watchlist is empty' : 'No stocks match your filter'}
          </h3>
          <p className="text-xs text-wv-text-3 max-w-md mt-1 mb-6">
            {items.length === 0
              ? 'Start tracking stocks to monitor trend verdicts, moving average alignments, and ATH breakouts before you buy.'
              : 'Try clearing the search query or switching to "All Stocks".'}
          </p>

          {items.length === 0 && (
            <div className="flex flex-col items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Quick Add Popular Stocks</span>
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {QUICK_STARTS.map((qs) => (
                  <button
                    key={qs.symbol}
                    type="button"
                    onClick={() => {
                      setInputSymbol(qs.symbol)
                      setInputName(qs.name)
                    }}
                    className="px-3 py-1.5 rounded-xl border border-wv-border bg-wv-surface-2 text-wv-text-2 text-xs font-mono font-semibold hover:border-amber-500/50 hover:text-amber-500 transition-colors"
                  >
                    + {qs.symbol.split(':').pop()}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-wv-surface border border-wv-border rounded-2xl overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-wv-border bg-wv-surface-2/60 text-[11px] font-bold uppercase tracking-wider text-wv-text-3">
                  <th className="py-3 px-4">Stock</th>
                  <th className="py-3 px-4 text-right">Last Price</th>
                  <th className="py-3 px-4 text-right">Added Price & Return</th>
                  <th className="py-3 px-4">Trend Verdict</th>
                  <th className="py-3 px-4">ATH Breakout</th>
                  <th className="py-3 px-4">Target / Notes</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-wv-border text-xs">
                {visibleItems.map((it) => {
                  const symOnly = it.symbol.split(':').pop()!
                  const score = it.trend_score ?? 0
                  const isBullish = score >= 4
                  const isBearish = score <= 2 && it.trend_score != null

                  return (
                    <tr key={it.symbol} className="hover:bg-wv-surface-2/40 transition-colors">
                      {/* Stock Identifier */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-col">
                          <Link
                            to={`/momentum?symbol=${encodeURIComponent(it.symbol)}`}
                            className="font-mono font-bold text-sm text-wv-text hover:text-amber-500 inline-flex items-center gap-1 group"
                          >
                            <span>{symOnly}</span>
                            <ArrowUpRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </Link>
                          <span className="text-[11px] text-wv-text-3 truncate max-w-[200px]" title={it.name}>
                            {it.name || it.symbol}
                          </span>
                        </div>
                      </td>

                      {/* Current Price */}
                      <td className="py-3.5 px-4 text-right font-mono font-semibold text-wv-text">
                        {it.last_price != null ? formatINR(it.last_price) : '—'}
                      </td>

                      {/* Added Price & Return */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex flex-col items-end">
                          <span className={`font-mono font-bold ${signedTone(it.pct_since_added)}`}>
                            {it.pct_since_added != null ? formatPct(it.pct_since_added) : '—'}
                          </span>
                          <span className="text-[10px] text-wv-text-3 font-mono">
                            {it.price_when_added != null ? `added @ ${formatINR(it.price_when_added)}` : `added ${formatDay(it.added_at)}`}
                          </span>
                        </div>
                      </td>

                      {/* Momentum Trend Verdict */}
                      <td className="py-3.5 px-4">
                        {it.trend_verdict ? (
                          <div className="flex items-center gap-2">
                            <span
                              className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                                isBullish
                                  ? 'bg-wv-gain-weak text-wv-gain border-wv-gain'
                                  : isBearish
                                  ? 'bg-wv-loss-weak text-wv-loss border-wv-loss'
                                  : 'bg-wv-surface-2 text-wv-text-2 border-wv-border'
                              }`}
                            >
                              {it.trend_verdict}
                            </span>
                            {it.trend_score != null && (
                              <span className="font-mono text-[11px] font-bold text-wv-text-3">
                                {it.trend_score}/5
                              </span>
                            )}
                          </div>
                        ) : (
                          <button
                            type="button"
                            onClick={handleRefresh}
                            className="text-wv-text-3 hover:text-amber-500 text-[11px] inline-flex items-center gap-1 group"
                            title="Click to scan signals now"
                          >
                            <span>Pending scan</span>
                            <RefreshCw className="w-2.5 h-2.5 opacity-60 group-hover:opacity-100 group-hover:rotate-180 transition-all" />
                          </button>
                        )}
                      </td>

                      {/* ATH Breakout State */}
                      <td className="py-3.5 px-4">
                        {it.signal_state ? (
                          <span
                            className={`px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                              it.signal_state === 'IN_POSITION'
                                ? 'bg-wv-gain-weak text-wv-gain border-wv-gain'
                                : it.signal_state === 'SETUP_ACTIVE'
                                ? 'bg-wv-warn-weak text-wv-warn border-wv-warn'
                                : 'bg-wv-surface-2 text-wv-text-3 border-wv-border'
                            }`}
                          >
                            {it.signal_state === 'FLAT' || it.signal_state === 'NO_SETUP'
                              ? 'No setup'
                              : it.signal_state === 'IN_POSITION'
                              ? 'In position'
                              : it.signal_state === 'SETUP_ACTIVE'
                              ? 'Setup active'
                              : it.signal_state.replace('_', ' ')}
                          </span>
                        ) : (
                          <span className="text-wv-text-3 text-[11px]">—</span>
                        )}
                      </td>

                      {/* Target Price & Notes */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-col gap-0.5">
                          {it.target_price != null && (
                            <span className="inline-flex items-center gap-1 font-mono text-[11px] text-amber-500 font-semibold">
                              <Target className="w-3 h-3" />
                              <span>{formatINR(it.target_price)}</span>
                            </span>
                          )}
                          {it.notes ? (
                            <span className="text-[11px] text-wv-text-2 italic truncate max-w-[200px]" title={it.notes}>
                              "{it.notes}"
                            </span>
                          ) : (
                            <span className="text-wv-text-3 text-[11px]">—</span>
                          )}
                        </div>
                      </td>

                      {/* Action Links */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link
                            to={`/momentum?symbol=${encodeURIComponent(it.symbol)}`}
                            title="Open Momentum Analyzer"
                            className="p-1.5 rounded-lg border border-wv-border bg-wv-surface text-wv-text-3 hover:text-wv-gain hover:border-wv-gain transition-colors"
                          >
                            <Activity className="w-4 h-4" />
                          </Link>

                          <Link
                            to={`/strategy?symbol=${encodeURIComponent(it.symbol)}`}
                            title="Open ATH Strategy"
                            className="p-1.5 rounded-lg border border-wv-border bg-wv-surface text-wv-text-3 hover:text-wv-accent hover:border-wv-accent transition-colors"
                          >
                            <CandlestickChart className="w-4 h-4" />
                          </Link>

                          <button
                            type="button"
                            onClick={() => handleRemove(it.symbol)}
                            title="Remove from Watchlist"
                            className="p-1.5 rounded-lg border border-wv-border bg-wv-surface text-wv-text-3 hover:text-rose-500 hover:border-rose-500/50 hover:bg-rose-500/10 transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Bottom Information Card: Watchlist & Pre-Flight Radar */}
      <div className="bg-wv-surface border border-wv-border rounded-xl p-4 shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-wv-text-3 mt-1">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-amber-500 shrink-0">
            <Star className="w-4 h-4 fill-amber-500" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-wv-text text-xs">Watchlist & Pre-Flight Radar</span>
              <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded-full bg-amber-500/15 text-amber-500 border border-amber-500/30">
                {items.length} {items.length === 1 ? 'stock' : 'stocks'}
              </span>
            </div>
            <p className="text-[11px] text-wv-text-3 mt-0.5">
              Continuous background tracking of daily momentum trends (50/200-DMA, MACD, RSI) and 200-DMA ATH breakout setups.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-wv-text-3 shrink-0 self-end sm:self-auto">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>Refreshes daily at market close (~3:35 PM) & on demand</span>
        </div>
      </div>
    </div>
  )
}
