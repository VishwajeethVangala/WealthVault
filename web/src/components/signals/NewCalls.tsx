import React, { useEffect, useMemo, useState } from 'react'
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

type Kind = 'ath'
export type BuyWindow = 2 | 7 | 'open'

const STRATEGY: Record<Kind, { title: string; sub: string; accent: string }> = {
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

/** Today's date when the signals were rebuilt on a live price (today's bar is still forming), else null. */
export const liveSessionDate = (sources: CallSource[]): string | null => {
  const days = sources.map((s) => s.sig?.live_date).filter(Boolean) as string[]
  return days.length > 0 ? days.sort().slice(-1)[0] : null
}

/**
 * The window for "last `n` sessions": the `n` most recent FINISHED sessions seen across all stocks (each stock
 * reports its own), plus today when live prices are in. Today never pushes a finished session out of the window.
 */
export const latestSessions = (sources: CallSource[], n = 2): string[] => {
  const live = new Set(sources.map((s) => s.sig?.live_date).filter(Boolean) as string[])
  const done = new Set<string>()
  sources.forEach((s) => s.sig?.last_sessions?.forEach((d) => !live.has(d) && done.add(d)))
  const finished = [...done].sort().slice(-n)
  const last = finished[finished.length - 1] ?? ''
  return [...finished, ...[...live].filter((d) => d > last).sort()]
}

const signed = (v: number | null | undefined) => (v == null ? DASH : `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(1)}%`)

/** Buys: filled inside the window, or (window 'open') every position that is open now, as the Strategies pages list them. */
export const buildBuys = (sources: CallSource[], sessions: string[], window: BuyWindow, fmt: Fmt, sessionOpen: boolean): Row[] => {
  const out: Row[] = []
  const p = (v: number | null | undefined) => fmt.price(v)
  const inWindow = (d: string | null | undefined) => !!d && (window === 'open' || sessions.includes(d))

  sources.forEach((src) => {
    const { sig } = src
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

/**
 * Sells: trades the strategy closed inside the window. Window
 * 'open' means every closed trade on record (the latest few per stock and strategy), however long ago.
 */
export const buildSells = (sources: CallSource[], sessions: string[], fmt: Fmt, sessionOpen: boolean, window: BuyWindow = 7): Row[] => {
  const out: Row[] = []
  const inWindow = (d: string) => window === 'open' || sessions.includes(d)
  const p = (v: number | null | undefined) => fmt.price(v)
  const ended = (entryDate: string, entryPrice: number | null | undefined, exitPrice: number | null | undefined, pnl: number | null | undefined) =>
    `Bought ${short(entryDate)} at ${p(entryPrice)}, sold ${p(exitPrice)}${pnl != null ? ` (${signed(pnl)})` : ''}`

  sources.forEach((src) => {
    const { sig } = src
    sig?.ath?.exits?.forEach((e, i) => {
      if (!inWindow(e.exit_date)) return
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

const CallTable: React.FC<{ kind: Kind; side: 'buy' | 'sell'; rows: Row[]; fmt: Fmt; empty: string; title?: string; sub?: string; accent?: string; startOpen?: boolean }> = ({
  startOpen = false,
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
  const [open, setOpen] = useState(startOpen && rows.length > 0)
  // a link that asks for these rows open must still open them when the data arrives a moment later
  const hasRows = rows.length > 0
  useEffect(() => {
    if (startOpen && hasRows) setOpen(true)
  }, [startOpen, hasRows])
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
    <details className="card callsec" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
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

export const CallsView: React.FC<{ sources: CallSource[]; fmt: Fmt; sessionOpen?: boolean; defaultWindow?: BuyWindow; defaultSide?: 'buy' | 'sell'; expand?: boolean }> = ({
  sources,
  fmt,
  sessionOpen = false,
  defaultWindow = 2,
  defaultSide = 'buy',
  expand = false,
}) => {
  const [side, setSide] = useState<'buy' | 'sell'>(defaultSide)
  const [window, setWindow] = useState<BuyWindow>(defaultWindow)
  const [mine, setMine] = useState(false)

  const hasHeld = sources.some((s) => s.held)
  const pool = useMemo(() => (mine ? sources.filter((s) => s.held) : sources), [sources, mine])
  const s2 = useMemo(() => latestSessions(sources, 2), [sources])
  const s7 = useMemo(() => latestSessions(sources, 7), [sources])
  const today = useMemo(() => liveSessionDate(sources), [sources])
  const hasDetail = sources.some((s) => s.sig?.last_sessions?.length)

  const buys = useMemo(() => buildBuys(pool, window === 7 ? s7 : s2, window, fmt, sessionOpen), [pool, window, s2, s7, fmt, sessionOpen])
  const sells = useMemo(() => buildSells(pool, window === 7 ? s7 : s2, fmt, sessionOpen, window), [pool, window, s2, s7, fmt, sessionOpen])
  const sellCounts = useMemo(
    () => ({
      2: buildSells(pool, s2, fmt, sessionOpen, 2).filter((r) => !r.waiting).length,
      7: buildSells(pool, s7, fmt, sessionOpen, 7).filter((r) => !r.waiting).length,
      open: buildSells(pool, s2, fmt, sessionOpen, 'open').filter((r) => !r.waiting).length,
    }),
    [pool, s2, s7, fmt, sessionOpen],
  )
  const counts = useMemo(
    () => ({
      2: buildBuys(pool, s2, 2, fmt, sessionOpen).filter((r) => !r.waiting).length,
      7: buildBuys(pool, s7, 7, fmt, sessionOpen).filter((r) => !r.waiting).length,
      open: buildBuys(pool, s2, 'open', fmt, sessionOpen).filter((r) => !r.waiting).length,
    }),
    [pool, s2, s7, fmt, sessionOpen],
  )
  const hasExitData = sources.some((s) => s.sig?.ath?.exits)

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
  const anyLive = rows.some((r) => r.live)
  const inWindow = window === 7 ? s7 : s2
  const todayNote = today && inWindow.includes(today) ? ` plus today, live (${longDate(today)})` : ''
  const windowLabel =
    window === 'open'
      ? 'Every position that is open now'
      : `Buys filled in the last ${window} sessions${todayNote} (${inWindow.map(longDate).join(', ')})`

  const sellLabel =
    window === 'open'
      ? 'Every closed trade on record: the latest few per stock and strategy, however long ago'
      : `Positions the strategies closed in the last ${window} sessions${todayNote} (${inWindow.map(longDate).join(', ')})`

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
            <span className="cnt num">{sellCounts[window]}</span>
          </button>
        </div>
        <div className="seg" role="group" aria-label="Period">
          {(
            [
              [2, 'Last 2 sessions'],
              [7, 'Last 7 sessions'],
              ['open', side === 'buy' ? 'All open' : 'All recorded'],
            ] as const
          ).map(([id, label]) => (
            <button key={String(id)} type="button" className={window === id ? 'on' : ''} aria-pressed={window === id} onClick={() => setWindow(id)}>
              {label}
              <span className="cnt num">{(side === 'buy' ? counts : sellCounts)[id]}</span>
            </button>
          ))}
        </div>
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
          : `${sellLabel}. ${anyLive ? 'Calls tagged Live fired in the session that is still open.' : ''}`}
      </p>
      {side === 'sell' && !hasExitData && <p className="calls-intro">Sell details are not in the saved signals yet. Press Refresh once to load them.</p>}

      {(['ath'] as const).map((kind) => (
        <CallTable
          key={`${side}-${kind}-${window}`}
          kind={kind}
          side={side}
          rows={filled.filter((r) => r.kind === kind)}
          startOpen={expand}
          fmt={fmt}
          empty={side === 'buy' ? (window === 'open' ? 'No open positions.' : 'No buys filled in this period.') : window === 'open' ? 'No closed trades on record.' : 'No sells in this period.'}
        />
      ))}
    </div>
  )
}
