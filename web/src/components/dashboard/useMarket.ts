import { useEffect, useMemo, useState } from 'react'
import { fetchMarketQuotes, fetchUsLive } from '../../utils/api'
import { usePortfolio } from '../../context/PortfolioContext'

const marketOpen = (): boolean => {
  const ist = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
  const mins = ist.getHours() * 60 + ist.getMinutes()
  return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
}

/** Nifty 50's change today (%), to set the portfolio's day against. Null until Kite answers. */
export const useNifty = (): number | null => {
  const [value, setValue] = useState<number | null>(null)
  useEffect(() => {
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchMarketQuotes(['NSE:NIFTY 50'])
          const q = res.quotes['NSE:NIFTY 50'] ?? Object.values(res.quotes)[0]
          const prev = q?.ohlc?.close
          if (!stop && q && prev && prev > 0) setValue(((q.last_price - prev) / prev) * 100)
        } catch {
          /* keep the last value */
        }
      }
      if (!stop) timer = window.setTimeout(tick, marketOpen() ? 60_000 : 600_000)
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [])
  return value
}

/** US stocks' average move in dollars today, so the rupee figure can be read against the stocks' own move. */
export const useUsdMove = (enabled: boolean): number | null => {
  const { holdings } = usePortfolio()
  const [quotes, setQuotes] = useState<Record<string, { day_change_pct: number | null }>>({})
  useEffect(() => {
    if (!enabled) return
    fetchUsLive()
      .then((r) => setQuotes(r.quotes))
      .catch(() => {})
  }, [enabled])
  return useMemo(() => {
    let num = 0
    let den = 0
    holdings.forEach((h) => {
      if (h.asset_class !== 'US_STOCKS') return
      const t = h.instrument_symbol.trim().split(/\s+/)[0].toUpperCase()
      const p = quotes[t]?.day_change_pct
      if (p == null) return
      num += (h.current_value || 0) * p
      den += h.current_value || 0
    })
    return den > 0 ? num / den : null
  }, [holdings, quotes])
}
