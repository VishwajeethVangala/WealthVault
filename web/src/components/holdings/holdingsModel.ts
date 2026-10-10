import type { Holding } from '../../types'
import { brokerKeyOf, brokerLabel, classifyAssetClass, type CanonicalAssetClass } from '../../utils/portfolioFilters'
import { dayPnlOf, displaySymbol } from '../../utils/dayChange'

export const CLASS_ORDER: CanonicalAssetClass[] = ['EQUITY', 'MUTUAL_FUND', 'US_STOCKS', 'GOLD', 'NPS', 'DEBT', 'OTHER']

export const CLASS_LABEL: Record<CanonicalAssetClass, string> = {
  EQUITY: 'Stocks',
  MUTUAL_FUND: 'Mutual funds',
  US_STOCKS: 'US stocks',
  GOLD: 'Gold',
  NPS: 'Retirement',
  DEBT: 'Debt',
  OTHER: 'Other',
}

export const CLASS_COLOR: Record<CanonicalAssetClass, string> = {
  EQUITY: 'var(--c-stocks)',
  MUTUAL_FUND: 'var(--c-mf)',
  US_STOCKS: 'var(--c-us)',
  GOLD: 'var(--c-gold)',
  NPS: 'var(--c-retire)',
  DEBT: 'var(--c-debt)',
  OTHER: 'var(--c-cash)',
}

const KNOWN_BROKER_COLORS = ['zerodha', 'groww', 'angelone', 'indmoney']

export const brokerColor = (key: string): string => (KNOWN_BROKER_COLORS.includes(key) ? `var(--b-${key})` : 'var(--text-3)')
export const brokerCode = (key: string): string => brokerLabel(key).charAt(0).toUpperCase()

/** One broker's position in an instrument. */
export interface Lot {
  holding: Holding
  brokerKey: string
  qty: number
  inv: number
  cur: number
  pnl: number
  /** 1-day change in rupees; null when the broker does not report one */
  day: number | null
}

/** The same instrument merged across brokers. */
export interface Instrument {
  key: string
  sym: string
  cls: CanonicalAssetClass
  lots: Lot[]
  brokers: string[]
  qty: number
  avg: number
  ltp: number
  inv: number
  cur: number
  pnl: number
  pnlPct: number | null
  day: number | null
  dayPct: number | null
  freshness: 'live' | 'cached' | 'mixed'
}

export type SortKey = 'sym' | 'qty' | 'avg' | 'ltp' | 'inv' | 'cur' | 'pnlPct' | 'dayPct'

export const buildInstruments = (holdings: Holding[]): Instrument[] => {
  const byKey = new Map<string, Holding[]>()
  holdings.forEach((h) => {
    const key = `${classifyAssetClass(h)}|${displaySymbol(h).toUpperCase()}`
    byKey.set(key, [...(byKey.get(key) ?? []), h])
  })

  return [...byKey.entries()].map(([key, hs]) => {
    const lots: Lot[] = hs.map((h) => {
      const inv = h.quantity * h.average_price
      const cur = h.current_value || 0
      return { holding: h, brokerKey: brokerKeyOf(h.connection_id), qty: h.quantity, inv, cur, pnl: h.pnl ?? cur - inv, day: dayPnlOf(h) }
    })

    const qty = lots.reduce((s, l) => s + l.qty, 0)
    const inv = lots.reduce((s, l) => s + l.inv, 0)
    const cur = lots.reduce((s, l) => s + l.cur, 0)
    const pnl = lots.reduce((s, l) => s + l.pnl, 0)

    const reporting = lots.filter((l) => l.day !== null)
    const day = reporting.length > 0 ? reporting.reduce((s, l) => s + (l.day as number), 0) : null
    const dayBase = reporting.reduce((s, l) => s + l.cur - (l.day as number), 0)

    const liveCount = hs.filter((h) => h.data_freshness === 'live').length
    return {
      key,
      sym: displaySymbol(hs[0]),
      cls: classifyAssetClass(hs[0]),
      lots,
      brokers: [...new Set(lots.map((l) => l.brokerKey))],
      qty,
      avg: qty > 0 ? inv / qty : 0,
      ltp: qty > 0 ? cur / qty : 0,
      inv,
      cur,
      pnl,
      pnlPct: inv > 0 ? (pnl / inv) * 100 : null,
      day,
      dayPct: day !== null && dayBase > 0 ? (day / dayBase) * 100 : null,
      freshness: liveCount === hs.length ? 'live' : liveCount === 0 ? 'cached' : 'mixed',
    }
  })
}

const sortValue = (i: Instrument, key: SortKey): string | number | null => {
  switch (key) {
    case 'sym':
      return i.sym.toLowerCase()
    case 'pnlPct':
      return i.pnlPct
    case 'dayPct':
      return i.dayPct
    default:
      return i[key]
  }
}

/** Sorts by a column; rows with no value for it (e.g. no day change) always go last. */
export const sortInstruments = (list: Instrument[], key: SortKey, dir: 1 | -1): Instrument[] =>
  [...list].sort((a, b) => {
    const x = sortValue(a, key)
    const y = sortValue(b, key)
    if (x === null && y === null) return 0
    if (x === null) return 1
    if (y === null) return -1
    if (typeof x === 'string' && typeof y === 'string') return x.localeCompare(y) * dir
    return ((x as number) - (y as number)) * dir
  })

/** Maps the sort values older dashboard links used onto the new column keys. */
export const sortKeyFromParam = (param: string | null): { key: SortKey; dir: 1 | -1 } => {
  switch (param) {
    case 'invested_value':
      return { key: 'inv', dir: -1 }
    case 'pnl':
      return { key: 'pnlPct', dir: -1 }
    case 'instrument_symbol':
      return { key: 'sym', dir: 1 }
    default:
      return { key: 'cur', dir: -1 }
  }
}

export const formatQty = (q: number): string =>
  Number.isInteger(q) ? q.toLocaleString('en-IN') : q.toLocaleString('en-IN', { maximumFractionDigits: 3 })
