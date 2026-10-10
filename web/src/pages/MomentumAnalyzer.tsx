import React, { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  Minus,
  TrendingDown,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AnalysisErrorCard,
  LoadingState,
  MetricCard,
  MetricRow as Row,
  SymbolPicker,
} from '../components/analytics/AnalysisParts'
import { createEndLabelStack } from '../components/analytics/chartLabels'
import { useAnalysisRequest } from '../components/analytics/useAnalysisRequest'
import { fetchMomentum } from '../utils/api'
import { formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../utils/format'
import type { MomentumAnalysis, ReturnWindow } from '../types'

// Validated categorical palette (light surface): close, 50-DMA, 200-DMA
const SERIES = [
  { key: 'close', label: 'Close', color: 'var(--accent)', dash: undefined },
  { key: 'sma50', label: '50-DMA', color: 'var(--gain)', dash: '6 4' },
  { key: 'sma200', label: '200-DMA', color: 'var(--warn)', dash: undefined },
] as const

const RETURN_WINDOWS: ReturnWindow[] = ['1M', '3M', '6M', '12M', '12-1']

type VerdictTone = 'up' | 'neutral' | 'down'

const verdictTone = (score: number, max: number): VerdictTone => {
  if (max === 0) return 'neutral'
  const scaled = Math.round((score * 5) / max)
  if (scaled >= 4) return 'up'
  if (scaled <= 1) return 'down'
  return 'neutral'
}

const VERDICT_STYLES: Record<VerdictTone, { badge: string; icon: React.ElementType }> = {
  up: { badge: 'bg-wv-gain-weak text-wv-gain border-wv-gain', icon: TrendingUp },
  neutral: { badge: 'bg-wv-warn-weak text-wv-warn border-wv-warn', icon: Minus },
  down: { badge: 'bg-wv-loss-weak text-wv-loss border-wv-loss', icon: TrendingDown },
}

const rsiZone = (rsi: number): { label: string; tone: string } => {
  if (rsi >= 70) return { label: 'Overbought', tone: 'text-wv-warn' }
  if (rsi >= 50) return { label: 'Bullish', tone: 'text-wv-gain' }
  if (rsi > 30) return { label: 'Bearish', tone: 'text-wv-loss' }
  return { label: 'Oversold', tone: 'text-wv-warn' }
}

const renderChartTooltip = (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const point = payload[0].payload
  return (
    <div className="bg-wv-surface rounded-xl border border-wv-border px-3.5 py-3 shadow-xl min-w-[170px]">
      <div className="text-[11px] font-bold text-wv-text mb-2">
        {new Date(label).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
      </div>
      <div className="flex flex-col gap-1">
        {SERIES.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-5 text-[11px]">
            <span className="flex items-center gap-1.5 text-wv-text-3">
              <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
              {s.label}
            </span>
            <strong className="font-mono text-wv-text">
              {point[s.key] != null ? formatINR(point[s.key]) : '—'}
            </strong>
          </div>
        ))}
      </div>
    </div>
  )
}


export const MomentumAnalyzer: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('symbol') || '')
  const [lastQuery, setLastQuery] = useState<string | null>(null)
  const { data: report, loading, error, authUrl, run } = useAnalysisRequest<MomentumAnalysis>()

  const analyze = (symbol: string) => {
    const clean = symbol.trim().toUpperCase()
    if (!clean) return
    setInput(clean)
    setLastQuery(clean)
    // Keep the symbol in the URL so the strategy page and reloads pick it up
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('symbol', clean)
        return next
      },
      { replace: true }
    )
    run(() => fetchMomentum(clean))
  }

  // Auto-run for a symbol passed in the URL (e.g. from the strategy page)
  useEffect(() => {
    const initial = searchParams.get('symbol')
    if (initial) analyze(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const tone = report ? verdictTone(report.trend_score, report.trend_max_score) : 'neutral'
  const VerdictIcon = VERDICT_STYLES[tone].icon
  const lastIndex = report ? report.series.length - 1 : -1
  const ticks = report ? monthTicks(report.series.map((p) => p.date)) : []
  const endLabel = createEndLabelStack(SERIES.map((s) => s.key))

  return (
    <div className="page-in">
      {/* 1. Header & Search */}
      <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-wv-text flex items-center justify-center text-wv-gain shrink-0 shadow-sm">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-serif text-xl sm:text-2xl text-wv-text font-semibold tracking-tight">Momentum Analyzer</h1>
            <p className="text-xs text-wv-text-3 mt-1">
              Trend verdict from moving averages (50/200-DMA, golden cross, 200-DMA slope, MACD), plus returns, RSI,
              52-week range and strength vs NIFTY 50. Uses one year of daily prices from Zerodha Kite.
            </p>
          </div>
        </div>

        <SymbolPicker
          value={input}
          onChange={setInput}
          onSubmit={analyze}
          loading={loading}
          activeInstrument={report?.instrument}
          submitLabel="Analyze Momentum"
        />
      </div>

      {/* 2. Loading / Error / Empty states */}
      {loading && <LoadingState message="Fetching one year of daily prices…" />}

      {!loading && error && (
        <AnalysisErrorCard
          error={error}
          authUrl={authUrl}
          title="Could not compute momentum"
          onRetry={lastQuery ? () => analyze(lastQuery) : undefined}
        />
      )}

      {!loading && !error && !report && (
        <div className="bg-wv-surface border border-dashed border-wv-border-strong rounded-2xl p-10 text-center">
          <Activity className="w-8 h-8 text-wv-text-3 mx-auto" />
          <p className="mt-3 text-sm font-semibold text-wv-text-2">Enter a stock to see its momentum</p>
          <p className="mt-1 text-xs text-wv-text-3">NSE symbols work directly (INFY). Use BSE:CODE for BSE-only stocks.</p>
        </div>
      )}

      {/* 3. Report */}
      {!loading && report && (
        <>
          {/* 3a. Verdict hero */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-5">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-md bg-wv-surface-2 text-wv-text-2">{report.instrument}</span>
                <span className="text-[11px] text-wv-text-3">as of {report.as_of} · {report.candles_used} trading days</span>
              </div>
              <h2 className="font-serif text-2xl text-wv-text font-semibold tracking-tight mt-2">{report.name || report.instrument}</h2>
              <div className="flex items-baseline gap-3 mt-1">
                <span className="text-2xl font-extrabold font-mono text-wv-text tracking-tight">{formatINR(report.last_price)}</span>
                <span className={`text-sm font-mono font-semibold ${signedTone(report.returns['1M'])}`}>
                  {formatPct(report.returns['1M'])} <span className="text-wv-text-3 font-sans font-medium text-xs">1M</span>
                </span>
              </div>
            </div>

            <div className="flex flex-col items-start md:items-end gap-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Trend verdict (moving averages)</span>
              <span className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border text-sm font-bold ${VERDICT_STYLES[tone].badge}`}>
                <VerdictIcon className="w-4 h-4" />
                {report.trend_verdict}
              </span>
              <div className="flex items-center gap-1.5" aria-label={`Trend score ${report.trend_score} of ${report.trend_max_score}`}>
                {report.trend_checks.map((c, i) => (
                  <span key={c.key} className={`w-5 h-1.5 rounded-full ${i < report.trend_score ? 'bg-wv-gain' : 'bg-wv-border'}`} />
                ))}
                <span className="text-xs font-mono font-semibold text-wv-text-2 ml-1">
                  {report.trend_score}/{report.trend_max_score}
                </span>
              </div>
              <Link
                to={`/strategy?symbol=${encodeURIComponent(report.instrument)}`}
                className="inline-flex items-center gap-1 text-[11px] font-semibold text-wv-text-2 hover:text-wv-text mt-1"
              >
                Run Swing V2.1 strategy <ArrowUpRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          {/* 3b. Trend checklist + chart */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <MetricCard title="Trend checklist" subtitle="Each rule that holds adds one point">
              <ul className="flex flex-col gap-2.5">
                {report.trend_checks.map((c) => (
                  <li key={c.key} className="flex items-start gap-2.5">
                    {c.passed ? (
                      <CheckCircle2 className="w-4 h-4 text-wv-gain shrink-0 mt-0.5" aria-label="Pass" />
                    ) : (
                      <XCircle className="w-4 h-4 text-wv-loss shrink-0 mt-0.5" aria-label="Fail" />
                    )}
                    <div>
                      <div className="text-xs font-semibold text-wv-text">{c.label}</div>
                      <div className="text-[11px] text-wv-text-3 font-mono">{c.detail}</div>
                    </div>
                  </li>
                ))}
              </ul>
              {report.trend_max_score < 5 && (
                <p className="text-[11px] text-wv-warn bg-wv-warn-weak border border-wv-warn rounded-lg px-2.5 py-1.5">
                  Some rules need more price history (200-DMA needs 200 trading days) and were skipped.
                </p>
              )}
            </MetricCard>

            <div className="xl:col-span-2 bg-wv-surface border border-wv-border rounded-2xl p-5 shadow-sm flex flex-col gap-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Price vs moving averages · 1Y</h3>
                <div className="flex items-center gap-4">
                  {SERIES.map((s) => (
                    <span key={s.key} className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
                      <svg width="16" height="4" aria-hidden="true">
                        <line x1="0" y1="2" x2="16" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinecap="round" />
                      </svg>
                      {s.label}
                    </span>
                  ))}
                </div>
              </div>
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={report.series} margin={{ top: 8, right: 56, bottom: 0, left: 0 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={formatMonth}
                      tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                      tickLine={false}
                      axisLine={{ stroke: 'var(--border)' }}
                      ticks={ticks}
                      interval="preserveStartEnd"
                    minTickGap={28}
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                      tickLine={false}
                      axisLine={false}
                      width={56}
                      tickFormatter={(v: number) => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    />
                    <Tooltip content={renderChartTooltip} cursor={{ stroke: 'var(--text-3)', strokeWidth: 1 }} />
                    {SERIES.map((s) => (
                      <Line
                        key={s.key}
                        type="monotone"
                        dataKey={s.key}
                        name={s.label}
                        stroke={s.color}
                        strokeWidth={2}
                        strokeDasharray={s.dash}
                        dot={false}
                        activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                        connectNulls={false}
                        isAnimationActive={false}
                        label={endLabel(s.key, s.label, lastIndex)}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* 3c. Supporting measures */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
            <MetricCard title="Price momentum" subtitle={`Return, and vs ${report.benchmark} (pp)`}>
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 text-xs">
                <span className="text-[10px] font-bold uppercase text-wv-text-3 pb-1">Window</span>
                <span className="text-[10px] font-bold uppercase text-wv-text-3 pb-1 text-right">Return</span>
                <span className="text-[10px] font-bold uppercase text-wv-text-3 pb-1 text-right">vs Index</span>
                {RETURN_WINDOWS.map((w) => {
                  const rs = w === '12-1' ? undefined : report.relative_strength[w]
                  return (
                    <React.Fragment key={w}>
                      <span className="py-1.5 border-t border-wv-border text-wv-text-3">{w === '12-1' ? '12M excl. last 1M' : w}</span>
                      <span className={`py-1.5 border-t border-wv-border text-right font-mono font-semibold ${signedTone(report.returns[w])}`}>
                        {formatPct(report.returns[w])}
                      </span>
                      <span className={`py-1.5 border-t border-wv-border text-right font-mono font-semibold ${signedTone(rs)}`}>
                        {w === '12-1' ? '' : formatPct(rs)}
                      </span>
                    </React.Fragment>
                  )
                })}
              </div>
            </MetricCard>

            <MetricCard title="Risk-adjusted" subtitle="Return ÷ annualized volatility">
              <Row label="6M score" value={report.risk_adjusted_6m?.toFixed(2) ?? '—'} tone={signedTone(report.risk_adjusted_6m)} />
              <Row label="12M score" value={report.risk_adjusted_12m?.toFixed(2) ?? '—'} tone={signedTone(report.risk_adjusted_12m)} />
              <Row label="6M volatility" value={report.volatility_6m != null ? `${report.volatility_6m.toFixed(1)}%` : '—'} />
              <Row label="12M volatility" value={report.volatility_12m != null ? `${report.volatility_12m.toFixed(1)}%` : '—'} />
              <p className="text-[11px] text-wv-text-3">Above 1 means the return outweighed the volatility taken to get it.</p>
            </MetricCard>

            <MetricCard title="RSI (14)" subtitle="Short-term strength oscillator">
              {report.rsi_14 != null ? (
                <>
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-extrabold font-mono text-wv-text">{report.rsi_14.toFixed(1)}</span>
                    <span className={`text-xs font-bold ${rsiZone(report.rsi_14).tone}`}>{rsiZone(report.rsi_14).label}</span>
                  </div>
                  <div className="relative h-2 rounded-full bg-wv-surface-2 overflow-hidden">
                    <div className="absolute inset-y-0 left-[30%] right-[30%] bg-wv-border" />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-wv-text ring-2 ring-wv-surface"
                      style={{ left: `calc(${Math.min(100, Math.max(0, report.rsi_14))}% - 5px)` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] font-mono text-wv-text-3">
                    <span>0</span><span>30</span><span>50</span><span>70</span><span>100</span>
                  </div>
                </>
              ) : (
                <span className="text-xs text-wv-text-3">Not enough data</span>
              )}
            </MetricCard>

            <MetricCard title="52-week range" subtitle="Where the price sits in its 1Y range">
              {report.high_52w != null && report.low_52w != null && report.high_52w > report.low_52w ? (
                <div className="flex flex-col gap-1.5">
                  <div className="relative h-2 rounded-full bg-wv-surface-2">
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-wv-text ring-2 ring-wv-surface"
                      style={{
                        left: `calc(${Math.min(100, Math.max(0, ((report.last_price - report.low_52w) / (report.high_52w - report.low_52w)) * 100))}% - 5px)`,
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] font-mono text-wv-text-3">
                    <span>{formatINR(report.low_52w)}</span>
                    <span>{formatINR(report.high_52w)}</span>
                  </div>
                </div>
              ) : null}
              <Row label="From 52W high" value={formatPct(report.pct_from_52w_high)} tone={signedTone(report.pct_from_52w_high)} />
              <Row label="From 52W low" value={formatPct(report.pct_from_52w_low)} tone={signedTone(report.pct_from_52w_low)} />
            </MetricCard>
          </div>

          <MetricCard title="Moving averages & MACD">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
              <div>
                <Row label="20-DMA" value={formatINR(report.sma_20)} />
                <Row label="50-DMA" value={`${formatINR(report.sma_50)}  (${formatPct(report.pct_from_sma50)})`} />
                <Row label="200-DMA" value={`${formatINR(report.sma_200)}  (${formatPct(report.pct_from_sma200)})`} />
                <Row label="200-DMA slope (20d)" value={formatPct(report.sma200_slope_pct)} tone={signedTone(report.sma200_slope_pct)} />
              </div>
              <div>
                <Row
                  label="50/200 cross"
                  value={
                    report.cross_state
                      ? `${report.cross_state === 'golden' ? 'Golden' : 'Death'}${report.days_since_cross != null ? ` · ${report.days_since_cross}d ago` : ''}`
                      : '—'
                  }
                  tone={report.cross_state === 'golden' ? 'text-wv-gain' : report.cross_state === 'death' ? 'text-wv-loss' : 'text-wv-text-3'}
                />
                <Row label="MACD (12, 26)" value={report.macd?.toFixed(2) ?? '—'} />
                <Row label="Signal (9)" value={report.macd_signal?.toFixed(2) ?? '—'} />
                <Row label="Histogram" value={report.macd_histogram?.toFixed(2) ?? '—'} tone={signedTone(report.macd_histogram)} />
              </div>
            </div>
          </MetricCard>

          <p className="text-[11px] text-wv-text-3 leading-relaxed">
            Momentum describes past price behaviour; it is not a forecast or investment advice. Trend signals lag and can
            reverse sharply around market turning points.
          </p>
        </>
      )}
    </div>
  )
}

export default MomentumAnalyzer
