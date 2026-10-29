import React, { useEffect, useState } from 'react'
import { BarChart3 } from 'lucide-react'
import { getConsent, setConsent, trackScreen, type Consent } from '../utils/analytics'

const CHANGED = 'wv-analytics-consent'

const choose = (value: 'granted' | 'denied') => {
  setConsent(value)
  window.dispatchEvent(new Event(CHANGED))
}

const useConsent = (): Consent => {
  const [value, setValue] = useState<Consent>(getConsent())
  useEffect(() => {
    const sync = () => setValue(getConsent())
    window.addEventListener(CHANGED, sync)
    return () => window.removeEventListener(CHANGED, sync)
  }, [])
  return value
}

/** Shown once, until the person picks. Nothing is sent before they say yes. */
export const AnalyticsBanner: React.FC = () => {
  const consent = useConsent()
  if (consent !== null) return null
  return (
    <aside className="consent" role="dialog" aria-label="Help improve WealthVault">
      <BarChart3 size={18} strokeWidth={1.75} aria-hidden="true" />
      <div className="consent-tx">
        <b>Help improve WealthVault</b>
        <span>
          Share which screens you use and what you search for, so we can fix what is slow or missing. Never your amounts, holdings, email or name. You can change this any time in Account.
        </span>
      </div>
      <div className="consent-btns">
        <button className="btn" type="button" onClick={() => choose('denied')}>
          Not now
        </button>
        <button
          className="btn btn-primary"
          type="button"
          onClick={() => {
            choose('granted')
            trackScreen(window.location.pathname)
          }}
        >
          Allow
        </button>
      </div>
    </aside>
  )
}

/** The Account page switch, so the choice can be changed later. */
export const AnalyticsSwitch: React.FC = () => {
  const consent = useConsent()
  const on = consent === 'granted'
  return (
    <label className="switch" style={{ marginTop: 12 }}>
      <input type="checkbox" checked={on} onChange={() => choose(on ? 'denied' : 'granted')} />
      Share anonymous usage data (screens used and searches; never amounts, holdings or personal details)
    </label>
  )
}
