import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { fetchLiveSignals, fetchSignals } from '../../utils/api'
import { price as inrPrice, tone } from '../../utils/format'
import { usePortfolio } from '../../context/PortfolioContext'
import { StockLink } from '../StockLink'
import { buildBuys, buildSells, latestSessions, type CallSource } from '../signals/NewCalls'
import { useLiveSignals } from '../signals/useLiveSignals'
import { FreshnessChip } from '../signals/FreshnessChip'
import { indiaSessionActive } from '../../utils/session'
import { readSignals } from '../signals/signalKit'
import type { Fmt } from '../signals/signalKit'
import type { SignalsResponse, StockSignals } from '../../types'
import type { Instrument } from '../holdings/holdingsModel'

const inr: Fmt = {
  price: (v) => inrPrice(v),
  perShare: (v) => `${v < 0 ? '−' : '+'}₹${Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`,
}
const usdFmt: Fmt = {
  price: (v) => (v == null ? '—' : `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`),
  perShare: (v) => `${v < 0 ? '−' : '+'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 2 })}`,
}

const longDate = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
const tickerOf = (s: string) => s.trim().split(/\s+/)[0].toUpperCase()

export interface SignalDigest {
  sells: number
  sellNames: string[]
  buys: number
  review: number
  ready: boolean
}

export const SignalsPanel: React.FC<{ instruments: Instrument[]; onDigest?: (d: SignalDigest) => void }> = ({ instruments, onDigest }) => {
  const { stockHref } = usePortfolio()
  const [base, setBase] = useState<{ in?: SignalsResponse; us?: SignalsResponse }>({})
  const [failed, setFailed] = useState(false)

  const hasIn = instruments.some((i) => i.cls === 'EQUITY')
  const hasUs = instruments.some((i) => i.cls === 'US_STOCKS')

  useEffect(() => {
    let stop = false
    Promise.all([hasIn ? fetchSignals('in') : Promise.resolve(undefined), hasUs ? fetchSignals('us') : Promise.resolve(undefined)])
      .then(([a, b]) => !stop && setBase({ in: a, us: b }))
      .catch(() => !stop && setFailed(true))
    return () => {
      stop = true
    }
  }, [hasIn, hasUs])

  const liveIn = useLiveSignals(() => fetchLiveSignals('in'), hasIn && !!base.in, () => 120_000, 'dash-in')
  const liveUs = useLiveSignals(() => fetchLiveSignals('us'), hasUs && !!base.us, () => 120_000, 'dash-us')

  const model = useMemo(() => {
    const make = (cls: 'EQUITY' | 'US_STOCKS', data: SignalsResponse | undefined, live: Record<string, StockSignals>): CallSource[] => {
      if (!data) return []
      const sigs = { ...data.signals, ...live }
      return instruments
        .filter((i) => i.cls === cls)
        .map((i) => {
          const id = data.symbol_map[i.lots[0]?.holding.instrument_symbol ?? '']
          const sig = id ? sigs[id] : undefined
          return {
            code: cls === 'US_STOCKS' ? tickerOf(i.sym) : i.sym,
            name: i.sym,
            held: true,
            sig,
            ltp: cls === 'US_STOCKS' ? sig?.momentum?.last_price ?? 0 : i.ltp,
            href: cls === 'EQUITY' ? stockHref(i) : null,
          }
        })
    }
    const inSrc = make('EQUITY', base.in, liveIn.signals)
    const usSrc = make('US_STOCKS', base.us, liveUs.signals)
    const all = [...inSrc, ...usSrc]
    const s7 = latestSessions(all, 7)
    const s2 = latestSessions(all, 2)
    const rows = (src: CallSource[], fmt: Fmt) => ({
      sells: buildSells(src, s7, fmt, false),
      buys: buildBuys(src, s2, 2, fmt, false),
    })
    const a = rows(inSrc, inr)
    const b = rows(usSrc, usdFmt)
    const sells = [...a.sells, ...b.sells].sort((x, y) => y.date.localeCompare(x.date))
    const buys = [...a.buys, ...b.buys].filter((r) => !r.waiting).sort((x, y) => y.date.localeCompare(x.date))
    const waitingBuys = [...a.buys, ...b.buys].filter((r) => r.waiting)
    // the same "all bearish" reading the Signals page filters on, so the count matches what the link opens
    const review = all.filter((s) => readSignals(s.sig, s.ltp).alignment === 'all-bear')
    const covered = all.filter((s) => s.sig && (s.sig.momentum || s.sig.ath)).length
    const market = (rows: { src: CallSource }[]) => (rows.length > 0 && rows.every((r) => inSrc.includes(r.src) === false) ? 'us' : 'in')
    const links = {
      // source=held: these counts are your holdings only, so the page opens on them
      sells: `/signals?view=calls&side=sell&source=held${market(sells) === 'us' ? '&market=us' : ''}`,
      buys: `/signals?view=calls&side=buy&window=2&source=held${market(buys) === 'us' ? '&market=us' : ''}`,
      review: `/signals?filter=all-bear&source=held${review.length > 0 && review.every((r) => usSrc.includes(r)) ? '&market=us' : ''}`,
    }
    return { links, sells, buys, waitingBuys, review, covered, total: all.length, hasExit: all.some((s) => s.sig?.ath?.exits), s7 }
  }, [base, liveIn.signals, liveUs.signals, instruments, stockHref])

  useEffect(() => {
    onDigest?.({
      sells: model.sells.filter((r) => !r.waiting).length + model.sells.filter((r) => r.waiting).length,
      sellNames: [...new Set(model.sells.map((r) => r.src.name))].slice(0, 3),
      buys: model.buys.length,
      review: model.review.length,
      ready: model.covered > 0,
    })
  }, [model, onDigest])

  return (
    <section className="card bx-panel" aria-label="Signals on your holdings">
      <header className="bx-ph">
        <div>
          <h2 className="card-t">Signals on your holdings</h2>
          <p className="card-s">ATH breakout calls, on live prices</p>
        </div>
        <div className="bx-ph-r">
          {hasIn && <FreshnessChip status={liveIn.status} broker="Kite" sessionOpen={indiaSessionActive()} />}
          <Link className="link" to="/signals">
            Open
          </Link>
        </div>
      </header>

      {failed || model.covered === 0 ? (
        <p className="empty-s">
          {failed ? 'Signals could not be loaded.' : 'No signals saved yet. Press Refresh Momentum Stocks on the Signals page once.'}
        </p>
      ) : (
        <div className="bx-sig">
          <div className="bx-sig-tiles">
            <Link to={model.links.sells} className={`bx-sig-tile ${model.sells.length ? 'bad' : ''}`} aria-label={`${model.sells.length} sell calls in the last 7 sessions: open them`}>
              <span className="n num">{model.sells.length}</span>
              <span className="l">Sell calls · 7 sessions</span>
              <ChevronRight className="go" size={16} strokeWidth={2} aria-hidden="true" />
            </Link>
            <Link to={model.links.buys} className="bx-sig-tile ok" aria-label={`${model.buys.length} new buys in the last 2 sessions: open them`}>
              <span className="n num">{model.buys.length}</span>
              <span className="l">New buys · 2 sessions</span>
              <ChevronRight className="go" size={16} strokeWidth={2} aria-hidden="true" />
            </Link>
            <Link to={model.links.review} className={`bx-sig-tile ${model.review.length ? 'warn' : ''}`} aria-label={`${model.review.length} holdings to review: open them`}>
              <span className="n num">{model.review.length}</span>
              <span className="l">To review</span>
              <ChevronRight className="go" size={16} strokeWidth={2} aria-hidden="true" />
            </Link>
          </div>

          {!model.hasExit && <p className="empty-s">Sell history is added after the next signals refresh.</p>}
          {model.review.length > 0 && (
            <p className="bx-fine">
              <b>To review</b> (both signals bearish): {model.review.slice(0, 6).map((r) => r.name).join(', ')}
              {model.review.length > 6 ? ` and ${model.review.length - 6} more` : ''}
            </p>
          )}

          <div className="bx-sig-list">
            <Link to={model.links.sells} className="bx-who-h neg bx-who-link">
              Sell calls <ChevronRight size={12} strokeWidth={2.2} aria-hidden="true" />
            </Link>
            {model.sells.length === 0 && <p className="empty-s">No sell calls on your holdings in the last 7 sessions.</p>}
            {model.sells.slice(0, 4).map((r) => (
              <div className="bx-sig-r" key={r.key}>
                <div>
                  <StockLink href={r.src.href ?? null}>{r.src.name.length > 26 ? `${r.src.name.slice(0, 25)}…` : r.src.name}</StockLink>
                  <span className="badge ok">ATH</span>
                  {r.waiting && <span className="badge warn">Waiting</span>}
                </div>
                <div className={`sub num ${r.tailTone ?? ''}`}>
                  {longDate(r.date)} · {r.tail || r.why}
                </div>
              </div>
            ))}
            <Link to={model.links.buys} className="bx-who-h pos bx-who-link">
              New buys <ChevronRight size={12} strokeWidth={2.2} aria-hidden="true" />
            </Link>
            {model.buys.length === 0 && <p className="empty-s">No new buys on your holdings in the last 2 sessions.</p>}
            {model.buys.slice(0, 3).map((r) => (
              <div className="bx-sig-r" key={r.key}>
                <div>
                  <StockLink href={r.src.href ?? null}>{r.src.name.length > 26 ? `${r.src.name.slice(0, 25)}…` : r.src.name}</StockLink>
                  <span className="badge ok">ATH</span>
                </div>
                <div className={`sub num ${tone(r.sinceRef?.abs)}`}>
                  {longDate(r.date)} · {r.why}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
