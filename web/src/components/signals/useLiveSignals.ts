import { useEffect, useRef, useState } from 'react'
import type { StockSignals } from '../../types'

export interface LiveSignalsResponse {
  signals: Record<string, StockSignals>
  live: boolean
  at?: string
}

/**
 * Signal rows recomputed on the live price. Starts when `enabled`, then repeats every `everyMs()` (slower
 * outside the session) and pauses while the tab is hidden. `rerunKey` forces a fresh pull, e.g. after a
 * refresh job finishes. The rows returned replace the cached ones for the stocks that could be recomputed.
 */
export function useLiveSignals(
  fetcher: () => Promise<LiveSignalsResponse>,
  enabled: boolean,
  everyMs: () => number,
  resetKey: string,
  rerunKey?: string | null,
): { signals: Record<string, StockSignals>; at: string | null } {
  const [state, setState] = useState<{ key: string; signals: Record<string, StockSignals>; at: string | null }>({ key: resetKey, signals: {}, at: null })
  const fetchRef = useRef(fetcher)
  fetchRef.current = fetcher
  const everyRef = useRef(everyMs)
  everyRef.current = everyMs

  useEffect(() => {
    if (!enabled) return
    let stop = false
    let timer: number | undefined
    const tick = async () => {
      if (!document.hidden) {
        try {
          const res = await fetchRef.current()
          if (!stop && res.live) setState({ key: resetKey, signals: res.signals, at: res.at ?? null })
        } catch {
          /* keep the cached rows */
        }
      }
      if (!stop) timer = window.setTimeout(tick, everyRef.current())
    }
    tick()
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
  }, [enabled, resetKey, rerunKey])

  // rows from another market or list must never leak into this one
  return state.key === resetKey ? { signals: state.signals, at: state.at } : { signals: {}, at: null }
}
