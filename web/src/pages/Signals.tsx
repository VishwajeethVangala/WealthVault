import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowDown, ArrowUp, ExternalLink, RefreshCw, Search } from 'lucide-react'
import { fetchLiveSignals, fetchSignals, fetchStage2, fetchStage2Live, fetchStage2LiveSignals, fetchUsLive, refreshSignals, refreshStage2 } from '../utils/api'
import { useLiveSignals } from '../components/signals/useLiveSignals'
import { FreshnessChip } from '../components/signals/FreshnessChip'
import { StockLink } from '../components/StockLink'
import { CallsView, type CallSource } from '../components/signals/NewCalls'
import { indiaSessionActive, usSessionActive } from '../utils/session'
import { usePortfolio } from '../context/PortfolioContext'
import { classifyAssetClass, brokerLabel } from '../utils/portfolioFilters'
import { pct, signedMoney as fmtSigned, tone } from '../utils/format'
import { useMoney } from '../utils/useMoney'
import { buildInstruments, type Instrument } from '../components/holdings/holdingsModel'
import type { SignalsResponse, Stage2Response, Stage2Row, StockSignals, UsLiveQuote } from '../types'
import {
  ALIGN_ORDER,
  AlignmentCell,
  AthCell,
  DASH,
  MomentumCell,
  momentumLean,
  readSignals,
  type Alignment,
  type Fmt,
  type Reading,
} from '../components/signals/signalKit'

/**
 * One page for every stock worth a signal: the stocks you hold and the stocks on your Chartink Stage 2 screener.
 * A stock that is both appears once, tagged Held and Stage 2. India is held + Stage 2; the US is held only.
 */

type Market = 'in' | 'us'
type Source = 'all' | 'held' | 'stage2' | 'new'
type AlignFilter = 'all' | Alignment | 'trade' | 'fresh'
type SortKey = 'sym' | 'price' | 'day' | 'pos' | 'pnlPct' | 'vol' | 'momentum' | 'ath' | 'align' | `x:${string}`

interface Row extends Reading {
  key: string
  code: string
  name: string
  href: string | null
  inst?: Instrument
  s2?: Stage2Row
  sig?: StockSignals
  /** price per share in the stock's own currency (USD for US stocks, INR for Indian) */
  ltp: number
  dayPct: number | null
  live?: UsLiveQuote
  /** an ATH trade that opened within the last FRESH_DAYS trading days */
  fresh: boolean
}

const FRESH_DAYS = 10
const PAGE = 100

const usd = (v: number | null | undefined, hidden = false): string =>
  v == null || !Number.isFinite(v) ? DASH : hidden ? '$ ••••' : `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const signedUsd = (v: number): string => `${v < 0 ? '−' : '+'}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const tickerOf = (symbol: string): string => symbol.trim().split(/\s+/)[0].toUpperCase()

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
const extraCell = (key: string, value: unknown): string => {
  if (value == null || value === '') return DASH
  if (key === 'market_cap' && typeof value === 'number') return value > 0 ? marketCap(value) : DASH
  if (key === 'sector') return titleCase(String(value))
  if (typeof value === 'number') return value.toLocaleString('en-IN', { maximumFractionDigits: 2 })
  return String(value)
}

/** Exchange id 'NSE:INFY' -> 'INFY'; also drops the trade-for-trade series suffix, so 'MTARTECH-BE' matches 'MTARTECH'. */
const codeOf = (id: string): string => id.split(':').pop()!.toUpperCase().replace(/-(BE|BZ|BL|IL)$/, '')

const sortValue = (r: Row, key: SortKey): string | number | null => {
  if (key.startsWith('x:')) {
    const v = r.s2?.[key.slice(2)]
    return typeof v === 'number' ? v : typeof v === 'string' && v ? v.toLowerCase() : null
  }
  switch (key) {
    case 'sym':
      return r.name.toLowerCase()
    case 'price':
      return r.ltp
    case 'day':
      return r.dayPct
    case 'pos':
      return r.inst ? r.inst.cur : null
    case 'pnlPct':
      return r.inst ? r.inst.pnlPct : null
    case 'vol':
      return r.s2 ? r.s2.volume : null
    case 'momentum':
      return r.sig?.momentum ? r.sig.momentum.score / (r.sig.momentum.max || 1) : null
    case 'ath':
      return r.athSince ? r.athSince.pct : null
    case 'align':
      return r.sig ? ALIGN_ORDER[r.alignment] : null
    default:
      return null
  }
}

export const Signals: React.FC = () => {
  const { holdings, loading: portfolioLoading, stockHref } = usePortfolio()
  const { money, price: inr, signedMoney, hidden } = useMoney()
  const [searchParams, setSearchParams] = useSearchParams()
  const market: Market = searchParams.get('market') === 'us' ? 'us' : 'in'
  const isUs = market === 'us'
  const price = (v: number | null | undefined) => (isUs ? usd(v, hidden) : inr(v))
  const perShare = (v: number) => (hidden ? (isUs ? '$ ••••' : '₹ ••••') : isUs ? signedUsd(v) : fmtSigned(v, 2))
  const fmt: Fmt = useMemo(() => ({ price, perShare }), [isUs, hidden]) // eslint-disable-line react-hooks/exhaustive-deps

  const [held, setHeld] = useState<SignalsResponse | null>(null)
  const [stage2, setStage2] = useState<Stage2Response | null>(null)
  const [liveQuotes, setLiveQuotes] = useState<Record<string, { price: number; day_change_pct: number | null }>>({})
  const [usLive, setUsLive] = useState<Record<string, UsLiveQuote>>({})
  const [usClosed, setUsClosed] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [q, setQ] = useState('')
  const startFilter = searchParams.get('filter')
  const [align, setAlign] = useState<AlignFilter>(startFilter === 'all-bear' || startFilter === 'all-bull' || startFilter === 'mixed' || startFilter === 'trade' ? startFilter : 'all')
  const startSource = searchParams.get('source')
  const [source, setSource] = useState<Source>(startSource === 'held' || startSource === 'stage2' || startSource === 'new' ? startSource : 'all')
  const [sector, setSector] = useState('all')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'align', dir: -1 })
  const [shown, setShown] = useState(PAGE)
  const [view, setView] = useState<'calls' | 'table'>(searchParams.get('view') === 'table' || startFilter ? 'table' : 'calls')
  const timer = useRef<number | undefined>(undefined)

  const loadHeld = useCallback(async () => {
    try {
      const res = await fetchSignals(market)
      setHeld(res)
      return res
    } catch (err: any) {
      setError(err?.message || 'Could not load signals')
      return null
    }
  }, [market])

  const loadStage2 = useCallback(async () => {
    if (market !== 'in') return null
    try {
      const res = await fetchStage2()
      setStage2(res)
      return res
    } catch (err: any) {
      setError(err?.message || 'Could not load the Stage 2 list')
      return null
    }
  }, [market])

  const load = useCallback(async () => {
    setError(null)
    return Promise.all([loadHeld(), loadStage2()])
  }, [loadHeld, loadStage2])

  // Each market has its own cache and refresh job, so start clean when switching
  useEffect(() => {
    setHeld(null)
    setStage2(null)
    setShown(PAGE)
    load()
  }, [load])

  // India: one job covers the Chartink list and the holdings. US: the holdings job.
  const job = isUs ? held?.job : stage2?.job
  const running = job?.state === 'running'
  useEffect(() => {
    if (!running) return
    timer.current = window.setInterval(load, 2000)
    return () => window.clearInterval(timer.current)
  }, [running, load])

  // The server refreshes on its own every few minutes in market hours; an open page picks that up (and shows its
  // progress) by re-reading every 2 minutes while the session runs. Paused while the tab is hidden.
  useEffect(() => {
    if (isUs || running) return
    const t = window.setInterval(() => {
      if (!document.hidden && indiaSessionActive()) loadStage2()
    }, 120_000)
    return () => window.clearInterval(t)
  }, [isUs, running, loadStage2])

  const list = isUs ? null : stage2?.list ?? null
  const hasList = !!list

  // Live Kite prices for the Chartink stocks: every 20s during the session, every 5 min otherwise; paused while the tab is hidden
  useEffect(() => {
    if (!hasList) return
    let stop = false
    let t: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchStage2Live()
          if (!stop) setLiveQuotes(res.quotes)
        } catch {
          /* keep the last prices */
        }
      }
      if (!stop) t = window.setTimeout(tick, indiaSessionActive() ? 20_000 : 300_000)
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(t)
    }
  }, [hasList])

  // Live USD prices: every 20s while the US session is active, every 5 min otherwise
  useEffect(() => {
    if (!isUs) return
    let stop = false
    let t: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchUsLive()
          if (!stop) {
            setUsLive(res.quotes)
            setUsClosed(res.session_closed)
          }
        } catch {
          /* keep the last prices */
        }
      }
      if (!stop) t = window.setTimeout(tick, usSessionActive() ? 20_000 : 300_000)
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(t)
    }
  }, [isUs])

  // Signals rebuilt on the live price (today's bar from the open), for holdings and for the Chartink list
  const sessionLive = isUs ? usSessionActive() : indiaSessionActive()
  const every = () => (sessionLive ? 60_000 : 600_000)
  const liveHeld = useLiveSignals(() => fetchLiveSignals(market), !!held?.signals && Object.keys(held.signals).length > 0, every, market, job?.finished_at)
  const liveList = useLiveSignals(fetchStage2LiveSignals, hasList, every, 'stage2', job?.finished_at)
  const liveStatus = !isUs && hasList ? liveList.status : liveHeld.status

  const startRefresh = async () => {
    setStarting(true)
    try {
      if (isUs) await refreshSignals('us')
      else await refreshStage2()
      await load()
    } catch (err: any) {
      setError(err?.message || 'Could not start the refresh')
    } finally {
      setStarting(false)
    }
  }

  const instruments = useMemo(() => buildInstruments(holdings.filter((h) => classifyAssetClass(h) === (isUs ? 'US_STOCKS' : 'EQUITY'))), [holdings, isUs])

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = []
    const heldSigs = { ...(held?.signals ?? {}), ...liveHeld.signals }
    const listSigs = { ...(stage2?.signals ?? {}), ...liveList.signals }
    const map = held?.symbol_map ?? {}

    if (isUs) {
      instruments.forEach((inst) => {
        const id = inst.lots.map((l) => map[l.holding.instrument_symbol]).find(Boolean)
        const sig = id ? heldSigs[id] : undefined
        const live = usLive[tickerOf(inst.sym)]
        const ltp = live?.price ?? sig?.momentum?.last_price ?? 0
        out.push({
          key: `us:${inst.key}`,
          code: inst.sym,
          name: sig?.name || inst.sym,
          href: null,
          inst,
          sig,
          ltp,
          dayPct: live?.day_change_pct ?? inst.dayPct,
          live,
          fresh: false,
          ...readSignals(sig, ltp),
        })
      })
      return out
    }

    const byCode = new Map<string, Row>()
    const add = (row: Omit<Row, keyof Reading | 'fresh'> & { fresh?: boolean }) => {
      const reading = readSignals(row.sig, row.ltp)
      const fresh =
        row.sig?.ath?.state === 'IN_POSITION' && (row.sig.ath.bars_held ?? 999) <= FRESH_DAYS
      const full: Row = { ...row, fresh, ...reading }
      out.push(full)
      return full
    }

    ;(list?.rows ?? []).forEach((s2) => {
      const code = s2.nsecode.toUpperCase()
      const sig = listSigs[code]
      const lv = liveQuotes[s2.nsecode]
      const ltp = lv?.price ?? s2.close
      byCode.set(code, add({ key: `s2:${code}`, code: s2.nsecode, name: s2.name, href: `/momentum?symbol=${encodeURIComponent(s2.nsecode)}`, s2, sig, ltp, dayPct: lv?.day_change_pct ?? s2.per_chg ?? null }))
    })

    instruments.forEach((inst) => {
      const id = inst.lots.map((l) => map[l.holding.instrument_symbol]).find(Boolean)
      const code = id ? codeOf(id) : null
      const match = code ? byCode.get(code) : undefined
      if (match) {
        // on both lists: keep the Chartink row, attach the position, prefer the live holdings signals if the list has none
        const idx = out.indexOf(match)
        const sig = match.sig ?? (id ? heldSigs[id] : undefined)
        const ltp = liveQuotes[match.code]?.price ?? inst.ltp ?? match.ltp
        const merged: Row = { ...match, inst, sig, ltp, href: stockHref(inst) ?? match.href, fresh: false, ...readSignals(sig, ltp) }
        merged.fresh =
          sig?.ath?.state === 'IN_POSITION' && (sig.ath.bars_held ?? 999) <= FRESH_DAYS
        out[idx] = merged
        return
      }
      const sig = id ? heldSigs[id] : undefined
      add({ key: `held:${inst.key}`, code: inst.sym, name: sig?.name || inst.sym, href: stockHref(inst), inst, sig, ltp: inst.ltp, dayPct: inst.dayPct })
    })
    return out
  }, [held, stage2, liveHeld.signals, liveList.signals, liveQuotes, usLive, instruments, isUs, list, stockHref])

  const inScope = useCallback(
    (r: Row) => {
      if (source === 'held') return !!r.inst
      if (source === 'stage2') return !!r.s2
      if (source === 'new') return !!r.s2?.is_new
      return true
    },
    [source],
  )
  const scoped = useMemo(() => rows.filter(inScope), [rows, inScope])

  const sourceCounts = useMemo(
    () => ({ all: rows.length, held: rows.filter((r) => r.inst).length, stage2: rows.filter((r) => r.s2).length, new: rows.filter((r) => r.s2?.is_new).length }),
    [rows],
  )

  const callSources = useMemo<CallSource[]>(
    () =>
      scoped.map((r) => ({
        code: r.code,
        name: r.name,
        sector: typeof r.s2?.sector === 'string' ? titleCase(r.s2.sector) : undefined,
        href: r.href,
        held: !!r.inst,
        isNew: r.s2?.is_new,
        sig: r.sig,
        ltp: r.ltp,
      })),
    [scoped],
  )

  const sectors = useMemo(() => {
    const m = new Map<string, number>()
    scoped.forEach((r) => {
      const v = r.s2?.sector
      if (typeof v === 'string' && v) m.set(v, (m.get(v) ?? 0) + 1)
    })
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [scoped])

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const out = scoped.filter((r) => {
      if (needle && !`${r.name} ${r.code}`.toLowerCase().includes(needle)) return false
      if (sector !== 'all' && String(r.s2?.sector ?? '') !== sector) return false
      if (align === 'trade') return r.sig?.ath?.state === 'IN_POSITION'
      if (align === 'fresh') return r.fresh
      if (align !== 'all') return r.alignment === align
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
  }, [scoped, q, align, sort, sector])

  const summary = useMemo(() => {
    const withM = scoped.filter((r) => r.sig?.momentum)
    const up = withM.filter((r) => momentumLean(r.sig!.momentum!) === 'bull').length
    const down = withM.filter((r) => momentumLean(r.sig!.momentum!) === 'bear').length
    const bull = scoped.filter((r) => r.alignment === 'all-bull')
    return {
      covered: scoped.filter((r) => r.sig && (r.sig.momentum || r.sig.ath)).length,
      up,
      down,
      neutral: withM.length - up - down,
      ath: scoped.filter((r) => r.sig?.ath?.state === 'IN_POSITION').length,
      fresh: scoped.filter((r) => r.fresh).length,
      bull: bull.length,
      bullHeld: bull.filter((r) => r.inst).length,
      reviewHeld: scoped.filter((r) => r.inst && r.alignment === 'all-bear').length,
      heldN: scoped.filter((r) => r.inst).length,
      s2N: scoped.filter((r) => r.s2).length,
      both: scoped.filter((r) => r.inst && r.s2).length,
    }
  }, [scoped])

  const computedAt = useMemo(() => {
    const times = [...Object.values(held?.signals ?? {}), ...Object.values(stage2?.signals ?? {})].map((s) => s.computed_at).filter(Boolean) as string[]
    return times.sort().slice(-1)[0] // the latest refresh, not the oldest stock left in the cache
  }, [held, stage2])

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

  // Chartink + holdings - on both = total, counted once. While a refresh runs the job reports it; otherwise it comes from the rows.
  const breakdown = useMemo(() => {
    const fromJob = !isUs && running && (job?.total ?? 0) > 0
    const chartink = fromJob ? job!.list_count ?? 0 : rows.filter((r) => r.s2).length
    const held = fromJob ? job!.holdings_count ?? 0 : rows.filter((r) => r.inst).length
    const both = fromJob ? job!.overlap ?? 0 : rows.filter((r) => r.s2 && r.inst).length
    return { chartink, held, both, total: chartink + held - both }
  }, [rows, job, running, isUs])
  const breakdownText = isUs
    ? `Holdings ${breakdown.held}`
    : `Chartink ${breakdown.chartink} + Holdings ${breakdown.held}${breakdown.both > 0 ? ` − ${breakdown.both} on both` : ''} = ${breakdown.total}`

  const auto = isUs ? undefined : stage2?.auto
  const clock = (iso: string) => new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
  const autoText = (() => {
    if (!auto?.enabled) return null
    const next = auto.next_run ? new Date(auto.next_run) : null
    const sameDay = next && next.toDateString() === new Date().toDateString()
    const nextText = next ? (sameDay ? clock(auto.next_run!) : next.toLocaleString('en-IN', { weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false })) : ''
    const last = auto.last_run
    const lastNote =
      last && last.outcome !== 'ran' && new Date(last.slot).toDateString() === new Date().toDateString()
        ? ` (the ${clock(last.slot)} run ${last.outcome === 'skipped' ? 'was skipped' : 'failed'}: ${last.message})`
        : ''
    return `Auto refresh every ${auto.every_minutes} min in market hours${nextText ? `, next ${nextText}` : ''}${lastNote}`
  })()
  const statusLine = [
    breakdownText,
    !isUs && list ? `list read ${new Date(list.fetched_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })}` : null,
    autoText,
  ]
    .filter(Boolean)
    .join(' · ')

  const pctDone = job && job.total > 0 ? Math.round((job.done / job.total) * 100) : 0
  const extras = !isUs && source !== 'held' ? list?.extra_columns ?? [] : []
  const showVolume = !isUs && source !== 'held' && hasList
  const colCount = 7 + (showVolume ? 1 : 0) + extras.length

  if (portfolioLoading && holdings.length === 0) {
    return (
      <div className="page-in" aria-busy="true">
        <p className="sub">Loading your holdings…</p>
      </div>
    )
  }

  const nothingYet = rows.length === 0
  const notComputed = summary.covered === 0 && !running

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

      <section className="sg-bar" aria-label="Stocks and refresh">
        <div className="sg-bar-l">
          <div className="seg" role="group" aria-label="Market">
            {([['in', 'India'], ['us', 'US']] as const).map(([id, label]) => (
              <button key={id} type="button" className={market === id ? 'on' : ''} aria-pressed={market === id} onClick={() => setSearchParams(id === 'us' ? { market: 'us' } : {}, { replace: true })}>
                {label}
              </button>
            ))}
          </div>
          {!isUs && hasList && (
            <div className="seg" role="group" aria-label="Stocks from">
              {(
                [
                  ['all', 'Everything'],
                  ['held', 'My holdings'],
                  ['stage2', 'Stage 2'],
                  ['new', 'New on Stage 2'],
                ] as const
              ).map(([id, label]) => (
                <button key={id} type="button" className={source === id ? 'on' : ''} aria-pressed={source === id} onClick={() => { setSource(id); setShown(PAGE) }}>
                  {label}
                  <span className="cnt num">{sourceCounts[id]}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="sg-run">
          {running && (
            <>
              <div className="sg-progress" role="progressbar" aria-valuenow={pctDone} aria-valuemin={0} aria-valuemax={100} aria-label="Refresh progress">
                <span style={{ width: `${pctDone}%` }} />
              </div>
              <span className="sub num">
                {job!.done} of {job!.total}
              </span>
            </>
          )}
          <button
            className="btn btn-primary"
            onClick={startRefresh}
            disabled={running || starting}
            title={isUs ? 'Recompute signals for your US stocks' : 'Re-read the Chartink Stage 2 screener, then recompute signals for it and for your holdings'}
          >
            <RefreshCw size={16} strokeWidth={1.75} className={running ? 'spin' : ''} />
            {running ? (job?.trigger === 'schedule' ? 'Auto refresh running…' : 'Refreshing…') : isUs ? 'Refresh signals' : 'Refresh Momentum Stocks'}
          </button>
        </div>
      </section>

      <div className="sg-status">
        {!running && <FreshnessChip status={liveStatus} broker={isUs ? 'INDmoney' : 'Kite'} sessionOpen={sessionLive} storedAt={isUs ? computedAt : job?.finished_at ?? computedAt} />}
        {isUs && <span className={`badge ${usClosed ? 'off' : 'ok'}`}>{usClosed ? 'US market closed' : 'US market open'}</span>}
        <span aria-live="polite">{statusLine}</span>
      </div>

      <section className="sum" aria-label="Signal summary">
        <div className="card">
          <div className="lbl">{isUs ? 'US stocks you hold' : 'Stocks in view'}</div>
          <div className="val num">{scoped.length}</div>
          <div className="foot">
            {isUs
              ? summary.covered < scoped.length
                ? `${scoped.length - summary.covered} without signals`
                : 'All analysed'
              : `${summary.heldN} held · ${summary.s2N} on Stage 2 · ${summary.both} both`}
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
          <div className="lbl">In an ATH trade</div>
          <div className="val num">{summary.ath}</div>
          <div className="foot">{summary.fresh} opened in the last {FRESH_DAYS} days</div>
        </div>
        <div className="card">
          <div className="lbl">Both bullish</div>
          <div className="val num pos">{summary.bull}</div>
          <div className="foot">
            {summary.bullHeld} held{summary.reviewHeld > 0 ? ` · ${summary.reviewHeld} held stock${summary.reviewHeld === 1 ? '' : 's'} all bearish` : ''}
          </div>
        </div>
      </section>

      <div className="sg-tabs" role="tablist" aria-label="View">
        <button type="button" role="tab" className={view === 'calls' ? 'on' : ''} aria-selected={view === 'calls'} onClick={() => setView('calls')}>
          Buy &amp; sell calls
        </button>
        <button type="button" role="tab" className={view === 'table' ? 'on' : ''} aria-selected={view === 'table'} onClick={() => setView('table')}>
          All stocks
          <span className="cnt num">{scoped.length}</span>
        </button>
      </div>

      {nothingYet ? (
        <div className="card">
          <p className="card-t">{isUs ? 'No US holdings' : 'Nothing to analyse yet'}</p>
          <p className="card-s">
            {isUs
              ? 'No US stocks or ETFs in your portfolio.'
              : 'Press Refresh Momentum Stocks. It reads your saved Chartink Stage 2 screener, then runs it and every Indian stock you hold through momentum and ATH breakout. The first run takes a few minutes; results are saved, so the page opens instantly after that.'}
          </p>
        </div>
      ) : notComputed ? (
        <div className="card">
          <p className="card-t">Signals have not been computed yet</p>
          <p className="card-s">
            Press {isUs ? 'Refresh signals' : 'Refresh Momentum Stocks'} to analyse {rows.length} stocks.{' '}
            {isUs ? 'The first run builds each stock’s full price history and stores it; later runs only add the latest days.' : 'The first run takes a few minutes.'} Results are saved, so the page opens instantly after that.
          </p>
        </div>
      ) : view === 'calls' ? (
        <CallsView
          sources={callSources}
          fmt={fmt}
          sessionOpen={sessionLive}
          defaultWindow={searchParams.get('window') === '2' ? 2 : searchParams.get('window') === '7' ? 7 : 'open'}
          defaultSide={searchParams.get('side') === 'sell' ? 'sell' : 'buy'}
          expand={searchParams.has('side')}
        />
      ) : (
        <>
          <section className="toolbar" aria-label="Filters">
            <div className="search">
              <label className="sr" htmlFor="sg-q">
                Search stocks
              </label>
              <Search size={16} strokeWidth={1.75} aria-hidden="true" />
              <input id="sg-q" className="input" type="search" placeholder="Search name or symbol" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <div className="seg" role="group" aria-label="Signal alignment">
              {(
                [
                  ['all', 'All'],
                  ['all-bull', 'All bullish'],
                  ['mixed', 'Mixed'],
                  ['all-bear', 'All bearish'],
                  ['trade', 'In a trade'],
                  ['fresh', 'Fresh entries'],
                ] as const
              ).map(([id, label]) => (
                <button key={id} type="button" className={align === id ? 'on' : ''} aria-pressed={align === id} onClick={() => { setAlign(id); setShown(PAGE) }}>
                  {label}
                </button>
              ))}
            </div>
            {sectors.length > 0 && (
              <>
                <label className="sr" htmlFor="sg-sector">
                  Sector
                </label>
                <select id="sg-sector" className="select" value={sector} onChange={(e) => { setSector(e.target.value); setShown(PAGE) }}>
                  <option value="all">All sectors</option>
                  {sectors.map(([name, n]) => (
                    <option key={name} value={name}>
                      {titleCase(name)} ({n})
                    </option>
                  ))}
                </select>
              </>
            )}
          </section>

          <div className="card stbl-wrap">
            <table className="stbl">
              <thead>
                <tr>
                  {head('sym', 'Stock')}
                  {head('price', 'Price', true)}
                  {head('day', 'Day', true)}
                  {head('pos', 'Your position', true)}
                  {head('momentum', 'Momentum')}
                  {head('ath', '200-DMA ATH breakout')}
                  {head('align', 'Signal alignment')}
                  {showVolume && head('vol', 'Volume', true)}
                  {extras.map((k) => head(`x:${k}`, columnLabel(k), k !== 'sector'))}
                </tr>
              </thead>
              <tbody>
                {visible.slice(0, shown).map((r) => {
                  const { inst, s2, sig } = r
                  return (
                    <tr key={r.key}>
                      <td>
                        <div className="sg-sym">
                          {isUs ? <StockLink href={null}>{r.name}</StockLink> : r.href ? <Link className="sg-link" to={r.href} title="Open in Momentum">{r.name}</Link> : <StockLink href={null}>{r.name}</StockLink>}
                          {s2?.is_new && <span className="badge info">New</span>}
                          {inst && <span className="badge ok">Held</span>}
                          {s2 && <span className="badge off">Stage 2</span>}
                        </div>
                        <div className="sg-sub mono">{r.code}</div>
                        {inst && (
                          <div className="sg-sub">
                            {inst.brokers.map(brokerLabel).join(' + ')} · {inst.qty.toLocaleString('en-IN', { maximumFractionDigits: 4 })} @ {inr(inst.avg)}
                          </div>
                        )}
                        {isUs && r.live?.ext_price != null && r.live.ext_price !== r.live.price && <div className="sg-sub num">extended {price(r.live.ext_price)}</div>}
                        {sig?.history_status === 'partial' && (
                          <div className="sg-sub" title={sig.history_note}>
                            Partial price history
                          </div>
                        )}
                      </td>
                      <td className="r num">{fmt.price(r.ltp)}</td>
                      <td className={`r num ${tone(r.dayPct)}`}>{pct(r.dayPct)}</td>
                      <td className="r num">
                        {inst ? (
                          <>
                            <div>{money(inst.cur)}</div>
                            <div className={`sg-sub ${tone(inst.pnlPct)}`}>
                              {signedMoney(inst.pnl)} · {pct(inst.pnlPct)}
                            </div>
                          </>
                        ) : (
                          <span className="sg-na">{DASH}</span>
                        )}
                      </td>
                      <td>
                        <MomentumCell sig={sig} fmt={fmt} />
                      </td>
                      <td>
                        <AthCell sig={sig} reading={r} fmt={fmt} />
                      </td>
                      <td>
                        <AlignmentCell sig={sig} reading={r} />
                      </td>
                      {showVolume && <td className="r num">{s2 ? compactVol(s2.volume) : DASH}</td>}
                      {extras.map((k) => (
                        <td key={k} className={k === 'sector' ? '' : 'r num'}>
                          {s2 ? extraCell(k, s2[k]) : DASH}
                        </td>
                      ))}
                    </tr>
                  )
                })}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={colCount}>
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
        </>
      )}

      {!isUs && list && list.dropped.length > 0 && view === 'table' && (
        <div className="card">
          <p className="card-t">Dropped out of Stage 2 since {list.previous_date}</p>
          <p className="card-s">No longer pass the screener</p>
          <p className="sg-line" style={{ marginTop: 8 }}>
            {list.dropped.map((d) => d.nsecode).join(' · ')}
          </p>
        </div>
      )}

      {!isUs && list && (
        <details className="card">
          <summary className="card-t" style={{ cursor: 'pointer' }}>
            Stage 2 screener source and conditions
          </summary>
          <p className="card-s" style={{ margin: '8px 0' }}>
            Stage 2 stocks come from the Chartink screener &quot;{list.title.replace(/,\s*Technical Analysis Scanner\.?$/i, '')}&quot;. Edit it on Chartink (conditions or extra columns) and press
            Refresh; the page reads the screener&apos;s current definition each time.{' '}
            <a className="link" href={list.url} target="_blank" rel="noreferrer">
              Open on Chartink <ExternalLink size={12} style={{ verticalAlign: '-1px' }} />
            </a>
          </p>
        </details>
      )}

      <p className="sg-legend">
        {isUs ? 'Your US stocks and ETFs. ' : 'Everything you hold in Indian stocks and ETFs, plus the stocks on your Chartink Stage 2 screener, on one list; a stock that is both is shown once. '}
        ATH entries are the strategy&apos;s own signals on daily candles, not your actual buys; &quot;since entry&quot; compares the live price with the strategy entry price, per share
        {isUs ? ', in US dollars; position values stay in rupees' : ''}. Signals are built from daily candles with today&apos;s bar made from the live price, so they can change until the close; the
        &quot;last sessions&quot; windows are the finished sessions plus today. Bullish: uptrend, a strategy in position, or a buy signal. Bearish: downtrend, a sell signal or an exit.
        {isUs
          ? ' US history is stored in Azure: INDmoney for the latest year and daily updates, with a validated backfill for earlier years. Momentum is measured against the S&P 500 (SPY). Prices update while the US session is open (about 19:00 to 01:30 IST).'
          : ' The Chartink list is as at its last end-of-day data; prices and day change are live from Kite while the NSE session is open. Mutual funds, US stocks, NPS and gold are not covered here.'}{' '}
        This is a rules-based reading of past prices, not advice.
      </p>
    </div>
  )
}
