import React, { useMemo } from 'react'
import { ChevronDown } from 'lucide-react'
import { Link } from 'react-router-dom'
import { pct, tone, weight } from '../../utils/format'
import { DASH, since, type Fmt } from './signalKit'
import type { StockSignals } from '../../types'

export interface CallSource {
  /** stable id, name and code for display */
  code: string
  name: string
  sector?: string
  held?: boolean
  isNew?: boolean | null
  sig?: StockSignals
  ltp: number
}

type Kind = 'swing' | 'ath'

interface Call {
  key: string
  src: CallSource
  kind: Kind
  /** the date the call counts under: the fill date, or the signal date while a Swing buy is still queued */
  date: string
  queued: boolean
  entryPrice: number | null
  /** one line: what fired */
  trigger: string
  /** one line: why the stock qualified */
  setup: string
  /** one line: where it is wrong */
  risk: string
  sinceEntry: { pct: number; abs: number } | null
}

const short = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
const weekday = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short' })

/** The two most recent sessions seen across all stocks (each stock reports its own last two). */
export const latestSessions = (sources: CallSource[]): string[] => {
  const all = new Set<string>()
  sources.forEach((s) => s.sig?.last_sessions?.forEach((d) => all.add(d)))
  return [...all].sort().slice(-2)
}

export const buildCalls = (sources: CallSource[], sessions: string[], fmt: Fmt): Call[] => {
  const out: Call[] = []
  const p = (v: number | null | undefined) => fmt.price(v)
  const signed = (v: number | null | undefined) => (v == null ? DASH : `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}%`)

  sources.forEach((src) => {
    const { sig } = src
    const s = sig?.swing
    const sc = s?.call
    if (s && sc) {
      const queued = sc.queued && s.pending_order === 'BUY'
      const filled = !sc.queued && !!sc.entry_date && sessions.includes(sc.entry_date) && s.state === 'IN_POSITION' && s.entry_date === sc.entry_date
      if (queued || filled) {
        const entry = queued ? sc.signal_close : sc.entry_price
        out.push({
          key: `${src.code}-swing`,
          src,
          kind: 'swing',
          date: queued ? sc.signal_date : (sc.entry_date as string),
          queued,
          entryPrice: entry,
          trigger: `UT Bot buy at the ${short(sc.signal_date)} close, ${p(sc.signal_close)}`,
          setup: `Close ${signed(sc.above_slow_pct)} over the 200-SMA; 50-SMA ${signed(sc.fast_over_slow_pct)} over it; 200-SMA ${signed(sc.slow_slope_pct)} in ${sc.slope_lookback} bars`,
          risk: queued
            ? 'Stop is set when it fills'
            : sc.stop != null
              ? `Stop ${p(sc.stop)}${sc.stop_pct != null ? `, ${weight(Math.abs(sc.stop_pct), 1)} below entry` : ''}`
              : 'No protective stop',
          sinceEntry: since(entry, src.ltp),
        })
      }
    }

    const a = sig?.ath
    const ac = a?.call
    if (a && ac && a.state === 'IN_POSITION' && a.entry_date === ac.entry_date && sessions.includes(ac.entry_date)) {
      out.push({
        key: `${src.code}-ath`,
        src,
        kind: 'ath',
        date: ac.entry_date,
        queued: false,
        entryPrice: ac.entry_price,
        trigger: `Closed ${p(ac.close)}, ${signed(ac.above_ath_pct)} over the prior all-time high ${p(ac.prior_ath)}`,
        setup:
          ac.days_since_below_dma != null
            ? `${ac.days_since_below_dma} trading days after a close under the 200-DMA (window ${ac.window_bars})`
            : `Inside the ${ac.window_bars}-day window after a 200-DMA break`,
        risk:
          ac.dma != null
            ? `Exit under the 200-DMA ${p(ac.dma)}, ${weight(Math.abs((ac.dma / ac.close - 1) * 100), 1)} below`
            : 'Exit on a close under the 200-DMA',
        sinceEntry: since(ac.entry_price, src.ltp),
      })
    }
  })

  return out.sort((x, y) => y.date.localeCompare(x.date) || x.src.name.localeCompare(y.src.name))
}

interface Group {
  id: string
  title: string
  note: string
  calls: Call[]
}

/** Queued signals first (they act next), then one group per fill date, newest first. */
const groupCalls = (calls: Call[]): Group[] => {
  const groups: Group[] = []
  const queued = calls.filter((c) => c.queued)
  if (queued.length) {
    groups.push({ id: 'queued', title: `Signalled ${short(queued[0].date)}, not filled yet`, note: 'The Swing engine buys at the next open. The price shown is the signal close.', calls: queued })
  }
  const dates = [...new Set(calls.filter((c) => !c.queued).map((c) => c.date))].sort().reverse()
  dates.forEach((d) =>
    groups.push({ id: d, title: `Entered ${weekday(d)} ${short(d)}`, note: '', calls: calls.filter((c) => !c.queued && c.date === d) }),
  )
  return groups
}

const CallTable: React.FC<{ title: string; sub: string; accent: string; calls: Call[]; fmt: Fmt; open?: boolean; empty: string }> = ({ title, sub, accent, calls, fmt, open = false, empty }) => {
  const groups = useMemo(() => groupCalls(calls), [calls])
  return (
    <details className="card callsec" aria-label={title} open={open}>
      <summary className="callsec-h">
        <span className="callsec-bar" style={{ background: accent }} aria-hidden="true" />
        <div>
          <h2 className="card-t">{title}</h2>
          <p className="card-s">{sub}</p>
        </div>
        <span className="callsec-n num">{calls.length}</span>
        <ChevronDown className="callsec-chev" size={18} strokeWidth={1.75} aria-hidden="true" />
      </summary>

      {calls.length === 0 ? (
        <p className="card-s callsec-empty">{empty}</p>
      ) : (
        <div className="ctbl-wrap">
          <table className="ctbl">
            <thead>
              <tr>
                <th>Stock</th>
                <th className="r">Entry</th>
                <th>Why it fired</th>
                <th>Risk</th>
                <th className="r">Now</th>
                <th className="r">Since entry</th>
              </tr>
            </thead>
            {groups.map((g) => (
              <tbody key={g.id}>
                <tr className="grp">
                  <th colSpan={6} scope="colgroup">
                    <span className={`grp-t ${g.id === 'queued' ? 'queued' : ''}`}>{g.title}</span>
                    <span className="grp-n num">{g.calls.length}</span>
                    {g.note && <span className="grp-note">{g.note}</span>}
                  </th>
                </tr>
                {g.calls.map((c) => (
                  <tr key={c.key}>
                    <td>
                      <div className="sg-sym">
                        <Link className="sg-link" to={`/momentum?symbol=${encodeURIComponent(c.src.code)}`} title="Open in Momentum">
                          {c.src.name}
                        </Link>
                        {c.src.isNew && <span className="badge info">New</span>}
                        {c.src.held && <span className="badge ok">Held</span>}
                      </div>
                      <div className="sg-sub mono">
                        {c.src.code}
                        {c.src.sector ? ` · ${c.src.sector}` : ''}
                      </div>
                    </td>
                    <td className="r num">
                      {fmt.price(c.entryPrice)}
                      {c.queued && <div className="sg-sub">indicative</div>}
                    </td>
                    <td className="why">
                      <div className="why-1">{c.trigger}</div>
                      <div className="why-2">{c.setup}</div>
                    </td>
                    <td className="risk">{c.risk}</td>
                    <td className="r num">{fmt.price(c.src.ltp)}</td>
                    <td className={`r num ${tone(c.sinceEntry?.abs)}`}>
                      {c.sinceEntry ? (
                        <>
                          {pct(c.sinceEntry.pct)}
                          <div className="sg-sub">{fmt.perShare(c.sinceEntry.abs)}</div>
                        </>
                      ) : (
                        DASH
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </details>
  )
}

export const NewCalls: React.FC<{ sources: CallSource[]; fmt: Fmt }> = ({ sources, fmt }) => {
  const sessions = useMemo(() => latestSessions(sources), [sources])
  const calls = useMemo(() => buildCalls(sources, sessions, fmt), [sources, sessions, fmt])
  const swing = useMemo(() => calls.filter((c) => c.kind === 'swing' && !c.queued), [calls])
  const ath = useMemo(() => calls.filter((c) => c.kind === 'ath'), [calls])
  const queued = useMemo(() => calls.filter((c) => c.queued), [calls])
  const hasDetail = sources.some((s) => s.sig?.last_sessions?.length)

  if (!hasDetail) {
    return (
      <div className="card">
        <p className="card-t">Call details are not in the saved signals yet</p>
        <p className="card-s">Press Refresh from Chartink once to load them.</p>
      </div>
    )
  }

  return (
    <div className="calls">
      <p className="calls-intro">
        Buys that filled in the last 2 sessions ({sessions.map((d) => `${weekday(d)} ${short(d)}`).join(', ')}). Entries are read from completed daily candles; Now and Since entry use the live price.
      </p>
      <CallTable title="Swing V2.1" sub="UT Bot buy inside a 200-SMA uptrend, filled at the next open." accent="var(--accent)" calls={swing} fmt={fmt} empty="No Swing buys filled in the last 2 sessions." />
      <CallTable title="200-DMA ATH breakout" sub="Close above the all-time high shortly after a 200-DMA reclaim, bought at that close." accent="var(--gain)" calls={ath} fmt={fmt} empty="No ATH breakouts in the last 2 sessions." />
      <CallTable
        title="Swing signals waiting to fill"
        sub={`The latest session's Swing buy signals. The strategy buys at the next open, so none of these has an entry yet. The price shown is the signal close, and the real fill can differ.`}
        accent="var(--warn)"
        calls={queued}
        fmt={fmt}
        empty="No Swing signals are waiting to fill."
      />
    </div>
  )
}
