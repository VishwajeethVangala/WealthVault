import type { HistoryPoint } from '../../utils/api'
import { CLASS_ORDER, type Instrument } from '../holdings/holdingsModel'
import type { CanonicalAssetClass } from '../../utils/portfolioFilters'

export type Period = '1D' | '1W' | '1M' | '3M' | 'YTD' | 'ALL'

export const PERIODS: { id: Period; label: string; long: string }[] = [
  { id: '1D', label: '1D', long: 'today' },
  { id: '1W', label: '1W', long: 'the last week' },
  { id: '1M', label: '1M', long: 'the last month' },
  { id: '3M', label: '3M', long: 'the last 3 months' },
  { id: 'YTD', label: 'YTD', long: 'this year' },
  { id: 'ALL', label: 'All', long: 'since you started' },
]

const startOf = (period: Period): string | null => {
  const d = new Date()
  if (period === '1D') return null
  if (period === 'YTD') return `${d.getFullYear()}-01-01`
  if (period === 'ALL') return '0000-00-00'
  d.setDate(d.getDate() - { '1W': 7, '1M': 30, '3M': 91 }[period])
  return d.toISOString().slice(0, 10)
}

/** The snapshot to measure from: the last one on or before the period start, else the earliest there is. */
export const baseline = (history: HistoryPoint[], period: Period): HistoryPoint | null => {
  const from = startOf(period)
  if (!from || history.length === 0) return null
  return [...history].reverse().find((p) => p.date <= from) ?? history[0]
}

/** Snapshots shown on the hero chart: the period, or the last 30 days for "today". */
export const chartWindow = (history: HistoryPoint[], period: Period): HistoryPoint[] => {
  const from = baseline(history, period === '1D' ? '1M' : period)
  return from ? history.filter((p) => p.date >= from.date) : history
}

export interface Totals {
  cur: number
  inv: number
  pnl: number
  pnlPct: number | null
  day: number | null
  dayPct: number | null
  reporting: number
}

export const totalsOf = (instruments: Instrument[]): Totals => {
  const cur = instruments.reduce((s, i) => s + i.cur, 0)
  const inv = instruments.reduce((s, i) => s + i.inv, 0)
  const rep = instruments.filter((i) => i.day !== null)
  const day = rep.reduce((s, i) => s + (i.day as number), 0)
  const base = rep.reduce((s, i) => s + i.cur - (i.day as number), 0)
  return {
    cur,
    inv,
    pnl: cur - inv,
    pnlPct: inv > 0 ? ((cur - inv) / inv) * 100 : null,
    day: rep.length ? day : null,
    dayPct: rep.length && base > 0 ? (day / base) * 100 : null,
    reporting: rep.length,
  }
}

export interface ClassCard {
  cls: CanonicalAssetClass
  items: Instrument[]
  cur: number
  inv: number
  weight: number
  pnl: number
  pnlPct: number | null
  day: number | null
  dayPct: number | null
  reporting: number
  /** value change over the chosen period from the daily snapshots (includes money added) */
  change: number | null
  spark: number[]
  best: Instrument | null
  worst: Instrument | null
}

export const buildClassCards = (
  instruments: Instrument[],
  classHistory: Record<string, { date: string; v: number }[]>,
  fromDate: string | null,
  totalCur: number,
): ClassCard[] =>
  CLASS_ORDER.map((cls) => {
    const items = instruments.filter((i) => i.cls === cls)
    const cur = items.reduce((s, i) => s + i.cur, 0)
    const inv = items.reduce((s, i) => s + i.inv, 0)
    const rep = items.filter((i) => i.day !== null)
    const day = rep.reduce((s, i) => s + (i.day as number), 0)
    const base = rep.reduce((s, i) => s + i.cur - (i.day as number), 0)
    const series = classHistory[cls] ?? []
    const then = fromDate ? [...series].reverse().find((p) => p.date <= fromDate) ?? series[0] : null
    const ranked = rep.slice().sort((a, b) => (b.day as number) - (a.day as number))
    return {
      cls,
      items,
      cur,
      inv,
      weight: totalCur > 0 ? (cur / totalCur) * 100 : 0,
      pnl: cur - inv,
      pnlPct: inv > 0 ? ((cur - inv) / inv) * 100 : null,
      day: rep.length ? day : null,
      dayPct: rep.length && base > 0 ? (day / base) * 100 : null,
      reporting: rep.length,
      change: then && series.length ? series[series.length - 1].v - then.v : null,
      spark: series.slice(-30).map((p) => p.v),
      best: ranked.length && (ranked[0].day as number) > 0 ? ranked[0] : null,
      worst: ranked.length && (ranked[ranked.length - 1].day as number) < 0 ? ranked[ranked.length - 1] : null,
    }
  })
    .filter((c) => c.items.length > 0 && c.cur > 0)
    .sort((a, b) => b.cur - a.cur)

export const concentration = (instruments: Instrument[], total: number) => {
  const sorted = [...instruments].sort((a, b) => b.cur - a.cur)
  const share = (n: number) => (total > 0 ? (sorted.slice(0, n).reduce((s, i) => s + i.cur, 0) / total) * 100 : 0)
  return { top1: sorted[0] ?? null, top1Pct: share(1), top5Pct: share(5), top10Pct: share(10), count: sorted.length }
}

/**
 * Drawdown of the market-only return, from the snapshots: each day's value change less the money added that
 * day, compounded. Money added does not read as a gain and money withdrawn does not read as a loss.
 */
export const drawdownOf = (history: HistoryPoint[]) => {
  if (history.length < 8) return null
  let level = 1
  let peak = 1
  let worst = 0
  for (let i = 1; i < history.length; i++) {
    const prev = history[i - 1]
    const cur = history[i]
    if (prev.value <= 0) continue
    level *= 1 + (cur.value - prev.value - (cur.invested - prev.invested)) / prev.value
    peak = Math.max(peak, level)
    worst = Math.min(worst, level / peak - 1)
  }
  return { current: (level / peak - 1) * 100, worst: worst * 100, days: history.length }
}

export interface DriftRow {
  cls: CanonicalAssetClass
  weight: number
  target: number
  drift: number
  /** rupees to add (positive) or trim (negative) to reach the target at today's total */
  move: number
}

export const driftRows = (cards: ClassCard[], targets: Record<string, number>, total: number): DriftRow[] => {
  const classes = new Set<CanonicalAssetClass>([...cards.map((c) => c.cls), ...(Object.keys(targets).filter((k) => (targets[k] || 0) > 0) as CanonicalAssetClass[])])
  return [...classes]
    .map((cls) => {
      const c = cards.find((x) => x.cls === cls)
      const weight = c?.weight ?? 0
      const target = targets[cls] || 0
      return { cls, weight, target, drift: weight - target, move: (target / 100) * total - (c?.cur ?? 0) }
    })
    .sort((a, b) => Math.abs(b.move) - Math.abs(a.move))
}
