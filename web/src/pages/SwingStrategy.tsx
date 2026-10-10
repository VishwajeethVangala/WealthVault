import React, { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CandlestickChart } from 'lucide-react'
import { SymbolPicker } from '../components/analytics/AnalysisParts'
import { AthBreakoutPanel } from '../components/strategies/AthBreakoutPanel'
import { SwingV21Panel } from '../components/strategies/SwingV21Panel'

type TabId = 'v21' | 'ath'

const TABS: Array<{ id: TabId; label: string; short: string; sub: string }> = [
  { id: 'v21', label: 'Swing Momentum V2.1', short: 'Swing V2.1', sub: 'Trend filter + UT Bot' },
  { id: 'ath', label: '200-DMA ATH Breakout', short: 'ATH Breakout', sub: 'Below DMA → new high' },
]

export const SwingStrategy: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('symbol') || '')
  const [symbol, setSymbol] = useState<string | null>(searchParams.get('symbol')?.toUpperCase() || null)
  const [runSeq, setRunSeq] = useState(0)
  const [tab, setTab] = useState<TabId>(searchParams.get('tab') === 'ath' ? 'ath' : 'v21')
  const [panelStatus, setPanelStatus] = useState<{ loading: boolean; instrument?: string }>({ loading: false })

  const updateParams = (changes: Record<string, string>) =>
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        Object.entries(changes).forEach(([k, v]) => next.set(k, v))
        return next
      },
      { replace: true }
    )

  const analyze = (value: string) => {
    const clean = value.trim().toUpperCase()
    if (!clean) return
    setInput(clean)
    setSymbol(clean)
    setRunSeq((n) => n + 1)
    updateParams({ symbol: clean })
  }

  const selectTab = (id: TabId) => {
    setTab(id)
    updateParams({ tab: id })
  }

  const handleStatus = useCallback((status: { loading: boolean; instrument?: string }) => setPanelStatus(status), [])

  return (
    <div className="page-in">
      {/* Header, strategy tabs & symbol */}
      <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-wv-text flex items-center justify-center text-wv-gain shrink-0 shadow-sm">
            <CandlestickChart className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-serif text-xl sm:text-2xl text-wv-text font-semibold tracking-tight">Swing Strategies</h1>
            <p className="text-xs text-wv-text-3 mt-1">
              Run a TradingView strategy on any NSE/BSE stock: today's signal, the chart with entries and exits, and a backtest
              of every past trade. Prices come from Zerodha Kite.
            </p>
          </div>
        </div>

        <div role="tablist" aria-label="Strategy" className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-wv-surface-2 border border-wv-border">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={tab === t.id}
              aria-controls={`panel-${t.id}`}
              onClick={() => selectTab(t.id)}
              className={`px-3 py-2 rounded-lg text-left transition-all ${
                tab === t.id ? 'bg-wv-surface shadow-sm text-wv-text' : 'text-wv-text-3 hover:text-wv-text'
              }`}
            >
              <span className="block text-xs sm:text-sm font-bold truncate">
                <span className="sm:hidden">{t.short}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </span>
              <span className="block text-[10px] sm:text-[11px] font-medium text-wv-text-3 truncate">{t.sub}</span>
            </button>
          ))}
        </div>

        <SymbolPicker
          value={input}
          onChange={setInput}
          onSubmit={analyze}
          loading={panelStatus.loading}
          activeInstrument={panelStatus.instrument}
          submitLabel="Run Strategy"
        />
      </div>

      {/* Both panels stay mounted so each keeps its inputs and last result when switching tabs */}
      <div role="tabpanel" id="panel-v21" aria-labelledby="tab-v21" hidden={tab !== 'v21'}>
        <SwingV21Panel symbol={symbol} runSeq={runSeq} active={tab === 'v21'} onStatus={handleStatus} />
      </div>
      <div role="tabpanel" id="panel-ath" aria-labelledby="tab-ath" hidden={tab !== 'ath'}>
        <AthBreakoutPanel symbol={symbol} runSeq={runSeq} active={tab === 'ath'} onStatus={handleStatus} />
      </div>
    </div>
  )
}

export default SwingStrategy
