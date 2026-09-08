import type { Holding } from '../types'

export type CanonicalAssetClass = 'EQUITY' | 'MUTUAL_FUND' | 'US_STOCKS' | 'GOLD' | 'NPS' | 'DEBT' | 'OTHER'

const US_TICKERS = ['SNDK', 'AMZN', 'SPCX', 'LITE', 'DELL', 'MU', 'CRWD', 'AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL', 'META']

export function classifyAssetClass(h: Holding): CanonicalAssetClass {
  const sym = (h.instrument_symbol || '').toUpperCase()
  const conn = (h.connection_id || '').toLowerCase()
  const assetClass = (h.asset_class || '').toUpperCase()

  if (sym.includes('SGB')) {
    return 'GOLD'
  }
  if (assetClass === 'NPS') {
    return 'NPS'
  }
  if (
    assetClass === 'US_STOCKS' ||
    h.currency === 'USD' ||
    conn.includes('us') ||
    conn.includes('alpaca') ||
    US_TICKERS.some((t) => sym.includes(t))
  ) {
    return 'US_STOCKS'
  }
  if (assetClass === 'MUTUAL_FUND') {
    return 'MUTUAL_FUND'
  }
  if (
    assetClass === 'DEBT' ||
    sym.includes('DEBT') ||
    sym.includes('LIQUID') ||
    sym.includes('BOND') ||
    sym.includes('GILT') ||
    sym.includes('TREASURY') ||
    sym.includes('ARBITRAGE') ||
    sym.includes('FD') ||
    sym.includes('CASH') ||
    sym.includes('OVERNIGHT')
  ) {
    return 'DEBT'
  }
  if (assetClass === 'EQUITY') {
    return 'EQUITY'
  }
  return 'OTHER'
}

export function filterHoldings(
  holdings: Holding[],
  filters: {
    broker?: string
    assetClass?: string
    pnl?: string
    search?: string
  }
): Holding[] {
  const { broker = 'all', assetClass = 'all', pnl = 'all', search = '' } = filters
  const normalizedQuery = search.trim().toLowerCase()

  const selectedBrokers = broker !== 'all' ? broker.split(',').filter(Boolean) : []
  const selectedAssetClasses = assetClass !== 'all' ? assetClass.split(',').filter(Boolean) : []

  return holdings.filter((h) => {
    // 1. Custodian filter (multi-select)
    if (selectedBrokers.length > 0) {
      const conn = (h.connection_id || '').toLowerCase()
      const match = selectedBrokers.some((b) => {
        if (b === 'zerodha') return conn.includes('zerodha')
        if (b === 'indmoney') return conn.includes('indmoney')
        return conn.includes(b.toLowerCase())
      })
      if (!match) return false
    }

    // 2. Asset class filter (multi-select)
    if (selectedAssetClasses.length > 0) {
      const canonical = classifyAssetClass(h)
      if (!selectedAssetClasses.includes(canonical)) {
        return false
      }
    }

    // 3. PnL Performance filter
    if (pnl !== 'all') {
      const investedCost = h.quantity * h.average_price
      const gain = h.pnl ?? (h.current_value - investedCost)
      if (pnl === 'gainers' && gain < 0) return false
      if (pnl === 'losers' && gain >= 0) return false
    }

    // 4. Search text
    if (normalizedQuery) {
      const symMatch = h.instrument_symbol.toLowerCase().includes(normalizedQuery)
      const brokerMatch = h.connection_id.toLowerCase().includes(normalizedQuery)
      const classMatch = h.asset_class.toLowerCase().includes(normalizedQuery)
      if (!symMatch && !brokerMatch && !classMatch) return false
    }

    return true
  })
}
