import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDown, ArrowUp, ArrowUpRight, CheckCircle2, CircleDot, Clock, Minus, Star, XCircle } from 'lucide-react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { AnalysisErrorCard, LoadingState, MetricRow } from '../analytics/AnalysisParts'
import { createEndLabelStack, triangleMarker } from '../analytics/chartLabels'
import { useAnalysisRequest } from '../analytics/useAnalysisRequest'
import { addToWatchlist, fetchSupertrendStrategy, fetchWatchlist, removeFromWatchlist } from '../../utils/api'
import { formatDay, formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../../utils/format'
import type { SupertrendBar, SupertrendResult, WatchlistItem } from '../../types'
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
import { BUY_COLOR, SELL_COLOR, sliceRange, type RangeOption } from './strategyShared'
import { useStrategyRun, type StrategyPanelProps } from './useStrategyRun'

const SUPERTREND_SERIES = [
  { key: 'close', label: 'Close', color: 'var(--text)', width: 1.5, dash: undefined, step: false },
  { key: 'supertrend', label: 'Supertrend', color: '#10b981', width: 2, dash: undefined, step: false },
] as const

const RANGES: RangeOption[] = [
  { label: '1Y', bars: 252 },
  { label: '3Y', bars: 756 },
  { label: '5Y', bars: 1260 },
  { label: 'All', bars: 0 },
]

type ChartBar = SupertrendBar & { buyMark: number | null; sellMark: number | null }

const makeTooltip = (factor: number, atrPeriod: number) => (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: ChartBar = payload[0].payload
  const signal = bar.buy ? 'BUY at close' : bar.sell ? 'SELL at close' : null
  const isBullish = bar.direction < 0

  return (
    <div className="bg-wv-surface rounded-xl border border-wv-border px-3.5 py-3 shadow-xl min-w-[200px]">
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="text-[11px] font-bold text-wv-text">{formatDay(label)}</span>
        {signal && (
          <span
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
              bar.buy ? 'bg-wv-gain-weak text-wv-gain' : 'bg-wv-loss-weak text-wv-loss'
            }`}
          >
            {signal}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-5 text-[11px]">
          <span className="flex items-center gap-1.5 text-wv-text-3">
            <span className="w-2.5 h-0.5 rounded-full bg-wv-text" />
            Close
          </span>
          <strong className="font-mono text-wv-text">{formatINR(bar.close)}</strong>
        </div>
        <div className="flex items-center justify-between gap-5 text-[11px]">
          <span className="flex items-center gap-1.5 text-wv-text-3">
            <span
              className="w-2.5 h-0.5 rounded-full"
              style={{ backgroundColor: isBullish ? '#10b981' : '#ef4444' }}
            />
            {`Supertrend (${factor}, ${atrPeriod})`}
          </span>
          <strong className="font-mono text-wv-text">{formatINR(bar.supertrend)}</strong>
        </div>
        {bar.adx != null && (
          <div className="flex items-center justify-between gap-5 text-[11px]">
            <span className="text-wv-text-3">ADX (14)</span>
            <strong className="font-mono text-wv-text">{bar.adx.toFixed(1)}</strong>
          </div>
        )}
        <div className="flex items-center justify-between gap-5 text-[11px] pt-1 mt-1 border-t border-wv-border">
          <span className="text-wv-text-3">Trend Status</span>
          <strong className={isBullish ? 'text-wv-gain' : 'text-wv-loss'}>
            {isBullish ? 'Bullish (Support)' : 'Bearish (Resistance)'}
          </strong>
        </div>
      </div>
    </div>
  )
}

const statusBadge = (r: SupertrendResult) => {
  const s = r.status
  if (s.last_signal === 'BUY')
    return { text: 'Bought today', cls: 'bg-wv-gain-weak text-wv-gain border-wv-gain', Icon: ArrowUp }
  if (s.last_signal === 'SELL')
    return { text: 'Sold today', cls: 'bg-wv-loss-weak text-wv-loss border-wv-loss', Icon: ArrowDown }
  if (s.state === 'IN_POSITION')
    return { text: 'In position', cls: 'bg-wv-accent-weak text-wv-accent border-wv-accent', Icon: CircleDot }
  if (s.direction < 0)
    return { text: 'Bullish cloud', cls: 'bg-wv-gain-weak text-wv-gain border-wv-gain', Icon: Clock }
  return { text: 'Bearish / Flat', cls: 'bg-wv-surface-2 text-wv-text-2 border-wv-border', Icon: Minus }
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
      <div className="text-[11px] text-wv-text-3">{detail}</div>
    </div>
  </div>
)

export const SupertrendPanel: React.FC<StrategyPanelProps> = (props) => {
  const { run, loading, error, authUrl, data: result } = useAnalysisRequest<SupertrendResult>()
  const [range, setRange] = useState<number>(0)
  const [startDate, setStartDate] = useState('2015-01-01')
  const [atrPeriod, setAtrPeriod] = useState(10)
  const [factor, setFactor] = useState(3.0)
  const [adxThreshold, setAdxThreshold] = useState(20)
  const [maxBarsAfterFlip, setMaxBarsAfterFlip] = useState(5)
  const [capital, setCapital] = useState(50000)

  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])
  const [watchLoading, setWatchLoading] = useState(false)
  const [watchlistToast, setWatchlistToast] = useState<string | null>(null)

  useEffect(() => {
    fetchWatchlist()
      .then((res) => setWatchlist(res.items || []))
      .catch(() => {})
  }, [])

  const isWatched = useMemo(() => {
    if (!result?.instrument) return false
    const clean = result.instrument.toUpperCase()
    return watchlist.some((w) => w.symbol.toUpperCase() === clean)
  }, [result?.instrument, watchlist])

  const showToast = (msg: string) => {
    setWatchlistToast(msg)
    setTimeout(() => setWatchlistToast(null), 3000)
  }

  const toggleWatch = async () => {
    if (!result?.instrument || watchLoading) return
    const targetSymbol = result.instrument
    const currentlyWatched = isWatched

    if (currentlyWatched) {
      setWatchlist((prev) => prev.filter((w) => w.symbol.toUpperCase() !== targetSymbol.toUpperCase()))
      showToast(`Removed ${targetSymbol} from Watchlist`)
    } else {
      const optimisticItem: WatchlistItem = {
        symbol: targetSymbol,
        name: result.name || targetSymbol,
        notes: result.status?.headline ? `Supertrend: ${result.status.headline}` : 'Supertrend Strategy',
        target_price: null,
        price_when_added: result.status?.entry_price || null,
        added_at: new Date().toISOString(),
        last_price: result.live_price || null,
        pct_since_added: 0,
        trend_verdict: null,
        trend_score: null,
        signal_state: result.status?.state || null,
      }
      setWatchlist((prev) => [optimisticItem, ...prev])
      showToast(`Added ${targetSymbol} to Watchlist`)
    }

    setWatchLoading(true)
    try {
      if (currentlyWatched) {
        await removeFromWatchlist(targetSymbol)
      } else {
        await addToWatchlist(targetSymbol, {
          name: result.name || undefined,
          notes: result.status?.headline ? `Supertrend: ${result.status.headline}` : 'Supertrend Strategy',
        })
      }
      const res = await fetchWatchlist()
      setWatchlist(res.items || [])
    } catch (e: any) {
      console.error('Watchlist toggle error:', e)
      showToast(`Failed: ${e?.message || 'Could not update watchlist'}`)
      const res = await fetchWatchlist().catch(() => null)
      if (res) setWatchlist(res.items || [])
    } finally {
      setWatchLoading(false)
    }
  }

  const execute = (symbol: string) =>
    run(() =>
      fetchSupertrendStrategy(symbol, {
        start_date: /^\d{4}-\d{2}-\d{2}$/.test(startDate) ? startDate : '2015-01-01',
        atr_period: Math.max(1, Math.round(atrPeriod) || 10),
        factor: Number(factor) || 3.0,
        adx_threshold: Number(adxThreshold) || 20.0,
        max_bars_after_flip: Math.max(1, Math.round(maxBarsAfterFlip) || 5),
        capital_per_trade: Math.max(1000, capital || 50000),
      })
    )
  useStrategyRun(props, execute, loading, result?.instrument)

  const chartData: ChartBar[] = useMemo(() => {
    if (!result) return []
    return sliceRange(result.series as any, range).map((b: any) => ({
      ...b,
      buyMark: b.buy ? b.close * 0.96 : null,
      sellMark: b.sell ? b.high * 1.04 : null,
    }))
  }, [result, range])

  const ticks = useMemo(() => monthTicks(chartData.map((b) => b.date)), [chartData])
  const lastIndex = chartData.length - 1
  const endLabel = createEndLabelStack(SUPERTREND_SERIES.map((s) => s.key))
  const badge = result ? statusBadge(result) : null
  const p = result?.params
  const s = result?.status
  const tooltip = useMemo(() => makeTooltip(p?.factor || 3.0, p?.atr_period || 10), [p?.factor, p?.atr_period])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <p className="text-xs text-wv-text-3">
          Asymmetric momentum strategy: buys when the Supertrend turns green with confirmed ADX trend strength and high volume;
          exits immediately on any Supertrend breakdown to protect capital.
        </p>
        <InputsPanel
          onApply={() => props.symbol && execute(props.symbol)}
          disabled={loading || !props.symbol}
          fixedNote="Asymmetric execution: strict filtered entry, zero-filter instant exit · capital per trade does not compound"
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
          <NumberInput label="ATR Period" value={atrPeriod} onChange={setAtrPeriod} min={1} />
          <NumberInput label="ATR Multiplier" value={factor} onChange={setFactor} min={0.5} step={0.1} />
          <NumberInput label="Min ADX" value={adxThreshold} onChange={setAdxThreshold} min={0} />
          <NumberInput
            label="Max Bars After Flip"
            value={maxBarsAfterFlip}
            onChange={setMaxBarsAfterFlip}
            min={1}
            width="w-24"
          />
          <NumberInput label="Capital / trade ₹" value={capital} onChange={setCapital} step={1000} min={1000} width="w-28" />
        </InputsPanel>
      </div>

      {loading && <LoadingState message="Calculating Supertrend, ADX, volume momentum, and running backtest…" />}

      {!loading && error && (
        <AnalysisErrorCard
          error={error}
          authUrl={authUrl}
          title="Could not run the Supertrend strategy"
          onRetry={props.symbol ? () => execute(props.symbol as string) : undefined}
        />
      )}

      {!loading && !error && !result && (
        <div className="bg-wv-surface border border-dashed border-wv-border-strong rounded-2xl p-10 text-center">
          <p className="text-sm font-semibold text-wv-text-2">Enter a stock to run the Supertrend strategy</p>
          <p className="mt-1 text-xs text-wv-text-3">Calculates 10-ATR Supertrend, 14-ADX momentum, and 20-day Volume SMA.</p>
        </div>
      )}

      {!loading && result && badge && p && s && (
        <>
          {/* Current status */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-xs font-bold px-2 py-0.5 rounded-md bg-wv-surface-2 text-wv-text-2">
                  {result.instrument}
                </span>
                <button
                  type="button"
                  onClick={toggleWatch}
                  disabled={watchLoading}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition-all shadow-sm active:scale-95 cursor-pointer ${
                    isWatched
                      ? 'bg-amber-500/15 text-amber-500 border-amber-500/40 hover:bg-amber-500/25'
                      : 'bg-wv-surface-2 text-wv-text-2 border-wv-border hover:text-wv-text hover:border-wv-border-strong'
                  }`}
                  title={isWatched ? 'Remove from Watchlist' : 'Add to Watchlist'}
                >
                  <Star className={`w-3.5 h-3.5 ${isWatched ? 'fill-amber-500 text-amber-500' : 'text-wv-text-3'}`} />
                  <span>{isWatched ? 'Watching' : 'Watch'}</span>
                  {watchLoading && (
                    <span className="w-2.5 h-2.5 border-2 border-current border-t-transparent rounded-full animate-spin ml-0.5" />
                  )}
                </button>
                {watchlistToast && (
                  <span className="text-[11px] font-medium text-amber-500 bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 rounded-full">
                    {watchlistToast}
                  </span>
                )}
                <span className="text-[11px] text-wv-text-3">as of {result.as_of} close</span>
                <Link
                  to={`/momentum?symbol=${encodeURIComponent(result.instrument)}`}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-wv-text-2 hover:text-wv-text"
                >
                  Momentum view <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              </div>
              <h2 className="font-serif text-2xl text-wv-text font-semibold tracking-tight">
                {result.name || result.instrument}
              </h2>
              <div className="flex items-center gap-3 flex-wrap">
                <StatusBadge {...badge} />
                <span className="text-sm font-semibold text-wv-text">{s.headline}</span>
              </div>
              <p className="text-xs text-wv-text-2 leading-relaxed">{s.detail}</p>
              {result.live_bar && (
                <p className="text-[11px] text-wv-warn bg-wv-warn-weak border border-wv-warn rounded-lg px-2.5 py-1.5 self-start">
                  Today's bar uses the live price ({formatINR(result.live_price)}), so the signal can change until the 3:30 pm close.
                </p>
              )}
              {result.partial_bar_excluded && (
                <p className="text-[11px] text-wv-warn bg-wv-warn-weak border border-wv-warn rounded-lg px-2.5 py-1.5 self-start">
                  Live price unavailable, so today's forming candle is left out. Signals use completed days only.
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
                <MetricRow
                  label="Supertrend"
                  value={`${formatINR(s.supertrend)} (${s.direction < 0 ? 'Support' : 'Resistance'})`}
                />
                <MetricRow label="ADX (14)" value={s.adx != null ? `${s.adx.toFixed(1)}` : '—'} />
                <MetricRow
                  label="Volume Ratio"
                  value={s.volume_ratio != null ? `${s.volume_ratio}x avg` : '—'}
                  tone={s.volume_ratio && s.volume_ratio >= 1.0 ? 'text-wv-gain' : undefined}
                />
              </div>
            </div>

            <div className="flex flex-col gap-2.5 lg:border-l lg:border-wv-border lg:pl-6">
              {s.state === 'IN_POSITION' ? (
                <>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Exit rule</h3>
                  <Check
                    passed={s.direction < 0}
                    label="Holding above Supertrend Support"
                    detail={`Exit immediately if close falls below ${formatINR(s.supertrend)}`}
                  />
                </>
              ) : (
                <>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">Entry rules</h3>
                  <Check
                    passed={s.direction < 0}
                    label="Supertrend Bullish (Green Support)"
                    detail={
                      s.direction < 0
                        ? `Support at ${formatINR(s.supertrend)} (${s.bars_since_flip != null ? `${s.bars_since_flip}d into flip` : ''})`
                        : `Bearish resistance at ${formatINR(s.supertrend)}`
                    }
                  />
                  <Check
                    passed={s.adx != null && s.adx >= p.adx_threshold}
                    label={`ADX >= ${p.adx_threshold} (Trend Strength)`}
                    detail={s.adx != null ? `Current ADX: ${s.adx.toFixed(1)}` : 'Calculating ADX'}
                  />
                  <Check
                    passed={s.volume_ratio != null && s.volume_ratio >= 1.0}
                    label="Volume > 20-day Average"
                    detail={s.volume_ratio != null ? `${s.volume_ratio}x of 20 SMA` : 'Calculating volume'}
                  />
                  <div
                    className={`text-xs font-bold mt-1 ${
                      s.direction < 0 && (s.adx ?? 0) >= p.adx_threshold && (s.volume_ratio ?? 0) >= 1.0
                        ? 'text-wv-gain'
                        : 'text-wv-text-3'
                    }`}
                  >
                    {s.direction < 0 && (s.adx ?? 0) >= p.adx_threshold && (s.volume_ratio ?? 0) >= 1.0
                      ? 'Setup ready: Buy condition met'
                      : 'Waiting for trend & volume confluence'}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Strategy KPIs */}
          <BacktestStats
            stats={result.stats}
            testStart={result.test_start}
            testEnd={result.test_end}
            barsTested={result.bars_tested}
            note={`₹${p.capital_per_trade.toLocaleString('en-IN')} per trade · no commission`}
            exitsSub={`${result.stats.signal_exits} on Supertrend flip`}
          />

          {/* Supertrend Chart */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 className="font-serif text-lg font-semibold text-wv-text">Supertrend Price & Signals</h3>
                <p className="text-xs text-wv-text-3">
                  Green line indicates Supertrend dynamic trailing support. Green triangles are BUY entries, red triangles are exits.
                </p>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <RangeToggle ranges={RANGES} value={range} onChange={setRange} />
              </div>
            </div>

            <div className="flex items-center gap-4 flex-wrap text-xs text-wv-text-3 border-y border-wv-border py-2">
              <LegendLine color="var(--text)" label="Close" />
              <LegendLine color="#10b981" label={`Supertrend Support (${p.factor}, ${p.atr_period})`} />
              <LegendSignals setupLabel="Supertrend Support" />
            </div>

            <div className="h-[360px] sm:h-[420px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 12, right: 30, bottom: 8, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    ticks={ticks}
                    tickFormatter={(d: string) => formatMonth(d)}
                    stroke="var(--text-3)"
                    fontSize={11}
                    tickLine={false}
                  />
                  <YAxis
                    domain={['auto', 'auto']}
                    orientation="right"
                    stroke="var(--text-3)"
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v: number) => formatINR(v)}
                    width={70}
                  />
                  <Tooltip content={tooltip} />
                  <Line
                    type="monotone"
                    dataKey="close"
                    stroke="var(--text)"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                    label={endLabel('close', 'Close', lastIndex)}
                  />
                  <Line
                    type="stepAfter"
                    dataKey="supertrend"
                    stroke="#10b981"
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                    label={endLabel('supertrend', 'Supertrend', lastIndex)}
                  />
                  <Line
                    dataKey="buyMark"
                    stroke="none"
                    dot={triangleMarker('up', BUY_COLOR)}
                    activeDot={false}
                    isAnimationActive={false}
                    legendType="none"
                  />
                  <Line
                    dataKey="sellMark"
                    stroke="none"
                    dot={triangleMarker('down', SELL_COLOR)}
                    activeDot={false}
                    isAnimationActive={false}
                    legendType="none"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Equity Curve */}
          <div className="bg-wv-surface border border-wv-border rounded-2xl p-5 sm:p-6 shadow-sm flex flex-col gap-4">
            <div>
              <h3 className="font-serif text-lg font-semibold text-wv-text">Equity Curve vs Buy & Hold</h3>
              <p className="text-xs text-wv-text-3">
                Starting capital of ₹{p.initial_capital.toLocaleString('en-IN')}, buying ₹{p.capital_per_trade.toLocaleString('en-IN')} per trade.
              </p>
            </div>
            <EquityCurveCard series={result.series} initialCapital={p.initial_capital} />
          </div>

          {/* Trades Table */}
          <TradesCard trades={result.trades} subtitle="Newest first. Entries and exits fill at the signal day's close; no commission." />
        </>
      )}
    </div>
  )
}

export default SupertrendPanel
