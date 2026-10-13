import React, { createContext, useContext, useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import type { Holding } from '../types'
import { fetchPortfolioHoldings, fetchSymbolMap } from '../utils/api'
import { type CanonicalAssetClass } from '../utils/portfolioFilters'
import { buildInstruments } from '../components/holdings/holdingsModel'

export interface PortfolioCounts {
  total: number
  byBroker: Record<string, number>
  byAssetClass: Record<CanonicalAssetClass, number>
  gainers: number
  losers: number
}

interface PortfolioContextValue {
  holdings: Holding[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  counts: PortfolioCounts
  dataFreshness: 'live' | 'cached'
  lastRefreshedAt: Date | null
  /** where a stock name should link to (its Momentum view), or null when there is no such view */
  stockHref: (i: LinkableInstrument) => string | null
}

/** The parts of a holding row needed to work out its Momentum link. */
export interface LinkableInstrument {
  sym: string
  cls: string
  lots: { holding: Holding }[]
}

const defaultCounts: PortfolioCounts = {
  total: 0,
  byBroker: {},
  byAssetClass: {
    EQUITY: 0,
    MUTUAL_FUND: 0,
    US_STOCKS: 0,
    GOLD: 0,
    NPS: 0,
    DEBT: 0,
    OTHER: 0,
  },
  gainers: 0,
  losers: 0,
}

const PortfolioContext = createContext<PortfolioContextValue>({
  holdings: [],
  loading: true,
  error: null,
  refresh: async () => {},
  counts: defaultCounts,
  dataFreshness: 'cached',
  lastRefreshedAt: null,
  stockHref: () => null,
})

export const PortfolioProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)
  const [indiaSymbols, setIndiaSymbols] = useState<Record<string, string>>({})
  // Only the Holdings page asks for INDmoney's own live prices (US stocks, NPS); other pages keep the cheaper poll
  const { pathname } = useLocation()
  const onHoldings = useRef(pathname === '/holdings')

  const load = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true)
      const data = await fetchPortfolioHoldings('all', { indmoneyLive: onHoldings.current })
      setHoldings(data)
      setLastRefreshedAt(new Date())
      setError(null)
    } catch (err: any) {
      console.error('PortfolioContext load failed:', err)
      if (!silent) {
        setError(err.message || 'Failed to fetch portfolio data')
      }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  // Switching to or from Holdings changes what the poll asks for, so reload straight away
  useEffect(() => {
    const now = pathname === '/holdings'
    if (onHoldings.current !== now) {
      onHoldings.current = now
      load(true)
    }
  }, [pathname, load])

  useEffect(() => {
    load()

    // NSE cash session, Mon-Fri 09:15-15:30 IST: refresh prices every 20s then, every 5 min otherwise.
    // Nothing runs while the tab is hidden, and returning to the tab refreshes straight away.
    const marketOpen = () => {
      const ist = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }))
      const mins = ist.getHours() * 60 + ist.getMinutes()
      return ist.getDay() >= 1 && ist.getDay() <= 5 && mins >= 9 * 60 + 15 && mins <= 15 * 60 + 30
    }
    let timer: number | undefined
    const schedule = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(async () => {
        if (!document.hidden) await load(true)
        schedule()
      }, marketOpen() ? 20_000 : 300_000)
    }
    const onVisible = () => {
      if (!document.hidden) {
        load(true)
        schedule()
      }
    }
    schedule()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [load])

  const counts = useMemo<PortfolioCounts>(() => {
    const byBroker: Record<string, number> = {}
    let gainers = 0
    let losers = 0

    const byAssetClass: Record<CanonicalAssetClass, number> = {
      EQUITY: 0,
      MUTUAL_FUND: 0,
      US_STOCKS: 0,
      GOLD: 0,
      NPS: 0,
      DEBT: 0,
      OTHER: 0,
    }

    // count distinct holdings, as the Holdings page does: a stock held with two brokers is one holding
    buildInstruments(holdings).forEach((i) => {
      i.brokers.forEach((broker) => {
        if (broker) byBroker[broker] = (byBroker[broker] || 0) + 1
      })
      byAssetClass[i.cls] = (byAssetClass[i.cls] || 0) + 1
      if (i.pnl >= 0) gainers++
      else losers++
    })

    return {
      total: buildInstruments(holdings).length,
      byBroker,
      byAssetClass,
      gainers,
      losers,
    }
  }, [holdings])

  // Broker symbols that are not exchange codes (INDmoney's INDS... ids) are resolved once by the signals runs
  const holdingCount = holdings.length
  useEffect(() => {
    if (holdingCount === 0) return
    fetchSymbolMap()
      .then((m) => setIndiaSymbols(m.in))
      .catch(() => {})
  }, [holdingCount])

  const stockHref = useCallback(
    (i: LinkableInstrument): string | null => {
      if (i.cls !== 'EQUITY') return null // Momentum covers NSE/BSE stocks; US stocks, funds and NPS have no such view
      const raw = i.lots[0]?.holding.instrument_symbol ?? i.sym
      const resolved = indiaSymbols[raw]
      const code = resolved ? resolved.replace(/^NSE:/, '') : /^INDS\d+/i.test(raw) ? null : raw.trim().split(/\s+/)[0]
      return code ? `/momentum?symbol=${encodeURIComponent(code)}` : null
    },
    [indiaSymbols],
  )

  const dataFreshness = useMemo<'live' | 'cached'>(() => {
    return holdings.some((h) => h.data_freshness === 'live') ? 'live' : 'cached'
  }, [holdings])

  return (
    <PortfolioContext.Provider
      value={{
        holdings,
        loading,
        error,
        refresh: () => load(false),
        counts,
        dataFreshness,
        lastRefreshedAt,
        stockHref,
      }}
    >
      {children}
    </PortfolioContext.Provider>
  )
}

export const usePortfolio = () => useContext(PortfolioContext)
