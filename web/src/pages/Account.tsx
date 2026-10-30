import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, MessageSquare, ShieldCheck } from 'lucide-react'
import { clearToken, deleteAccount, getStoredUser, sendFeedback } from '../utils/api'
import { DISCLAIMER } from './Legal'
import { AnalyticsSwitch } from '../components/AnalyticsConsent'
import { ShareCard } from '../components/ShareCard'
import { WebPushCard } from '../components/WebPushCard'

type Category = 'idea' | 'problem' | 'praise' | 'other'
const MAX_FEEDBACK = 2000

/** An idea, a problem or praise, sent to the server with the sender's account (same form as the Android app). */
const FeedbackCard: React.FC = () => {
  const [category, setCategory] = useState<Category>('idea')
  const [message, setMessage] = useState('')
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  const send = async () => {
    setState('sending')
    try {
      await sendFeedback(category, message.trim())
      setState('sent')
    } catch {
      setState('error')
    }
  }

  return (
    <section className="card">
      <h2 className="card-t">
        <MessageSquare size={16} strokeWidth={1.75} aria-hidden="true" /> Send feedback
      </h2>
      <p className="card-s">An idea, a problem or anything else. It goes straight to the people who build WealthVault.</p>
      {state === 'sent' ? (
        <div className="acct-confirm">
          <p>
            <b>Thank you, it&apos;s received.</b> If a reply is needed, it comes to the email you signed in with.
          </p>
          <div className="acct-actions">
            <button className="btn" type="button" onClick={() => { setMessage(''); setState('idle') }}>
              Send another
            </button>
          </div>
        </div>
      ) : (
        <div className="acct-confirm">
          <div className="seg" role="group" aria-label="What is it about?">
            {([['idea', 'Idea'], ['problem', 'Problem'], ['praise', 'Praise'], ['other', 'Other']] as const).map(([id, label]) => (
              <button key={id} type="button" className={category === id ? 'on' : ''} aria-pressed={category === id} onClick={() => setCategory(id)}>
                {label}
              </button>
            ))}
          </div>
          <label htmlFor="fb-msg">Your message</label>
          <textarea
            id="fb-msg"
            className="input"
            rows={5}
            maxLength={MAX_FEEDBACK}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={category === 'problem' ? 'What happened, and on which page?' : 'Tell us what you think'}
          />
          <p className="sub">
            {message.length} / {MAX_FEEDBACK} · sent with your sign-in email so we can reply; nothing about your holdings is included.
          </p>
          {state === 'error' && (
            <p className="acct-err" role="alert">
              Could not send right now. Please try again.
            </p>
          )}
          <div className="acct-actions">
            <button className="btn btn-primary" type="button" onClick={send} disabled={state === 'sending' || !message.trim()}>
              {state === 'sending' ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

export const Account: React.FC = () => {
  const user = getStoredUser()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirmDelete = async () => {
    setBusy(true)
    setError(null)
    try {
      await deleteAccount()
      clearToken()
      window.location.assign('/')
    } catch {
      setError('Could not delete your account right now. Nothing was changed; please try again.')
      setBusy(false)
    }
  }

  return (
    <div className="acct">
      <section className="card">
        <h2 className="card-t">Your account</h2>
        <p className="card-s">Signed in with Google</p>
        {user && (
          <div className="acct-who">
            <span className="avatar big">
              {user.picture ? <img src={user.picture} alt="" referrerPolicy="no-referrer" /> : user.name.charAt(0).toUpperCase()}
            </span>
            <div>
              <b>{user.name}</b>
              <div className="sub">{user.email}</div>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card-t">
          <ShieldCheck size={16} strokeWidth={1.75} aria-hidden="true" /> Privacy and use
        </h2>
        <p className="card-s">{DISCLAIMER}</p>
        <p className="acct-links">
          <a href="/privacy" target="_blank" rel="noreferrer">
            Privacy policy
          </a>
          <Link to="/brokers">Manage brokers</Link>
        </p>
        <AnalyticsSwitch />
      </section>

      <WebPushCard />

      <ShareCard />

      <FeedbackCard />

      <section className="card acct-danger">
        <h2 className="card-t">
          <AlertTriangle size={16} strokeWidth={1.75} aria-hidden="true" /> Delete my account and data
        </h2>
        <p className="card-s">
          Permanently erases your profile, holdings, portfolio history, targets, broker connections and saved broker logins. This cannot be
          undone.
        </p>
        {!open ? (
          <button className="btn btn-danger" type="button" onClick={() => setOpen(true)}>
            Delete my account…
          </button>
        ) : (
          <div className="acct-confirm">
            <label htmlFor="del-confirm">
              Type <b>DELETE</b> to confirm
            </label>
            <input
              id="del-confirm"
              className="input"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
            />
            {error && (
              <p className="acct-err" role="alert">
                {error}
              </p>
            )}
            <div className="acct-actions">
              <button className="btn btn-danger" type="button" onClick={confirmDelete} disabled={busy || typed.trim() !== 'DELETE'}>
                {busy ? 'Deleting…' : 'Delete everything'}
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setOpen(false)
                  setTyped('')
                  setError(null)
                }}
                disabled={busy}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
