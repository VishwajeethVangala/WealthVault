import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, Check, Info } from 'lucide-react'
import { StockLink } from '../components/StockLink'
import { fetchBrokerSessions, fetchHistory, fetchTargets, saveTargets, type HistoryPoint } from '../utils/api'
import { usePortfolio } from '../context/PortfolioContext'
import { brokerLabel, classifyAssetClass, matchesBroker, brokerKeyOf } from '../utils/portfolioFilters'
import { SINGLE_POSITION_LIMIT_PCT, dayPctOf, displaySymbol } from '../utils/dayChange'
import { pct, weight } from '../utils/format'
import { useMoney } from '../utils/useMoney'
import { CLASS_COLOR, CLASS_LABEL, brokerCode, brokerColor, buildInstruments } from '../components/holdings/holdingsModel'
import { TargetAllocationEditor } from '../components/dashboard/TargetAllocationEditor'
import { HeroBand } from '../components/dashboard/HeroBand'
import { SummaryPin } from '../components/SummaryPin'
import { CategoryGrid } from '../components/dashboard/CategoryGrid'
import { DayMove } from '../components/dashboard/DayMove'
import { SignalsPanel, type SignalDigest } from '../components/dashboard/SignalsPanel'
import { RiskPanel } from '../components/dashboard/RiskPanel'
import { DriftPanel } from '../components/dashboard/DriftPanel'
import { Brief } from '../components/dashboard/Brief'
import { useNifty, useUsdMove } from '../components/dashboard/useMarket'
import { baseline, buildClassCards, concentration, drawdownOf, driftRows, totalsOf, type Period } from '../components/dashboard/metrics'
import type { BrokerSessionInfo } from '../types'

type Note = { id: string; tone: 'ok' | 'warn' | 'info' | 'neg'; title: string; body: string }

const NOTE_ICON = { ok: Check, warn: AlertTriangle, info: Info, neg: AlertTriangle }

export const ExecutiveOverview: React.FC = () => {
  const [searchParams] = useSearchParams()
  const { holdings, loading, error, refresh, stockHref } = usePortfolio()
  const { compact, signedCompact } = useMoney()

  const heroRef = useRef<HTMLDivElement>(null)
  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [targets, setTargets] = useState<Record<string, number>>({})
  const [editingTargets, setEditingTargets] = useState(false)
  const [history, setHistory] = useState<HistoryPoint[]>([])
    const [period, setPeriod] = useState<Period>('1D')

  const activeBroker = searchParams.get('broker') || 'all'
  const activeAssetClass = searchParams.get('assetClass') || 'all'

  // The login banner must go once Kite is authorised (in another tab): re-check when the tab comes back and each minute
  useEffect(() => {
    const check = () => fetchBrokerSessions().then(setSessions).catch(() => {})
    const onVisible = () => {
      if (!document.hidden) check()
    }
    const t = window.setInterval(onVisible, 60_000)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearInterval(t)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  useEffect(() => {
    fetchBrokerSessions().then(setSessions).catch(() => setSessions([]))
    fetchTargets()
      .then((t) => setTargets(t.targets || {}))
      .catch((err) => console.warn('Could not load target allocation:', err))
    fetchHistory(3650)
      .then(setHistory)
      .catch(() => setHistory([]))
  }, [])

  // per-class value by day, for the category cards
  const classHistory = useMemo(() => {
    const out: Record<string, { date: string; v: number }[]> = {}
    history.forEach((p) => Object.entries(p.classes ?? {}).forEach(([k, v]) => (out[k] = [...(out[k] ?? []), { date: p.date, v }])))
    return out
  }, [history])

  const filtered = useMemo(() => {
    const brokers = activeBroker !== 'all' ? activeBroker.split(',').filter(Boolean) : []
    const classes = activeAssetClass !== 'all' ? activeAssetClass.split(',').filter(Boolean) : []
    return holdings.filter(
      (h) =>
        (brokers.length === 0 || brokers.some((b) => matchesBroker(h, b))) &&
        (classes.length === 0 || classes.includes(classifyAssetClass(h))),
    )
  }, [holdings, activeBroker, activeAssetClass])

  const instruments = useMemo(() => buildInstruments(filtered), [filtered])

  const totals = useMemo(() => totalsOf(instruments), [instruments])

  const nifty = useNifty()
  const usdMove = useUsdMove(instruments.some((i) => i.cls === 'US_STOCKS'))
  const [digest, setDigest] = useState<SignalDigest | null>(null)

  const fromDate = useMemo(() => baseline(history, period === '1D' ? '1M' : period)?.date ?? null, [history, period])
  const cards = useMemo(() => buildClassCards(instruments, classHistory, fromDate, totals.cur), [instruments, classHistory, fromDate, totals.cur])
  const conc = useMemo(() => concentration(instruments, totals.cur), [instruments, totals.cur])
  const drawdown = useMemo(() => drawdownOf(history), [history])
  const drift = useMemo(() => driftRows(cards, targets, totals.cur), [cards, targets, totals.cur])
  const usdPct = useMemo(() => cards.find((c) => c.cls === 'US_STOCKS')?.weight ?? 0, [cards])
  const allocation = useMemo(() => drift.map((d) => ({ cls: d.cls, w: d.weight, target: d.target, drift: d.drift })), [drift])

  const byBroker = useMemo(() => {
    const map = new Map<string, { cur: number; inv: number; count: number }>()
    filtered.forEach((h) => {
      const k = brokerKeyOf(h.connection_id)
      const e = map.get(k) ?? { cur: 0, inv: 0, count: 0 }
      e.cur += h.current_value || 0
      e.inv += h.quantity * h.average_price
      e.count += 1
      map.set(k, e)
    })
    return [...map.entries()]
      .map(([key, e]) => ({ key, ...e, w: totals.cur > 0 ? (e.cur / totals.cur) * 100 : 0, ret: e.inv > 0 ? ((e.cur - e.inv) / e.inv) * 100 : null }))
      .sort((a, b) => b.cur - a.cur)
  }, [filtered, totals.cur])

  const top = useMemo(() => [...instruments].sort((a, b) => b.cur - a.cur).slice(0, 6), [instruments])

  const notes = useMemo<Note[]>(() => {
    const out: Note[] = []
    sessions
      .filter((s) => s.status !== 'CONNECTED')
      .forEach((s) =>
        out.push({
          id: `session-${s.connection_id}`,
          tone: 'neg',
          title: `${s.display_name.split(' — ')[0]} needs attention`,
          body: `It is ${s.status.replace(/_/g, ' ').toLowerCase()}, so its holdings may be stale until you reconnect.`,
        }),
      )
    instruments
      .filter((i) => totals.cur > 0 && (i.cur / totals.cur) * 100 >= SINGLE_POSITION_LIMIT_PCT)
      .slice(0, 2)
      .forEach((i) =>
        out.push({
          id: `conc-${i.key}`,
          tone: 'warn',
          title: `${i.sym} is concentrated`,
          body: `${weight((i.cur / totals.cur) * 100, 1)} of the portfolio, above the ${SINGLE_POSITION_LIMIT_PCT}% single-position guide.`,
        }),
      )
    allocation
      .filter((a) => a.target > 0 && Math.abs(a.drift) >= 5)
      .forEach((a) =>
        out.push({
          id: `drift-${a.cls}`,
          tone: 'warn',
          title: `${CLASS_LABEL[a.cls]} has drifted`,
          body: `${weight(a.w, 1)} of the portfolio against a ${a.target.toFixed(0)}% target, ${Math.abs(a.drift).toFixed(1)} points ${a.drift > 0 ? 'over' : 'under'}.`,
        }),
      )
    filtered
      .map((h) => ({ h, p: dayPctOf(h) }))
      .filter((r): r is { h: typeof r.h; p: number } => r.p !== null && Math.abs(r.p) >= 5)
      .sort((a, b) => Math.abs(b.p) - Math.abs(a.p))
      .slice(0, 2)
      .forEach(({ h, p }) => out.push({ id: `move-${h.holding_id}`, tone: 'info', title: `${displaySymbol(h)} moved ${pct(p)}`, body: 'Large move in the last session.' }))
    if (filtered.length > 0 && filtered.every((h) => h.data_freshness !== 'live')) {
      out.push({ id: 'stale', tone: 'warn', title: 'No live prices', body: 'Every holding shows stored prices. Check the Kite session or run a sync.' })
    }
    if (Object.keys(targets).length === 0 && filtered.length > 0) {
      out.push({ id: 'no-targets', tone: 'info', title: 'No target allocation set', body: 'Set one to get drift notes when your mix moves away from plan.' })
    }
    if (out.length === 0) out.push({ id: 'clear', tone: 'ok', title: 'Nothing to flag', body: 'Brokers are connected, no position is oversized and allocation is on target.' })
    return out
  }, [sessions, instruments, totals.cur, allocation, filtered, targets])

  const brief = useMemo(() => {
    const out: string[] = []
    if (totals.day !== null && totals.dayPct !== null) {
      const dir = totals.day >= 0 ? 'up' : 'down'
      const worst = [...cards].filter((c) => c.day !== null).sort((a, b) => (a.day as number) - (b.day as number))[0]
      const best = [...cards].filter((c) => c.day !== null).sort((a, b) => (b.day as number) - (a.day as number))[0]
      let line = `Your portfolio is ${dir} ${Math.abs(totals.dayPct).toFixed(2)}% today (${signedCompact(totals.day)})`
      if (nifty != null) line += `, ${totals.dayPct - nifty >= 0 ? 'ahead of' : 'behind'} the Nifty (${pct(nifty)})`
      line += '.'
      if (worst && (worst.day as number) < 0) line += ` ${CLASS_LABEL[worst.cls]} cost the most (${signedCompact(worst.day)})`
      if (best && (best.day as number) > 0 && best !== worst) line += `${worst && (worst.day as number) < 0 ? ', ' : ' '}${CLASS_LABEL[best.cls]} helped most (${signedCompact(best.day)})`
      if (/[a-z)]$/.test(line)) line += '.'
      out.push(line)
    }
    if (digest?.ready) {
      const parts: string[] = []
      if (digest.sells > 0) parts.push(`${digest.sells} sell call${digest.sells === 1 ? '' : 's'} on your holdings this week${digest.sellNames.length ? ` (${digest.sellNames.join(', ')})` : ''}`)
      if (digest.buys > 0) parts.push(`${digest.buys} new buy${digest.buys === 1 ? '' : 's'}`)
      if (digest.review > 0) parts.push(`${digest.review} to review`)
      out.push(parts.length ? `Signals: ${parts.join(', ')}.` : 'Signals: no sell calls on your holdings this week.')
    }
    const guide = drift.filter((d) => d.target > 0 && Math.abs(d.drift) >= 3).sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift))[0]
    if (conc.top1 && conc.top1Pct >= SINGLE_POSITION_LIMIT_PCT) out.push(`${conc.top1.sym} is ${weight(conc.top1Pct, 1)} of the portfolio, above the ${SINGLE_POSITION_LIMIT_PCT}% guide.`)
    else if (guide) out.push(`${CLASS_LABEL[guide.cls]} sits ${Math.abs(guide.drift).toFixed(1)} points ${guide.drift > 0 ? 'over' : 'under'} target.`)
    return out
  }, [totals, cards, nifty, digest, drift, conc, signedCompact])

  const kiteSession = sessions.find((s) => s.broker_name.toLowerCase().includes('zerodha') && s.auth_url)

  if (loading && holdings.length === 0) {
    return (
      <div className="page-in" aria-busy="true">
        <p className="sub">Loading your portfolio…</p>
      </div>
    )
  }

  if (error && holdings.length === 0) {
    return (
      <div className="page-in">
        <div className="banner bad" role="alert">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">
            <b>Could not load your portfolio.</b> {error}
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => refresh()}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (holdings.length === 0) {
    return (
      <div className="page-in">
        <div className="card">
          <h2 className="card-t">No holdings yet</h2>
          <p className="card-s">
            <Link to="/brokers" className="link">
              Connect a broker
            </Link>{' '}
            and run a sync to see your portfolio here.
          </p>
        </div>
      </div>
    )
  }

  const filterActive = activeBroker !== 'all' || activeAssetClass !== 'all'

  return (
    <div className="page-in">
      {kiteSession && (
        <div className="banner" role="status">
          <AlertTriangle className="ic" size={18} strokeWidth={1.75} />
          <div className="tx">
            <b>Kite needs a login.</b> Authorize it to get live quotes and day changes.
          </div>
          <a className="btn btn-primary btn-sm" href={kiteSession.auth_url} target="_blank" rel="noreferrer">
            Authorize Kite
          </a>
        </div>
      )}

      <SummaryPin totals={totals} watch={heroRef} />

      <div ref={heroRef}>
        <HeroBand
          instruments={instruments}
          totals={totals}
          history={history}
          period={period}
          onPeriod={setPeriod}
          nifty={nifty}
          filterActive={filterActive}
        />
      </div>

      <Brief lines={brief} />

      <CategoryGrid cards={cards} period={period} usdMove={usdMove} />

      <section className="bx-two">
        <DayMove cards={cards} instruments={instruments} total={totals.day} />
        <SignalsPanel instruments={instruments} onDigest={setDigest} />
      </section>

      <section className="bx-two">
        <DriftPanel rows={drift} hasTargets={Object.keys(targets).length > 0} onEdit={() => setEditingTargets(true)} />
        <RiskPanel concentration={conc} drawdown={drawdown} usdPct={usdPct} />
      </section>

      <section className="bx-three">
        <div className="card bx-panel">
          <header className="bx-ph">
            <div>
              <h2 className="card-t">Notes</h2>
              <p className="card-s">Computed from your holdings and connections</p>
            </div>
          </header>
          <div className="ins">
            {notes.map((n) => {
              const Icon = NOTE_ICON[n.tone]
              return (
                <div className="ins-row" key={n.id}>
                  <span className={`ins-ic ${n.tone}`}>
                    <Icon size={16} strokeWidth={1.75} />
                  </span>
                  <div>
                    <div className="t">{n.title}</div>
                    <div className="b">{n.body}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="card bx-panel">
          <header className="bx-ph">
            <div>
              <h2 className="card-t">Largest positions</h2>
              <p className="card-s">Merged across brokers, share of portfolio value</p>
            </div>
            <Link className="link" to="/holdings">
              All holdings
            </Link>
          </header>
          {top.map((t, idx) => {
            const w = totals.cur > 0 ? (t.cur / totals.cur) * 100 : 0
            return (
              <div className="bx-pos" key={t.key}>
                <span className="rk num">{idx + 1}</span>
                <div className="nm">
                  <StockLink href={stockHref(t)}>{t.sym}</StockLink>
                  <small>
                    <span className="dot" style={{ background: CLASS_COLOR[t.cls] }} /> {CLASS_LABEL[t.cls]} · {t.brokers.map(brokerLabel).join(' + ')}
                  </small>
                </div>
                <div className="bar" aria-hidden="true">
                  <i style={{ width: `${Math.min(100, w * 4)}%` }} />
                </div>
                <div className="v num">{weight(w, 1)}</div>
              </div>
            )
          })}
        </div>

        <div className="card bx-panel">
          <header className="bx-ph">
            <div>
              <h2 className="card-t">By broker</h2>
              <p className="card-s">Holdings value at each account</p>
            </div>
            <Link className="link" to="/brokers">
              Manage
            </Link>
          </header>
          <div>
            {byBroker.map((b) => (
              <div className="brow" key={b.key}>
                <span className="mono-tile" style={{ background: brokerColor(b.key) }}>
                  {brokerCode(b.key)}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div className="n">{brokerLabel(b.key)}</div>
                  <div className="m num">
                    {b.count} holdings · {weight(b.w, 1)} of total
                  </div>
                  <div className="dtrack">
                    <span style={{ width: `${b.w}%`, background: brokerColor(b.key) }} />
                  </div>
                </div>
                <div>
                  <div className="v num">{compact(b.cur)}</div>
                  <div className={`m num ${b.ret != null && b.ret < 0 ? 'neg' : 'pos'}`} style={{ textAlign: 'right' }}>
                    {pct(b.ret, 1)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {editingTargets && (
        <TargetAllocationEditor
          initial={targets}
          onSave={async (t) => {
            const saved = await saveTargets(t)
            setTargets(saved.targets || {})
          }}
          onClose={() => setEditingTargets(false)}
        />
      )}
    </div>
  )
}
