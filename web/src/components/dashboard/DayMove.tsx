import React from 'react'
import { pct, tone } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { usePortfolio } from '../../context/PortfolioContext'
import { StockLink } from '../StockLink'
import { CLASS_COLOR, CLASS_LABEL, type Instrument } from '../holdings/holdingsModel'
import type { ClassCard } from './metrics'

const short = (s: string, n = 24) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

/** Today's P&L by asset class on a centred axis, then the holdings behind it. */
export const DayMove: React.FC<{ cards: ClassCard[]; instruments: Instrument[]; total: number | null }> = ({ cards, instruments, total }) => {
  const { signedCompact } = useMoney()
  const { stockHref } = usePortfolio()
  const rows = cards.filter((c) => c.day !== null).sort((a, b) => Math.abs(b.day as number) - Math.abs(a.day as number))
  const max = Math.max(...rows.map((r) => Math.abs(r.day as number)), 1)
  const ranked = instruments.filter((i) => i.day !== null).sort((a, b) => (b.day as number) - (a.day as number))
  const up = ranked.filter((i) => (i.day as number) > 0).slice(0, 5)
  const down = ranked.filter((i) => (i.day as number) < 0).reverse().slice(0, 5)
  const byPct = instruments.filter((i) => i.dayPct !== null).sort((a, b) => (b.dayPct as number) - (a.dayPct as number))
  const pctUp = byPct.filter((i) => (i.dayPct as number) > 0).slice(0, 4)
  const pctDown = byPct.filter((i) => (i.dayPct as number) < 0).reverse().slice(0, 4)

  return (
    <section className="card bx-panel" aria-label="Why today moved">
      <header className="bx-ph">
        <div>
          <h2 className="card-t">Why today moved</h2>
          <p className="card-s">{total === null ? 'No day change reported yet' : `${signedCompact(total)} in total, by asset class and by holding`}</p>
        </div>
      </header>
      {rows.length === 0 ? (
        <p className="empty-s">No asset class has reported a 1-day change yet.</p>
      ) : (
        <div className="bx-axis-rows">
          {rows.map((r) => {
            const neg = (r.day as number) < 0
            return (
              <div className="bx-ax" key={r.cls}>
                <span className="bx-ax-n">
                  <span className="dot" style={{ background: CLASS_COLOR[r.cls] }} aria-hidden="true" />
                  {CLASS_LABEL[r.cls]}
                </span>
                <span className="bx-ax-track" aria-hidden="true">
                  <span className="bx-ax-zero" />
                  <i className={neg ? 'neg' : 'pos'} style={{ width: `${(Math.abs(r.day as number) / max) * 50}%`, [neg ? 'right' : 'left']: '50%' }} />
                </span>
                <span className={`bx-ax-v num ${tone(r.day)}`}>{signedCompact(r.day)}</span>
              </div>
            )
          })}
        </div>
      )}
      <div className="bx-who">
        <div>
          <p className="bx-who-h pos">Lifted the day</p>
          {up.length === 0 && <p className="empty-s">Nothing gained</p>}
          {up.map((i) => (
            <div className="bx-who-r" key={i.key}>
              <StockLink href={stockHref(i)}>{short(i.sym)}</StockLink>
              <span className="num pos">{signedCompact(i.day)}</span>
            </div>
          ))}
        </div>
        <div>
          <p className="bx-who-h neg">Pulled it down</p>
          {down.length === 0 && <p className="empty-s">Nothing lost</p>}
          {down.map((i) => (
            <div className="bx-who-r" key={i.key}>
              <StockLink href={stockHref(i)}>{short(i.sym)}</StockLink>
              <span className="num neg">{signedCompact(i.day)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="bx-who bx-who-pct">
        <div>
          <p className="bx-who-h pos">Biggest % gains</p>
          {pctUp.length === 0 && <p className="empty-s">None</p>}
          {pctUp.map((i) => (
            <div className="bx-who-r" key={i.key}>
              <StockLink href={stockHref(i)}>{short(i.sym)}</StockLink>
              <span className="num pos">{pct(i.dayPct)}</span>
            </div>
          ))}
        </div>
        <div>
          <p className="bx-who-h neg">Biggest % falls</p>
          {pctDown.length === 0 && <p className="empty-s">None</p>}
          {pctDown.map((i) => (
            <div className="bx-who-r" key={i.key}>
              <StockLink href={stockHref(i)}>{short(i.sym)}</StockLink>
              <span className="num neg">{pct(i.dayPct)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
