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
