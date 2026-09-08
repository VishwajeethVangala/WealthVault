import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import type { Holding } from '../types'
import { fetchPortfolioHoldings } from '../utils/api'
import { classifyAssetClass, type CanonicalAssetClass } from '../utils/portfolioFilters'

export interface PortfolioCounts {
  total: number
  zerodha: number
  indmoney: number
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
}

const defaultCounts: PortfolioCounts = {
  total: 0,
  zerodha: 0,
  indmoney: 0,
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
})

export const PortfolioProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await fetchPortfolioHoldings('all')
      setHoldings(data)
      setError(null)
    } catch (err: any) {
      console.error('PortfolioContext load failed:', err)
      setError(err.message || 'Failed to fetch portfolio data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const counts = useMemo<PortfolioCounts>(() => {
    let zerodha = 0
    let indmoney = 0
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

    holdings.forEach((h) => {
      const conn = (h.connection_id || '').toLowerCase()
      if (conn.includes('zerodha')) zerodha++
      if (conn.includes('indmoney')) indmoney++

      const c = classifyAssetClass(h)
      byAssetClass[c] = (byAssetClass[c] || 0) + 1

      const invested = h.quantity * h.average_price
      const gain = h.pnl ?? (h.current_value - invested)
      if (gain >= 0) gainers++
      else losers++
    })

    return {
      total: holdings.length,
      zerodha,
      indmoney,
      byAssetClass,
      gainers,
      losers,
    }
  }, [holdings])

  return (
    <PortfolioContext.Provider
      value={{
        holdings,
        loading,
        error,
        refresh: load,
        counts,
      }}
    >
      {children}
    </PortfolioContext.Provider>
  )
}

export const usePortfolio = () => useContext(PortfolioContext)
