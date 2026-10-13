import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowDown, ArrowUp, ExternalLink, RefreshCw, Search } from 'lucide-react'
import { fetchStage2, fetchStage2Live, fetchStage2LiveSignals, refreshStage2 } from '../utils/api'
import { useLiveSignals } from '../components/signals/useLiveSignals'
import { pct, price, tone } from '../utils/format'
import {
  ALIGN_ORDER,
  AlignmentCell,
  AthCell,
  DASH,
  MomentumCell,
  SwingCell,
  momentumLean,
  readSignals,
  type Fmt,
  type Reading,
} from '../components/signals/signalKit'
import { CallsView, type CallSource } from '../components/signals/NewCalls'
import type { Stage2Response, Stage2Row, StockSignals } from '../types'

type Filter = 'all' | 'new' | 'bull' | 'fresh' | 'held'
type SortKey = 'sym' | 'price' | 'day' | 'vol' | 'momentum' | 'swing' | 'ath' | 'align' | `x:${string}`

interface Row extends Reading {
  row: Stage2Row
  sig?: StockSignals
  ltp: number
  dayPct: number | null
  /** a Swing or ATH trade that opened within the last FRESH_DAYS trading days */
  fresh: boolean
}

const FRESH_DAYS = 10
const PAGE = 100
const fmt: Fmt = {
  price: (v) => price(v),
  perShare: (v) => `${v < 0 ? '−' : '+'}₹${Math.abs(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
}

/** NSE cash session, Mon-Fri 09:15-15:30 IST. */
const marketOpen = (): boolean => {
  const ist = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const mins = ist.getHours() * 60 + ist.getMinutes()
  return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
}

const compactVol = (v: number) => (v >= 1e7 ? `${(v / 1e7).toFixed(2)} Cr` : v >= 1e5 ? `${(v / 1e5).toFixed(2)} L` : v.toLocaleString('en-IN'))

const titleCase = (v: string) =>
  v
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')

const LABELS: Record<string, string> = { market_cap: 'Market cap', obv: 'OBV' }
const columnLabel = (key: string) => LABELS[key] ?? titleCase(key.split('_').join(' '))

/** Chartink reports market cap in crore rupees. */
const marketCap = (v: number) => (v >= 1e5 ? `₹${(v / 1e5).toFixed(2)} L Cr` : `₹${Math.round(v).toLocaleString('en-IN')} Cr`)

/** Display form of an extra Chartink column. */
const extraCell = (key: string, value: unknown): string => {
  if (value == null || value === '') return DASH
  if (key === 'market_cap' && typeof value === 'number') return value > 0 ? marketCap(value) : DASH
  if (key === 'sector') return titleCase(String(value))
  if (typeof value === 'number') return value.toLocaleString('en-IN', { maximumFractionDigits: 2 })
  return String(value)
}

const sortValue = (r: Row, key: SortKey): string | number | null => {
  if (key.startsWith('x:')) {
    const v = r.row[key.slice(2)]
    return typeof v === 'number' ? v : typeof v === 'string' && v ? v.toLowerCase() : null
  }
  switch (key) {
    case 'sym':
      return r.row.name.toLowerCase()
    case 'price':
      return r.ltp
    case 'day':
      return r.dayPct
    case 'vol':
      return r.row.volume
    case 'momentum':
      return r.sig?.momentum ? r.sig.momentum.score / (r.sig.momentum.max || 1) : null
    case 'swing':
      return r.swingSince ? r.swingSince.pct : null
    case 'ath':
      return r.athSince ? r.athSince.pct : null
    case 'align':
      return r.sig ? ALIGN_ORDER[r.alignment] : null
    default:
      return null
  }
}

export const Stage2: React.FC = () => {
  const [data, setData] = useState<Stage2Response | null>(null)
  const [live, setLive] = useState<Record<string, { price: number; day_change_pct: number | null }>>({})
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sector, setSector] = useState('all')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'align', dir: -1 })
  const [shown, setShown] = useState(PAGE)
  const [starting, setStarting] = useState(false)
  const [view, setView] = useState<'calls' | 'list'>('calls')

  const load = useCallback(async () => {
    try {
      const res = await fetchStage2()
      setData(res)
      setError(null)
      return res
    } catch (err: any) {
      setError(err?.message || 'Could not load the Stage 2 list')
      return null
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const running = data?.job.state === 'running'
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(load, 2000)
    return () => window.clearInterval(t)
  }, [running, load])

  // Live Kite prices: every 20s during market hours, every 5 min otherwise; paused while the tab is hidden
  const hasList = !!data?.list
  useEffect(() => {
    if (!hasList) return
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchStage2Live()
          if (!stop) setLive(res.quotes)
        } catch {
          /* keep the last prices */
        }
      }
      if (!stop) timer = window.setTimeout(tick, marketOpen() ? 20_000 : 300_000)
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [hasList])

  const startRefresh = async () => {
    setStarting(true)
    try {
      await refreshStage2()
      await load()
    } catch (err: any) {
      setError(err?.message || 'Could not start the refresh')
    } finally {
      setStarting(false)
    }
  }

  const list = data?.list ?? null

  // Signals rebuilt on the live price: from the 09:15 open (every minute while the session runs, once more after the close)
  const sessionOpen = marketOpen()
  const liveSignals = useLiveSignals(fetchStage2LiveSignals, hasList, () => (marketOpen() ? 60_000 : 600_000), 'stage2', data?.job.finished_at)

  const rows = useMemo<Row[]>(() => {
    if (!list) return []
    return list.rows.map((row) => {
      const code = row.nsecode.toUpperCase()
      const sig = liveSignals.signals[code] ?? data?.signals[code]
      const lv = live[row.nsecode]
      const ltp = lv?.price ?? row.close
      const reading = readSignals(sig, ltp)
      const fresh =
        (sig?.swing?.state === 'IN_POSITION' && (sig.swing.bars_held ?? 999) <= FRESH_DAYS) ||
        (sig?.ath?.state === 'IN_POSITION' && (sig.ath.bars_held ?? 999) <= FRESH_DAYS)
      return { row, sig, ltp, dayPct: lv?.day_change_pct ?? row.per_chg ?? null, fresh, ...reading }
    })
  }, [list, data, live, liveSignals.signals])

  const counts = useMemo(
    () => ({
      all: rows.length,
      new: rows.filter((r) => r.row.is_new).length,
      bull: rows.filter((r) => r.alignment === 'all-bull').length,
      fresh: rows.filter((r) => r.fresh).length,
      held: rows.filter((r) => r.row.held).length,
    }),
    [rows],
  )

  const callSources = useMemo<CallSource[]>(
    () =>
      rows.map((r) => ({
        code: r.row.nsecode,
        name: r.row.name,
        sector: typeof r.row.sector === 'string' ? titleCase(r.row.sector) : undefined,
        href: `/momentum?symbol=${encodeURIComponent(r.row.nsecode)}`,
        held: r.row.held,
        isNew: r.row.is_new,
        sig: r.sig,
        ltp: r.ltp,
      })),
    [rows],
  )

  const sectors = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((r) => {
      const v = r.row.sector
      if (typeof v === 'string' && v) m.set(v, (m.get(v) ?? 0) + 1)
    })
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [rows])

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const out = rows.filter((r) => {
      if (needle && !`${r.row.name} ${r.row.nsecode}`.toLowerCase().includes(needle)) return false
      if (sector !== 'all' && String(r.row.sector ?? '') !== sector) return false
      if (filter === 'new') return !!r.row.is_new
      if (filter === 'bull') return r.alignment === 'all-bull'
      if (filter === 'fresh') return r.fresh
      if (filter === 'held') return r.row.held
      return true
    })
    return out.sort((a, b) => {
      const x = sortValue(a, sort.key)
      const y = sortValue(b, sort.key)
      if (x === null && y === null) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (typeof x === 'string' && typeof y === 'string' ? x.localeCompare(y) : (x as number) - (y as number)) * sort.dir
    })
  }, [rows, q, filter, sort, sector])

  const summary = useMemo(() => {
    const withM = rows.filter((r) => r.sig?.momentum)
    const up = withM.filter((r) => momentumLean(r.sig!.momentum!) === 'bull').length
    const down = withM.filter((r) => momentumLean(r.sig!.momentum!) === 'bear').length
    return {
      covered: rows.filter((r) => r.sig && (r.sig.momentum || r.sig.swing || r.sig.ath)).length,
      up,
      down,
      neutral: withM.length - up - down,
      swing: rows.filter((r) => r.sig?.swing?.state === 'IN_POSITION').length,
      ath: rows.filter((r) => r.sig?.ath?.state === 'IN_POSITION').length,
    }
  }, [rows])

  const sortBy = (key: SortKey) => {
    setShown(PAGE)
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === 'sym' ? 1 : -1 }))
  }
  const head = (key: SortKey, label: string, right = false) => (
    <th className={right ? 'r' : ''} aria-sort={sort.key === key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
      <button type="button" onClick={() => sortBy(key)}>
        {label}
        {sort.key === key && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
      </button>
    </th>
  )

  const job = data?.job
  const pctDone = job && job.total > 0 ? Math.round((job.done / job.total) * 100) : 0
  const extras = list?.extra_columns ?? []

  return (
    <div className="page-in">
      {error && (
        <div className="banner bad" role="alert">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">{error}</div>
        </div>
      )}

      {job?.state === 'error' && (
        <div className="banner" role="status">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">
            <b>Refresh stopped.</b> {job.message}
          </div>
          {job.auth_url && (
            <a className="btn btn-primary btn-sm" href={job.auth_url} target="_blank" rel="noreferrer">
              Log in to Kite
            </a>
          )}
        </div>
      )}

      {list && (
        <section className="sum" aria-label="Stage 2 summary">
          <div className="card">
            <div className="lbl">In the screener</div>
            <div className="val num">{rows.length}</div>
            <div className="foot">
              {list.previous_date ? `${counts.new} new · ${list.dropped.length} dropped since ${list.previous_date}` : 'First snapshot, no comparison yet'}
            </div>
          </div>
          <div className="card">
            <div className="lbl">Momentum</div>
            <div className="val num">
              <span className="pos">{summary.up}</span> / {summary.neutral} / <span className="neg">{summary.down}</span>
            </div>
            <div className="foot">Uptrend / neutral / downtrend</div>
          </div>
          <div className="card">
            <div className="lbl">In a Swing trade</div>
            <div className="val num">{summary.swing}</div>
            <div className="foot">{counts.fresh} opened in the last {FRESH_DAYS} days (either strategy)</div>
          </div>
          <div className="card">
            <div className="lbl">In an ATH trade</div>
            <div className="val num">{summary.ath}</div>
            <div className="foot">Stage 2 stocks near or at highs</div>
          </div>
          <div className="card">
            <div className="lbl">All three bullish</div>
            <div className="val num pos">{counts.bull}</div>
            <div className="foot">{counts.held} already in your portfolio</div>
          </div>
        </section>
      )}

      {list && (
        <section className="viewbar" aria-label="View">
          <div className="seg" role="group" aria-label="View">
            <button type="button" className={view === 'calls' ? 'on' : ''} aria-pressed={view === 'calls'} onClick={() => setView('calls')}>
              New buy calls
            </button>
            <button type="button" className={view === 'list' ? 'on' : ''} aria-pressed={view === 'list'} onClick={() => setView('list')}>
              Full list
              <span className="cnt num">{rows.length}</span>
            </button>
          </div>
          <span className="spacer" style={{ flex: 1 }} />
        <div className="sg-run">
          {running && (
            <>
              <div className="sg-progress" role="progressbar" aria-valuenow={pctDone} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${pctDone}%` }} />
              </div>
              <span className="sub num">
                {job!.done} of {job!.total}
              </span>
            </>
          )}
          {!running && liveSignals.at && (
            <span className="sub">Signals on the live price, {new Date(liveSignals.at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</span>
          )}
          {!running && list && (
            <span className="sub">
              Screener read {new Date(list.fetched_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          <button className="btn btn-primary" onClick={startRefresh} disabled={running || starting}>
            <RefreshCw size={16} strokeWidth={1.75} className={running ? 'spin' : ''} />
            {running ? 'Refreshing…' : 'Refresh from Chartink'}
          </button>
        </div>
        </section>
      )}

      {list && view === 'calls' && <CallsView sources={callSources} fmt={fmt} sessionOpen={sessionOpen} />}

      {(!list || view === 'list') && (<section className="toolbar" aria-label="Filters">
        <div className="search">
          <label className="sr" htmlFor="s2-q">
            Search stocks
          </label>
          <Search size={16} strokeWidth={1.75} aria-hidden="true" />
          <input id="s2-q" className="input" type="search" placeholder="Search name or symbol" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="seg" role="group" aria-label="Filter">
          {(
            [
              ['all', 'All'],
              ['new', 'New today'],
              ['bull', 'All bullish'],
              ['fresh', 'Fresh entries'],
              ['held', 'In my portfolio'],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" className={filter === id ? 'on' : ''} aria-pressed={filter === id} onClick={() => { setFilter(id); setShown(PAGE) }}>
              {label}
              <span className="cnt num">{counts[id]}</span>
            </button>
          ))}
        </div>
        {sectors.length > 0 && (
          <>
            <label className="sr" htmlFor="s2-sector">
              Sector
            </label>
            <select
              id="s2-sector"
              className="select"
              value={sector}
              onChange={(e) => {
                setSector(e.target.value)
                setShown(PAGE)
              }}
            >
              <option value="all">All sectors</option>
              {sectors.map(([name, n]) => (
                <option key={name} value={name}>
                  {titleCase(name)} ({n})
                </option>
              ))}
            </select>
          </>
        )}
      </section>)}

      {!list ? (
        <div className="card">
          <p className="card-t">The Stage 2 list has not been fetched yet</p>
          <p className="card-s">
            Press Refresh from Chartink. It reads your saved screener, then runs every stock through momentum, Swing V2.1 and ATH breakout. The first run takes a few minutes for a
            list this size; results are saved, so the page opens instantly after that.
          </p>
        </div>
      ) : (
        view === 'list' && (<>
          <div className="card stbl-wrap">
            <table className="stbl">
              <thead>
                <tr>
                  {head('sym', 'Stock')}
                  {head('price', 'Price', true)}
                  {head('day', 'Day', true)}
                  {head('vol', 'Volume', true)}
                  {head('momentum', 'Momentum')}
                  {head('swing', 'Swing V2.1')}
                  {head('ath', '200-DMA ATH breakout')}
                  {head('align', 'Signal alignment')}
                  {extras.map((k) => head(`x:${k}`, columnLabel(k), k !== 'sector'))}
                </tr>
              </thead>
              <tbody>
                {visible.slice(0, shown).map((r) => (
                  <tr key={r.row.nsecode}>
                    <td>
                      <div className="sg-sym">
                        <Link className="sg-link" to={`/momentum?symbol=${encodeURIComponent(r.row.nsecode)}`} title="Open in Momentum">
                          {r.row.name}
                        </Link>
                        {r.row.is_new && <span className="badge info">New</span>}
                        {r.row.held && <span className="badge ok">Held</span>}
                      </div>
                      <div className="sg-sub mono">{r.row.nsecode}</div>
                    </td>
                    <td className="r num">{fmt.price(r.ltp)}</td>
                    <td className={`r num ${tone(r.dayPct)}`}>{pct(r.dayPct)}</td>
                    <td className="r num">{compactVol(r.row.volume)}</td>
                    <td>
                      <MomentumCell sig={r.sig} fmt={fmt} />
                    </td>
                    <td>
                      <SwingCell sig={r.sig} ltp={r.ltp} reading={r} fmt={fmt} />
                    </td>
                    <td>
                      <AthCell sig={r.sig} reading={r} fmt={fmt} />
                    </td>
                    <td>
                      <AlignmentCell sig={r.sig} reading={r} />
                    </td>
                    {extras.map((k) => (
                      <td key={k} className={k === 'sector' ? '' : 'r num'}>
                        {extraCell(k, r.row[k])}
                      </td>
                    ))}
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={8 + extras.length}>
                      <span className="sg-na">No stocks match this filter.</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            {visible.length > shown && (
              <div style={{ padding: 14, textAlign: 'center', borderTop: '1px solid var(--border)' }}>
                <button className="btn" onClick={() => setShown((n) => n + PAGE)}>
                  Show {Math.min(PAGE, visible.length - shown)} more of {visible.length - shown}
                </button>
              </div>
            )}
          </div>

          {list.dropped.length > 0 && (
            <div className="card">
              <p className="card-t">Dropped out since {list.previous_date}</p>
              <p className="card-s">No longer pass the screener</p>
              <p className="sg-line" style={{ marginTop: 8 }}>
                {list.dropped.map((d) => d.nsecode).join(' · ')}
              </p>
            </div>
          )}

          <details className="card">
            <summary className="card-t" style={{ cursor: 'pointer' }}>
              Screener source and conditions
            </summary>
            <p className="card-s" style={{ margin: '8px 0' }}>
              Stocks come from the Chartink screener &quot;{list.title.replace(/,\s*Technical Analysis Scanner\.?$/i, '')}&quot;. Edit it on Chartink (conditions or extra columns) and press
              Refresh; the page reads the screener&apos;s current definition each time.{' '}
              <a className="link" href={list.url} target="_blank" rel="noreferrer">
                Open on Chartink <ExternalLink size={12} style={{ verticalAlign: '-1px' }} />
              </a>
            </p>
          </details>

          <p className="sg-legend">
            The list is Chartink&apos;s, read from the site as at its last end-of-day data. Prices and day change are live from Kite while the NSE session is open. Signals are computed
            here from daily candles with today&apos;s bar built from the live price, so they can change until the 15:30 close. Swing V2.1 and ATH entries are the strategies&apos; own signals, not buys you made, and &quot;since entry&quot; is per share. &quot;Fresh entries&quot; are
            trades that opened within the last {FRESH_DAYS} trading days. This is a rules-based reading of past prices, not advice.
          </p>
        </>)
      )}
    </div>
  )
}
