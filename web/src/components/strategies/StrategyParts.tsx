import React, { useMemo } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { MetricCard } from '../analytics/AnalysisParts'
import { createEndLabelStack } from '../analytics/chartLabels'
import { formatDay, formatINR, formatMonth, formatPct, monthTicks, signedTone } from '../../utils/format'
import type { StrategyStats, StrategyTrade } from '../../types'
import { BUY_COLOR, EQUITY_SERIES, SELL_COLOR, SETUP_FILL, type RangeOption } from './strategyShared'

export const StatTile: React.FC<{ label: string; value: string; tone?: string; sub?: string }> = ({
  label,
  value,
  tone = 'text-wv-text',
  sub,
}) => (
  <div className="bg-wv-surface border border-wv-border rounded-2xl p-4 shadow-sm">
    <div className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">{label}</div>
    <div className={`text-xl font-extrabold font-mono tracking-tight mt-1 ${tone}`}>{value}</div>
    {sub && <div className="text-[11px] text-wv-text-3 mt-0.5">{sub}</div>}
  </div>
)

// Segmented control used for backtest length and chart range
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: Array<{ label: string; value: T }>
  value: T
  onChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <div className="inline-flex rounded-lg border border-wv-border p-0.5 bg-wv-surface-2" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-colors ${
            value === o.value ? 'bg-wv-surface text-wv-text shadow-sm' : 'text-wv-text-3 hover:text-wv-text'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export const RangeToggle: React.FC<{ ranges: RangeOption[]; value: number; onChange: (bars: number) => void }> = ({
  ranges,
  value,
  onChange,
}) => <Segmented options={ranges.map((r) => ({ label: r.label, value: r.bars }))} value={value} onChange={onChange} ariaLabel="Chart range" />

// Collapsible inputs card with an Apply button that re-runs the strategy
export const InputsPanel: React.FC<{ fixedNote: string; onApply: () => void; disabled: boolean; children: React.ReactNode }> = ({
  fixedNote,
  onApply,
  disabled,
  children,
}) => (
  <details className="group text-xs bg-wv-surface border border-wv-border rounded-2xl px-5 py-3 shadow-sm">
    <summary className="cursor-pointer select-none inline-flex items-center gap-1.5 font-semibold text-wv-text-2 hover:text-wv-text">
      <SlidersHorizontal className="w-3.5 h-3.5" /> Strategy inputs
    </summary>
    <div className="mt-3 flex flex-wrap items-end gap-4">
      {children}
      <button
        type="button"
        onClick={onApply}
        disabled={disabled}
        className="px-3.5 py-1.5 bg-wv-text text-wv-bg text-[11px] font-semibold rounded-lg hover:bg-wv-text disabled:opacity-40"
      >
        Apply
      </button>
      <span className="text-[11px] text-wv-text-3 pb-1.5 basis-full">{fixedNote}</span>
    </div>
  </details>
)

export const NumberInput: React.FC<{
  label: string
  value: number
  onChange: (value: number) => void
  step?: number
  min?: number
  disabled?: boolean
  width?: string
}> = ({ label, value, onChange, step = 1, min, disabled, width = 'w-20' }) => (
  <label className="flex flex-col gap-1">
    <span className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3">{label}</span>
    <input
      type="number"
      step={step}
      min={min}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`${width} px-2 py-1.5 rounded-lg border border-wv-border font-mono disabled:opacity-40`}
    />
  </label>
)

// Legend entries for price charts
export const LegendLine: React.FC<{ color: string; label: string; dash?: string }> = ({ color, label, dash }) => (
  <span className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
    <svg width="16" height="4" aria-hidden="true">
      <line x1="0" y1="2" x2="16" y2="2" stroke={color} strokeWidth="2" strokeDasharray={dash} strokeLinecap="round" />
    </svg>
    {label}
  </span>
)

export const LegendSignals: React.FC<{ buyLabel?: string; sellLabel?: string; stopLabel?: string; setupLabel: string }> = ({
  buyLabel = 'BUY',
  sellLabel = 'SELL',
  stopLabel,
  setupLabel,
}) => (
  <>
    <span className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
      <svg width="12" height="12" aria-hidden="true"><polygon points="6,1 1,11 11,11" fill={BUY_COLOR} /></svg>
      {buyLabel}
    </span>
    <span className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
      <svg width="12" height="12" aria-hidden="true"><polygon points="6,11 1,1 11,1" fill={SELL_COLOR} /></svg>
      {sellLabel}
    </span>
    {stopLabel && (
      <span className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
        <svg width="12" height="12" aria-hidden="true" stroke={SELL_COLOR} strokeWidth="2.5" strokeLinecap="round">
          <line x1="2" y1="2" x2="10" y2="10" />
          <line x1="2" y1="10" x2="10" y2="2" />
        </svg>
        {stopLabel}
      </span>
    )}
    <span className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
      <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: SETUP_FILL, opacity: 0.18 }} />
      {setupLabel}
    </span>
  </>
)

export const BacktestStats: React.FC<{
  stats: StrategyStats
  testStart: string
  testEnd: string
  barsTested: number
  note: string
  exitsSub: string
}> = ({ stats, testStart, testEnd, barsTested, note, exitsSub }) => (
  <>
    <div className="flex items-baseline justify-between flex-wrap gap-2">
      <h3 className="text-xs font-bold uppercase tracking-wider text-wv-text-3">
        Backtest · {formatDay(testStart)} – {formatDay(testEnd)}
      </h3>
      <span className="text-[11px] text-wv-text-3">
        {barsTested} trading days · {note}
      </span>
    </div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatTile
        label="Net return"
        value={formatPct(stats.net_profit_pct)}
        tone={signedTone(stats.net_profit_pct)}
        sub={`Buy & hold ${formatPct(stats.buy_hold_return_pct)}`}
      />
      <StatTile label="CAGR" value={formatPct(stats.cagr_pct)} tone={signedTone(stats.cagr_pct)} sub={formatINR(stats.final_equity)} />
      <StatTile label="Max drawdown" value={formatPct(stats.max_drawdown_pct)} tone="text-wv-loss" sub="Peak-to-trough equity" />
      <StatTile
        label="Win rate"
        value={stats.win_rate_pct != null ? `${stats.win_rate_pct.toFixed(1)}%` : '—'}
        sub={`Avg win ${formatPct(stats.avg_win_pct)} · loss ${formatPct(stats.avg_loss_pct)}`}
      />
      <StatTile label="Profit factor" value={stats.profit_factor != null ? stats.profit_factor.toFixed(2) : '—'} sub="Gross profit ÷ gross loss" />
      <StatTile label="Closed trades" value={String(stats.total_trades)} sub={exitsSub + (stats.open_trade ? ' · 1 open' : '')} />
      <StatTile
        label="Avg hold"
        value={stats.avg_bars_held != null ? `${stats.avg_bars_held.toFixed(0)} days` : '—'}
        sub="Trading days per trade"
      />
      <StatTile label="Time in market" value={`${stats.exposure_pct.toFixed(0)}%`} sub="Share of days holding" />
    </div>
  </>
)

type EquityPoint = { date: string; equity: number; buy_hold: number }

const renderEquityTooltip = (props: any) => {
  const { active, payload, label } = props
  if (!active || !payload || payload.length === 0) return null
  const bar: EquityPoint = payload[0].payload
  return (
    <div className="bg-wv-surface rounded-xl border border-wv-border px-3.5 py-3 shadow-xl min-w-[180px]">
      <div className="text-[11px] font-bold text-wv-text mb-2">{formatDay(label)}</div>
      {EQUITY_SERIES.map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-5 text-[11px]">
          <span className="flex items-center gap-1.5 text-wv-text-3">
            <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
          <strong className="font-mono text-wv-text">{formatINR(bar[s.key])}</strong>
        </div>
      ))}
    </div>
  )
}

export const EquityCurveCard: React.FC<{ series: EquityPoint[]; initialCapital: number }> = ({ series, initialCapital }) => {
  const ticks = useMemo(() => monthTicks(series.map((b) => b.date)), [series])
  const endLabel = createEndLabelStack(EQUITY_SERIES.map((s) => s.key))
  return (
    <MetricCard title="Equity curve" subtitle="Strategy vs buying and holding over the same period">
      <div className="flex items-center gap-4">
        {EQUITY_SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-[11px] font-medium text-wv-text-2">
            <span className="w-4 h-0.5 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 8, right: 80, bottom: 0, left: 0 }}>
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
              width={64}
              tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
            />
            <ReferenceLine y={initialCapital} stroke="var(--border-strong)" strokeDasharray="3 3" />
            <Tooltip content={renderEquityTooltip} cursor={{ stroke: 'var(--text-3)', strokeWidth: 1 }} />
            {EQUITY_SERIES.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: 'var(--surface)', strokeWidth: 2 }}
                isAnimationActive={false}
                label={endLabel(s.key, s.label, series.length - 1)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </MetricCard>
  )
}

const EXIT_STYLES: Record<StrategyTrade['exit_reason'], { label: string; cls: string }> = {
  'UT + EMA20 SELL': { label: 'UT + EMA20', cls: 'bg-wv-surface-2 text-wv-text-2' },
  'ATR STOP': { label: 'ATR stop', cls: 'bg-wv-loss-weak text-wv-loss' },
  '200DMA BREAK': { label: 'Below 200-DMA', cls: 'bg-wv-surface-2 text-wv-text-2' },
  OPEN: { label: 'Open', cls: 'bg-wv-accent-weak text-wv-accent' },
}

export const TradesCard: React.FC<{ trades: StrategyTrade[]; subtitle: string }> = ({ trades, subtitle }) => {
  const newestFirst = useMemo(() => [...trades].reverse(), [trades])
  return (
    <MetricCard title="Trades" subtitle={subtitle}>
      {newestFirst.length === 0 ? (
        <p className="text-xs text-wv-text-3">No trades in this period: the entry conditions never lined up.</p>
      ) : (
        <div className="overflow-x-auto -mx-5 px-5">
          <table className="w-full text-xs min-w-[720px]">
            <thead>
              <tr className="text-[10px] font-bold uppercase tracking-wider text-wv-text-3 text-left">
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
              {newestFirst.map((t) => {
                const style = EXIT_STYLES[t.exit_reason]
                return (
                  <tr key={`${t.entry_date}-${t.exit_date}`} className="border-t border-wv-border">
                    <td className="py-2 pr-3 font-mono text-wv-text-2">{t.entry_date}</td>
                    <td className="py-2 pr-3 font-mono text-right text-wv-text">{formatINR(t.entry_price)}</td>
                    <td className="py-2 pr-3 font-mono text-wv-text-2">{t.exit_date ?? '—'}</td>
                    <td className="py-2 pr-3 font-mono text-right text-wv-text">{t.exit_price != null ? formatINR(t.exit_price) : '—'}</td>
                    <td className="py-2 pr-3">
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${style.cls}`}>{style.label}</span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-right text-wv-text-2">{t.quantity}</td>
                    <td className={`py-2 pr-3 font-mono text-right font-semibold ${signedTone(t.pnl)}`}>
                      {t.pnl >= 0 ? '+' : ''}
                      {formatINR(t.pnl)}
                    </td>
                    <td className={`py-2 pr-3 font-mono text-right font-semibold ${signedTone(t.pnl_pct)}`}>{formatPct(t.pnl_pct)}</td>
                    <td className="py-2 font-mono text-right text-wv-text-2">{t.bars_held}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </MetricCard>
  )
}

// Status badge with icon + label (never color alone)
export const StatusBadge: React.FC<{ text: string; cls: string; Icon: React.ElementType }> = ({ text, cls, Icon }) => (
  <span className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl border text-sm font-bold ${cls}`}>
    <Icon className="w-4 h-4" />
    {text}
  </span>
)
