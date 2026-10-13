import React from 'react'
import { Link } from 'react-router-dom'
import { Radio, WifiOff } from 'lucide-react'
import type { LiveStatus } from './useLiveSignals'

const clock = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }) : ''

/**
 * One line that says whether the numbers beside it are on a live price or on stored ones, and if stored, why and
 * what to do. `broker` names the login that supplies live prices (Kite for India, INDmoney for the US).
 */
export const FreshnessChip: React.FC<{
  status: LiveStatus
  broker: 'Kite' | 'INDmoney'
  sessionOpen: boolean
  storedAt?: string | null
}> = ({ status, broker, sessionOpen, storedAt }) => {
  const stored = storedAt ? new Date(storedAt).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) : null

  if (status.kind === 'checking') return <span className="fresh">Checking live prices…</span>

  if (status.kind === 'live') {
    return sessionOpen ? (
      <span className="fresh live" title={`Signals are rebuilt on the live ${broker} price every minute or two`}>
        <Radio size={13} strokeWidth={2} aria-hidden="true" />
        Live · {clock(status.at)}
      </span>
    ) : (
      <span className="fresh" title="The market is closed, so the last traded price is used">
        Market closed · last traded price
      </span>
    )
  }

  const login = status.reason === 'login'
  const why =
    login ? `${broker} is not logged in`
    : status.reason === 'no_signals' ? 'no signals saved yet'
    : status.reason === 'error' ? 'live prices could not be read'
    : sessionOpen ? 'no live price available' : 'market closed'
  return (
    <span className={`fresh ${login || status.reason === 'error' ? 'stale' : ''}`} title={stored ? `Signals last computed ${stored}` : undefined}>
      <WifiOff size={13} strokeWidth={2} aria-hidden="true" />
      Stored prices{stored ? ` (${stored})` : ''} · {why}
      {login && (
        <span className="fresh-act">
          · <Link to="/brokers">log in for live</Link>
        </span>
      )}
    </span>
  )
}
