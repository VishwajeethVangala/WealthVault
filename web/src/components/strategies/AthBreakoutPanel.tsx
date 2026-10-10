import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, ArrowUpRight, CheckCircle2, CircleDot, Clock, Minus, XCircle } from 'lucide-react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AnalysisErrorCard, LoadingState, MetricRow } from '../analytics/AnalysisParts'
import { createEndLabelStack, triangleMarker } from '../analytics/chartLabels'
import { useAnalysisRequest } from '../analytics/useAnalysisRequest'
import { fetchAthBreakoutStrategy } from '../../utils/api'
import { formatDay, formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../../utils/format'
import type { AthBreakoutBar, AthBreakoutResult } from '../../types'
import {
  BacktestStats,
  EquityCurveCard,
  InputsPanel,
  LegendLine,
  LegendSignals,
  NumberInput,
  RangeToggle,
  StatusBadge,
  TradesCard,
} from './StrategyParts'
import { BUY_COLOR, SELL_COLOR, SETUP_FILL, booleanSpans, sliceRange, type RangeOption } from './strategyShared'
import { useStrategyRun, type StrategyPanelProps } from './useStrategyRun'

// Close is the subject (neutral ink); one categorical hue for the DMA; the ATH is a level (neutral dotted step)
const PRICE_SERIES = [
  { key: 'close', label: 'Close', color: 'var(--text)', width: 1.5, dash: undefined, step: false },
  { key: 'dma', label: '200-DMA', color: 'var(--warn)', width: 2, dash: undefined, step: false },
  { key: 'ath', label: 'All-time high', color: 'var(--text-3)', width: 1.5, dash: '2 3', step: true },
] as const

const RANGES: RangeOption[] = [
  { label: '1Y', bars: 252 },
  { label: '3Y', bars: 756 },
  { label: '5Y', bars: 1260 },
  { label: 'All', bars: 0 },
]

type ChartBar = AthBreakoutBar & { buyMark: number | null; sellMark: number | null }

const makeTooltip = (dmaLabel: string) => (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: ChartBar = payload[0].payload
  const signal = bar.buy ? 'BUY at close' : bar.sell ? 'SELL at close' : null
  return (
    <div className="bg-wv-surface rounded-xl border border-wv-border px-3.5 py-3 shadow-xl min-w-[190px]">
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="text-[11px] font-bold text-wv-text">{formatDay(label)}</span>
        {signal && (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${bar.buy ? 'bg-wv-gain-weak text-wv-gain' : 'bg-wv-loss-weak text-wv-loss'}`}>
            {signal}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        {PRICE_SERIES.map((s) => (
          <div key={s.key} className="flex items-center justify-between gap-5 text-[11px]">
            <span className="flex items-center gap-1.5 text-wv-text-3">
              <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
              {s.key === 'dma' ? dmaLabel : s.label}
            </span>
            <strong className="font-mono text-wv-text">{formatINR(bar[s.key as keyof AthBreakoutBar] as number | null)}</strong>
          </div>
        ))}
        <div className="flex items-center justify-between gap-5 text-[11px] pt-1 mt-1 border-t border-wv-border">
          <span className="text-wv-text-3">Setup window</span>
          <strong className={bar.in_window ? 'text-wv-gain' : 'text-wv-text-3'}>{bar.in_window ? 'Active' : 'Inactive'}</strong>
        </div>
      </div>
    </div>
  )
}

const statusBadge = (r: AthBreakoutResult) => {
  const s = r.status
  if (s.last_signal === 'BUY') return { text: 'Bought today', cls: 'bg-wv-gain-weak text-wv-gain border-wv-gain', Icon: ArrowUp }
  if (s.last_signal === 'SELL') return { text: 'Sold today', cls: 'bg-wv-loss-weak text-wv-loss border-wv-loss', Icon: ArrowDown }
  if (s.state === 'IN_POSITION') return { text: 'In position', cls: 'bg-wv-accent-weak text-wv-accent border-wv-accent', Icon: CircleDot }
  if (s.in_window) return { text: 'Setup active', cls: 'bg-wv-warn-weak text-wv-warn border-wv-warn', Icon: Clock }
  return { text: 'No setup', cls: 'bg-wv-surface-2 text-wv-text-2 border-wv-border', Icon: Minus }
}

const Check: React.FC<{ passed: boolean; label: string; detail: string }> = ({ passed, label, detail }) => (
  <div className="flex items-start gap-2.5">
    {passed ? (
      <CheckCircle2 className="w-4 h-4 text-wv-gain shrink-0 mt-0.5" aria-label="Pass" />
    ) : (
      <XCircle className="w-4 h-4 text-wv-loss shrink-0 mt-0.5" aria-label="Fail" />
    )}
    <div>
      <div className="text-xs font-semibold text-wv-text">{label}</div>
      <div className="text-[11px] text-wv-text-3 font-mono">{detail}</div>
    </div>
  </div>
)

export const AthBreakoutPanel: React.FC<StrategyPanelProps> = (props) => {
  const [startDate, setStartDate] = useState('2015-01-01')
  const [dmaLength, setDmaLength] = useState(200)
  const [windowBars, setWindowBars] = useState(200)
  const [capital, setCapital] = useState(50000)
  const [range, setRange] = useState(0)
  const { data: result, loading, error, authUrl, run } = useAnalysisRequest<AthBreakoutResult>()

  const execute = (symbol: string) =>
    run(() =>
      fetchAthBreakoutStrategy(symbol, {
        start_date: /^\d{4}-\d{2}-\d{2}$/.test(startDate) ? startDate : '2015-01-01',
        dma_length: Math.min(400, Math.max(50, Math.round(dmaLength) || 200)),
        window_bars: Math.max(1, Math.round(windowBars) || 200),
        capital_per_trade: Math.max(1000, capital || 50000),
      })
    )
  useStrategyRun(props, execute, loading, result?.instrument)

  const chartData: ChartBar[] = useMemo(() => {
    if (!result) return []
    return sliceRange(result.series, range).map((b) => ({
      ...b,
      buyMark: b.buy ? b.close * 0.96 : null,
      sellMark: b.sell ? b.high * 1.04 : null,
    }))
  }, [result, range])

  const spans = useMemo(() => booleanSpans(chartData, (b) => b.in_window), [chartData])
  const ticks = useMemo(() => monthTicks(chartData.map((b) => b.date)), [chartData])
  const lastIndex = chartData.length - 1
  const endLabel = createEndLabelStack(PRICE_SERIES.map((s) => s.key))
  const badge = result ? statusBadge(result) : null
  const p = result?.params
  const s = result?.status
  const dmaLabel = p ? `${p.dma_length}-DMA` : '200-DMA'
  const tooltip = useMemo(() => makeTooltip(dmaLabel), [dmaLabel])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-wv-text-3">
          Buys when the close breaks above the prior all-time high within 200 trading days of a close below the 200-DMA, and
          holds until a close below the 200-DMA. Orders fill at the signal day's close, with a fixed amount per trade.
        </p>
        <InputsPanel
          onApply={() => props.symbol && execute(props.symbol)}
          disabled={loading || !props.symbol}
          fixedNote="Fixed: fills at the signal close · no commission (as in the script) · capital per trade does not compound"
        >
          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Backtest start</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-2 py-1.5 rounded-lg border border-wv-border font-mono"
            />
          </label>
          <NumberInput label="DMA length" value={dmaLength} onChange={setDmaLength} min={50} />
          <NumberInput label="Window (days)" value={windowBars} onChange={setWindowBars} min={1} />
          <NumberInput label="Capital / trade ₹" value={capital} onChange={setCapital} step={1000} min={1000} width="w-28" />
        </InputsPanel>
      </div>

      {loading && <LoadingState message="Fetching the full daily price history and running the backtest…" />}

      {!loading && error && (
        <AnalysisErrorCard
          error={error}
          authUrl={authUrl}
          title="Could not run the strategy"
          onRetry={props.symbol ? () => execute(props.symbol as string) : undefined}
        />
      )}

      {!loading && !error && !result && (
        <div className="bg-wv-surface border border-dashed border-wv-border-strong rounded-2xl p-10 text-center">
          <p className="text-sm font-semibold text-wv-text-2">Enter a stock to run the strategy</p>
          <p className="mt-1 text-xs text-wv-text-3">Uses the stock's full price history so the all-time high is real.</p>
        </div>
      )}

      {!loading && result && badge && p && s && (
        <>
          {/* Current status */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-md bg-wv-surface-2 text-wv-text-2">{result.instrument}</span>
                <span className="text-[11px] text-wv-text-3">as of {result.as_of} close</span>
                <Link
                  to={`/momentum?symbol=${encodeURIComponent(result.instrument)}`}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-wv-text-2 hover:text-wv-text"
                >
                  Momentum view <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              <h2 className="font-serif text-2xl text-wv-text font-semibold tracking-tight">{result.name || result.instrument}</h2>
              <div className="flex items-center gap-3 flex-wrap">
                <StatusBadge {...badge} />
                <span className="text-sm font-semibold text-wv-text">{s.headline}</span>
              </div>
              <p className="text-xs text-wv-text-2 leading-relaxed">{s.detail}</p>
              {result.partial_bar_excluded && (
                <p className="text-[11px] text-wv-warn bg-wv-warn-weak border border-wv-warn rounded-lg px-2.5 py-1.5 self-start">
                  Today's candle is still forming, so it's excluded until the 3:30 pm close. Signals use completed days only.
                </p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6">
                {s.state === 'IN_POSITION' && (
                  <>
                    <MetricRow label="Entry" value={formatINR(s.entry_price)} />
                    <MetricRow label="Entry date" value={s.entry_date ?? '—'} />
                    <MetricRow label="Unrealized" value={formatPct(s.unrealized_pct)} tone={signedTone(s.unrealized_pct)} />
                    <MetricRow label="Days held" value={String(s.bars_held ?? '—')} />
                  </>
                )}
                <MetricRow label="Last close" value={formatINR(s.close)} />
                <MetricRow label={dmaLabel} value={`${formatINR(s.dma)} (${formatPct(s.pct_above_dma)})`} />
                <MetricRow label="Prior ATH" value={formatINR(s.prior_ath)} />
                <MetricRow label="To ATH" value={formatPct(s.pct_to_ath)} />
              </div>
              <p className="text-[11px] text-wv-text-3">
                All-time high measured from {formatDay(result.history_start)}, the earliest daily data Kite returned.
              </p>
            </div>

            <div className="flex flex-col gap-2.5 lg:border-l lg:border-wv-border lg:pl-6">
              {s.state === 'IN_POSITION' ? (
                <>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Exit rule</h3>
                  <Check
                    passed={(s.pct_above_dma ?? 0) >= 0}
                    label={`Holding above the ${dmaLabel}`}
                    detail={`${formatPct(s.pct_above_dma)} above · exit on a close below ${formatINR(s.dma)}`}
                  />
                </>
              ) : (
                <>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Entry rules</h3>
                  <Check
                    passed={s.in_window}
                    label={`Closed below the ${dmaLabel} in the last ${p.window_bars} days`}
                    detail={
                      s.days_since_below_dma != null
                        ? `${s.days_since_below_dma} trading days ago${s.window_days_left != null ? ` · ${s.window_days_left} days left` : ''}`
                        : 'No close below the DMA yet'
                    }
                  />
                  <Check
                    passed={s.prior_ath != null && s.close > s.prior_ath}
                    label="Close above the prior all-time high"
                    detail={`${formatINR(s.close)} vs ${formatINR(s.prior_ath)}`}
                  />
                  <div className={`text-xs font-bold mt-1 ${s.in_window ? 'text-wv-gain' : 'text-wv-text-3'}`}>
                    {s.in_window ? 'Setup active: an ATH break would trigger a buy' : 'No setup: waiting for a close below the DMA'}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Price chart with signals */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Price, DMA, all-time high & signals</h3>
              <RangeToggle ranges={RANGES} value={range} onChange={setRange} />
            </div>
            <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap">
              {PRICE_SERIES.map((ps) => (
                <LegendLine key={ps.key} color={ps.color} label={ps.key === 'dma' ? dmaLabel : ps.label} dash={ps.dash} />
              ))}
              <LegendSignals setupLabel="Setup window" />
            </div>
            <div className="h-[380px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 8, right: 84, bottom: 0, left: 0 }}>
                  {spans.map((sp) => (
                    <ReferenceArea key={sp.x1} x1={sp.x1} x2={sp.x2} fill={SETUP_FILL} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
                  ))}
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="date"
                    ticks={ticks}
                    interval="preserveStartEnd"
                    minTickGap={28}
                    tickFormatter={formatMonth}
                    tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                    tickLine={false}
                    axisLine={{ stroke: 'var(--border)' }}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                    tickFormatter={(v: number) => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  />
                  <Tooltip content={tooltip} cursor={{ stroke: 'var(--text-3)', strokeWidth: 1 }} />
                  {PRICE_SERIES.map((ps) => (
                    <Line
                      key={ps.key}
                      type={ps.step ? 'stepAfter' : 'monotone'}
                      dataKey={ps.key}
                      stroke={ps.color}
                      strokeWidth={ps.width}
                      strokeDasharray={ps.dash}
                      dot={false}
                      activeDot={ps.key === 'close' ? { r: 4, stroke: 'var(--surface)', strokeWidth: 2 } : false}
                      isAnimationActive={false}
                      label={endLabel(ps.key, ps.key === 'dma' ? dmaLabel : ps.key === 'ath' ? 'ATH' : ps.label, lastIndex)}
                    />
                  ))}
                  <Line dataKey="buyMark" stroke="none" dot={triangleMarker('up', BUY_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                  <Line dataKey="sellMark" stroke="none" dot={triangleMarker('down', SELL_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          <BacktestStats
            stats={result.stats}
            testStart={result.test_start}
            testEnd={result.test_end}
            barsTested={result.bars_tested}
            note={`₹${p.capital_per_trade.toLocaleString('en-IN')} per trade · no commission`}
            exitsSub={`${result.stats.signal_exits} on DMA break`}
          />
          <EquityCurveCard series={result.series} initialCapital={p.initial_capital} />
          <TradesCard trades={result.trades} subtitle="Newest first. Entries and exits fill at the signal day's close; no commission." />

          <p className="text-[11px] text-wv-text-3 leading-relaxed">
            A backtest replays past prices; it is not a forecast or investment advice. The all-time high depends on how far back
            Kite's data goes and how it adjusts for splits and bonuses, so it can differ from TradingView. Each trade buys
            floor(₹{p.capital_per_trade.toLocaleString('en-IN')} ÷ close) shares regardless of earlier gains or losses.
          </p>
        </>
      )}
    </div>
  )
}
