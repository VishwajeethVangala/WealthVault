import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Check, Info, PieChart } from 'lucide-react'
import { fetchBrokerSessions, fetchHistory, fetchTargets, saveTargets, type HistoryPoint } from '../utils/api'
import { usePortfolio } from '../context/PortfolioContext'
import { brokerLabel, classifyAssetClass, matchesBroker, brokerKeyOf } from '../utils/portfolioFilters'
import { SINGLE_POSITION_LIMIT_PCT, dayPctOf, displaySymbol } from '../utils/dayChange'
import { pct, tone, weight } from '../utils/format'
import { useMoney } from '../utils/useMoney'
import { CLASS_COLOR, CLASS_LABEL, CLASS_ORDER, brokerCode, brokerColor, buildInstruments, type Instrument } from '../components/holdings/holdingsModel'
import { TargetAllocationEditor } from '../components/dashboard/TargetAllocationEditor'
import { ValueChart } from '../components/dashboard/ValueChart'
import type { BrokerSessionInfo } from '../types'

type Note = { id: string; tone: 'ok' | 'warn' | 'info' | 'neg'; title: string; body: string }

const NOTE_ICON = { ok: Check, warn: AlertTriangle, info: Info, neg: AlertTriangle }

export const ExecutiveOverview: React.FC = () => {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { holdings, loading, error, refresh } = usePortfolio()
  const { money, compact, signedCompact, signedMoney } = useMoney()

  const [sessions, setSessions] = useState<BrokerSessionInfo[]>([])
  const [targets, setTargets] = useState<Record<string, number>>({})
  const [editingTargets, setEditingTargets] = useState(false)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)

  const activeBroker = searchParams.get('broker') || 'all'
  const activeAssetClass = searchParams.get('assetClass') || 'all'

  useEffect(() => {
    fetchBrokerSessions().then(setSessions).catch(() => setSessions([]))
    fetchTargets()
      .then((t) => setTargets(t.targets || {}))
      .catch((err) => console.warn('Could not load target allocation:', err))
    fetchHistory(3650)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false))
  }, [])

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

  const totals = useMemo(() => {
    const cur = instruments.reduce((s, i) => s + i.cur, 0)
    const inv = instruments.reduce((s, i) => s + i.inv, 0)
    const reporting = instruments.filter((i) => i.day !== null)
    const day = reporting.reduce((s, i) => s + (i.day as number), 0)
    const dayBase = reporting.reduce((s, i) => s + i.cur - (i.day as number), 0)
    return {
      cur,
      inv,
      pnl: cur - inv,
      pnlPct: inv > 0 ? ((cur - inv) / inv) * 100 : null,
      day: reporting.length > 0 ? day : null,
      dayPct: reporting.length > 0 && dayBase > 0 ? (day / dayBase) * 100 : null,
      reporting: reporting.length,
    }
  }, [instruments])

  const allocation = useMemo(
    () =>
      CLASS_ORDER.map((cls) => {
        const items = instruments.filter((i) => i.cls === cls)
        const cur = items.reduce((s, i) => s + i.cur, 0)
        const inv = items.reduce((s, i) => s + i.inv, 0)
        const w = totals.cur > 0 ? (cur / totals.cur) * 100 : 0
        const target = targets[cls] || 0
        return { cls, count: items.length, cur, w, ret: inv > 0 ? ((cur - inv) / inv) * 100 : null, target, drift: w - target }
      }).filter((a) => a.count > 0 && a.cur > 0),
    [instruments, totals.cur, targets],
  )

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

  const movers = useMemo(() => {
    const ranked = instruments.filter((i) => i.dayPct !== null && i.day !== null)
    const by = (a: Instrument, b: Instrument) => (b.dayPct as number) - (a.dayPct as number)
    return {
      gainers: ranked.filter((i) => (i.day as number) > 0).sort(by).slice(0, 4),
      losers: ranked.filter((i) => (i.day as number) < 0).sort((a, b) => by(b, a)).slice(0, 4),
    }
  }, [instruments])

  const top = useMemo(() => [...instruments].sort((a, b) => b.cur - a.cur).slice(0, 6), [instruments])

  const contributors = useMemo(() => {
    const sorted = [...instruments].sort((a, b) => b.pnl - a.pnl)
    return [...sorted.slice(0, 5), ...sorted.slice(-2).filter((i) => i.pnl < 0)].filter((v, i, arr) => arr.indexOf(v) === i)
  }, [instruments])

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

  const drill = useCallback(
    (params: { assetClass?: string; highlight?: string; pnl?: string }) => {
      const next = new URLSearchParams()
      if (activeBroker !== 'all') next.set('broker', activeBroker)
      if (params.assetClass) next.set('assetClass', params.assetClass)
      if (params.highlight) next.set('highlight', params.highlight)
      if (params.pnl) next.set('pnl', params.pnl)
      navigate(`/holdings${next.toString() ? `?${next.toString()}` : ''}`)
    },
    [activeBroker, navigate],
  )

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

      <section className="kpis" aria-label="Key figures">
        <div className="card kpi hero">
          <span className="lbl">Net worth{filterActive ? ' (filtered)' : ''}</span>
          <span className="val num">{compact(totals.cur)}</span>
          <span className="foot num">
            {instruments.length} instruments · {byBroker.length} {byBroker.length === 1 ? 'broker' : 'brokers'}
          </span>
        </div>
        <div className="card kpi">
          <span className="lbl">Invested</span>
          <span className="val num">{compact(totals.inv)}</span>
          <span className="foot">Cost basis of current holdings</span>
        </div>
        <div className="card kpi">
          <span className="lbl">Total returns</span>
          <span className={`val num ${tone(totals.pnl)}`}>{signedCompact(totals.pnl)}</span>
          <span className="foot">
            <span className={`pill ${tone(totals.pnlPct)}`}>{pct(totals.pnlPct)}</span> unrealised
          </span>
        </div>
        <div className="card kpi">
          <span className="lbl">Today&apos;s P&amp;L</span>
          <span className={`val num ${tone(totals.day)}`}>{signedCompact(totals.day)}</span>
          <span className="foot">
            <span className={`pill ${tone(totals.dayPct)}`}>{pct(totals.dayPct)}</span>
            {totals.reporting} of {instruments.length} reporting
          </span>
        </div>
      </section>

      <section className="g-main">
        <ValueChart history={history} loading={historyLoading} />

        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">Asset allocation</h2>
              <p className="card-s">Share of portfolio value by asset class</p>
            </div>
            <button className="btn btn-sm" onClick={() => setEditingTargets(true)}>
              <PieChart size={16} strokeWidth={1.75} /> {Object.keys(targets).length ? 'Edit targets' : 'Set targets'}
            </button>
          </div>
          <div className="stack" role="img" aria-label="Allocation bar">
            {allocation.map((a) => (
              <span key={a.cls} style={{ width: `${a.w}%`, background: CLASS_COLOR[a.cls] }} title={`${CLASS_LABEL[a.cls]} ${weight(a.w, 1)}`} />
            ))}
          </div>
          <div className="alist">
            <div className="arow thead">
              <span>Class</span>
              <span>Value</span>
              <span style={{ textAlign: 'right' }}>Weight</span>
              <span style={{ textAlign: 'right' }} className="r">
                Return
              </span>
              <span style={{ textAlign: 'right' }} className="tg">
                Target
              </span>
            </div>
            {allocation.map((a) => (
              <button key={a.cls} className="arow" onClick={() => drill({ assetClass: a.cls })} aria-label={`Open ${CLASS_LABEL[a.cls]} in Holdings`}>
                <span className="nm">
                  <span className="dot" style={{ background: CLASS_COLOR[a.cls] }} />
                  {CLASS_LABEL[a.cls]}
                </span>
                <span className="num">{compact(a.cur)}</span>
                <span className="w num dim">{weight(a.w, 1)}</span>
                <span className={`r num ${tone(a.ret)}`}>{pct(a.ret, 1)}</span>
                <span className="tg num dim">{a.target > 0 ? `${a.target.toFixed(0)}% (${a.drift > 0 ? '+' : a.drift < 0 ? '−' : ''}${Math.abs(a.drift).toFixed(1)})` : '—'}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="g-3">
        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">Notes</h2>
              <p className="card-s">Computed from your holdings and connections</p>
            </div>
          </div>
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

        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">Profit contributors</h2>
              <p className="card-s">What drives your {signedCompact(totals.pnl)} unrealised result</p>
            </div>
          </div>
          <div className="bars">
            {contributors.map((i) => {
              const maxAbs = Math.max(...contributors.map((c) => Math.abs(c.pnl)), 1)
              return (
                <div className="bar-row" key={i.key}>
                  <div className="bar-top">
                    <span className="n">{i.sym}</span>
                    <span className={`v num ${tone(i.pnl)}`}>{signedCompact(i.pnl)}</span>
                  </div>
                  <div className="dtrack">
                    <span style={{ width: `${(Math.abs(i.pnl) / maxAbs) * 100}%`, background: i.pnl < 0 ? 'var(--loss)' : 'var(--gain)' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">By broker</h2>
              <p className="card-s">Holdings value at each account</p>
            </div>
            <Link className="link" to="/brokers">
              Manage
            </Link>
          </div>
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
                  <div className={`m num ${tone(b.ret)}`} style={{ textAlign: 'right' }}>
                    {pct(b.ret, 1)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="g-2">
        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">Today&apos;s movers</h2>
              <p className="card-s">Ranked by 1-day change. Funds and NPS report none.</p>
            </div>
          </div>
          <div className="mv">
            {([
              { label: 'Top gainers', icon: <ArrowUpRight size={14} className="pos" />, rows: movers.gainers, cls: 'pos' },
              { label: 'Top losers', icon: <ArrowDownRight size={14} className="neg" />, rows: movers.losers, cls: 'neg' },
            ] as const).map((col) => (
              <div key={col.label}>
                <p className="mv-h">
                  {col.icon} {col.label}
                </p>
                {col.rows.length === 0 && <p className="empty-s">None today</p>}
                {col.rows.map((m) => (
                  <div className="mrow" key={m.key}>
                    <div style={{ minWidth: 0 }}>
                      <div className="s">{m.sym}</div>
                      <div className="nm">{CLASS_LABEL[m.cls]}</div>
                    </div>
                    <div className="rt">
                      <span className={`pill ${col.cls}`}>{pct(m.dayPct)}</span>
                      <span className={`num ${col.cls}`}>{signedMoney(m.day)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div>
              <h2 className="card-t">Largest positions</h2>
              <p className="card-s">Merged across brokers, share of portfolio value</p>
            </div>
            <Link className="link" to="/holdings">
              All holdings
            </Link>
          </div>
          {top.map((t, idx) => {
            const w = totals.cur > 0 ? (t.cur / totals.cur) * 100 : 0
            return (
              <div className="trow" key={t.key}>
                <span className="rk num">{idx + 1}</span>
                <div style={{ minWidth: 0 }}>
                  <div className="s">
                    {t.sym}
                    <span className="tag-cls">
                      <span className="dot" style={{ background: CLASS_COLOR[t.cls], width: 6, height: 6 }} />
                      {CLASS_LABEL[t.cls]}
                    </span>
                  </div>
                  <div className="nm">{t.brokers.map(brokerLabel).join(' + ')}</div>
                </div>
                <div className="wbar">
                  <div className="dtrack" style={{ margin: 0 }}>
                    <span style={{ width: `${Math.min(100, w * 4)}%` }} />
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="num" style={{ fontWeight: 600 }}>
                    {weight(w, 1)}
                  </div>
                  <div className="num dim" style={{ fontSize: 12 }}>
                    {money(t.cur)}
                  </div>
                </div>
              </div>
            )
          })}
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
