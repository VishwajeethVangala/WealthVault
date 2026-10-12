import React from 'react'
import { pct, tone, weight } from '../../utils/format'
import type { AthSignal, MomentumSignal, StockSignals, SwingSignal } from '../../types'

/** Shared reading of a stock's three signals, used by the Equity signals and Stage 2 pages. */

export type Lean = 'bull' | 'bear' | 'neutral'
export type Alignment = 'all-bull' | 'mixed' | 'all-bear' | 'none'

export const DASH = '—'

export const dateFmt = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : DASH

export const momentumLean = (m: MomentumSignal): Lean => (/uptrend/i.test(m.verdict) ? 'bull' : /downtrend/i.test(m.verdict) ? 'bear' : 'neutral')

export const swingLean = (s: SwingSignal): Lean =>
  s.state === 'IN_POSITION' ? (s.pending_order === 'SELL' ? 'bear' : 'bull') : s.pending_order === 'BUY' ? 'bull' : s.regime_bullish ? 'neutral' : 'bear'

export const athLean = (a: AthSignal): Lean => (a.state === 'IN_POSITION' ? 'bull' : a.last_signal === 'SELL' ? 'bear' : 'neutral')

export const momentumBadge = (m: MomentumSignal) => {
  const lean = momentumLean(m)
  return { cls: lean === 'bull' ? 'ok' : lean === 'bear' ? 'bad' : 'off', text: m.verdict }
}

export const swingBadge = (s: SwingSignal) => {
  if (s.state === 'IN_POSITION') return s.pending_order === 'SELL' ? { cls: 'warn', text: 'Sell signal' } : { cls: 'ok', text: 'In position' }
  if (s.pending_order === 'BUY') return { cls: 'info', text: 'Buy signal' }
  return s.regime_bullish ? { cls: 'off', text: 'Waiting for entry' } : { cls: 'off', text: 'No trade' }
}

export const athBadge = (a: AthSignal) => {
  if (a.state === 'IN_POSITION') return { cls: 'ok', text: 'In position' }
  if (a.last_signal === 'SELL') return { cls: 'warn', text: 'Exited' }
  return a.in_window ? { cls: 'info', text: 'Setup active' } : { cls: 'off', text: 'No setup' }
}

export const since = (entry: number | null | undefined, ltp: number): { pct: number; abs: number } | null =>
  entry && entry > 0 && ltp > 0 ? { pct: ((ltp - entry) / entry) * 100, abs: ltp - entry } : null

export interface Reading {
  leans: Lean[]
  bull: number
  bear: number
  alignment: Alignment
  swingSince: { pct: number; abs: number } | null
  athSince: { pct: number; abs: number } | null
}

/** Combine a stock's signals with its live price into the alignment and since-entry figures. */
export const readSignals = (sig: StockSignals | undefined, ltp: number): Reading => {
  const leans: Lean[] = []
  if (sig?.momentum) leans.push(momentumLean(sig.momentum))
  if (sig?.swing) leans.push(swingLean(sig.swing))
  if (sig?.ath) leans.push(athLean(sig.ath))
  const bull = leans.filter((l) => l === 'bull').length
  const bear = leans.filter((l) => l === 'bear').length
  return {
    leans,
    bull,
    bear,
    alignment: leans.length < 2 ? 'none' : bull === leans.length ? 'all-bull' : bear === leans.length ? 'all-bear' : 'mixed',
    swingSince: sig?.swing?.state === 'IN_POSITION' ? since(sig.swing.entry_price, ltp) : null,
    athSince: sig?.ath?.state === 'IN_POSITION' ? since(sig.ath.entry_price, ltp) : null,
  }
}

export const ALIGN_ORDER: Record<Alignment, number> = { 'all-bull': 3, mixed: 2, none: 1, 'all-bear': 0 }

export interface Fmt {
  /** price per share in the stock's own currency */
  price: (v: number | null | undefined) => string
  /** signed per-share change */
  perShare: (v: number) => string
}

const na = (sig: StockSignals | undefined, key: 'momentum' | 'swing' | 'ath') => (
  <span className="sg-na">{sig?.errors?.[key] ?? sig?.errors?.all ?? DASH}</span>
)

export const MomentumCell: React.FC<{ sig?: StockSignals; fmt: Fmt }> = ({ sig, fmt }) => {
  const m = sig?.momentum
  if (!m) return na(sig, 'momentum')
  return (
    <div className="sg-cell">
      <span className={`badge ${momentumBadge(m).cls}`}>{momentumBadge(m).text}</span>
      <span className="sg-line num">
        Score {m.score}/{m.max}
      </span>
      {m.range_pos !== null && (
        <>
          <div className="rng" title={`52-week range ${fmt.price(m.low_52w)} to ${fmt.price(m.high_52w)}`}>
            <i style={{ left: `${Math.min(100, Math.max(0, m.range_pos))}%` }} />
          </div>
          <span className="sg-line dim num">{pct(m.pct_from_52w_high, 1)} from 52W high</span>
        </>
      )}
    </div>
  )
}

export const SwingCell: React.FC<{ sig?: StockSignals; ltp: number; reading: Reading; fmt: Fmt }> = ({ sig, ltp, reading, fmt }) => {
  const s = sig?.swing
  if (!s) return na(sig, 'swing')
  return (
    <div className="sg-cell" title={s.detail}>
      <span className={`badge ${swingBadge(s).cls}`}>{swingBadge(s).text}</span>
      {s.state === 'IN_POSITION' ? (
        <>
          <span className="sg-line">
            Entered {dateFmt(s.entry_date)}
            {s.bars_held != null ? ` · ${s.bars_held} days` : ''}
          </span>
          {reading.swingSince && (
            <span className={`sg-line num ${tone(reading.swingSince.abs)}`}>
              {fmt.perShare(reading.swingSince.abs)}/sh ({pct(reading.swingSince.pct)}) since entry
            </span>
          )}
          {s.stop_price != null && ltp > 0 && (
            <span className="sg-line dim num">
              Stop {fmt.price(s.stop_price)} · {weight(((ltp - s.stop_price) / ltp) * 100, 1)} below
            </span>
          )}
        </>
      ) : (
        <span className="sg-line dim">{s.headline}</span>
      )}
    </div>
  )
}

export const AthCell: React.FC<{ sig?: StockSignals; reading: Reading; fmt: Fmt }> = ({ sig, reading, fmt }) => {
  const a = sig?.ath
  if (!a) return na(sig, 'ath')
  return (
    <div className="sg-cell" title={a.detail}>
      <span className={`badge ${athBadge(a).cls}`}>{athBadge(a).text}</span>
      {a.state === 'IN_POSITION' ? (
        <>
          <span className="sg-line">
            Entered {dateFmt(a.entry_date)}
            {a.bars_held != null ? ` · ${a.bars_held} days` : ''}
          </span>
          {reading.athSince && (
            <span className={`sg-line num ${tone(reading.athSince.abs)}`}>
              {fmt.perShare(reading.athSince.abs)}/sh ({pct(reading.athSince.pct)}) since entry
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
  )
}

export const AlignmentCell: React.FC<{ sig?: StockSignals; reading: Reading }> = ({ sig, reading }) => {
  if (reading.alignment === 'none') return <span className="sg-na">{sig ? 'Too few signals' : DASH}</span>
  return (
    <div className="sg-cell">
      <span className={`badge ${reading.alignment === 'all-bull' ? 'ok' : reading.alignment === 'all-bear' ? 'bad' : 'off'}`}>
        {reading.alignment === 'all-bull' ? 'All bullish' : reading.alignment === 'all-bear' ? 'All bearish' : 'Mixed'}
      </span>
      <span className="sg-line dim num">
        {reading.bull} bullish · {reading.bear} bearish
      </span>
    </div>
  )
}
