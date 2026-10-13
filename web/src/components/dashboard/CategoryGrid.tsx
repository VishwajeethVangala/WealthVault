import React from 'react'
import { Link } from 'react-router-dom'
import { pct, tone } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { CLASS_COLOR, CLASS_LABEL } from '../holdings/holdingsModel'
import { PERIODS, type ClassCard, type Period } from './metrics'

const Spark: React.FC<{ values: number[]; color: string }> = ({ values, color }) => {
  if (values.length < 2) return <div className="bx-spark empty" aria-hidden="true" />
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${30 - ((v - min) / span) * 26 - 2}`).join(' ')
  return (
    <svg className="bx-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={`0,30 ${pts} 100,30`} fill={color} fillOpacity="0.10" stroke="none" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

const short = (s: string, n = 16) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

export const CategoryGrid: React.FC<{ cards: ClassCard[]; period: Period; usdMove: number | null }> = ({ cards, period, usdMove }) => {
  const { compact, signedCompact } = useMoney()
  const periodLabel = PERIODS.find((p) => p.id === period)?.label ?? ''
  return (
    <section className="bx-cats" aria-label="By asset class" style={{ ['--n' as string]: cards.length }}>
      {cards.map((c) => (
        <Link key={c.cls} to={`/holdings?assetClass=${c.cls}`} className="card bx-cat" aria-label={`${CLASS_LABEL[c.cls]}: open holdings`}>
          <div className="bx-cat-h">
            <span className="dot" style={{ background: CLASS_COLOR[c.cls] }} aria-hidden="true" />
            <span className="bx-cat-t">{CLASS_LABEL[c.cls]}</span>
            <span className="bx-cat-w num">{c.weight.toFixed(1)}%</span>
          </div>
          <div className="bx-cat-v num">{compact(c.cur)}</div>
          <div className="bx-wbar" aria-hidden="true">
            <i style={{ width: `${Math.min(100, c.weight)}%`, background: CLASS_COLOR[c.cls] }} />
          </div>
          <div className="bx-cat-pair">
            <div>
              <span className="bx-mini">Total P&amp;L</span>
              <span className={`bx-m num ${tone(c.pnl)}`}>{signedCompact(c.pnl)}</span>
              <span className={`bx-p num ${tone(c.pnl)}`}>{pct(c.pnlPct)}</span>
            </div>
            <div>
              <span className="bx-mini">1-day</span>
              <span className={`bx-m num ${tone(c.day)}`}>{c.day === null ? '—' : signedCompact(c.day)}</span>
              <span className={`bx-p num ${tone(c.day)}`}>{c.day === null ? 'no feed' : pct(c.dayPct)}</span>
            </div>
          </div>
          <Spark values={c.spark} color={CLASS_COLOR[c.cls]} />
          <div className="bx-cat-foot">
            {period !== '1D' && (
              <span className={`num ${tone(c.change)}`} title="Includes money you added">
                {periodLabel}: {c.change === null ? '—' : signedCompact(c.change)}
              </span>
            )}
            {c.cls === 'US_STOCKS' && usdMove != null && <span className="num">{pct(usdMove)} in USD today</span>}
            {c.best && <span className="pos num">▲ {short(c.best.sym)}</span>}
            {c.worst && <span className="neg num">▼ {short(c.worst.sym)}</span>}
          </div>
        </Link>
      ))}
    </section>
  )
}
