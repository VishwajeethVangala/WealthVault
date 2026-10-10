import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, ArrowUpRight, CheckCircle2, CircleDot, Clock, Minus, XCircle } from 'lucide-react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AnalysisErrorCard, LoadingState, MetricRow } from '../analytics/AnalysisParts'
import { createEndLabelStack, crossMarker, triangleMarker } from '../analytics/chartLabels'
import { useAnalysisRequest } from '../analytics/useAnalysisRequest'
import { fetchSwingStrategy } from '../../utils/api'
import { formatDay, formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../../utils/format'
import type { StrategyBar, SwingStrategyResult } from '../../types'
import {
  BacktestStats,
  EquityCurveCard,
  InputsPanel,
  LegendLine,
  LegendSignals,
  NumberInput,
  RangeToggle,
  Segmented,
  StatusBadge,
  TradesCard,
} from './StrategyParts'
import { BUY_COLOR, SELL_COLOR, SETUP_FILL, booleanSpans, sliceRange, type RangeOption } from './strategyShared'
import { useStrategyRun, type StrategyPanelProps } from './useStrategyRun'

// Close is the subject (neutral ink); three validated categorical hues for the averages;
// the UT stop is a level, drawn as a neutral dotted step line
const PRICE_SERIES = [
  { key: 'close', label: 'Close', color: 'var(--text)', width: 1.5, dash: undefined, step: false },
  { key: 'sma_fast', label: '50-SMA', color: 'var(--accent)', width: 2, dash: undefined, step: false },
  { key: 'sma_slow', label: '200-SMA', color: 'var(--warn)', width: 2, dash: undefined, step: false },
  { key: 'exit_ema', label: '20-EMA', color: 'var(--gain)', width: 1.5, dash: '5 3', step: false },
  { key: 'ut_stop', label: 'UT stop', color: 'var(--text-3)', width: 1.5, dash: '2 3', step: true },
] as const

const RANGES: RangeOption[] = [
  { label: '6M', bars: 126 },
  { label: '1Y', bars: 252 },
  { label: '2Y', bars: 504 },
  { label: 'All', bars: 0 },
]

type ChartBar = StrategyBar & { buyMark: number | null; sellMark: number | null; stopMark: number | null }

const renderPriceTooltip = (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: ChartBar = payload[0].payload
  const signal = bar.buy ? 'BUY signal' : bar.sell ? 'SELL signal' : bar.stop_exit ? 'Stop exit' : null
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
              {s.label}
            </span>
            <strong className="font-mono text-wv-text">{formatINR(bar[s.key as keyof StrategyBar] as number | null)}</strong>
          </div>
        ))}
        <div className="flex items-center justify-between gap-5 text-[11px] pt-1 mt-1 border-t border-wv-border">
          <span className="text-wv-text-3">Regime</span>
          <strong className={bar.regime ? 'text-wv-gain' : 'text-wv-text-3'}>{bar.regime ? 'Bullish' : 'Not bullish'}</strong>
        </div>
        {bar.stop_level != null && (
          <div className="flex items-center justify-between gap-5 text-[11px]">
            <span className="text-wv-text-3">Protective stop</span>
            <strong className="font-mono text-wv-text">{formatINR(bar.stop_level)}</strong>
          </div>
        )}
      </div>
    </div>
  )
}

const statusBadge = (r: SwingStrategyResult) => {
  const s = r.status
  if (s.pending_order === 'BUY') return { text: 'BUY signal', cls: 'bg-wv-gain-weak text-wv-gain border-wv-gain', Icon: ArrowUp }
  if (s.pending_order === 'SELL') return { text: 'SELL signal', cls: 'bg-wv-loss-weak text-wv-loss border-wv-loss', Icon: ArrowDown }
  if (s.state === 'IN_POSITION') return { text: 'In position', cls: 'bg-wv-accent-weak text-wv-accent border-wv-accent', Icon: CircleDot }
  if (s.regime_bullish) return { text: 'Waiting for entry', cls: 'bg-wv-warn-weak text-wv-warn border-wv-warn', Icon: Clock }
  return { text: 'No trade', cls: 'bg-wv-surface-2 text-wv-text-2 border-wv-border', Icon: Minus }
}

export const SwingV21Panel: React.FC<StrategyPanelProps> = (props) => {
  const [years, setYears] = useState(5)
  const [utKey, setUtKey] = useState(1.0)
  const [utAtrPeriod, setUtAtrPeriod] = useState(10)
  const [useStop, setUseStop] = useState(true)
  const [stopMult, setStopMult] = useState(2.0)
  const [range, setRange] = useState(252)
  const { data: result, loading, error, authUrl, run } = useAnalysisRequest<SwingStrategyResult>()

  const execute = (symbol: string) =>
    run(() =>
      fetchSwingStrategy(symbol, {
        years,
        ut_key: utKey > 0 ? utKey : 1,
        ut_atr_period: Math.max(1, Math.round(utAtrPeriod) || 10),
        use_stop: useStop,
        stop_atr_mult: stopMult > 0 ? stopMult : 2,
      })
    )
  useStrategyRun(props, execute, loading, result?.instrument)

  const chartData: ChartBar[] = useMemo(() => {
    if (!result) return []
    const stopFills = new Map(
      result.trades.filter((t) => t.exit_reason === 'ATR STOP' && t.exit_date).map((t) => [t.exit_date as string, t.exit_price])
    )
    return sliceRange(result.series, range).map((b) => ({
      ...b,
      buyMark: b.buy ? b.low * 0.975 : null,
      sellMark: b.sell ? b.high * 1.025 : null,
      stopMark: b.stop_exit ? stopFills.get(b.date) ?? b.low : null,
    }))
  }, [result, range])

  const spans = useMemo(() => booleanSpans(chartData, (b) => b.regime), [chartData])
  const priceTicks = useMemo(() => monthTicks(chartData.map((b) => b.date)), [chartData])
  const lastIndex = chartData.length - 1
  const priceLabel = createEndLabelStack(PRICE_SERIES.map((s) => s.key))
  const badge = result ? statusBadge(result) : null
  const p = result?.params

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-wv-text-3">
          Long-only daily swing strategy. Buys a UT Bot cross-up while the 50/200-SMA trend filter is bullish; exits on a UT Bot
          flip with a close under the 20-EMA, or at a fixed 2×ATR(14) protective stop. Orders fill at the next open.
        </p>
        <InputsPanel
          onApply={() => props.symbol && execute(props.symbol)}
          disabled={loading || !props.symbol}
          fixedNote="Fixed: 50/200-SMA · 20-bar slope · 20-EMA exit · ATR(14) stop · ₹1,00,000 · 0.10% commission · 1 tick slippage"
        >
          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">Backtest</span>
            <Segmented
              options={[1, 2, 3, 5].map((y) => ({ label: `${y}Y`, value: y }))}
              value={years}
              onChange={setYears}
              ariaLabel="Backtest length"
            />
          </label>
          <NumberInput label="UT key" value={utKey} onChange={setUtKey} step={0.1} min={0.1} />
          <NumberInput label="UT ATR period" value={utAtrPeriod} onChange={setUtAtrPeriod} min={1} />
          <NumberInput label="Stop ATR ×" value={stopMult} onChange={setStopMult} step={0.1} min={0.1} disabled={!useStop} />
          <label className="flex items-center gap-2 pb-1.5">
            <input type="checkbox" checked={useStop} onChange={(e) => setUseStop(e.target.checked)} className="accent-slate-900" />
            <span className="font-medium text-wv-text-2">ATR protective stop</span>
          </label>
        </InputsPanel>
      </div>

      {loading && <LoadingState message={`Fetching ${years} year${years > 1 ? 's' : ''} of daily prices and running the backtest…`} />}

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
          <p className="mt-1 text-xs text-wv-text-3">Shows today's status, signals on the chart, and a backtest of every past trade.</p>
        </div>
      )}

      {!loading && result && badge && p && (
        <>
          {/* Current status */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-md bg-wv-surface-2 text-wv-text-2">{result.instrument}</span>
                <span className="text-[11px] text-wv-text-3">signals as of {result.as_of} close</span>
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
                <span className="text-sm font-semibold text-wv-text">{result.status.headline}</span>
              </div>
              <p className="text-xs text-wv-text-2 leading-relaxed">{result.status.detail}</p>
              {result.partial_bar_excluded && (
                <p className="text-[11px] text-wv-warn bg-wv-warn-weak border border-wv-warn rounded-lg px-2.5 py-1.5 self-start">
                  Today's candle is still forming, so it's excluded until the 3:30 pm close. Signals use completed days only.
                </p>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6">
                {result.status.state === 'IN_POSITION' && (
                  <>
                    <MetricRow label="Entry" value={formatINR(result.status.entry_price)} />
                    <MetricRow label="Entry date" value={result.status.entry_date ?? '—'} />
                    <MetricRow label="Unrealized" value={formatPct(result.status.unrealized_pct)} tone={signedTone(result.status.unrealized_pct)} />
                    <MetricRow label="Protective stop" value={p.use_stop ? formatINR(result.status.stop_price) : 'Off'} />
                    <MetricRow label="Days held" value={String(result.status.bars_held ?? '—')} />
                  </>
                )}
                <MetricRow label="Last close" value={formatINR(result.series[result.series.length - 1]?.close)} />
                <MetricRow label="UT stop" value={formatINR(result.status.ut_stop)} />
                <MetricRow label="20-EMA" value={formatINR(result.status.exit_ema)} />
              </div>
            </div>

            <div className="flex flex-col gap-2.5 lg:border-l lg:border-wv-border lg:pl-6">
              <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Trend filter</h3>
              {result.status.regime_checks.map((c) => (
                <div key={c.key} className="flex items-start gap-2.5">
                  {c.passed ? (
                    <CheckCircle2 className="w-4 h-4 text-wv-gain shrink-0 mt-0.5" aria-label="Pass" />
                  ) : (
                    <XCircle className="w-4 h-4 text-wv-loss shrink-0 mt-0.5" aria-label="Fail" />
                  )}
                  <div>
                    <div className="text-xs font-semibold text-wv-text">{c.label}</div>
                    <div className="text-[11px] text-wv-text-3 font-mono">{c.detail}</div>
                  </div>
                </div>
              ))}
              <div className={`text-xs font-bold mt-1 ${result.status.regime_bullish ? 'text-wv-gain' : 'text-wv-text-3'}`}>
                {result.status.regime_bullish ? 'Bullish regime: entries allowed' : 'Not bullish: no new entries'}
              </div>
            </div>
          </div>

          {/* Price chart with signals */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 shadow-sm flex flex-col gap-3">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Price, indicators & signals</h3>
              <RangeToggle ranges={RANGES} value={range} onChange={setRange} />
            </div>
            <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap">
              {PRICE_SERIES.map((s) => (
                <LegendLine key={s.key} color={s.color} label={s.label} dash={s.dash} />
              ))}
              <LegendSignals stopLabel="Stop exit" setupLabel="Bullish regime" />
            </div>
            <div className="h-[380px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
                  {spans.map((s) => (
                    <ReferenceArea key={s.x1} x1={s.x1} x2={s.x2} fill={SETUP_FILL} fillOpacity={0.08} stroke="none" ifOverflow="hidden" />
                  ))}
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis
                    dataKey="date"
                    ticks={priceTicks}
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
                  <Tooltip content={renderPriceTooltip} cursor={{ stroke: 'var(--text-3)', strokeWidth: 1 }} />
                  {result.status.state === 'IN_POSITION' && p.use_stop && result.status.stop_price != null && (
                    <ReferenceLine
                      y={result.status.stop_price}
                      stroke={SELL_COLOR}
                      strokeDasharray="6 4"
                      strokeWidth={1.5}
                      label={{ value: `Stop ${formatINR(result.status.stop_price)}`, position: 'insideBottomLeft', fontSize: 10, fill: 'var(--loss)' }}
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
                      activeDot={s.key === 'close' ? { r: 4, stroke: 'var(--surface)', strokeWidth: 2 } : false}
                      isAnimationActive={false}
                      label={s.key === 'ut_stop' ? undefined : priceLabel(s.key, s.label, lastIndex)}
                    />
                  ))}
                  <Line dataKey="buyMark" stroke="none" dot={triangleMarker('up', BUY_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                  <Line dataKey="sellMark" stroke="none" dot={triangleMarker('down', SELL_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                  <Line dataKey="stopMark" stroke="none" dot={crossMarker(SELL_COLOR)} activeDot={false} isAnimationActive={false} legendType="none" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          <BacktestStats
            stats={result.stats}
            testStart={result.test_start}
            testEnd={result.test_end}
            barsTested={result.bars_tested}
            note={`₹${p.initial_capital.toLocaleString('en-IN')} start · ${p.commission_pct}% commission`}
            exitsSub={`${result.stats.signal_exits} signal · ${result.stats.stop_exits} stop`}
          />
          <EquityCurveCard series={result.series} initialCapital={p.initial_capital} />
          <TradesCard trades={result.trades} subtitle="Newest first. Entry and exit prices include 1 tick of slippage; P&L is after commission." />

          <p className="text-[11px] text-wv-text-3 leading-relaxed">
            A backtest replays past prices; it is not a forecast or investment advice. Results can differ from TradingView because
            of price-adjustment differences in the data, and because this port sizes positions in whole shares bought at the fill
            price. Note the script only exits on a UT Bot flip that closes under the 20-EMA on the same day; otherwise the fixed
            protective stop is the only exit.
          </p>
        </>
      )}
    </div>
  )
}
