import { useEffect, useRef } from 'react'

export interface StrategyPanelProps {
  symbol: string | null
  // Bumped by the page on every Run click so the same symbol can be re-run
  runSeq: number
  active: boolean
  onStatus: (status: { loading: boolean; instrument?: string }) => void
}

// Runs `execute(symbol)` when the panel is active and has not yet run this symbol/run request.
// Inactive tabs stay idle and catch up when they are opened.
export function useStrategyRun(
  { symbol, runSeq, active, onStatus }: StrategyPanelProps,
  execute: (symbol: string) => void,
  loading: boolean,
  instrument: string | undefined
) {
  const ranKey = useRef<string | null>(null)

  useEffect(() => {
    if (!active || !symbol) return
    const key = `${symbol}#${runSeq}`
    if (ranKey.current === key) return
    ranKey.current = key
    execute(symbol)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, symbol, runSeq])

  useEffect(() => {
    if (active) onStatus({ loading, instrument })
  }, [active, loading, instrument, onStatus])
}
