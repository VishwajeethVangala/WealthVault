import { useEffect, useMemo, useState } from 'react'
import { fetchSignals } from '../../utils/api'
import type { SignalsResponse } from '../../types'
import type { Instrument } from './holdingsModel'

/** The momentum verdict of a holding, from the signals the scheduled refresh saves (the Signals page reads the same). */
export interface Trend {
  verdict: string
  bucket: TrendBucket
  asOf?: string
}

export type TrendBucket = 'up' | 'neutral' | 'down' | 'none'

export const TREND_LABEL: Record<TrendBucket, string> = { up: 'Uptrend', neutral: 'Neutral', down: 'Downtrend', none: 'Not rated' }
export const TREND_ORDER: TrendBucket[] = ['up', 'neutral', 'down', 'none']

export const bucketOf = (verdict: string): TrendBucket =>
  /uptrend/i.test(verdict) ? 'up' : /downtrend/i.test(verdict) ? 'down' : /neutral/i.test(verdict) ? 'neutral' : 'none'

export const trendBadge = (bucket: TrendBucket) => (bucket === 'up' ? 'ok' : bucket === 'down' ? 'bad' : 'off')

/**
 * Loads the saved signals for Indian and US holdings once, and answers "what is this holding's trend?". Mutual funds,
 * NPS, gold and cash have none (momentum is a stock and ETF measure), so they come back as null: "Not rated".
 */
export const useTrend = (count: number) => {
  const [data, setData] = useState<SignalsResponse[]>([])
  useEffect(() => {
    let stale = false
    Promise.all([fetchSignals('in').catch(() => null), fetchSignals('us').catch(() => null)]).then((res) => {
      if (!stale) setData(res.filter((r): r is SignalsResponse => r !== null))
    })
    return () => {
      stale = true
    }
  }, [count])

  return useMemo(() => {
    const map: Record<string, string> = {}
    const signals: SignalsResponse['signals'] = {}
    data.forEach((r) => {
      Object.assign(map, r.symbol_map)
      Object.assign(signals, r.signals)
    })
    return (inst: Instrument): Trend | null => {
      const id = inst.lots.map((l) => map[l.holding.instrument_symbol]).find(Boolean)
      const m = id ? signals[id]?.momentum : null
      if (!m?.verdict || /insufficient/i.test(m.verdict)) return null
      return { verdict: m.verdict, bucket: bucketOf(m.verdict), asOf: id ? signals[id]?.computed_at : undefined }
    }
  }, [data])
}
