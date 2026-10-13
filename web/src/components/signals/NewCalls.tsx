import React, { useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { pct, tone, weight } from '../../utils/format'
import { StockLink } from '../StockLink'
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
  /** where the stock name links to (its Momentum view) */
  href?: string | null
}

type Kind = 'swing' | 'ath'
export type BuyWindow = 2 | 7 | 'open'

const STRATEGY: Record<Kind, { title: string; sub: string; accent: string }> = {
  swing: { title: 'Swing V2.1', sub: 'UT Bot buy inside a 200-SMA uptrend; fills at the next open.', accent: 'var(--accent)' },
  ath: { title: '200-DMA ATH breakout', sub: 'Close above the all-time high shortly after a 200-DMA reclaim; bought at that close.', accent: 'var(--gain)' },
}

interface Row {
  key: string
  src: CallSource
  kind: Kind
  /** the date the row is grouped under */
  date: string
  waiting: boolean
  live: boolean
  price: number | null
  /** buy: where the entry is; sell: where the exit is */
  priceNote: string
  why: string
  detail: string
  /** buy: the protective stop / exit rule; sell: how the trade ended */
  tail: string
  tailTone?: string
  sinceRef: { pct: number; abs: number } | null
}

const short = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
const weekday = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short' })
const longDate = (iso: string) => `${weekday(iso)} ${short(iso)}`

/** The most recent `n` sessions seen across all stocks (each stock reports its own). */
export const latestSessions = (sources: CallSource[], n = 2): string[] => {
  const all = new Set<string>()
  sources.forEach((s) => s.sig?.last_sessions?.forEach((d) => all.add(d)))
  return [...all].sort().slice(-n)
}

const signed = (v: number | null | undefined) => (v == null ? DASH : `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}%`)

/** Buys: filled inside the window, or (window 'open') every position that is open now, as the Strategies pages list them. */
export const buildBuys = (sources: CallSource[], sessions: string[], window: BuyWindow, fmt: Fmt, sessionOpen: boolean): Row[] => {
  const out: Row[] = []
  const p = (v: number | null | undefined) => fmt.price(v)
  const inWindow = (d: string | null | undefined) => !!d && (window === 'open' || sessions.includes(d))

  sources.forEach((src) => {
    const { sig } = src
    const s = sig?.swing
    const sc = s?.call
    if (s && sc) {
      const waiting = sc.queued && s.pending_order === 'BUY'
      const open = !sc.queued && !!sc.entry_date && s.state === 'IN_POSITION' && s.entry_date === sc.entry_date
      if (waiting || (open && inWindow(sc.entry_date))) {
        const entry = waiting ? sc.signal_close : sc.entry_price
        out.push({
          key: `${src.code}-swing`,
          src,
          kind: 'swing',
          date: waiting ? sc.signal_date : (sc.entry_date as string),
          waiting,
          live: sessionOpen && waiting && sc.signal_date === sig?.live_date,
          price: entry,
          priceNote: waiting ? 'indicative' : `signal ${short(sc.signal_date)}`,
          why: `UT Bot buy at the ${short(sc.signal_date)} close, ${p(sc.signal_close)}`,
          detail: `Close ${signed(sc.above_slow_pct)} over the 200-SMA; 50-SMA ${signed(sc.fast_over_slow_pct)} over it; 200-SMA ${signed(sc.slow_slope_pct)} in ${sc.slope_lookback} bars`,
          tail: waiting ? 'Stop is set when it fills' : sc.stop != null ? `Stop ${p(sc.stop)}${sc.stop_pct != null ? `, ${weight(Math.abs(sc.stop_pct), 1)} below entry` : ''}` : 'No protective stop',
          sinceRef: since(entry, src.ltp),
        })
      }
    }

    const a = sig?.ath
    const ac = a?.call
    if (a && ac && a.state === 'IN_POSITION' && a.entry_date === ac.entry_date && inWindow(ac.entry_date)) {
      out.push({
        key: `${src.code}-ath`,
        src,
        kind: 'ath',
        date: ac.entry_date,
        waiting: false,
        live: sessionOpen && ac.entry_date === sig?.live_date,
        price: ac.entry_price,
        priceNote: 'at the close',
        why: `Closed ${p(ac.close)}, ${signed(ac.above_ath_pct)} over the prior all-time high ${p(ac.prior_ath)}`,
        detail:
          ac.days_since_below_dma != null
            ? `${ac.days_since_below_dma} trading days after a close under the 200-DMA (window ${ac.window_bars})`
            : `Inside the ${ac.window_bars}-day window after a 200-DMA break`,
        tail: ac.dma != null ? `Exit under the 200-DMA ${p(ac.dma)}, ${weight(Math.abs((ac.dma / ac.close - 1) * 100), 1)} below` : 'Exit on a close under the 200-DMA',
        sinceRef: since(ac.entry_price, src.ltp),
      })
    }
  })
  return out.sort((x, y) => y.date.localeCompare(x.date) || x.src.name.localeCompare(y.src.name))
}

/** Sells: trades the strategies closed inside the window, plus Swing sells signalled and not yet filled. */
export const buildSells = (sources: CallSource[], sessions: string[], fmt: Fmt, sessionOpen: boolean): Row[] => {
  const out: Row[] = []
  const p = (v: number | null | undefined) => fmt.price(v)
  const ended = (entryDate: string, entryPrice: number | null | undefined, exitPrice: number | null | undefined, pnl: number | null | undefined) =>
    `Bought ${short(entryDate)} at ${p(entryPrice)}, sold ${p(exitPrice)}${pnl != null ? ` (${signed(pnl)})` : ''}`

  sources.forEach((src) => {
    const { sig } = src
    sig?.swing?.exits?.forEach((e, i) => {
      if (!sessions.includes(e.exit_date)) return
      const stop = e.reason === 'ATR STOP'
      out.push({
        key: `${src.code}-swing-exit-${i}`,
        src,
        kind: 'swing',
        date: e.exit_date,
        waiting: false,
        live: false,
        price: e.exit_price,
        priceNote: stop ? 'stop hit' : 'at the open',
        why: stop ? `Protective ATR stop hit on ${short(e.exit_date)}` : `UT Bot sell and a close under the 20-EMA on ${short(e.signal_date)}`,
        detail: stop ? 'The stop sits 2 ATR below the entry and trails up with the position' : `Sold at the ${short(e.exit_date)} open`,
        tail: ended(e.entry_date, e.entry_price, e.exit_price, e.pnl_pct),
        tailTone: tone(e.pnl_pct),
        sinceRef: since(e.exit_price, src.ltp),
      })
    })
    const ps = sig?.swing?.pending_sell
    if (ps) {
      out.push({
        key: `${src.code}-swing-pending`,
        src,
        kind: 'swing',
        date: ps.signal_date,
        waiting: true,
        live: sessionOpen && ps.signal_date === sig?.live_date,
        price: ps.signal_close,
        priceNote: 'indicative',
        why: `UT Bot sell and a close under the 20-EMA on the ${short(ps.signal_date)} close`,
        detail: 'Sells at the next open',
        tail: ps.entry_date ? `Bought ${short(ps.entry_date)} at ${p(ps.entry_price)}` : '',
        sinceRef: since(ps.signal_close, src.ltp),
      })
    }
    sig?.ath?.exits?.forEach((e, i) => {
      if (!sessions.includes(e.exit_date)) return
      out.push({
        key: `${src.code}-ath-exit-${i}`,
        src,
        kind: 'ath',
        date: e.exit_date,
        waiting: false,
        live: sessionOpen && e.exit_date === sig?.live_date,
        price: e.exit_price,
        priceNote: 'at the close',
        why: `Closed ${p(e.exit_price)}, under the 200-DMA`,
        detail: 'The breakout position is held until a close below the 200-DMA',
        tail: ended(e.entry_date, e.entry_price, e.exit_price, e.pnl_pct),
        tailTone: tone(e.pnl_pct),
        sinceRef: since(e.exit_price, src.ltp),
      })
    })
  })
  return out.sort((x, y) => y.date.localeCompare(x.date) || x.src.name.localeCompare(y.src.name))
}

interface Group {
  id: string
  title: string
  rows: Row[]
}

const groupRows = (rows: Row[], side: 'buy' | 'sell'): Group[] => {
  const dates = [...new Set(rows.filter((r) => !r.waiting).map((r) => r.date))].sort().reverse()
  return dates.map((d) => ({ id: d, title: `${side === 'buy' ? 'Entered' : 'Exited'} ${longDate(d)}`, rows: rows.filter((r) => !r.waiting && r.date === d) }))
}

const PAGE = 40

const CallTable: React.FC<{ kind: Kind; side: 'buy' | 'sell'; rows: Row[]; fmt: Fmt; empty: string; title?: string; sub?: string; accent?: string }> = ({
  kind,
  side,
  rows,
  fmt,
  empty,
  title,
  sub,
  accent,
}) => {
  const [shown, setShown] = useState(PAGE)
  const flat = useMemo<Group[]>(() => (rows.every((r) => r.waiting) ? [{ id: 'waiting', title: '', rows }] : groupRows(rows, side)), [rows, side])
  // page by rows so a long "all open" list stays quick to scroll
  let budget = shown
  const visible = flat
    .map((g) => {
      const take = g.rows.slice(0, Math.max(0, budget))
      budget -= take.length
      return { ...g, rows: take }
    })
    .filter((g) => g.rows.length > 0)
  const total = rows.length
  const head = STRATEGY[kind]
  const labels = side === 'buy' ? ['Stock', 'Entry', 'Why it fired', 'Risk', 'Now', 'Since entry'] : ['Stock', 'Exit', 'Why it fired', 'Trade', 'Now', 'Since exit']

  return (
    <details className="card callsec">
      <summary className="callsec-h">
        <span className="callsec-bar" style={{ background: accent ?? head.accent }} aria-hidden="true" />
        <div className="callsec-t">
          <h2 className="card-t">{title ?? head.title}</h2>
          <p className="card-s">{sub ?? head.sub}</p>
        </div>
        <span className="callsec-n num">{total}</span>
        <ChevronDown className="callsec-chev" size={18} strokeWidth={1.75} aria-hidden="true" />
      </summary>

      {total === 0 ? (
        <p className="card-s callsec-empty">{empty}</p>
      ) : (
        <div className="ctbl-wrap">
          <table className="ctbl">
            <thead>
              <tr>
                {labels.map((l, i) => (
                  <th key={l} className={i === 1 || i >= 4 ? 'r' : ''}>
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            {visible.map((g) => (
              <tbody key={g.id}>
                {g.title && (
                  <tr className="grp">
                    <th colSpan={6} scope="colgroup">
                      <span className="grp-t">{g.title}</span>
                      <span className="grp-n num">{g.rows.length}</span>
                    </th>
                  </tr>
                )}
                {g.rows.map((c) => (
                  <tr key={c.key}>
                    <td data-label={labels[0]}>
                      <div className="sg-sym">
                        <StockLink href={c.src.href ?? null}>{c.src.name}</StockLink>
                        {c.src.isNew && <span className="badge info">New</span>}
                        {c.src.held && <span className="badge ok">Held</span>}
                        {c.live && (
                          <span className="badge warn" title="Fired on today's live price; it can change before the 15:30 close">
                            Live
                          </span>
                        )}
                      </div>
                      <div className="sg-sub mono">
                        {c.src.code}
                        {c.src.sector ? ` · ${c.src.sector}` : ''}
                      </div>
                    </td>
                    <td className="r num" data-label={labels[1]}>
                      {fmt.price(c.price)}
                      <div className="sg-sub">{c.waiting ? `${longDate(c.date)} · ${c.priceNote}` : `${short(c.date)} · ${c.priceNote}`}</div>
                    </td>
                    <td className="why" data-label={labels[2]}>
                      <div className="why-1">{c.why}</div>
                      <div className="why-2">{c.detail}</div>
                    </td>
                    <td className={`risk ${c.tailTone ?? ''}`} data-label={labels[3]}>
                      {c.tail || DASH}
                    </td>
                    <td className="r num" data-label={labels[4]}>
                      {fmt.price(c.src.ltp)}
                    </td>
                    <td className={`r num ${tone(c.sinceRef?.abs)}`} data-label={labels[5]}>
                      {c.sinceRef ? (
                        <>
                          {pct(c.sinceRef.pct)}
                          <div className="sg-sub">{fmt.perShare(c.sinceRef.abs)}</div>
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
          {total > shown && (
            <div className="ctbl-more">
              <button className="btn" type="button" onClick={() => setShown((n) => n + PAGE)}>
                Show {Math.min(PAGE, total - shown)} more of {total - shown}
              </button>
            </div>
          )}
        </div>
      )}
    </details>
  )
}

export const CallsView: React.FC<{ sources: CallSource[]; fmt: Fmt; sessionOpen?: boolean; defaultWindow?: BuyWindow }> = ({
  sources,
  fmt,
  sessionOpen = false,
  defaultWindow = 2,
}) => {
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [window, setWindow] = useState<BuyWindow>(defaultWindow)
  const [mine, setMine] = useState(false)

  const hasHeld = sources.some((s) => s.held)
  const pool = useMemo(() => (mine ? sources.filter((s) => s.held) : sources), [sources, mine])
  const s2 = useMemo(() => latestSessions(sources, 2), [sources])
  const s7 = useMemo(() => latestSessions(sources, 7), [sources])
  const hasDetail = sources.some((s) => s.sig?.last_sessions?.length)

  const buys = useMemo(() => buildBuys(pool, window === 7 ? s7 : s2, window, fmt, sessionOpen), [pool, window, s2, s7, fmt, sessionOpen])
  const sells = useMemo(() => buildSells(pool, s7, fmt, sessionOpen), [pool, s7, fmt, sessionOpen])
  const counts = useMemo(
    () => ({
      2: buildBuys(pool, s2, 2, fmt, sessionOpen).filter((r) => !r.waiting).length,
      7: buildBuys(pool, s7, 7, fmt, sessionOpen).filter((r) => !r.waiting).length,
      open: buildBuys(pool, s2, 'open', fmt, sessionOpen).filter((r) => !r.waiting).length,
    }),
    [pool, s2, s7, fmt, sessionOpen],
  )
  const hasExitData = sources.some((s) => s.sig?.swing?.exits || s.sig?.ath?.exits)

  if (!hasDetail) {
    return (
      <div className="card">
        <p className="card-t">Call details are not in the saved signals yet</p>
        <p className="card-s">Press Refresh once to load them.</p>
      </div>
    )
  }

  const rows = side === 'buy' ? buys : sells
  const filled = rows.filter((r) => !r.waiting)
  const waiting = rows.filter((r) => r.waiting)
  const anyLive = rows.some((r) => r.live)
  const windowLabel = window === 'open' ? 'Every position that is open now' : `Buys filled in the last ${window} sessions (${s7.slice(-window).map(longDate).join(', ')})`

  return (
    <div className="calls">
      <div className="calls-bar">
        <div className="seg seg-lg" role="group" aria-label="Buy or sell calls">
          <button type="button" className={side === 'buy' ? 'on' : ''} aria-pressed={side === 'buy'} onClick={() => setSide('buy')}>
            Buy calls
            <span className="cnt num">{counts[window]}</span>
          </button>
          <button type="button" className={side === 'sell' ? 'on' : ''} aria-pressed={side === 'sell'} onClick={() => setSide('sell')}>
            Sell calls
            <span className="cnt num">{sells.filter((r) => !r.waiting).length}</span>
          </button>
        </div>
        {side === 'buy' && (
          <div className="seg" role="group" aria-label="Period">
            {(
              [
                [2, 'Last 2 sessions'],
                [7, 'Last 7 sessions'],
                ['open', 'All open'],
              ] as const
            ).map(([id, label]) => (
              <button key={String(id)} type="button" className={window === id ? 'on' : ''} aria-pressed={window === id} onClick={() => setWindow(id)}>
                {label}
                <span className="cnt num">{counts[id]}</span>
              </button>
            ))}
          </div>
        )}
        {hasHeld && (
          <label className="chk">
            <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            Only my holdings
          </label>
        )}
      </div>

      <p className="calls-intro">
        {side === 'buy'
          ? `${windowLabel}. Signals use today's live price as the latest bar. ${anyLive ? 'Calls tagged Live fired in the session that is still open and can change before the 15:30 close.' : ''}`
          : `Positions the strategies closed in the last 7 sessions (${s7.map(longDate).join(', ')}). ${anyLive ? 'Calls tagged Live fired in the session that is still open.' : ''}`}
      </p>
      {side === 'sell' && !hasExitData && <p className="calls-intro">Sell details are not in the saved signals yet. Press Refresh once to load them.</p>}

      {(['swing', 'ath'] as const).map((kind) => (
        <CallTable
          key={`${side}-${kind}-${window}`}
          kind={kind}
          side={side}
          rows={filled.filter((r) => r.kind === kind)}
          fmt={fmt}
          empty={side === 'buy' ? (window === 'open' ? 'No open positions.' : 'No buys filled in this period.') : 'No sells in the last 7 sessions.'}
        />
      ))}
      {waiting.length > 0 && (
        <CallTable
          key={`${side}-waiting`}
          kind="swing"
          side={side}
          rows={waiting}
          fmt={fmt}
          title={side === 'buy' ? 'Swing buys waiting to fill' : 'Swing sells waiting to fill'}
          sub={`The latest session's Swing ${side} signals. The strategy trades at the next open, so none has filled yet; the price shown is the signal close and the real fill can differ.`}
          accent="var(--warn)"
          empty="Nothing is waiting to fill."
        />
      )}
    </div>
  )
}
