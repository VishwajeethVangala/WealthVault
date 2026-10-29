import React, { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CandlestickChart } from 'lucide-react'
import { SymbolPicker } from '../components/analytics/AnalysisParts'
import { AthBreakoutPanel } from '../components/strategies/AthBreakoutPanel'

export const AthStrategy: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('symbol') || '')
  const [symbol, setSymbol] = useState<string | null>(searchParams.get('symbol')?.toUpperCase() || null)
  const [runSeq, setRunSeq] = useState(0)
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
            <h1 className="font-serif text-xl sm:text-2xl text-wv-text font-semibold tracking-tight">ATH Strategy</h1>
            <p className="text-xs text-wv-text-3 mt-1">
              Buy when a stock breaks its all-time high soon after closing below its 200-DMA, sell on a close below the 200-DMA. Run it on any NSE/BSE stock: today's signal, the chart with entries and exits, and a backtest of every past trade. Prices come from Zerodha Kite.
            </p>
          </div>
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

      <AthBreakoutPanel symbol={symbol} runSeq={runSeq} active onStatus={handleStatus} />
    </div>
  )
}

export default AthStrategy
