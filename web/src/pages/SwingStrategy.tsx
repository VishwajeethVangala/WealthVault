import React, { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  CandlestickChart,
  CheckCircle2,
  CircleDot,
  Clock,
  Minus,
  SlidersHorizontal,
  XCircle,
} from 'lucide-react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AnalysisErrorCard,
  LoadingState,
  MetricCard,
  MetricRow,
  SymbolPicker,
} from '../components/analytics/AnalysisParts'
import { createEndLabelStack } from '../components/analytics/chartLabels'
import { useAnalysisRequest } from '../components/analytics/useAnalysisRequest'
import { fetchSwingStrategy } from '../utils/api'
import { formatDay, formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../utils/format'
import type { StrategyBar, StrategyTrade, SwingStrategyResult } from '../types'

// Close is the subject (neutral ink); three validated categorical hues for the averages;
// the UT stop is a level, drawn as a neutral dotted step line
const PRICE_SERIES = [
  { key: 'close', label: 'Close', color: '#1e293b', width: 1.5, dash: undefined, step: false },
  { key: 'sma_fast', label: '50-SMA', color: '#2a78d6', width: 2, dash: undefined, step: false },
  { key: 'sma_slow', label: '200-SMA', color: '#eb6834', width: 2, dash: undefined, step: false },
  { key: 'exit_ema', label: '20-EMA', color: '#1baf7a', width: 1.5, dash: '5 3', step: false },
  { key: 'ut_stop', label: 'UT stop', color: '#94a3b8', width: 1.5, dash: '2 3', step: true },
] as const

const EQUITY_SERIES = [
  { key: 'equity', label: 'Strategy', color: '#2a78d6' },
  { key: 'buy_hold', label: 'Buy & hold', color: '#eb6834' },
] as const

const BUY_COLOR = '#059669'
const SELL_COLOR = '#e11d48'
const REGIME_FILL = '#10b981'

const RANGES = [
  { label: '6M', bars: 126 },
  { label: '1Y', bars: 252 },
  { label: '2Y', bars: 504 },
  { label: 'All', bars: 0 },
]

type ChartBar = StrategyBar & { buyMark: number | null; sellMark: number | null; stopMark: number | null }

const TriangleMarker = (direction: 'up' | 'down', color: string) => (props: any) => {
  const { cx, cy, value, index } = props
  if (value == null || cx == null || cy == null) return <g key={index} />
  const s = 6
  const points =
    direction === 'up'
      ? `${cx},${cy - s} ${cx - s},${cy + s} ${cx + s},${cy + s}`
      : `${cx},${cy + s} ${cx - s},${cy - s} ${cx + s},${cy - s}`
  return <polygon key={index} points={points} fill={color} stroke="#ffffff" strokeWidth={1.5} />
}

const CrossMarker = (props: any) => {
  const { cx, cy, value, index } = props
  if (value == null || cx == null || cy == null) return <g key={index} />
  const s = 5
  return (
    <g key={index} stroke={SELL_COLOR} strokeWidth={2.5} strokeLinecap="round">
      <line x1={cx - s} y1={cy - s} x2={cx + s} y2={cy + s} />
      <line x1={cx - s} y1={cy + s} x2={cx + s} y2={cy - s} />
    </g>
  )
}

const renderPriceTooltip = (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: ChartBar = payload[0].payload
  const signal = bar.buy ? 'BUY signal' : bar.sell ? 'SELL signal' : bar.stop_exit ? 'Stop exit' : null
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-3.5 py-3 shadow-xl min-w-[190px]">
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="text-[11px] font-bold text-slate-900">{formatDay(label)}</span>
        {signal && (
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
              bar.buy ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'
            }`}
          >
            {signal}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        {PRICE_SERIES.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-5 text-[11px]">
            <span className="flex items-center gap-1.5 text-slate-500">
              <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
              {s.label}
            </span>
            <strong className="font-mono text-slate-900">{formatINR(bar[s.key as keyof StrategyBar] as number | null)}</strong>
          </div>
        ))}
        <div className="flex items-center justify-between gap-5 text-[11px] pt-1 mt-1 border-t border-slate-100">
          <span className="text-slate-500">Regime</span>
          <strong className={bar.regime ? 'text-emerald-700' : 'text-slate-500'}>{bar.regime ? 'Bullish' : 'Not bullish'}</strong>
        </div>
        {bar.stop_level != null && (
          <div className="flex items-center justify-between gap-5 text-[11px]">
            <span className="text-slate-500">Protective stop</span>
            <strong className="font-mono text-slate-900">{formatINR(bar.stop_level)}</strong>
          </div>
        )}
      </div>
    </div>
  )
}

const renderEquityTooltip = (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: StrategyBar = payload[0].payload
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-3.5 py-3 shadow-xl min-w-[180px]">
      <div className="text-[11px] font-bold text-slate-900 mb-2">{formatDay(label)}</div>
      {EQUITY_SERIES.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-5 text-[11px]">
          <span className="flex items-center gap-1.5 text-slate-500">
            <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
          <strong className="font-mono text-slate-900">{formatINR(bar[s.key])}</strong>
        </div>
      ))}
    </div>
  )
}

// Contiguous bullish-regime spans for background shading (Pine bgcolor)
const regimeSpans = (bars: StrategyBar[]): Array<{ x1: string; x2: string }> => {
  const spans: Array<{ x1: string; x2: string }> = []
  let start: string | null = null
  bars.forEach((b, i) => {
    if (b.regime && start == null) start = b.date
    const endsHere = b.regime && (i === bars.length - 1 || !bars[i + 1].regime)
    if (endsHere && start != null) {
      spans.push({ x1: start, x2: b.date })
      start = null
    }
  })
  return spans
}

const StatTile: React.FC<{ label: string; value: string; tone?: string; sub?: string }> = ({ label, value, tone = 'text-slate-900', sub }) => (
  <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-sm">
    <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
    <div className={`text-xl font-extrabold font-mono tracking-tight mt-1 ${tone}`}>{value}</div>
    {sub && <div className="text-[11px] text-slate-500 mt-0.5">{sub}</div>}
  </div>
)

const exitBadge = (t: StrategyTrade) => {
  const styles: Record<StrategyTrade['exit_reason'], string> = {
    'UT + EMA20 SELL': 'bg-slate-100 text-slate-700',
    'ATR STOP': 'bg-rose-50 text-rose-800',
    OPEN: 'bg-sky-50 text-sky-800',
  }
  const labels: Record<StrategyTrade['exit_reason'], string> = {
    'UT + EMA20 SELL': 'UT + EMA20',
    'ATR STOP': 'ATR stop',
    OPEN: 'Open',
  }
  return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${styles[t.exit_reason]}`}>{labels[t.exit_reason]}</span>
}

const statusBadge = (r: SwingStrategyResult) => {
  const s = r.status
  if (s.pending_order === 'BUY') return { text: 'BUY signal', cls: 'bg-emerald-50 text-emerald-800 border-emerald-200', Icon: ArrowUp }
  if (s.pending_order === 'SELL') return { text: 'SELL signal', cls: 'bg-rose-50 text-rose-800 border-rose-200', Icon: ArrowDown }
  if (s.state === 'IN_POSITION') return { text: 'In position', cls: 'bg-sky-50 text-sky-800 border-sky-200', Icon: CircleDot }
  if (s.regime_bullish) return { text: 'Waiting for entry', cls: 'bg-amber-50 text-amber-800 border-amber-200', Icon: Clock }
  return { text: 'No trade', cls: 'bg-slate-100 text-slate-700 border-slate-200', Icon: Minus }
}

export const SwingStrategy: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(searchParams.get('symbol') || '')
  const [lastQuery, setLastQuery] = useState<string | null>(null)
  const [years, setYears] = useState(5)
  const [utKey, setUtKey] = useState(1.0)
  const [utAtrPeriod, setUtAtrPeriod] = useState(10)
  const [useStop, setUseStop] = useState(true)
  const [stopMult, setStopMult] = useState(2.0)
  const [range, setRange] = useState(252)
  const { data: result, loading, error, authUrl, run } = useAnalysisRequest<SwingStrategyResult>()

  const analyze = (symbol: string) => {
    const clean = symbol.trim().toUpperCase()
    if (!clean) return
    setInput(clean)
    setLastQuery(clean)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set('symbol', clean)
        return next
      },
      { replace: true }
    )
    run(() =>
      fetchSwingStrategy(clean, {
        years,
        ut_key: utKey,
        ut_atr_period: utAtrPeriod,
        use_stop: useStop,
        stop_atr_mult: stopMult,
      })
    )
  }

  useEffect(() => {
    const initial = searchParams.get('symbol')
    if (initial) analyze(initial)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const chartData: ChartBar[] = useMemo(() => {
    if (!result) return []
    const stopFills = new Map(
      result.trades.filter((t) => t.exit_reason === 'ATR STOP' && t.exit_date).map((t) => [t.exit_date as string, t.exit_price])
    )
    const visible = range > 0 ? result.series.slice(-range) : result.series
    return visible.map((b) => ({
      ...b,
      buyMark: b.buy ? b.low * 0.975 : null,
      sellMark: b.sell ? b.high * 1.025 : null,
      stopMark: b.stop_exit ? stopFills.get(b.date) ?? b.low : null,
    }))
  }, [result, range])

  const spans = useMemo(() => regimeSpans(chartData), [chartData])
  const lastIndex = chartData.length - 1
  const priceTicks = useMemo(() => monthTicks(chartData.map((b) => b.date)), [chartData])
  const equityTicks = useMemo(() => monthTicks(result ? result.series.map((b) => b.date) : []), [result])
  // Fresh label stacks each render; placement within a stack is order-stable across hovers
  const priceLabel = createEndLabelStack(PRICE_SERIES.map((s) => s.key))
  const equityLabel = createEndLabelStack(EQUITY_SERIES.map((s) => s.key))
  const trades = useMemo(() => (result ? [...result.trades].reverse() : []), [result])
  const badge = result ? statusBadge(result) : null
  const p = result?.params

  return (
    <div className="flex flex-col gap-6">
      {/* 1. Header, symbol & inputs */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
        <div className="flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-slate-950 flex items-center justify-center text-emerald-400 shrink-0 shadow-sm">
            <CandlestickChart className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-serif text-xl sm:text-2xl text-slate-950 font-semibold tracking-tight">NSE Swing Momentum V2.1</h1>
            <p className="text-xs text-slate-500 mt-1">
              Long-only daily swing strategy. Buys a UT Bot cross-up while the 50/200-SMA trend filter is bullish; exits on a
              UT Bot flip with a close under the 20-EMA, or at a fixed 2×ATR(14) protective stop. Orders fill at the next open.
            </p>
          </div>
        </div>

        <SymbolPicker
          value={input}
          onChange={setInput}
          onSubmit={analyze}
          loading={loading}
          activeInstrument={result?.instrument}
          submitLabel="Run Strategy"
        />

        <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-6 pt-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Backtest</span>
            <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50" role="group" aria-label="Backtest length">
              {[1, 2, 3, 5].map((y) => (
                <button
                  key={y}
                  type="button"
                  onClick={() => setYears(y)}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
                    years === y ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'
                  }`}
                >
                  {y}Y
                </button>
              ))}
            </div>
          </div>

          <details className="group text-xs">
            <summary className="cursor-pointer select-none inline-flex items-center gap-1.5 font-semibold text-slate-600 hover:text-slate-950">
              <SlidersHorizontal className="w-3.5 h-3.5" /> Strategy inputs
            </summary>
            <div className="mt-3 flex flex-wrap items-end gap-4">
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">UT key</span>
                <input
                  type="number"
                  step={0.1}
                  min={0.1}
                  value={utKey}
                  onChange={(e) => setUtKey(Number(e.target.value) || 1)}
                  className="w-20 px-2 py-1.5 rounded-lg border border-slate-200 font-mono"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">UT ATR period</span>
                <input
                  type="number"
                  min={1}
                  value={utAtrPeriod}
                  onChange={(e) => setUtAtrPeriod(Math.max(1, Math.round(Number(e.target.value) || 10)))}
                  className="w-20 px-2 py-1.5 rounded-lg border border-slate-200 font-mono"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Stop ATR ×</span>
                <input
                  type="number"
                  step={0.1}
                  min={0.1}
                  value={stopMult}
                  disabled={!useStop}
                  onChange={(e) => setStopMult(Number(e.target.value) || 2)}
                  className="w-20 px-2 py-1.5 rounded-lg border border-slate-200 font-mono disabled:opacity-40"
                />
              </label>
              <label className="flex items-center gap-2 pb-1.5">
                <input type="checkbox" checked={useStop} onChange={(e) => setUseStop(e.target.checked)} className="accent-slate-900" />
                <span className="font-medium text-slate-700">ATR protective stop</span>
              </label>
              <span className="text-[11px] text-slate-400 pb-1.5">
                Fixed: 50/200-SMA · 20-bar slope · 20-EMA exit · ATR(14) stop · ₹1,00,000 · 0.10% commission · 1 tick slippage
              </span>
            </div>
          </details>
        </div>
      </div>

      {/* 2. Loading / Error / Empty */}
      {loading && <LoadingState message={`Fetching ${years} year${years > 1 ? 's' : ''} of daily prices and running the backtest…`} />}

      {!loading && error && (
        <AnalysisErrorCard
          error={error}
          authUrl={authUrl}
          title="Could not run the strategy"
          onRetry={lastQuery ? () => analyze(lastQuery) : undefined}
        />
      )}

      {!loading && !error && !result && (
        <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center">
          <CandlestickChart className="w-8 h-8 text-slate-300 mx-auto" />
          <p className="mt-3 text-sm font-semibold text-slate-700">Enter a stock to run the strategy</p>
          <p className="mt-1 text-xs text-slate-500">Shows today's status, signals on the chart, and a backtest of every past trade.</p>
        </div>
      )}

      {!loading && result && badge && p && (
        <>
          {/* 3. Current status */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 sm:p-6 shadow-sm grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700">{result.instrument}</span>
                <span className="text-[11px] text-slate-400">signals as of {result.as_of} close</span>
                <Link
                  to={`/momentum?symbol=${encodeURIComponent(result.instrument)}`}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-600 hover:text-slate-950"
                >
                  Momentum view <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              <h2 className="font-serif text-2xl text-slate-950 font-semibold tracking-tight">{result.name || result.instrument}</h2>
              <div className="flex items-center gap-3 flex-wrap">
                <span className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border text-sm font-bold ${badge.cls}`}>
                  <badge.Icon className="w-4 h-4" />
                  {badge.text}
                </span>
                <span className="text-sm font-semibold text-slate-900">{result.status.headline}</span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">{result.status.detail}</p>
              {result.partial_bar_excluded && (
                <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 self-start">
                  Today's candle is still forming, so it's excluded until the 3:30 pm close. Signals use completed days only.
                </p>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6">
                {result.status.state === 'IN_POSITION' && (
                  <>
                    <MetricRow label="Entry" value={`${formatINR(result.status.entry_price)}`} />
                    <MetricRow label="Entry date" value={result.status.entry_date ?? '—'} />
                    <MetricRow
                      label="Unrealized"
                      value={formatPct(result.status.unrealized_pct)}
                      tone={signedTone(result.status.unrealized_pct)}
                    />
                    <MetricRow label="Protective stop" value={p.use_stop ? formatINR(result.status.stop_price) : 'Off'} />
                    <MetricRow label="Days held" value={String(result.status.bars_held ?? '—')} />
                  </>
                )}
                <MetricRow label="Last close" value={formatINR(result.series[result.series.length - 1]?.close)} />
                <MetricRow label="UT stop" value={formatINR(result.status.ut_stop)} />
                <MetricRow label="20-EMA" value={formatINR(result.status.exit_ema)} />
              </div>
            </div>

            <div className="flex flex-col gap-2.5 lg:border-l lg:border-slate-100 lg:pl-6">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Trend filter</h3>
              {result.status.regime_checks.map((c) => (
                <div key={c.key} className="flex items-start gap-2.5">
                  {c.passed ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" aria-label="Pass" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" aria-label="Fail" />
                  )}
                  <div>
                    <div className="text-xs font-semibold text-slate-900">{c.label}</div>
                    <div className="text-[11px] text-slate-500 font-mono">{c.detail}</div>
                  </div>
                </div>
              ))}
              <div className={`text-xs font-bold mt-1 ${result.status.regime_bullish ? 'text-emerald-700' : 'text-slate-500'}`}>
                {result.status.regime_bullish ? 'Bullish regime: entries allowed' : 'Not bullish: no new entries'}
              </div>
            </div>
          </div>

          {/* 4. Price chart with signals */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">Price, indicators & signals</h3>
              <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50" role="group" aria-label="Chart range">
                {RANGES.map((r) => (
                  <button
                    key={r.label}
                    type="button"
                    onClick={() => setRange(r.bars)}
                    className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
                      range === r.bars ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500 hover:text-slate-900'
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap">
              {PRICE_SERIES.map((s) => (
                <span key={s.key} className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                  <svg width="16" height="4" aria-hidden="true">
                    <line x1="0" y1="2" x2="16" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinecap="round" />
                  </svg>
                  {s.label}
                </span>
              ))}
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                <svg width="12" height="12" aria-hidden="true"><polygon points="6,1 1,11 11,11" fill={BUY_COLOR} /></svg>BUY
              </span>
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                <svg width="12" height="12" aria-hidden="true"><polygon points="6,11 1,1 11,1" fill={SELL_COLOR} /></svg>SELL
              </span>
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                <svg width="12" height="12" aria-hidden="true" stroke={SELL_COLOR} strokeWidth="2.5" strokeLinecap="round">
                  <line x1="2" y1="2" x2="10" y2="10" /><line x1="2" y1="10" x2="10" y2="2" />
                </svg>
                Stop exit
              </span>
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: REGIME_FILL, opacity: 0.18 }} />
                Bullish regime
              </span>
            </div>
            <div className="h-[380px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
                  {spans.map((s) => (
                    <ReferenceArea key={s.x1} x1={s.x1} x2={s.x2} fill={REGIME_FILL} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
                  ))}
                  <CartesianGrid vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    ticks={priceTicks}
                    interval="preserveStartEnd"
                    minTickGap={28}
                    tickFormatter={formatMonth}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={{ stroke: '#e2e8f0' }}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                    tickFormatter={(v: number) => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  />
                  <Tooltip content={renderPriceTooltip} cursor={{ stroke: '#94a3b8', strokeWidth: 1 }} />
                  {result.status.state === 'IN_POSITION' && p.use_stop && result.status.stop_price != null && (
                    <ReferenceLine
                      y={result.status.stop_price}
                      stroke={SELL_COLOR}
                      strokeDasharray="6 4"
                      strokeWidth={1.5}
                      label={{ value: `Stop ${formatINR(result.status.stop_price)}`, position: 'insideBottomLeft', fontSize: 10, fill: '#9f1239' }}
                    />
                  )}
                  {PRICE_SERIES.map((s) => (
                    <Line
                      key={s.key}
                      type={s.step ? 'stepAfter' : 'monotone'}
                      dataKey={s.key}
                      stroke={s.color}
                      strokeWidth={s.width}
                      strokeDasharray={s.dash}
                      dot={false}
                      activeDot={s.key === 'close' ? { r: 4, stroke: '#ffffff', strokeWidth: 2 } : false}
                      isAnimationActive={false}
                      label={s.key === 'ut_stop' ? undefined : priceLabel(s.key, s.label, lastIndex)}
                    />
                  ))}
                  <Line dataKey="buyMark" stroke="none" dot={TriangleMarker('up', BUY_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                  <Line dataKey="sellMark" stroke="none" dot={TriangleMarker('down', SELL_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                  <Line dataKey="stopMark" stroke="none" dot={CrossMarker} activeDot={false} isAnimationActive={false} legendType="none" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 5. Backtest stats */}
          <div className="flex items-baseline justify-between flex-wrap gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Backtest · {formatDay(result.test_start)} – {formatDay(result.test_end)}
            </h3>
            <span className="text-[11px] text-slate-400">
              {result.bars_tested} trading days · ₹{p.initial_capital.toLocaleString('en-IN')} start · {p.commission_pct}% commission
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatTile
              label="Net return"
              value={formatPct(result.stats.net_profit_pct)}
              tone={signedTone(result.stats.net_profit_pct)}
              sub={`Buy & hold ${formatPct(result.stats.buy_hold_return_pct)}`}
            />
            <StatTile label="CAGR" value={formatPct(result.stats.cagr_pct)} tone={signedTone(result.stats.cagr_pct)} sub={formatINR(result.stats.final_equity)} />
            <StatTile label="Max drawdown" value={formatPct(result.stats.max_drawdown_pct)} tone="text-rose-700" sub="Peak-to-trough equity" />
            <StatTile
              label="Win rate"
              value={result.stats.win_rate_pct != null ? `${result.stats.win_rate_pct.toFixed(1)}%` : '—'}
              sub={`Avg win ${formatPct(result.stats.avg_win_pct)} · loss ${formatPct(result.stats.avg_loss_pct)}`}
            />
            <StatTile
              label="Profit factor"
              value={result.stats.profit_factor != null ? result.stats.profit_factor.toFixed(2) : '—'}
              sub="Gross profit ÷ gross loss"
            />
            <StatTile
              label="Closed trades"
              value={String(result.stats.total_trades)}
              sub={`${result.stats.signal_exits} signal · ${result.stats.stop_exits} stop${result.stats.open_trade ? ' · 1 open' : ''}`}
            />
            <StatTile
              label="Avg hold"
              value={result.stats.avg_bars_held != null ? `${result.stats.avg_bars_held.toFixed(0)} days` : '—'}
              sub="Trading days per trade"
            />
            <StatTile label="Time in market" value={`${result.stats.exposure_pct.toFixed(0)}%`} sub="Share of days holding" />
          </div>

          {/* 6. Equity curve */}
          <MetricCard title="Equity curve" subtitle="Strategy vs buying and holding over the same period">
            <div className="flex items-center gap-4">
              {EQUITY_SERIES.map((s) => (
                <span key={s.key} className="flex items-center gap-1.5 text-[11px] font-medium text-slate-600">
                  <span className="w-4 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
                  {s.label}
                </span>
              ))}
            </div>
            <div className="h-[240px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.series} margin={{ top: 8, right: 80, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="date"
                    ticks={equityTicks}
                    interval="preserveStartEnd"
                    minTickGap={28}
                    tickFormatter={formatMonth}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={{ stroke: '#e2e8f0' }}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    width={64}
                    tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
                  />
                  <ReferenceLine y={p.initial_capital} stroke="#cbd5e1" strokeDasharray="3 3" />
                  <Tooltip content={renderEquityTooltip} cursor={{ stroke: '#94a3b8', strokeWidth: 1 }} />
                  {EQUITY_SERIES.map((s) => (
                    <Line
                      key={s.key}
                      type="monotone"
                      dataKey={s.key}
                      stroke={s.color}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, stroke: '#ffffff', strokeWidth: 2 }}
                      isAnimationActive={false}
                      label={equityLabel(s.key, s.label, result.series.length - 1)}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </MetricCard>

          {/* 7. Trade list */}
          <MetricCard title="Trades" subtitle="Newest first. Entry and exit prices include 1 tick of slippage; P&L is after commission.">
            {trades.length === 0 ? (
              <p className="text-xs text-slate-500">No trades in this period: the entry conditions never lined up.</p>
            ) : (
              <div className="overflow-x-auto -mx-5 px-5">
                <table className="w-full text-xs min-w-[720px]">
                  <thead>
                    <tr className="text-[10px] font-bold uppercase tracking-wider text-slate-400 text-left">
                      <th className="py-2 pr-3">Entry</th>
                      <th className="py-2 pr-3 text-right">Entry ₹</th>
                      <th className="py-2 pr-3">Exit</th>
                      <th className="py-2 pr-3 text-right">Exit ₹</th>
                      <th className="py-2 pr-3">Reason</th>
                      <th className="py-2 pr-3 text-right">Qty</th>
                      <th className="py-2 pr-3 text-right">P&amp;L ₹</th>
                      <th className="py-2 pr-3 text-right">P&amp;L %</th>
                      <th className="py-2 text-right">Days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t) => (
                      <tr key={`${t.entry_date}-${t.exit_date}`} className="border-t border-slate-100">
                        <td className="py-2 pr-3 font-mono text-slate-700">{t.entry_date}</td>
                        <td className="py-2 pr-3 font-mono text-right text-slate-900">{formatINR(t.entry_price)}</td>
                        <td className="py-2 pr-3 font-mono text-slate-700">{t.exit_date ?? '—'}</td>
                        <td className="py-2 pr-3 font-mono text-right text-slate-900">{t.exit_price != null ? formatINR(t.exit_price) : '—'}</td>
                        <td className="py-2 pr-3">{exitBadge(t)}</td>
                        <td className="py-2 pr-3 font-mono text-right text-slate-700">{t.quantity}</td>
                        <td className={`py-2 pr-3 font-mono text-right font-semibold ${signedTone(t.pnl)}`}>
                          {t.pnl >= 0 ? '+' : ''}
                          {formatINR(t.pnl)}
                        </td>
                        <td className={`py-2 pr-3 font-mono text-right font-semibold ${signedTone(t.pnl_pct)}`}>{formatPct(t.pnl_pct)}</td>
                        <td className="py-2 font-mono text-right text-slate-700">{t.bars_held}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </MetricCard>

          <p className="text-[11px] text-slate-400 leading-relaxed">
            A backtest replays past prices; it is not a forecast or investment advice. Results can differ from TradingView
            because of price-adjustment differences in the data, and because this port sizes positions in whole shares bought
            at the fill price. Note the script only exits on a UT Bot flip that closes under the 20-EMA on the same day; otherwise
            the fixed protective stop is the only exit.
          </p>
        </>
      )}
    </div>
  )
}

export default SwingStrategy
