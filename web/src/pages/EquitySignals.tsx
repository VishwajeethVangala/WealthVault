import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowDown, ArrowUp, RefreshCw, Search } from 'lucide-react'
import { fetchSignals, refreshSignals } from '../utils/api'
import { usePortfolio } from '../context/PortfolioContext'
import { classifyAssetClass, brokerLabel } from '../utils/portfolioFilters'
import { pct, signedMoney as fmtSigned, tone, weight } from '../utils/format'
import { useMoney } from '../utils/useMoney'
import { buildInstruments, type Instrument } from '../components/holdings/holdingsModel'
import type { AthSignal, MomentumSignal, SignalsResponse, StockSignals, SwingSignal } from '../types'

type Lean = 'bull' | 'bear' | 'neutral'
type Alignment = 'all-bull' | 'mixed' | 'all-bear' | 'none'

interface Row {
  inst: Instrument
  sig?: StockSignals
  leans: Lean[]
  alignment: Alignment
  swingSince: { pct: number; abs: number } | null
  athSince: { pct: number; abs: number } | null
}

const DASH = '—'

const dateFmt = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : DASH

const momentumLean = (m: MomentumSignal): Lean =>
  /uptrend/i.test(m.verdict) ? 'bull' : /downtrend/i.test(m.verdict) ? 'bear' : 'neutral'

const swingLean = (s: SwingSignal): Lean =>
  s.state === 'IN_POSITION' ? (s.pending_order === 'SELL' ? 'bear' : 'bull') : s.pending_order === 'BUY' ? 'bull' : s.regime_bullish ? 'neutral' : 'bear'

const athLean = (a: AthSignal): Lean => (a.state === 'IN_POSITION' ? 'bull' : a.last_signal === 'SELL' ? 'bear' : 'neutral')

const momentumBadge = (m: MomentumSignal) => {
  const lean = momentumLean(m)
  return { cls: lean === 'bull' ? 'ok' : lean === 'bear' ? 'bad' : 'off', text: m.verdict }
}

const swingBadge = (s: SwingSignal) => {
  if (s.state === 'IN_POSITION') return s.pending_order === 'SELL' ? { cls: 'warn', text: 'Sell signal' } : { cls: 'ok', text: 'In position' }
  if (s.pending_order === 'BUY') return { cls: 'info', text: 'Buy signal' }
  return s.regime_bullish ? { cls: 'off', text: 'Waiting for entry' } : { cls: 'off', text: 'No trade' }
}

const athBadge = (a: AthSignal) => {
  if (a.state === 'IN_POSITION') return { cls: 'ok', text: 'In position' }
  if (a.last_signal === 'SELL') return { cls: 'warn', text: 'Exited' }
  return a.in_window ? { cls: 'info', text: 'Setup active' } : { cls: 'off', text: 'No setup' }
}

const since = (entry: number | null | undefined, ltp: number): { pct: number; abs: number } | null =>
  entry && entry > 0 && ltp > 0 ? { pct: ((ltp - entry) / entry) * 100, abs: ltp - entry } : null

type SortKey = 'sym' | 'inv' | 'cur' | 'pnlPct' | 'momentum' | 'swing' | 'ath' | 'align'
const ALIGN_ORDER: Record<Alignment, number> = { 'all-bull': 3, mixed: 2, none: 1, 'all-bear': 0 }

const sortValue = (r: Row, key: SortKey): string | number | null => {
  switch (key) {
    case 'sym':
      return r.inst.sym.toLowerCase()
    case 'inv':
      return r.inst.inv
    case 'cur':
      return r.inst.cur
    case 'pnlPct':
      return r.inst.pnlPct
    case 'momentum':
      return r.sig?.momentum ? r.sig.momentum.score / (r.sig.momentum.max || 1) : null
    case 'swing':
      return r.swingSince ? r.swingSince.pct : null
    case 'ath':
      return r.athSince ? r.athSince.pct : null
    case 'align':
      return r.sig ? ALIGN_ORDER[r.alignment] : null
  }
}

export const EquitySignals: React.FC = () => {
  const { holdings, loading: portfolioLoading } = usePortfolio()
  const { money, price, signedMoney, hidden } = useMoney()
  const perShare = (v: number) => (hidden ? '₹ ••••' : fmtSigned(v, 2))

  const [data, setData] = useState<SignalsResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | Alignment | 'trade'>('all')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'cur', dir: -1 })
  const [starting, setStarting] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const load = useCallback(async () => {
    try {
      const res = await fetchSignals()
      setData(res)
      setLoadError(null)
      return res
    } catch (err: any) {
      setLoadError(err?.message || 'Could not load signals')
      return null
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Poll while a refresh is running
  const running = data?.job.state === 'running'
  useEffect(() => {
    if (!running) return
    timer.current = window.setInterval(load, 2000)
    return () => window.clearInterval(timer.current)
  }, [running, load])

  const startRefresh = async () => {
    setStarting(true)
    try {
      await refreshSignals()
      await load()
    } catch (err: any) {
      setLoadError(err?.message || 'Could not start the refresh')
    } finally {
      setStarting(false)
    }
  }

  const instruments = useMemo(() => buildInstruments(holdings.filter((h) => classifyAssetClass(h) === 'EQUITY')), [holdings])

  const rows = useMemo<Row[]>(() => {
    const map = data?.symbol_map ?? {}
    const sigs = data?.signals ?? {}
    return instruments.map((inst) => {
      const id = inst.lots.map((l) => map[l.holding.instrument_symbol]).find(Boolean)
      const sig = id ? sigs[id] : undefined
      const leans: Lean[] = []
      if (sig?.momentum) leans.push(momentumLean(sig.momentum))
      if (sig?.swing) leans.push(swingLean(sig.swing))
      if (sig?.ath) leans.push(athLean(sig.ath))
      const bull = leans.filter((l) => l === 'bull').length
      const bear = leans.filter((l) => l === 'bear').length
      const alignment: Alignment =
        leans.length < 2 ? 'none' : bull === leans.length ? 'all-bull' : bear === leans.length ? 'all-bear' : 'mixed'
      return {
        inst,
        sig,
        leans,
        alignment,
        swingSince: sig?.swing?.state === 'IN_POSITION' ? since(sig.swing.entry_price, inst.ltp) : null,
        athSince: sig?.ath?.state === 'IN_POSITION' ? since(sig.ath.entry_price, inst.ltp) : null,
      }
    })
  }, [instruments, data])

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = rows.filter((r) => {
      if (needle && !`${r.inst.sym} ${r.sig?.name ?? ''}`.toLowerCase().includes(needle)) return false
      if (filter === 'trade') return r.sig?.swing?.state === 'IN_POSITION' || r.sig?.ath?.state === 'IN_POSITION'
      if (filter !== 'all') return r.alignment === filter
      return true
    })
    return [...list].sort((a, b) => {
      const x = sortValue(a, sort.key)
      const y = sortValue(b, sort.key)
      if (x === null && y === null) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (typeof x === 'string' && typeof y === 'string' ? x.localeCompare(y) : (x as number) - (y as number)) * sort.dir
    })
  }, [rows, q, filter, sort])

  const summary = useMemo(() => {
    const withSig = rows.filter((r) => r.sig?.momentum)
    const up = withSig.filter((r) => momentumLean(r.sig!.momentum!) === 'bull').length
    const down = withSig.filter((r) => momentumLean(r.sig!.momentum!) === 'bear').length
    const swing = rows.filter((r) => r.sig?.swing?.state === 'IN_POSITION')
    const ath = rows.filter((r) => r.sig?.ath?.state === 'IN_POSITION')
    const review = rows.filter((r) => r.alignment === 'all-bear')
    return {
      covered: rows.filter((r) => r.sig && (r.sig.momentum || r.sig.swing || r.sig.ath)).length,
      up,
      down,
      neutral: withSig.length - up - down,
      swing: swing.length,
      swingValue: swing.reduce((s, r) => s + r.inst.cur, 0),
      ath: ath.length,
      athValue: ath.reduce((s, r) => s + r.inst.cur, 0),
      review: review.length,
      reviewValue: review.reduce((s, r) => s + r.inst.cur, 0),
    }
  }, [rows])

  const computedAt = useMemo(() => {
    const times = Object.values(data?.signals ?? {})
      .map((s) => s.computed_at)
      .filter(Boolean) as string[]
    return times.sort()[0]
  }, [data])

  const sortBy = (key: SortKey) => setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === 'sym' ? 1 : -1 }))
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

  if (portfolioLoading && holdings.length === 0) {
    return (
      <div className="page-in" aria-busy="true">
        <p className="sub">Loading your holdings…</p>
      </div>
    )
  }

  return (
    <div className="page-in">
      {loadError && (
        <div className="banner bad" role="alert">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">{loadError}</div>
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

      <section className="sum" aria-label="Signal summary">
        <div className="card">
          <div className="lbl">Stocks covered</div>
          <div className="val num">
            {summary.covered} / {rows.length}
          </div>
          <div className="foot">{rows.length - summary.covered > 0 ? `${rows.length - summary.covered} without signals` : 'All analysed'}</div>
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
          <div className="foot">{money(summary.swingValue)} of holdings</div>
        </div>
        <div className="card">
          <div className="lbl">In an ATH trade</div>
          <div className="val num">{summary.ath}</div>
          <div className="foot">{money(summary.athValue)} of holdings</div>
        </div>
        <div className="card">
          <div className="lbl">Review: all bearish</div>
          <div className={`val num ${summary.review > 0 ? 'neg' : ''}`}>{summary.review}</div>
          <div className="foot">{money(summary.reviewValue)} of holdings</div>
        </div>
      </section>

      <section className="toolbar" aria-label="Filters">
        <div className="search">
          <label className="sr" htmlFor="sig-q">
            Search stocks
          </label>
          <Search size={16} strokeWidth={1.75} aria-hidden="true" />
          <input id="sig-q" className="input" type="search" placeholder="Search stock" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="seg" role="group" aria-label="Signal alignment">
          {(
            [
              ['all', 'All'],
              ['all-bull', 'All bullish'],
              ['mixed', 'Mixed'],
              ['all-bear', 'All bearish'],
              ['trade', 'In a trade'],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" className={filter === id ? 'on' : ''} aria-pressed={filter === id} onClick={() => setFilter(id)}>
              {label}
            </button>
          ))}
        </div>
        <span className="spacer" />
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
          {!running && computedAt && (
            <span className="sub">
              Computed {new Date(computedAt).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          <button className="btn btn-primary" onClick={startRefresh} disabled={running || starting}>
            <RefreshCw size={16} strokeWidth={1.75} className={running ? 'spin' : ''} />
            {running ? 'Refreshing…' : 'Refresh signals'}
          </button>
        </div>
      </section>

      {rows.length === 0 ? (
        <div className="card">
          <p className="card-t">No stock holdings</p>
          <p className="card-s">Signals cover Indian-listed stocks and ETFs. Mutual funds, US stocks, NPS and gold are not included.</p>
        </div>
      ) : summary.covered === 0 && !running ? (
        <div className="card">
          <p className="card-t">Signals have not been computed yet</p>
          <p className="card-s">
            Press Refresh signals to analyse your {rows.length} stocks. The first run takes a minute or two; results are saved, so the page opens instantly after that.
          </p>
        </div>
      ) : (
        <div className="card stbl-wrap">
          <table className="stbl">
            <thead>
              <tr>
                {head('sym', 'Stock')}
                {head('inv', 'Invested', true)}
                {head('cur', 'Current', true)}
                {head('pnlPct', 'P&L', true)}
                {head('momentum', 'Momentum')}
                {head('swing', 'Swing V2.1')}
                {head('ath', '200-DMA ATH breakout')}
                {head('align', 'Signal alignment')}
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const { inst, sig } = r
                const m = sig?.momentum
                const s = sig?.swing
                const a = sig?.ath
                const bull = r.leans.filter((l) => l === 'bull').length
                const bear = r.leans.filter((l) => l === 'bear').length
                return (
                  <tr key={inst.key}>
                    <td>
                      <div className="sg-sym">{inst.sym}</div>
                      <div className="sg-sub">
                        {inst.brokers.map(brokerLabel).join(' + ')} · {inst.qty.toLocaleString('en-IN')} @ {price(inst.avg)}
                      </div>
                      <div className="sg-sub num">LTP {price(inst.ltp)}</div>
                    </td>
                    <td className="r num">{money(inst.inv)}</td>
                    <td className="r num">{money(inst.cur)}</td>
                    <td className="r num">
                      <div className={tone(inst.pnl)}>{signedMoney(inst.pnl)}</div>
                      <div className={`sg-sub ${tone(inst.pnlPct)}`}>{pct(inst.pnlPct)}</div>
                    </td>

                    <td>
                      {m ? (
                        <div className="sg-cell">
                          <span className={`badge ${momentumBadge(m).cls}`}>{momentumBadge(m).text}</span>
                          <span className="sg-line num">
                            Score {m.score}/{m.max}
                          </span>
                          {m.range_pos !== null && (
                            <>
                              <div className="rng" title={`52-week range ${price(m.low_52w)} to ${price(m.high_52w)}`}>
                                <i style={{ left: `${Math.min(100, Math.max(0, m.range_pos))}%` }} />
                              </div>
                              <span className="sg-line dim num">{pct(m.pct_from_52w_high, 1)} from 52W high</span>
                            </>
                          )}
                        </div>
                      ) : (
                        <span className="sg-na">{sig?.errors.momentum ?? sig?.errors.all ?? DASH}</span>
                      )}
                    </td>

                    <td>
                      {s ? (
                        <div className="sg-cell" title={s.detail}>
                          <span className={`badge ${swingBadge(s).cls}`}>{swingBadge(s).text}</span>
                          {s.state === 'IN_POSITION' ? (
                            <>
                              <span className="sg-line">
                                Entered {dateFmt(s.entry_date)}
                                {s.bars_held != null ? ` · ${s.bars_held} days` : ''}
                              </span>
                              {r.swingSince && (
                                <span className={`sg-line num ${tone(r.swingSince.abs)}`}>
                                  {perShare(r.swingSince.abs)}/sh ({pct(r.swingSince.pct)}) since entry
                                </span>
                              )}
                              {s.stop_price != null && inst.ltp > 0 && (
                                <span className="sg-line dim num">
                                  Stop {price(s.stop_price)} · {weight(((inst.ltp - s.stop_price) / inst.ltp) * 100, 1)} below
                                </span>
                              )}
                            </>
                          ) : (
                            <span className="sg-line dim">{s.headline}</span>
                          )}
                        </div>
                      ) : (
                        <span className="sg-na">{sig?.errors.swing ?? sig?.errors.all ?? DASH}</span>
                      )}
                    </td>

                    <td>
                      {a ? (
                        <div className="sg-cell" title={a.detail}>
                          <span className={`badge ${athBadge(a).cls}`}>{athBadge(a).text}</span>
                          {a.state === 'IN_POSITION' ? (
                            <>
                              <span className="sg-line">
                                Entered {dateFmt(a.entry_date)}
                                {a.bars_held != null ? ` · ${a.bars_held} days` : ''}
                              </span>
                              {r.athSince && (
                                <span className={`sg-line num ${tone(r.athSince.abs)}`}>
                                  {perShare(r.athSince.abs)}/sh ({pct(r.athSince.pct)}) since entry
                                </span>
                              )}
                              {a.pct_above_dma != null && <span className="sg-line dim num">{weight(a.pct_above_dma, 1)} above 200-DMA</span>}
                            </>
                          ) : a.in_window ? (
                            <span className="sg-line dim num">
                              {a.window_days_left != null ? `${a.window_days_left} days left · ` : ''}
                              {a.pct_to_ath != null ? `${weight(a.pct_to_ath, 1)} to ATH` : ''}
                            </span>
                          ) : (
                            <span className="sg-line dim">{a.headline}</span>
                          )}
                        </div>
                      ) : (
                        <span className="sg-na">{sig?.errors.ath ?? sig?.errors.all ?? DASH}</span>
                      )}
                    </td>

                    <td>
                      {r.alignment === 'none' ? (
                        <span className="sg-na">{sig ? 'Too few signals' : DASH}</span>
                      ) : (
                        <div className="sg-cell">
                          <span className={`badge ${r.alignment === 'all-bull' ? 'ok' : r.alignment === 'all-bear' ? 'bad' : 'off'}`}>
                            {r.alignment === 'all-bull' ? 'All bullish' : r.alignment === 'all-bear' ? 'All bearish' : 'Mixed'}
                          </span>
                          <span className="sg-line dim num">
                            {bull} bullish · {bear} bearish
                          </span>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
              {visible.length === 0 && (
                <tr>
                  <td colSpan={8}>
                    <span className="sg-na">No stocks match this filter.</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="sg-legend">
        Swing V2.1 and ATH entries are the strategies&apos; own signals on daily candles, not your actual buys. &quot;Since entry&quot; compares today&apos;s price with the
        strategy entry price, per share. Bullish: uptrend, a strategy in position, or a buy signal. Bearish: downtrend, a failing Swing trend filter, a sell signal or an
        exit. Mutual funds, US stocks, NPS and gold are not covered. This is a rules-based reading of past prices, not advice.
      </p>
    </div>
  )
}
