// Constants and helpers shared by the strategy panels

export const BUY_COLOR = '#059669'
export const SELL_COLOR = '#e11d48'
export const SETUP_FILL = '#10b981'

// Two validated categorical hues (see dataviz palette check)
export const EQUITY_SERIES = [
  { key: 'equity', label: 'Strategy', color: '#2a78d6' },
  { key: 'buy_hold', label: 'Buy & hold', color: '#eb6834' },
] as const

export interface RangeOption {
  label: string
  bars: number // 0 = all
}

// Contiguous spans where `flag(bar)` holds, for chart background shading
export function booleanSpans<T extends { date: string }>(bars: T[], flag: (bar: T) => boolean): Array<{ x1: string; x2: string }> {
  const spans: Array<{ x1: string; x2: string }> = []
  let start: string | null = null
  bars.forEach((b, i) => {
    const on = flag(b)
    if (on && start == null) start = b.date
    if (on && start != null && (i === bars.length - 1 || !flag(bars[i + 1]))) {
      spans.push({ x1: start, x2: b.date })
      start = null
    }
  })
  return spans
}

export const sliceRange = <T,>(series: T[], bars: number): T[] => (bars > 0 ? series.slice(-bars) : series)
