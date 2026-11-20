import { useEffect, useMemo, useState } from 'react'
import { fetchSignals } from '../../utils/api'
import type { SignalsResponse } from '../../types'
import type { Instrument } from './holdingsModel'

/** The momentum and strategy verdict of a holding, from the signals the scheduled refresh saves (the Signals page reads the same). */
export interface SupertrendInfo {
  direction: number
  supertrend: number
  cushion_pct: number | null
  last_signal: 'BUY' | 'SELL' | null
  status: 'bullish' | 'near_support' | 'sell_call' | 'bearish'
  label: string
  badgeCls: 'ok' | 'warn' | 'bad' | 'off'
  symbolCode: string
}

export interface Trend {
  verdict: string
  bucket: TrendBucket
  asOf?: string
  supertrend?: SupertrendInfo | null
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
      const sig = id ? signals[id] : null
      const m = sig?.momentum
      const st = sig?.supertrend
      if ((!m?.verdict || /insufficient/i.test(m.verdict)) && !st) return null

      let stInfo: SupertrendInfo | null = null
      if (st && st.supertrend) {
        const symbolCode = id ? id.split(':').pop()?.replace(/-(BE|BZ|BL|IL)$/, '') || '' : ''
        let status: SupertrendInfo['status'] = 'bearish'
        let label = 'ST Bearish'
        let badgeCls: SupertrendInfo['badgeCls'] = 'bad'

        if (st.direction < 0) {
          if (st.cushion_pct != null && st.cushion_pct < 1.5) {
            status = 'near_support'
            label = `ST Near Stop (${st.cushion_pct > 0 ? '+' : ''}${st.cushion_pct.toFixed(1)}%)`
            badgeCls = 'warn'
          } else {
            status = 'bullish'
            label = `ST Bullish${st.cushion_pct != null ? ` (+${st.cushion_pct.toFixed(1)}%)` : ''}`
            badgeCls = 'ok'
          }
        } else {
          if (st.last_signal === 'SELL') {
            status = 'sell_call'
            label = 'ST SELL CALL'
            badgeCls = 'bad'
          } else {
            status = 'bearish'
            label = 'ST Bearish'
            badgeCls = 'off'
          }
        }

        stInfo = {
          direction: st.direction,
          supertrend: st.supertrend,
          cushion_pct: st.cushion_pct,
          last_signal: st.last_signal,
          status,
          label,
          badgeCls,
          symbolCode,
        }
      }

      return {
        verdict: m?.verdict && !/insufficient/i.test(m.verdict) ? m.verdict : '',
        bucket: m?.verdict ? bucketOf(m.verdict) : 'none',
        asOf: id ? signals[id]?.computed_at : undefined,
        supertrend: stInfo,
      }
    }
  }, [data])
}
