import React, { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronRight, Download, Search, X } from 'lucide-react'
import { usePortfolio } from '../context/PortfolioContext'
import { useMoney } from '../utils/useMoney'
import { pct, tone, weight } from '../utils/format'
import { brokerKeyOf, brokerLabel, matchesBroker, type CanonicalAssetClass } from '../utils/portfolioFilters'
import {
  CLASS_COLOR,
  CLASS_LABEL,
  CLASS_ORDER,
  brokerCode,
  brokerColor,
  buildInstruments,
  formatQty,
  sortInstruments,
  sortKeyFromParam,
  type Instrument,
  type SortKey,
} from '../components/holdings/holdingsModel'

const EM_DASH = '—'

const BrokerBadges: React.FC<{ keys: string[] }> = ({ keys }) => (
  <span className="bk">
    {keys.map((k) => (
      <span key={k} style={{ background: brokerColor(k) }} title={brokerLabel(k)}>
        {brokerCode(k)}
      </span>
    ))}
  </span>
)

const COLUMNS: { key: SortKey | null; label: string; cell: string }[] = [
  { key: 'sym', label: 'Instrument', cell: 'c0' },
  { key: 'qty', label: 'Qty', cell: 'c' },
  { key: 'avg', label: 'Avg cost', cell: 'c' },
  { key: 'ltp', label: 'LTP', cell: 'c' },
  { key: 'inv', label: 'Invested', cell: 'c' },
  { key: 'cur', label: 'Current', cell: 'c' },
  { key: 'pnlPct', label: 'P&L', cell: 'c' },
  { key: 'dayPct', label: '1D P&L', cell: 'c' },
  { key: null, label: 'Weight', cell: 'c' },
]

export const HoldingsTable: React.FC = () => {
  const [params, setParams] = useSearchParams()
  const { holdings, loading, error, refresh } = usePortfolio()
  const fmt = useMoney()

  const [q, setQ] = useState('')
  const [sort, setSort] = useState(() => sortKeyFromParam(params.get('sort')))
  const [grouped, setGrouped] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Filters live in the URL so dashboard drill-downs and shared links keep working
  const brokers = useMemo(() => (params.get('broker') || '').split(',').filter(Boolean), [params])
  const classes = useMemo(() => (params.get('assetClass') || '').split(',').filter(Boolean) as CanonicalAssetClass[], [params])
  const pnlFilter = params.get('pnl') || 'all'
  const highlight = (params.get('highlight') || '').toLowerCase()

  const setParam = (name: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(name, value)
    else next.delete(name)
    next.delete('highlight')
    setParams(next, { replace: true })
  }

  const totalValue = useMemo(() => holdings.reduce((s, h) => s + (h.current_value || 0), 0), [holdings])
  const brokerOptions = useMemo(
    () => [...new Set(holdings.map((h) => brokerKeyOf(h.connection_id)).filter(Boolean))].sort(),
    [holdings],
  )

  // 1. broker -> merge across brokers -> search; class counts are taken here so they reflect the other filters
  const searched = useMemo(() => {
    const scoped = brokers.length > 0 ? holdings.filter((h) => brokers.some((b) => matchesBroker(h, b))) : holdings
    const needle = q.trim().toLowerCase()
    return buildInstruments(scoped).filter(
      (i) =>
        !needle ||
        i.sym.toLowerCase().includes(needle) ||
        CLASS_LABEL[i.cls].toLowerCase().includes(needle) ||
        i.brokers.some((b) => brokerLabel(b).toLowerCase().includes(needle)),
    )
  }, [holdings, brokers, q])

  const classCounts = useMemo(() => {
    const counts = new Map<CanonicalAssetClass, number>()
    searched.forEach((i) => counts.set(i.cls, (counts.get(i.cls) ?? 0) + 1))
    return counts
  }, [searched])

  const rows = useMemo(() => {
    let list = classes.length > 0 ? searched.filter((i) => classes.includes(i.cls)) : searched
    if (pnlFilter === 'gainers') list = list.filter((i) => i.pnl >= 0)
    if (pnlFilter === 'losers') list = list.filter((i) => i.pnl < 0)
    return sortInstruments(list, sort.key, sort.dir)
  }, [searched, classes, pnlFilter, sort])

  // Totals for the summary tiles and footer
  const totals = useMemo(() => {
    const cur = rows.reduce((s, i) => s + i.cur, 0)
    const inv = rows.reduce((s, i) => s + i.inv, 0)
    const reporting = rows.filter((i) => i.day !== null)
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
      winners: rows.filter((i) => i.pnl >= 0).length,
      losers: rows.filter((i) => i.pnl < 0).length,
    }
  }, [rows])

  const maxCur = useMemo(() => Math.max(1, ...rows.map((i) => i.cur)), [rows])
  const highlightedKey = useMemo(
    () => (highlight ? rows.find((i) => i.sym.toLowerCase().includes(highlight))?.key ?? null : null),
    [highlight, rows],
  )

  // Bring a dashboard-linked instrument into view
  useEffect(() => {
    if (!highlightedKey) return
    const t = setTimeout(() => document.getElementById(`ins-${highlightedKey}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 250)
    return () => clearTimeout(t)
  }, [highlightedKey])

  const toggleOpen = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'sym' ? 1 : -1 }))

  const exportCsv = () => {
    const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
    const header = ['Symbol', 'Asset class', 'Broker', 'Quantity', 'Avg cost', 'LTP', 'Invested', 'Current value', 'P&L', 'P&L %', '1D P&L']
    const lines = rows.flatMap((i) =>
      i.lots.map((l) => {
        const inv = l.inv
        return [
          i.sym,
          CLASS_LABEL[i.cls],
          brokerLabel(l.brokerKey),
          l.qty,
          (l.holding.average_price || 0).toFixed(2),
          i.ltp.toFixed(2),
          inv.toFixed(2),
          l.cur.toFixed(2),
          l.pnl.toFixed(2),
          inv > 0 ? ((l.pnl / inv) * 100).toFixed(2) : '',
          l.day === null ? '' : l.day.toFixed(2),
        ]
          .map(esc)
          .join(',')
      }),
    )
    const blob = new Blob([[header.map(esc).join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `holdings_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const clearFilters = () => {
    setQ('')
    setParams(new URLSearchParams(), { replace: true })
  }

  if (loading && holdings.length === 0) {
    return <div className="card empty">Loading holdings…</div>
  }
  if (error && holdings.length === 0) {
    return (
      <div className="card" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span className="badge bad">
          <i />
          Could not load holdings
        </span>
        <span className="sub" style={{ margin: 0, flex: '1 1 240px' }}>
          {error}
        </span>
        <button className="btn" type="button" onClick={() => refresh()}>
          Retry
        </button>
      </div>
    )
  }

  const activeFilters: { label: string; clear: () => void }[] = [
    ...(pnlFilter !== 'all' ? [{ label: pnlFilter === 'gainers' ? 'Gainers only' : 'Losers only', clear: () => setParam('pnl', null) }] : []),
    ...(classes.length > 1 ? [{ label: `${classes.length} asset classes`, clear: () => setParam('assetClass', null) }] : []),
    ...(brokers.length > 1 ? [{ label: `${brokers.length} brokers`, clear: () => setParam('broker', null) }] : []),
  ]

  const renderRow = (i: Instrument) => {
    const open = expanded.has(i.key) || i.key === highlightedKey
    const noDay = i.day === null
    return (
      <React.Fragment key={i.key}>
        <div className={`tr${i.key === highlightedKey ? ' hl' : ''}`} id={`ins-${i.key}`}>
          <div className="c0">
            <button
              type="button"
              className={`exp${open ? ' open' : ''}`}
              aria-expanded={open}
              aria-label={`Show broker breakdown for ${i.sym}`}
              onClick={() => toggleOpen(i.key)}
            >
              <ChevronRight size={16} strokeWidth={1.75} />
            </button>
            <div style={{ minWidth: 0 }}>
              <div className="ins-sym">
                <span title={i.sym}>{i.sym.length > 34 ? `${i.sym.slice(0, 33)}…` : i.sym}</span>
                <BrokerBadges keys={i.brokers} />
              </div>
              <div className="ins-nm">
                <span className="cls-tag">
                  <span className="dot" style={{ background: CLASS_COLOR[i.cls], width: 6, height: 6 }} />
                  {CLASS_LABEL[i.cls]}
                </span>
              </div>
            </div>
          </div>
          <div className="c c-hide">{formatQty(i.qty)}</div>
          <div className="c c-hide">{fmt.price(i.avg)}</div>
          <div className="c c-hide">{fmt.price(i.ltp)}</div>
          <div className="c" data-label="Invested">
            {fmt.money(i.inv)}
          </div>
          <div className="c" data-label="Current" style={{ fontWeight: 600 }}>
            {fmt.money(i.cur)}
          </div>
          <div className={`c ${tone(i.pnl)}`} data-label="P&L">
            <div>{fmt.signedMoney(i.pnl)}</div>
            <div className="s2">{pct(i.pnlPct)}</div>
          </div>
          <div className={`c ${tone(i.day)}`} data-label="1-day P&L" title={noDay ? 'Not reported by the broker' : undefined}>
            <div>{noDay ? EM_DASH : fmt.signedMoney(i.day)}</div>
            <div className="s2">{noDay ? '' : pct(i.dayPct)}</div>
          </div>
          <div className="c c-hide">
            <div className="wcell">
              <span>{weight(totalValue > 0 ? (i.cur / totalValue) * 100 : null)}</span>
              <span className="track">
                <span style={{ width: `${(i.cur / maxCur) * 100}%` }} />
              </span>
            </div>
          </div>
        </div>

        {open && (
          <div className="detail">
            <div className="dscroll">
              <div className="dgrid">
                <div className="dh">Broker</div>
                <div className="dh r">Qty</div>
                <div className="dh r">Avg cost</div>
                <div className="dh r">Invested</div>
                <div className="dh r">Current</div>
                <div className="dh r">P&amp;L</div>
                <div className="dh r">Share</div>
                {i.lots.map((l) => (
                  <React.Fragment key={l.holding.holding_id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <BrokerBadges keys={[l.brokerKey]} />
                      {brokerLabel(l.brokerKey)}
                    </div>
                    <div className="r">{formatQty(l.qty)}</div>
                    <div className="r">{fmt.price(l.holding.average_price)}</div>
                    <div className="r">{fmt.money(l.inv)}</div>
                    <div className="r">{fmt.money(l.cur)}</div>
                    <div className={`r ${tone(l.pnl)}`}>
                      {fmt.signedMoney(l.pnl)} ({pct(l.inv > 0 ? (l.pnl / l.inv) * 100 : null)})
                    </div>
                    <div className="r">{i.qty > 0 ? `${Math.round((l.qty / i.qty) * 100)}%` : EM_DASH}</div>
                  </React.Fragment>
                ))}
              </div>
            </div>
            <div className="dmeta">
              <span>
                LTP <b className="num">{fmt.price(i.ltp)}</b>
              </span>
              <span>
                Day change <b className={`num ${tone(i.dayPct)}`}>{pct(i.dayPct)}</b>
              </span>
              <span>
                Price <b>{i.freshness === 'live' ? 'Live' : i.freshness === 'cached' ? 'Stored (not live)' : 'Partly live'}</b>
              </span>
            </div>
          </div>
        )}
      </React.Fragment>
    )
  }

  const body: React.ReactNode[] = []
  if (grouped) {
    CLASS_ORDER.forEach((c) => {
      const items = rows.filter((i) => i.cls === c)
      if (items.length === 0) return
      const cur = items.reduce((s, i) => s + i.cur, 0)
      const inv = items.reduce((s, i) => s + i.inv, 0)
      const reporting = items.filter((i) => i.day !== null)
      const day = reporting.reduce((s, i) => s + (i.day as number), 0)
      const dayBase = reporting.reduce((s, i) => s + i.cur - (i.day as number), 0)
      const groupPct = inv > 0 ? ((cur - inv) / inv) * 100 : null
      const groupDayPct = reporting.length > 0 && dayBase > 0 ? (day / dayBase) * 100 : null
      body.push(
        <div className="tr gr" key={`g-${c}`}>
          <div className="c0">
            <span className="dot" style={{ background: CLASS_COLOR[c] }} />
            {CLASS_LABEL[c]} <span className="muted num">{items.length}</span>
          </div>
          <div className="c c-hide" />
          <div className="c c-hide" />
          <div className="c c-hide" />
          <div className="c c-hide num">{fmt.money(inv)}</div>
          <div className="c num c-keep">{fmt.money(cur)}</div>
          <div className={`c c-hide num ${tone(cur - inv)}`}>{pct(groupPct)}</div>
          <div className={`c c-hide num ${tone(groupDayPct)}`}>{pct(groupDayPct)}</div>
          <div className="c c-hide num">{weight(totalValue > 0 ? (cur / totalValue) * 100 : null)}</div>
        </div>,
      )
      items.forEach((i) => body.push(renderRow(i)))
    })
  } else {
    rows.forEach((i) => body.push(renderRow(i)))
  }

  const dayNote =
    totals.reporting === 0
      ? 'No day change reported yet'
      : totals.reporting < rows.length
      ? `${totals.reporting} of ${rows.length} reporting`
      : 'All positions reporting'

  return (
    <>
      <section className="sum" aria-label="Summary of filtered holdings">
        <div className="card">
          <div className="lbl">Current value</div>
          <div className="val num">{fmt.compact(totals.cur)}</div>
          <div className="foot num">{rows.length} holdings shown</div>
        </div>
        <div className="card">
          <div className="lbl">Invested</div>
          <div className="val num">{fmt.compact(totals.inv)}</div>
          <div className="foot">Weighted avg. cost</div>
        </div>
        <div className="card">
          <div className="lbl">Total P&amp;L</div>
          <div className={`val num ${tone(totals.pnl)}`}>{fmt.signedCompact(totals.pnl)}</div>
          <div className="foot">
            <span className={`pill ${tone(totals.pnl)}`}>{pct(totals.pnlPct)}</span>
          </div>
        </div>
        <div className="card">
          <div className="lbl">1-day P&amp;L</div>
          <div className={`val num ${tone(totals.day)}`}>{totals.day === null ? EM_DASH : fmt.signedCompact(totals.day)}</div>
          <div className="foot">
            {totals.day === null ? (
              dayNote
            ) : (
              <>
                <span className={`pill ${tone(totals.day)}`}>{pct(totals.dayPct)}</span> <span>{dayNote}</span>
              </>
            )}
          </div>
        </div>
        <div className="card">
          <div className="lbl">Winners / losers</div>
          <div className="val num">
            {totals.winners} <span style={{ color: 'var(--text-3)', fontWeight: 500 }}>/</span> {totals.losers}
          </div>
          <div className="foot">Positions above / below cost</div>
        </div>
      </section>

      <section className="toolbar" aria-label="Filters">
        <div className="search">
          <label className="sr" htmlFor="holdings-q">
            Search holdings
          </label>
          <Search size={16} strokeWidth={1.75} aria-hidden="true" />
          <input
            id="holdings-q"
            className="input"
            type="search"
            placeholder="Search symbol, class or broker"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>

        <div className="seg" role="group" aria-label="Asset class">
          <button type="button" className={classes.length === 0 ? 'on' : ''} aria-pressed={classes.length === 0} onClick={() => setParam('assetClass', null)}>
            All<span className="cnt num">{searched.length}</span>
          </button>
          {CLASS_ORDER.filter((c) => (classCounts.get(c) ?? 0) > 0 || classes.includes(c)).map((c) => {
            const on = classes.length === 1 && classes[0] === c
            return (
              <button key={c} type="button" className={on ? 'on' : ''} aria-pressed={on} onClick={() => setParam('assetClass', c)}>
                <span className="dot" style={{ background: CLASS_COLOR[c] }} />
                {CLASS_LABEL[c]}
                <span className="cnt num">{classCounts.get(c) ?? 0}</span>
              </button>
            )
          })}
        </div>

        <label className="sr" htmlFor="holdings-broker">
          Broker
        </label>
        <select
          id="holdings-broker"
          className="select"
          value={brokers.length > 1 ? '__multi' : brokers[0] ?? 'all'}
          onChange={(e) => setParam('broker', e.target.value === 'all' ? null : e.target.value)}
        >
          <option value="all">All brokers</option>
          {brokers.length > 1 && (
            <option value="__multi" disabled>
              {brokers.length} selected
            </option>
          )}
          {brokerOptions.map((b) => (
            <option key={b} value={b}>
              {brokerLabel(b)}
            </option>
          ))}
        </select>

        <span className="spacer" />
        <label className="switch">
          <input type="checkbox" checked={grouped} onChange={() => setGrouped((g) => !g)} />
          Group by asset class
        </label>
        <button className="btn" type="button" onClick={exportCsv} disabled={rows.length === 0}>
          <Download size={16} strokeWidth={1.75} aria-hidden="true" />
          <span className="hide-sm">Export CSV</span>
        </button>
      </section>

      {activeFilters.length > 0 && (
        <div className="chips" aria-label="Active filters">
          {activeFilters.map((f) => (
            <button key={f.label} type="button" className="chip" onClick={f.clear} aria-label={`Remove filter: ${f.label}`}>
              {f.label}
              <X size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          ))}
          <button type="button" className="btn btn-ghost" style={{ minHeight: 26, padding: '0 8px' }} onClick={clearFilters}>
            Clear all
          </button>
        </div>
      )}

      <section className="card tcard" aria-label="Holdings table">
        <div className="tscroll">
          <div className="tbl">
            <div className="tr th">
              {COLUMNS.map((col) => {
                const on = col.key !== null && sort.key === col.key
                return (
                  <div key={col.label} className={col.cell}>
                    {col.key ? (
                      <button type="button" className={on ? 'on' : ''} onClick={() => onSort(col.key as SortKey)} aria-label={`Sort by ${col.label}`}>
                        {col.label}
                        <span aria-hidden="true">{on ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}</span>
                      </button>
                    ) : (
                      <button type="button" style={{ cursor: 'default' }} tabIndex={-1}>
                        {col.label}
                      </button>
                    )}
                  </div>
                )
              })}
            </div>

            {rows.length === 0 ? (
              <div className="empty">{holdings.length === 0 ? 'No holdings yet. Connect a broker and run a sync.' : 'No holdings match these filters.'}</div>
            ) : (
              body
            )}

            {rows.length > 0 && (
              <div className="tr tf">
                <div className="c0">Total · {rows.length} holdings</div>
                <div className="c c-hide" />
                <div className="c c-hide" />
                <div className="c c-hide" />
                <div className="c" data-label="Invested">
                  {fmt.money(totals.inv)}
                </div>
                <div className="c" data-label="Current">
                  {fmt.money(totals.cur)}
                </div>
                <div className={`c ${tone(totals.pnl)}`} data-label="P&L">
                  <div>{fmt.signedMoney(totals.pnl)}</div>
                  <div className="s2">{pct(totals.pnlPct)}</div>
                </div>
                <div className={`c ${tone(totals.day)}`} data-label="1-day P&L">
                  <div>{totals.day === null ? EM_DASH : fmt.signedMoney(totals.day)}</div>
                  <div className="s2">{totals.day === null ? '' : pct(totals.dayPct)}</div>
                </div>
                <div className="c c-hide">{weight(totalValue > 0 ? (totals.cur / totalValue) * 100 : null)}</div>
              </div>
            )}
          </div>
        </div>
      </section>

      <p className="sub">
        Weight is the share of your total portfolio value across all brokers. Average cost is quantity-weighted across brokers. Day change comes from the
        brokers; mutual funds and NPS do not report one, so they show a dash and are left out of the 1-day total.
      </p>
    </>
  )
}
