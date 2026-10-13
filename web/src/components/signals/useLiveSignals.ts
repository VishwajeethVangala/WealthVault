import { useEffect, useRef, useState } from 'react'
import type { StockSignals } from '../../types'

/** Why the rows are not live: no broker login, nothing to price, nothing computed yet, or a failure. */
export type LiveReason = 'ok' | 'login' | 'no_prices' | 'no_signals' | 'error'

export interface LiveSignalsResponse {
  signals: Record<string, StockSignals>
  live: boolean
  reason?: LiveReason
  at?: string
}

/** `checking` until the first answer arrives, then `live` or `stored` (with the reason). */
export type LiveStatus = { kind: 'checking' } | { kind: 'live'; at: string | null } | { kind: 'stored'; reason: LiveReason }

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
): { signals: Record<string, StockSignals>; at: string | null; status: LiveStatus } {
  const [state, setState] = useState<{ key: string; signals: Record<string, StockSignals>; at: string | null; status: LiveStatus }>({
    key: resetKey,
    signals: {},
    at: null,
    status: { kind: 'checking' },
  })
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
          if (!stop) {
            if (res.live) setState({ key: resetKey, signals: res.signals, at: res.at ?? null, status: { kind: 'live', at: res.at ?? null } })
            else setState({ key: resetKey, signals: {}, at: null, status: { kind: 'stored', reason: res.reason ?? 'no_prices' } })
          }
        } catch {
          /* a network blip keeps whatever was showing */
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
  return state.key === resetKey ? { signals: state.signals, at: state.at, status: state.status } : { signals: {}, at: null, status: { kind: 'checking' } }
}
