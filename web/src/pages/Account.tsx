import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { clearToken, deleteAccount, getStoredUser } from '../utils/api'
import { DISCLAIMER } from './Legal'

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
      </section>

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
