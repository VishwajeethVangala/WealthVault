import React, { useEffect, useState } from 'react'
import { pct, tone } from '../utils/format'
import { useMoney } from '../utils/useMoney'
import type { Totals } from './dashboard/metrics'

/** Height of the pinned bar; the search row pins just under it (see .pin-search in holdings.css). */
const PIN_HEIGHT = 52

/** True once the watched block has scrolled up past the pinned bar. */
const useScrolledPast = (watch: React.RefObject<HTMLElement | null>): boolean => {
  const [past, setPast] = useState(false)
  useEffect(() => {
    const el = watch.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      ([entry]) => setPast(!entry.isIntersecting && entry.boundingClientRect.bottom < PIN_HEIGHT),
      { rootMargin: `-${PIN_HEIGHT}px 0px 0px 0px` },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [watch])
  return past
}

/**
 * A slim Invested / Current / Total P&L / Day P&L bar that slides in at the top of the page once the full
 * summary cards have scrolled away. Tapping it returns to the cards.
 */
export const SummaryPin: React.FC<{ totals: Totals; watch: React.RefObject<HTMLElement | null> }> = ({ totals, watch }) => {
  const past = useScrolledPast(watch)
  const fmt = useMoney()

  const back = () => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
  }

  return (
    <div className="pin-mini">
      <button type="button" className={`mini${past ? ' on' : ''}`} onClick={back} tabIndex={past ? 0 : -1} aria-hidden={!past} aria-label="Portfolio summary. Back to top">
        <span>
          <i>Invested</i>
          <b className="num">{fmt.compact(totals.inv)}</b>
        </span>
        <span>
          <i>Current</i>
          <b className="num">{fmt.compact(totals.cur)}</b>
        </span>
        <span className={tone(totals.pnl)}>
          <i>Total P&amp;L</i>
          <b className="num">{fmt.signedCompact(totals.pnl)}</b>
          <em className="num">{pct(totals.pnlPct)}</em>
        </span>
        <span className={tone(totals.day)}>
          <i>Day P&amp;L</i>
          <b className="num">{totals.day === null ? '—' : fmt.signedCompact(totals.day)}</b>
          <em className="num">{totals.day === null ? '' : pct(totals.dayPct)}</em>
        </span>
      </button>
    </div>
  )
}
