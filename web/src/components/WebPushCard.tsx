import React, { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { disableWebPush, enableWebPush, webPushState, type WebPushState } from '../utils/webPush'
import { fetchNotificationPrefs, saveNotificationPrefs, sendTestNotification, type NotificationPrefs } from '../utils/api'
import { track } from '../utils/analytics'

// the same kinds, in the same words, as Settings in the Android app
const KINDS: [string, string][] = [
  ['holdings_ath', 'Strategy calls on my holdings'],
  ['stage2_ath', 'Strategy calls on the Stage 2 list'],
  ['networth_daily', 'Daily net worth, after the close'],
  ['networth_weekly', 'Weekly net worth, Sunday morning'],
  ['us_stocks', 'US stocks look, 9 PM on US trading days'],
  ['kite_login', 'Kite login reminder, mornings'],
]

const NOTE: Partial<Record<WebPushState, string>> = {
  unsupported: "This browser can't show notifications. On an iPhone, add WealthVault to your Home Screen first, then open it from there.",
  unavailable: 'Browser notifications are not switched on for this site yet.',
  blocked: 'Notifications are blocked for this site. Allow them in the browser’s site settings, then come back here.',
}

/** The Account page card for notifications in this browser, with the same switches as the Android app. */
export const WebPushCard: React.FC = () => {
  const [state, setState] = useState<WebPushState>(webPushState)
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (state === 'on') fetchNotificationPrefs().then(setPrefs).catch(() => setPrefs(null))
  }, [state])

  const run = async (job: () => Promise<void>) => {
    setBusy(true)
    setMessage('')
    try {
      await job()
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const turnOn = () =>
    run(async () => {
      const next = await enableWebPush()
      setState(next)
      if (next === 'on') track('notifications_enabled', { where: 'web' })
      else if (next === 'off') setMessage('Notifications were not allowed. You can try again any time.')
    })

  const turnOff = () => run(async () => setState(await disableWebPush()))

  const flip = (key: string) =>
    run(async () => {
      if (!prefs) return
      const next = { ...prefs, [key]: !prefs[key] }
      setPrefs(next)
      setPrefs(await saveNotificationPrefs(next))
    })

  const test = () =>
    run(async () => {
      await sendTestNotification()
      setMessage('Sent. It should arrive in a moment.')
    })

  return (
    <section className="card">
      <h2 className="card-t">
        <Bell size={16} strokeWidth={1.75} aria-hidden="true" /> Notifications in this browser
      </h2>
      <p className="card-s">
        Strategy calls, daily and weekly net worth, a look at your US stocks and the Kite login reminder, even when WealthVault is closed. The alert holds
        no text when it travels: your browser asks WealthVault for it, so stock names and amounts never pass through Google. With amounts hidden, no rupee
        figure appears.
      </p>
      {NOTE[state] && <p className="sub">{NOTE[state]}</p>}
      {state === 'off' && (
        <button className="btn btn-primary" type="button" disabled={busy} onClick={turnOn} style={{ marginTop: 12 }}>
          <Bell size={16} strokeWidth={1.75} aria-hidden="true" />
          Turn on notifications
        </button>
      )}
      {state === 'on' && (
        <>
          {prefs &&
            KINDS.map(([key, label]) => (
              <label className="switch" key={key} style={{ marginTop: 12, display: 'flex' }}>
                <input type="checkbox" checked={prefs[key] !== false} disabled={busy} onChange={() => flip(key)} />
                {label}
              </label>
            ))}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
            <button className="btn" type="button" disabled={busy} onClick={test}>
              Send me a test notification
            </button>
            <button className="btn" type="button" disabled={busy} onClick={turnOff}>
              Turn off in this browser
            </button>
          </div>
        </>
      )}
      {message && (
        <p className="sub" role="status" style={{ marginTop: 10 }}>
          {message}
        </p>
      )}
    </section>
  )
}
