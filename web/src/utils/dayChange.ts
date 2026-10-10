import type { Holding } from '../types'

/** Day P&L in ₹ for a holding, or null when the broker/market feed reported none. */
export const dayPnlOf = (h: Holding): number | null => {
  if (h.day_pnl !== undefined && h.day_pnl !== null) return h.day_pnl
  if (h.day_change !== undefined && h.day_change !== null) return h.quantity * h.day_change
  return null
}

/** Day change % for a holding (vs previous value), or null when unknown. */
export const dayPctOf = (h: Holding): number | null => {
  if (h.day_change_percentage !== undefined && h.day_change_percentage !== null) return h.day_change_percentage
  const pnl = dayPnlOf(h)
  const prev = (h.current_value || 0) - (pnl ?? 0)
  return pnl !== null && prev > 0 ? (pnl / prev) * 100 : null
}

/** Short display name; INDmoney symbols look like "CODE (Company Name)". */
export const displaySymbol = (h: Holding): string => {
  const sym = h.instrument_symbol || ''
  const m = sym.match(/\((.+)\)\s*$/)
  return (m ? m[1] : sym).trim()
}

// A single holding above this share of the portfolio is flagged as concentrated
export const SINGLE_POSITION_LIMIT_PCT = 10
