import React, { useMemo } from 'react'
import { AlertCircle, ExternalLink, RotateCcw, Search } from 'lucide-react'
import { usePortfolio } from '../../context/PortfolioContext'
import { classifyAssetClass } from '../../utils/portfolioFilters'

// Search box plus quick-pick chips from the user's Indian equity holdings
export const SymbolPicker: React.FC<{
  value: string
  onChange: (value: string) => void
  onSubmit: (symbol: string) => void
  loading: boolean
  activeInstrument?: string
  submitLabel: string
  children?: React.ReactNode
}> = ({ value, onChange, onSubmit, loading, activeInstrument, submitLabel, children }) => {
  const { holdings } = usePortfolio()

  const quickPicks = useMemo(() => {
    const seen = new Set<string>()
    return [...holdings]
      .filter((h) => classifyAssetClass(h) === 'EQUITY')
      .sort((a, b) => (b.current_value || 0) - (a.current_value || 0))
      .map((h) => h.instrument_symbol.trim().toUpperCase().split(/\s+/)[0])
      .filter((sym) => {
        if (!sym || seen.has(sym)) return false
        seen.add(sym)
        return true
      })
      .slice(0, 12)
  }, [holdings])

  return (
    <>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit(value)
        }}
        className="flex flex-col sm:flex-row gap-2"
      >
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-wv-text-3 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Enter a stock symbol, e.g. INFY, RELIANCE, BSE:500209"
            aria-label="Stock symbol"
            className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl border border-wv-border bg-wv-surface-2 focus:bg-wv-surface focus:outline-none focus:ring-2 focus:ring-wv-text focus:border-wv-border-strong font-mono uppercase placeholder:normal-case placeholder:font-sans"
          />
        </div>
        {children}
        <button
          type="submit"
          disabled={loading || !value.trim()}
          className="px-5 py-2.5 bg-wv-text text-wv-bg text-xs font-semibold rounded-xl hover:bg-wv-text disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
        >
          {loading ? 'Analyzing…' : submitLabel}
        </button>
      </form>

      {quickPicks.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Your holdings</span>
          {quickPicks.map((sym) => (
            <button
              key={sym}
              type="button"
              onClick={() => onSubmit(sym)}
              disabled={loading}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-mono font-semibold border transition-colors ${
                activeInstrument?.endsWith(`:${sym}`)
                  ? 'bg-wv-text text-wv-bg border-wv-text'
                  : 'bg-wv-surface text-wv-text-2 border-wv-border hover:border-wv-border-strong'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
      )}
    </>
  )
}

export const LoadingState: React.FC<{ message: string }> = ({ message }) => (
  <div className="py-16 flex flex-col items-center justify-center">
    <div className="w-10 h-10 border-3 border-wv-accent border-t-transparent rounded-full animate-spin"></div>
    <p className="mt-4 text-sm font-medium text-wv-text-3">{message}</p>
  </div>
)

// Error card; shows the Kite login link when the broker session needs today's login
export const AnalysisErrorCard: React.FC<{
  error: string
  authUrl: string | null
  title: string
  onRetry?: () => void
}> = ({ error, authUrl, title, onRetry }) => (
  <div className={`bg-wv-surface border p-6 rounded-2xl shadow-sm flex items-start gap-4 ${authUrl ? 'border-wv-warn' : 'border-wv-loss'}`}>
    <AlertCircle className={`w-6 h-6 shrink-0 mt-0.5 ${authUrl ? 'text-wv-warn' : 'text-wv-loss'}`} />
    <div className="flex-1">
      <h3 className="font-semibold text-wv-text text-base">{authUrl ? 'Zerodha Kite login required' : title}</h3>
      <p className="text-xs text-wv-text-3 mt-1 break-words">{error}</p>
      <div className="flex flex-wrap gap-2 mt-4">
        {authUrl && (
          <a
            href={authUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-wv-text text-wv-bg text-xs font-semibold rounded-xl hover:bg-wv-text transition-all shadow-sm"
          >
            Log in to Kite <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-wv-surface border border-wv-border text-wv-text-2 text-xs font-semibold rounded-xl hover:border-wv-border-strong transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Retry
          </button>
        )}
      </div>
    </div>
  </div>
)

export const MetricCard: React.FC<{ title: string; subtitle?: string; className?: string; children: React.ReactNode }> = ({
  title,
  subtitle,
  className = '',
  children,
}) => (
  <div className={`bg-wv-surface border border-wv-border rounded-2xl p-5 shadow-sm flex flex-col gap-3 ${className}`}>
    <div>
      <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">{title}</h3>
      {subtitle && <p className="text-[11px] text-wv-text-3 mt-0.5">{subtitle}</p>}
    </div>
    {children}
  </div>
)

export const MetricRow: React.FC<{ label: string; value: React.ReactNode; tone?: string }> = ({
  label,
  value,
  tone = 'text-wv-text',
}) => (
  <div className="flex items-center justify-between text-xs py-1.5 border-b border-wv-border last:border-0">
    <span className="text-wv-text-3">{label}</span>
    <span className={`font-mono font-semibold ${tone}`}>{value}</span>
  </div>
)
