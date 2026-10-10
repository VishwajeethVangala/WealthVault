import React, { useState } from 'react'
import { ExternalLink, Lock, X } from 'lucide-react'
import { saveBrokerCredentials } from '../../utils/api'
import type { BrokerCatalogItem, CredentialSaveResponse } from '../../types'

interface Props {
  broker: BrokerCatalogItem
  connectionId: string
  displayName: string
  alreadySaved: boolean
  onClose: () => void
  /** Called after credentials were saved and the broker accepted them. */
  onVerified: () => void
}

export const BrokerCredentialsModal: React.FC<Props> = ({ broker, connectionId, displayName, alreadySaved, onClose, onVerified }) => {
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<CredentialSaveResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const missingRequired = broker.credential_fields.filter((f) => f.required && !values[f.key]?.trim())

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setResult(null)
    try {
      const res = await saveBrokerCredentials(connectionId, values)
      setResult(res)
      if (res.login_ok) onVerified()
    } catch (err: any) {
      setError(err?.message || 'Could not save credentials')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="scrim" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="cred-title"
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <div className="modal-h">
          <div style={{ flex: '1 1 auto' }}>
            <h2 className="h2" id="cred-title">
              {broker.display_name} credentials
            </h2>
            <p className="sub">{displayName}</p>
          </div>
          <button type="button" className="btn btn-icon btn-ghost" aria-label="Close" onClick={onClose}>
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        <div className="modal-b">
          {broker.setup_steps.length > 0 && (
            <ol className="steps">
              {broker.setup_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          )}
          {broker.setup_url && (
            <a href={broker.setup_url} target="_blank" rel="noreferrer" className="link">
              Open {broker.display_name} setup <ExternalLink size={13} style={{ verticalAlign: '-2px' }} />
            </a>
          )}

          {alreadySaved && <p className="note">Credentials are already saved. Saving again replaces them. Saved values are never shown.</p>}

          {broker.credential_fields.map((f) => (
            <div className="field" key={f.key}>
              <label htmlFor={`cred-${f.key}`}>
                <span>
                  {f.label}
                  {f.required && <span style={{ color: 'var(--loss)' }}> *</span>}
                </span>
                {f.help && <em>{f.help}</em>}
              </label>
              <input
                id={`cred-${f.key}`}
                className="input mono"
                type={f.secret ? 'password' : 'text'}
                autoComplete="off"
                spellCheck={false}
                value={values[f.key] ?? ''}
                onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              />
            </div>
          ))}

          {result && !result.login_ok && (
            <div className="banner" role="alert">
              <div className="tx">
                <b>Saved, but {broker.display_name} did not accept the login.</b> {result.message}
                {result.auth_url && (
                  <>
                    {' '}
                    <a href={result.auth_url} target="_blank" rel="noreferrer" className="link">
                      Open approval page
                    </a>
                  </>
                )}
              </div>
            </div>
          )}
          {error && <p className="note bad">{error}</p>}
        </div>

        <div className="modal-f">
          <span className="lock">
            <Lock size={14} strokeWidth={1.75} /> Encrypted before it is stored
          </span>
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || missingRequired.length > 0}>
            {saving ? 'Testing login…' : 'Save & test'}
          </button>
        </div>
      </form>
    </div>
  )
}
