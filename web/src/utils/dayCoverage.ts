import type { Instrument } from '../components/holdings/holdingsModel'

export interface DayCoverage {
  reporting: number
  total: number
  missing: Instrument[]
  /** one short explanation per kind of holding that has no day change */
  reasons: string[]
}

const REASON: Record<string, string> = {
  MUTUAL_FUND: 'Mutual funds publish one NAV a day. Their change is filled in from the published NAV history once the fund has an ISIN on file (press Sync after updating).',
  US_STOCKS: 'INDmoney sent no day change for these US stocks.',
  EQUITY: 'The broker sent no previous close for these stocks.',
  GOLD: 'Gold bonds trade thinly, so no previous close is reported.',
  NPS: 'NPS NAV is published once a day and the broker did not send a change.',
}

export const dayCoverage = (instruments: Instrument[]): DayCoverage => {
  const missing = instruments.filter((i) => i.day === null)
  const kinds = [...new Set(missing.map((i) => i.cls))]
  return {
    reporting: instruments.length - missing.length,
    total: instruments.length,
    missing,
    reasons: kinds.map((k) => REASON[k] ?? 'The broker sent no day change for these.'),
  }
}
