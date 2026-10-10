// Shared number formatting for analytics pages

export const formatINR = (val: number | null | undefined): string => {
  if (val == null) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(val)
}

export const formatPct = (val: number | null | undefined, digits = 2): string => {
  if (val == null) return '—'
  return `${val > 0 ? '+' : ''}${val.toFixed(digits)}%`
}

// Compact Indian-style amounts: ₹1.25Cr, ₹13.95L, ₹4.2k
export const formatCompactValue = (val: number): string => {
  const absVal = Math.abs(val)
  const sign = val < 0 ? '-' : ''

  if (absVal >= 10000000) return `${sign}₹${(absVal / 10000000).toFixed(2)}Cr`
  if (absVal >= 100000) return `${sign}₹${(absVal / 100000).toFixed(2)}L`
  if (absVal >= 1000) return `${sign}₹${(absVal / 1000).toFixed(1)}k`
  return `${sign}₹${absVal.toFixed(0)}`
}

// Gain/loss text tone; pair with a +/- sign so meaning is not color-alone
export const signedTone = (val: number | null | undefined): string => {
  if (val == null) return 'text-slate-400'
  return val >= 0 ? 'text-emerald-700' : 'text-rose-700'
}

export const formatMonth = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })

export const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

// X-axis ticks on the first trading day of each month, thinned to at most `maxTicks`
export const monthTicks = (dates: string[], maxTicks = 8): string[] => {
  const firsts = dates.filter((d, i) => i > 0 && d.slice(0, 7) !== dates[i - 1].slice(0, 7))
  const step = Math.max(1, Math.ceil(firsts.length / maxTicks))
  return firsts.filter((_, i) => i % step === 0)
}

// ---------------------------------------------------------------------------
// Design-system number helpers (one set for every page)
//  - Indian digit grouping, true minus (U+2212), em dash for missing values, never 0 for unknown
// ---------------------------------------------------------------------------

const MINUS = '\u2212'
const EM_DASH = '\u2014'

const grouped = (abs: number, digits: number) =>
  new Intl.NumberFormat('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(abs)

/** Table amounts: ₹3,52,608 (0 dp) */
export const money = (v: number | null | undefined, digits = 0): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  return `${v < 0 ? MINUS : ''}₹${grouped(Math.abs(v), digits)}`
}

/** Prices and average costs: ₹2,938.40 (2 dp) */
export const price = (v: number | null | undefined): string => money(v, 2)

/** KPIs and charts: ₹70.41 L, ₹1.24 Cr; below one lakh falls back to grouped rupees */
export const compact = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  const abs = Math.abs(v)
  const sign = v < 0 ? MINUS : ''
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`
  return `${sign}₹${grouped(abs, 0)}`
}

/** Changes are always signed: +₹63,408 / −₹4,600 */
export const signedMoney = (v: number | null | undefined, digits = 0): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  return `${v < 0 ? MINUS : '+'}₹${grouped(Math.abs(v), digits)}`
}

export const signedCompact = (v: number | null | undefined): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  return `${v < 0 ? MINUS : '+'}${compact(Math.abs(v))}`
}

/** Percent changes: 2 dp, signed (+21.93%) */
export const pct = (v: number | null | undefined, digits = 2): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  return `${v < 0 ? MINUS : '+'}${Math.abs(v).toFixed(digits)}%`
}

/** Weights and shares: 2 dp, unsigned (6.23%) */
export const weight = (v: number | null | undefined, digits = 2): string => {
  if (v == null || !Number.isFinite(v)) return EM_DASH
  return `${v.toFixed(digits)}%`
}

/** CSS class for a gain/loss value: 'pos' | 'neg' | '' (use together with a sign, never colour alone) */
export const tone = (v: number | null | undefined): '' | 'pos' | 'neg' => (v == null || v === 0 ? '' : v > 0 ? 'pos' : 'neg')
