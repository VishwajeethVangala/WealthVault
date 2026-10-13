import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchMarketQuotes, fetchUsLive, type HistoryPoint } from '../../utils/api'
import { pct, tone } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { usePortfolio } from '../../context/PortfolioContext'
import { StockLink } from '../StockLink'
import { DayCoverageNote } from '../DayCoverageNote'
import { dayCoverage } from '../../utils/dayCoverage'
import { CLASS_COLOR, CLASS_LABEL, CLASS_ORDER, type Instrument } from '../holdings/holdingsModel'

export type Period = '1D' | '1W' | '1M' | '3M' | 'YTD' | 'ALL'
const PERIODS: { id: Period; label: string }[] = [
  { id: '1D', label: '1D' },
  { id: '1W', label: '1W' },
  { id: '1M', label: '1M' },
  { id: '3M', label: '3M' },
  { id: 'YTD', label: 'YTD' },
  { id: 'ALL', label: 'All' },
]

const startOf = (period: Period): string | null => {
  const d = new Date()
  if (period === '1D') return null
  if (period === 'YTD') return `${d.getFullYear()}-01-01`
  if (period === 'ALL') return '0000-00-00'
  d.setDate(d.getDate() - { '1W': 7, '1M': 30, '3M': 91 }[period])
  return d.toISOString().slice(0, 10)
}

/** The snapshot to measure from: the last one on or before the period start, else the earliest there is. */
const baseline = (history: HistoryPoint[], period: Period): HistoryPoint | null => {
  const from = startOf(period)
  if (!from || history.length === 0) return null
  const before = [...history].reverse().find((p) => p.date <= from)
  return before ?? history[0]
}

const marketOpen = (): boolean => {
  const ist = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const mins = ist.getHours() * 60 + ist.getMinutes()
  return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
}

/** Nifty 50's change today, to set the portfolio's day against. */
const useNifty = (): number | null => {
  const [value, setValue] = useState<number | null>(null)
  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchMarketQuotes(['NSE:NIFTY 50'])
          const q = res.quotes['NSE:NIFTY 50'] ?? Object.values(res.quotes)[0]
          const prev = q?.ohlc?.close
          if (!stop && q && prev && prev > 0) setValue(((q.last_price - prev) / prev) * 100)
        } catch {
          /* keep the last value */
        }
      }
      if (!stop) timer = window.setTimeout(tick, marketOpen() ? 60_000 : 600_000)
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [])
  return value
}

/** US stocks' average move in dollars today, so the rupee figure can be read against the stock's own move. */
const useUsdMove = (enabled: boolean): number | null => {
  const { holdings } = usePortfolio()
  const [quotes, setQuotes] = useState<Record<string, { day_change_pct: number | null }>>({})
  useEffect(() => {
    if (!enabled) return
    fetchUsLive()
      .then((r) => setQuotes(r.quotes))
      .catch(() => {})
  }, [enabled])
  return useMemo(() => {
    let num = 0
    let den = 0
    holdings.forEach((h) => {
      if (h.asset_class !== 'US_STOCKS') return
      const t = h.instrument_symbol.trim().split(/\s+/)[0].toUpperCase()
      const p = quotes[t]?.day_change_pct
      if (p == null) return
      num += (h.current_value || 0) * p
      den += h.current_value || 0
    })
    return den > 0 ? num / den : null
  }, [holdings, quotes])
}

const Spark: React.FC<{ values: number[]; color: string }> = ({ values, color }) => {
  if (values.length < 2) return <svg className="xs-spark" aria-hidden="true" />
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / span) * 24 - 2}`).join(' ')
  return (
    <svg className="xs-spark" viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

interface Props {
  instruments: Instrument[]
  history: HistoryPoint[]
  classHistory: Record<string, { date: string; v: number }[]>
  period: Period
  onPeriod: (p: Period) => void
  filterActive: boolean
}

export const ExecutiveStrip: React.FC<Props> = ({ instruments, history, classHistory, period, onPeriod, filterActive }) => {
  const { compact, signedCompact } = useMoney()
  const { stockHref } = usePortfolio()
  const nifty = useNifty()
  const usdMove = useUsdMove(instruments.some((i) => i.cls === 'US_STOCKS'))

  const totals = useMemo(() => {
    const cur = instruments.reduce((s, i) => s + i.cur, 0)
    const inv = instruments.reduce((s, i) => s + i.inv, 0)
    const rep = instruments.filter((i) => i.day !== null)
    const day = rep.reduce((s, i) => s + (i.day as number), 0)
    const base = rep.reduce((s, i) => s + i.cur - (i.day as number), 0)
    return { cur, inv, pnl: cur - inv, pnlPct: inv > 0 ? ((cur - inv) / inv) * 100 : null, day: rep.length ? day : null, dayPct: rep.length && base > 0 ? (day / base) * 100 : null }
  }, [instruments])

  const coverage = useMemo(() => dayCoverage(instruments), [instruments])
  const from = useMemo(() => baseline(history, period), [history, period])
  const last = history[history.length - 1]

  // Whole-portfolio change over the period: value change less money added = what the market did
  const periodGain = useMemo(() => {
    if (!from || !last) return null
    const dv = last.value - from.value
    const di = last.invested - from.invested
    return { since: from.date, value: dv, added: di, market: dv - di, pct: from.value > 0 ? ((dv - di) / from.value) * 100 : null }
  }, [from, last])

  const cards = useMemo(
    () =>
      CLASS_ORDER.map((cls) => {
        const items = instruments.filter((i) => i.cls === cls)
        const cur = items.reduce((s, i) => s + i.cur, 0)
        const inv = items.reduce((s, i) => s + i.inv, 0)
        const rep = items.filter((i) => i.day !== null)
        const day = rep.reduce((s, i) => s + (i.day as number), 0)
        const base = rep.reduce((s, i) => s + i.cur - (i.day as number), 0)
        const series = classHistory[cls] ?? []
        const then = from ? [...series].reverse().find((p) => p.date <= from.date) ?? series[0] : null
        const ranked = rep.slice().sort((a, b) => (b.day as number) - (a.day as number))
        return {
          cls,
          items,
          cur,
          weight: totals.cur > 0 ? (cur / totals.cur) * 100 : 0,
          pnl: cur - inv,
          pnlPct: inv > 0 ? ((cur - inv) / inv) * 100 : null,
          day: rep.length ? day : null,
          dayPct: rep.length && base > 0 ? (day / base) * 100 : null,
          reporting: rep.length,
          change: then && series.length ? series[series.length - 1].v - then.v : null,
          spark: series.slice(-30).map((p) => p.v),
          best: ranked.length && (ranked[0].day as number) > 0 ? ranked[0] : null,
          worst: ranked.length && (ranked[ranked.length - 1].day as number) < 0 ? ranked[ranked.length - 1] : null,
        }
      })
        .filter((c) => c.items.length > 0 && c.cur > 0)
        .sort((a, b) => b.cur - a.cur),
    [instruments, classHistory, from, totals.cur],
  )

  // "Why it moved": every class's share of today's P&L, then the stocks behind it
  const moved = useMemo(() => {
    const rows = cards.filter((c) => c.day !== null).sort((a, b) => Math.abs(b.day as number) - Math.abs(a.day as number))
    const max = Math.max(...rows.map((r) => Math.abs(r.day as number)), 1)
    const ranked = instruments.filter((i) => i.day !== null).sort((a, b) => (b.day as number) - (a.day as number))
    return {
      rows,
      max,
      up: ranked.filter((i) => (i.day as number) > 0).slice(0, 4),
      down: ranked.filter((i) => (i.day as number) < 0).reverse().slice(0, 4),
    }
  }, [cards, instruments])

  const vsNifty = totals.dayPct != null && nifty != null ? totals.dayPct - nifty : null
  const periodLabel = PERIODS.find((p) => p.id === period)?.label ?? ''

  return (
    <>
      <section className="xs-head" aria-label="Portfolio at a glance">
        <h2 className="xs-title">At a glance{filterActive ? ' (filtered)' : ''}</h2>
        <div className="seg" role="group" aria-label="Period">
          {PERIODS.map((p) => (
            <button key={p.id} type="button" className={period === p.id ? 'on' : ''} aria-pressed={period === p.id} onClick={() => onPeriod(p.id)}>
              {p.label}
            </button>
          ))}
        </div>
      </section>

      <section className="xs-strip" aria-label="Key figures">
        <div className="card xs-hero">
          <span className="lbl">Net worth</span>
          <span className="val num">{compact(totals.cur)}</span>
          <span className="foot num">
            {instruments.length} holdings · invested {compact(totals.inv)}
          </span>
        </div>
        <div className="card xs-kpi">
          <span className="lbl">Today&apos;s P&amp;L</span>
          <span className={`val num ${tone(totals.day)}`}>{signedCompact(totals.day)}</span>
          <span className="foot">
            <span className={`pill ${tone(totals.dayPct)}`}>{pct(totals.dayPct)}</span>
            {vsNifty != null && (
              <span className="num" title={`Nifty 50 ${pct(nifty)} today`}>
                {vsNifty >= 0 ? 'ahead of' : 'behind'} Nifty by {Math.abs(vsNifty).toFixed(2)}%
              </span>
            )}
          </span>
          <span className="foot">
            <DayCoverageNote coverage={coverage} />
          </span>
        </div>
        <div className="card xs-kpi">
          <span className="lbl">Total P&amp;L</span>
          <span className={`val num ${tone(totals.pnl)}`}>{signedCompact(totals.pnl)}</span>
          <span className="foot">
            <span className={`pill ${tone(totals.pnlPct)}`}>{pct(totals.pnlPct)}</span> on {compact(totals.inv)} invested
          </span>
        </div>
        <div className="card xs-kpi">
          <span className="lbl">{period === '1D' ? 'Last 30 days' : `${periodLabel} market gain`}</span>
          {(() => {
            const p = period === '1D' ? baseline(history, '1M') : from
            const l = last
            if (!p || !l) return <span className="val num">—</span>
            const gain = l.value - p.value - (l.invested - p.invested)
            const g = p.value > 0 ? (gain / p.value) * 100 : null
            return (
              <>
                <span className={`val num ${tone(gain)}`}>{signedCompact(gain)}</span>
                <span className="foot">
                  <span className={`pill ${tone(g)}`}>{pct(g)}</span> since {new Date(p.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                </span>
                <span className="foot num">{periodGain && period !== '1D' ? `${signedCompact(periodGain.added)} money added` : 'excluding money added'}</span>
              </>
            )
          })()}
        </div>
      </section>

      <section className="xs-cards" aria-label="By asset class">
        {cards.map((c) => (
          <Link key={c.cls} to={`/holdings?assetClass=${c.cls}`} className="card xs-card" aria-label={`${CLASS_LABEL[c.cls]}: open holdings`}>
            <div className="xs-card-h">
              <span className="dot" style={{ background: CLASS_COLOR[c.cls] }} aria-hidden="true" />
              <span className="xs-card-t">{CLASS_LABEL[c.cls]}</span>
              <span className="xs-card-w num">{c.weight.toFixed(1)}%</span>
            </div>
            <div className="xs-card-v num">{compact(c.cur)}</div>
            <Spark values={c.spark} color={CLASS_COLOR[c.cls]} />
            <dl className="xs-rows">
              <div>
                <dt>Total P&amp;L</dt>
                <dd className={`num ${tone(c.pnl)}`}>
                  {signedCompact(c.pnl)} <small>{pct(c.pnlPct)}</small>
                </dd>
              </div>
              <div>
                <dt>1-day P&amp;L</dt>
                <dd className={`num ${tone(c.day)}`}>
                  {c.day === null ? '—' : signedCompact(c.day)} <small>{c.day === null ? '' : pct(c.dayPct)}</small>
                  {c.cls === 'US_STOCKS' && usdMove != null && <small className="xs-note"> · {pct(usdMove)} in USD</small>}
                </dd>
              </div>
              {period !== '1D' && (
                <div>
                  <dt>{periodLabel} value change</dt>
                  <dd className={`num ${tone(c.change)}`}>{c.change === null ? '—' : signedCompact(c.change)}</dd>
                </div>
              )}
            </dl>
            {(c.best || c.worst) && (
              <div className="xs-moves">
                {c.best && (
                  <span className="pos num" title="Biggest gain today">
                    ▲ {c.best.sym.length > 18 ? `${c.best.sym.slice(0, 17)}…` : c.best.sym}
                  </span>
                )}
                {c.worst && (
                  <span className="neg num" title="Biggest loss today">
                    ▼ {c.worst.sym.length > 18 ? `${c.worst.sym.slice(0, 17)}…` : c.worst.sym}
                  </span>
                )}
              </div>
            )}
          </Link>
        ))}
      </section>

      {moved.rows.length > 0 && (
        <section className="card xs-move" aria-label="Why today moved">
          <div className="card-h">
            <div>
              <h2 className="card-t">Why today moved</h2>
              <p className="card-s">
                {signedCompact(totals.day)} in total, split by asset class and by the holdings behind it
              </p>
            </div>
          </div>
          <div className="xs-move-body">
            <div className="xs-bars">
              {moved.rows.map((r) => (
                <div className="xs-bar-row" key={r.cls}>
                  <span className="xs-bar-n">
                    <span className="dot" style={{ background: CLASS_COLOR[r.cls] }} aria-hidden="true" />
                    {CLASS_LABEL[r.cls]}
                  </span>
                  <span className="xs-bar-track" aria-hidden="true">
                    <span
                      className={(r.day as number) < 0 ? 'neg' : 'pos'}
                      style={{ width: `${(Math.abs(r.day as number) / moved.max) * 100}%` }}
                    />
                  </span>
                  <span className={`xs-bar-v num ${tone(r.day)}`}>{signedCompact(r.day)}</span>
                </div>
              ))}
            </div>
            <div className="xs-who">
              <div>
                <p className="xs-who-h pos">Lifted the day</p>
                {moved.up.length === 0 && <p className="empty-s">Nothing gained</p>}
                {moved.up.map((i) => (
                  <div className="xs-who-r" key={i.key}>
                    <StockLink href={stockHref(i)}>{i.sym.length > 22 ? `${i.sym.slice(0, 21)}…` : i.sym}</StockLink>
                    <span className="num pos">{signedCompact(i.day)}</span>
                  </div>
                ))}
              </div>
              <div>
                <p className="xs-who-h neg">Pulled it down</p>
                {moved.down.length === 0 && <p className="empty-s">Nothing lost</p>}
                {moved.down.map((i) => (
                  <div className="xs-who-r" key={i.key}>
                    <StockLink href={stockHref(i)}>{i.sym.length > 22 ? `${i.sym.slice(0, 21)}…` : i.sym}</StockLink>
                    <span className="num neg">{signedCompact(i.day)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
    </>
  )
}
