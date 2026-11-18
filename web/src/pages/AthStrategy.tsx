import React, { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CandlestickChart, Sparkles, TrendingUp } from 'lucide-react'
import { SymbolPicker } from '../components/analytics/AnalysisParts'
import { AthBreakoutPanel } from '../components/strategies/AthBreakoutPanel'
import { SupertrendPanel } from '../components/strategies/SupertrendPanel'
import { fetchSupertrendRecommendations, fetchWatchlist } from '../utils/api'
import type { ScreenerRecommendation, WatchlistItem } from '../types'

export type StrategyTab = 'ath' | 'supertrend'

export const AthStrategy: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('symbol') || '')
  const [symbol, setSymbol] = useState<string | null>(searchParams.get('symbol')?.toUpperCase() || null)
  const initialTab = (searchParams.get('tab') as StrategyTab) || 'ath'
  const [tab, setTab] = useState<StrategyTab>(initialTab === 'supertrend' ? 'supertrend' : 'ath')
  const [runSeq, setRunSeq] = useState(0)
  const [panelStatus, setPanelStatus] = useState<{ loading: boolean; instrument?: string }>({ loading: false })
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])

  const [recommendations, setRecommendations] = useState<ScreenerRecommendation[]>([])
  const [recsLoading, setRecsLoading] = useState(false)

  const loadRecommendations = useCallback(async () => {
    setRecsLoading(true)
    try {
      const res = await fetchSupertrendRecommendations('vishwa-supertrend')
      setRecommendations(res.items || [])
    } catch (err) {
      console.error('Failed to load supertrend recommendations:', err)
    } finally {
      setRecsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchWatchlist()
      .then((res) => setWatchlist(res.items || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadRecommendations()
  }, [loadRecommendations])

  const updateParams = (changes: Record<string, string>) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        Object.entries(changes).forEach(([k, v]) => next.set(k, v))
        return next
      },
      { replace: true }
    )

  const handleTabChange = (newTab: StrategyTab) => {
    setTab(newTab)
    updateParams({ tab: newTab })
  }

  const analyze = (value: string) => {
    const clean = value.trim().toUpperCase()
    if (!clean) return
    setInput(clean)
    setSymbol(clean)
    setRunSeq((n) => n + 1)
    updateParams({ symbol: clean })
  }

  const handleStatus = useCallback((status: { loading: boolean; instrument?: string }) => setPanelStatus(status), [])

  return (
    <div className="page-in flex flex-col gap-6">
      {/* Header, strategy tabs & symbol */}
      <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-wv-text flex items-center justify-center text-wv-gain shrink-0 shadow-sm">
              <CandlestickChart className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-serif text-xl sm:text-2xl text-wv-text font-semibold tracking-tight">Strategies</h1>
              <p className="text-xs text-wv-text-3 mt-1">
                Systematic breakout & trend-following models. Run backtests, check entry/exit rules, and inspect full trade logs on any NSE/BSE stock using live Kite data.
              </p>
            </div>
          </div>

          {/* Strategy Tabs Switcher */}
          <div className="inline-flex rounded-xl border border-wv-border p-1 bg-wv-surface-2 self-start sm:self-center" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'ath'}
              onClick={() => handleTabChange('ath')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                tab === 'ath'
                  ? 'bg-wv-surface text-wv-text shadow-sm'
                  : 'text-wv-text-3 hover:text-wv-text'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5 text-amber-500" />
              <span>200-DMA → ATH Breakout</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'supertrend'}
              onClick={() => handleTabChange('supertrend')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all cursor-pointer ${
                tab === 'supertrend'
                  ? 'bg-wv-surface text-wv-text shadow-sm'
                  : 'text-wv-text-3 hover:text-wv-text'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
              <span>SuperTrend Magic Trend</span>
            </button>
          </div>
        </div>

        <SymbolPicker
          value={input}
          onChange={setInput}
          onSubmit={analyze}
          loading={panelStatus.loading}
          activeInstrument={panelStatus.instrument}
          submitLabel="Run Strategy"
          watchlist={watchlist}
          recommendations={tab === 'supertrend' ? recommendations : undefined}
          onRefreshRecommendations={tab === 'supertrend' ? loadRecommendations : undefined}
          recommendationsLoading={recsLoading}
        />
      </div>

      {/* Render active panel */}
      {tab === 'ath' && (
        <AthBreakoutPanel symbol={symbol} runSeq={runSeq} active={tab === 'ath'} onStatus={handleStatus} />
      )}
      {tab === 'supertrend' && (
        <SupertrendPanel symbol={symbol} runSeq={runSeq} active={tab === 'supertrend'} onStatus={handleStatus} />
      )}
    </div>
  )
}

export default AthStrategy
