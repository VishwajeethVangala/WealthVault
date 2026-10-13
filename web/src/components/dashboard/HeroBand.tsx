import React, { useMemo, useRef, useState } from 'react'
import type { HistoryPoint } from '../../utils/api'
import { pct, tone } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { DayCoverageNote } from '../DayCoverageNote'
import { dayCoverage } from '../../utils/dayCoverage'
import type { Instrument } from '../holdings/holdingsModel'
import { PERIODS, baseline, chartWindow, type Period, type Totals } from './metrics'

const W = 800
const H = 220
const dateLabel = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

/** Value against money invested, with a hover read-out. */
const HeroChart: React.FC<{ points: HistoryPoint[] }> = ({ points }) => {
  const { compact } = useMoney()
  const ref = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  const chart = useMemo(() => {
    if (points.length < 2) return null
    const all = points.flatMap((p) => [p.value, p.invested])
    let lo = Math.min(...all)
    let hi = Math.max(...all)
    const pad = (hi - lo || hi * 0.02 || 1) * 0.12
    lo -= pad
    hi += pad
    const t0 = new Date(points[0].date).getTime()
    const span = new Date(points[points.length - 1].date).getTime() - t0 || 1
    const x = (p: HistoryPoint) => ((new Date(p.date).getTime() - t0) / span) * W
    const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
    const line = (k: 'value' | 'invested') => points.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(1)} ${y(p[k]).toFixed(1)}`).join(' ')
    return { x, y, port: line('value'), inv: line('invested'), lo, hi }
  }, [points])

  if (!chart) return <div className="bx-chart-empty">The chart appears once there are two daily snapshots. Each sync adds one.</div>

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const px = ((e.clientX - r.left) / r.width) * W
    let best = 0
    points.forEach((p, i) => {
      if (Math.abs(chart.x(p) - px) < Math.abs(chart.x(points[best]) - px)) best = i
    })
    setHover(best)
  }
  const hp = hover !== null ? points[hover] : null
  const first = points[0]
  const last = points[points.length - 1]

  return (
    <div className="bx-chart">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" onPointerMove={onMove} onPointerLeave={() => setHover(null)} role="img" aria-label="Portfolio value against money invested">
        <defs>
          <linearGradient id="bx-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={`${chart.port} L${W} ${H} L0 ${H} Z`} fill="url(#bx-fill)" />
        <path d={chart.inv} fill="none" stroke="var(--text-3)" strokeWidth="1.4" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        <path d={chart.port} fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {hp && <line x1={chart.x(hp)} x2={chart.x(hp)} y1="0" y2={H} stroke="var(--text-3)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      </svg>
      {hp && (
        <div className="bx-tip num" style={{ left: `${(chart.x(hp) / W) * 100}%` }}>
          <b>{dateLabel(hp.date)}</b>
          <span>Value {compact(hp.value)}</span>
          <span>Invested {compact(hp.invested)}</span>
        </div>
      )}
      <div className="bx-axis num">
        <span>{dateLabel(first.date)}</span>
        <span className="bx-legend">
          <i className="v" /> Value <i className="i" /> Invested
        </span>
        <span>{dateLabel(last.date)}</span>
      </div>
    </div>
  )
}

interface Props {
  instruments: Instrument[]
  totals: Totals
  history: HistoryPoint[]
  period: Period
  onPeriod: (p: Period) => void
  nifty: number | null
  filterActive: boolean
}

export const HeroBand: React.FC<Props> = ({ instruments, totals, history, period, onPeriod, nifty, filterActive }) => {
  const { compact, signedCompact } = useMoney()
  const coverage = useMemo(() => dayCoverage(instruments), [instruments])
  const window = useMemo(() => chartWindow(history, period), [history, period])
  const from = useMemo(() => baseline(history, period === '1D' ? '1M' : period), [history, period])
  const last = history[history.length - 1]
  const gain = from && last ? last.value - from.value - (last.invested - from.invested) : null
  const gainPct = from && last && from.value > 0 && gain !== null ? (gain / from.value) * 100 : null
  const added = from && last ? last.invested - from.invested : null
  const long = PERIODS.find((p) => p.id === period)?.long ?? ''
  const vs = totals.dayPct != null && nifty != null ? totals.dayPct - nifty : null
  const scale = Math.max(Math.abs(totals.dayPct ?? 0), Math.abs(nifty ?? 0), 0.01)

  return (
    <section className="bx-band" aria-label="Portfolio at a glance">
      <div className="card bx-hero">
        <div className="bx-hero-top">
          <div>
            <span className="bx-lbl">Net worth{filterActive ? ' · filtered' : ''}</span>
            <div className="bx-big num">{compact(totals.cur)}</div>
            <div className="bx-sub num">
              {instruments.length} holdings · {compact(totals.inv)} invested
            </div>
          </div>
          <div className="seg" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p.id} type="button" className={period === p.id ? 'on' : ''} aria-pressed={period === p.id} onClick={() => onPeriod(p.id)}>
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <HeroChart points={window} />
      </div>

      <div className="bx-rail">
        <div className="card bx-tile">
          <span className="bx-lbl">Today&apos;s P&amp;L</span>
          <span className={`bx-val num ${tone(totals.day)}`}>{signedCompact(totals.day)}</span>
          <span className={`pill ${tone(totals.dayPct)}`}>{pct(totals.dayPct)}</span>
          {nifty != null && totals.dayPct != null && (
            <div className="bx-vs" title={`Nifty 50 ${pct(nifty)} today`}>
              <div className="bx-vs-row">
                <span>You</span>
                <span className="bx-vs-bar">
                  <i className={(totals.dayPct as number) < 0 ? 'neg' : 'pos'} style={{ width: `${(Math.abs(totals.dayPct) / scale) * 100}%` }} />
                </span>
                <span className="num">{pct(totals.dayPct)}</span>
              </div>
              <div className="bx-vs-row">
                <span>Nifty</span>
                <span className="bx-vs-bar">
                  <i className="ref" style={{ width: `${(Math.abs(nifty) / scale) * 100}%` }} />
                </span>
                <span className="num">{pct(nifty)}</span>
              </div>
              {vs != null && <span className="bx-vs-note">{vs >= 0 ? 'Ahead of' : 'Behind'} the Nifty by {Math.abs(vs).toFixed(2)}%</span>}
            </div>
          )}
          <span className="bx-foot">
            <DayCoverageNote coverage={coverage} />
          </span>
        </div>

        <div className="card bx-tile">
          <span className="bx-lbl">Total P&amp;L</span>
          <span className={`bx-val num ${tone(totals.pnl)}`}>{signedCompact(totals.pnl)}</span>
          <span className={`pill ${tone(totals.pnlPct)}`}>{pct(totals.pnlPct)}</span>
          <span className="bx-foot num">on {compact(totals.inv)} invested</span>
        </div>

        <div className="card bx-tile">
          <span className="bx-lbl">Market gain · {period === '1D' ? 'last month' : long}</span>
          <span className={`bx-val num ${tone(gain)}`}>{gain === null ? '—' : signedCompact(gain)}</span>
          {gainPct !== null && <span className={`pill ${tone(gainPct)}`}>{pct(gainPct)}</span>}
          <span className="bx-foot num">{from ? `since ${dateLabel(from.date)}${added ? ` · ${signedCompact(added)} money added, not counted` : ''}` : 'needs a few daily snapshots'}</span>
        </div>
      </div>
    </section>
  )
}
