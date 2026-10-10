import React, { useMemo, useState } from 'react'
import type { HistoryPoint } from '../../utils/api'
import { useMoney } from '../../utils/useMoney'
import { tone } from '../../utils/format'

const RANGES: { id: string; days: number | null }[] = [
  { id: '1M', days: 30 },
  { id: '3M', days: 91 },
  { id: '6M', days: 182 },
  { id: '1Y', days: 365 },
  { id: 'All', days: null },
]

const W = 800
const H = 240
const dayMs = 86400000

const shortDate = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

export const ValueChart: React.FC<{ history: HistoryPoint[]; loading: boolean }> = ({ history, loading }) => {
  const { compact, signedCompact } = useMoney()
  const [range, setRange] = useState('All')

  const view = useMemo(() => {
    const def = RANGES.find((r) => r.id === range)!
    if (history.length === 0) return null
    const last = new Date(history[history.length - 1].date).getTime()
    const pts = def.days === null ? history : history.filter((p) => new Date(p.date).getTime() >= last - def.days! * dayMs)
    if (pts.length < 2) return { pts, chart: null }

    const all = pts.flatMap((p) => [p.value, p.invested])
    let lo = Math.min(...all)
    let hi = Math.max(...all)
    const pad = (hi - lo || hi * 0.02 || 1) * 0.08
    lo -= pad
    hi += pad
    const t0 = new Date(pts[0].date).getTime()
    const span = new Date(pts[pts.length - 1].date).getTime() - t0 || 1
    const x = (p: HistoryPoint) => ((new Date(p.date).getTime() - t0) / span) * W
    const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
    const line = (key: 'value' | 'invested') => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ')
    const port = line('value')
    const ticks = [0, 1, 2, 3].map((i) => {
      const v = hi - ((hi - lo) * i) / 3
      return { v, y: y(v) }
    })
    const first = pts[0]
    const lastP = pts[pts.length - 1]
    return {
      pts,
      chart: {
        port,
        inv: line('invested'),
        area: `${port} L${W} ${H} L0 ${H} Z`,
        ticks,
        xl: [first.date, pts[Math.floor(pts.length / 2)].date, lastP.date],
        dValue: lastP.value - first.value,
        dInvested: lastP.invested - first.invested,
        base: first.value,
      },
    }
  }, [history, range])

  const c = view?.chart
  const marketGain = c ? c.dValue - c.dInvested : 0

  return (
    <div className="card">
      <div className="card-h">
        <div>
          <h2 className="card-t">Portfolio value</h2>
          <p className="card-s">Market value against money invested, from your daily sync snapshots</p>
        </div>
        <div className="seg" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r.id} className={r.id === range ? 'on' : ''} aria-pressed={r.id === range} onClick={() => setRange(r.id)}>
              {r.id}
            </button>
          ))}
        </div>
      </div>

      {c ? (
        <>
          <div className="retrow">
            <div className="ret">
              <div className="k">Change in value</div>
              <div className={`v num ${tone(c.dValue)}`}>{signedCompact(c.dValue)}</div>
            </div>
            <div className="ret">
              <div className="k">Net money added</div>
              <div className="v num">{signedCompact(c.dInvested)}</div>
            </div>
            <div className="ret">
              <div className="k">Market gain</div>
              <div className={`v num ${tone(marketGain)}`}>{signedCompact(marketGain)}</div>
            </div>
          </div>
          <div className="chart">
            {c.ticks.map((t) => (
              <span key={t.y} className="ylab num" style={{ top: `${(t.y / H) * 100}%` }}>
                {compact(t.v)}
              </span>
            ))}
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="Line chart of portfolio value over the selected range">
              {c.ticks.map((t) => (
                <line key={t.y} className="grid-ln" x1="0" x2={W} y1={t.y} y2={t.y} vectorEffect="non-scaling-stroke" />
              ))}
              <path className="area" d={c.area} />
              <path className="ln-inv" d={c.inv} vectorEffect="non-scaling-stroke" />
              <path className="ln-port" d={c.port} vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
          <div className="xlabs num">
            {c.xl.map((d, i) => (
              <span key={i}>{shortDate(d)}</span>
            ))}
          </div>
          <div className="legend" style={{ marginTop: 16 }}>
            <span>
              <i className="sw" style={{ background: 'var(--accent)' }} />
              Portfolio value
            </span>
            <span>
              <i className="sw" style={{ background: 'var(--warn)' }} />
              Invested
            </span>
          </div>
        </>
      ) : (
        <div className="chart-empty">
          {loading
            ? 'Loading history…'
            : `History builds up from your syncs, one point per day. ${history.length === 0 ? 'No snapshots yet.' : `${view?.pts.length ?? 0} point in this range so far.`} Sync again on another day to see the line.`}
        </div>
      )}
    </div>
  )
}
