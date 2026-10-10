import React, { useState } from 'react'
import { X } from 'lucide-react'
import { CLASS_LABEL } from '../holdings/holdingsModel'
import type { CanonicalAssetClass } from '../../utils/portfolioFilters'

const TARGET_CLASSES: CanonicalAssetClass[] = ['EQUITY', 'MUTUAL_FUND', 'US_STOCKS', 'GOLD', 'NPS']

interface Props {
  initial: Record<string, number>
  onSave: (targets: Record<string, number>) => Promise<void>
  onClose: () => void
}

export const TargetAllocationEditor: React.FC<Props> = ({ initial, onSave, onClose }) => {
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(TARGET_CLASSES.map((c) => [c, initial[c] ? String(initial[c]) : ''])),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const parsed = Object.fromEntries(TARGET_CLASSES.map((c) => [c, Number(values[c]) || 0]))
  const total = Object.values(parsed).reduce((s, v) => s + v, 0)
  const invalid = total > 100.01 || Object.values(parsed).some((v) => v < 0 || v > 100)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onSave(Object.fromEntries(Object.entries(parsed).filter(([, v]) => v > 0)))
      onClose()
    } catch (err: any) {
      setError(err?.message || 'Could not save targets')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="scrim" onClick={onClose}>
      <form className="modal" role="dialog" aria-modal="true" aria-labelledby="tgt-title" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="modal-h">
          <div style={{ flex: '1 1 auto' }}>
            <h2 className="h2" id="tgt-title">
              Target allocation
            </h2>
            <p className="sub">
              Your intended mix as a share of portfolio value. Drift notes compare the live mix against it. Leave a class empty to set no
              target.
            </p>
          </div>
          <button type="button" className="btn btn-icon btn-ghost" aria-label="Close" onClick={onClose}>
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        <div className="modal-b">
          {TARGET_CLASSES.map((c) => (
            <div className="kv" key={c} style={{ alignItems: 'center' }}>
              <label htmlFor={`tgt-${c}`} style={{ color: 'var(--text)' }}>
                {CLASS_LABEL[c]}
              </label>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <input
                  id={`tgt-${c}`}
                  className="input mono"
                  style={{ width: 88, textAlign: 'right' }}
                  type="number"
                  min={0}
                  max={100}
                  step="0.5"
                  inputMode="decimal"
                  value={values[c]}
                  placeholder="—"
                  onChange={(e) => setValues((v) => ({ ...v, [c]: e.target.value }))}
                />
                <span className="dim">%</span>
              </span>
            </div>
          ))}
          <div className="kv" style={{ fontWeight: 600 }}>
            <span style={{ color: 'var(--text)' }}>Total</span>
            <span className="num" style={{ color: invalid ? 'var(--loss)' : undefined }}>
              {total.toFixed(1)}%{' '}
              <span className="hint">{invalid ? 'over 100%' : total < 100 ? `${(100 - total).toFixed(1)}% unassigned` : ''}</span>
            </span>
          </div>
          {error && <p className="note bad">{error}</p>}
        </div>

        <div className="modal-f">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={invalid || saving}>
            {saving ? 'Saving…' : 'Save targets'}
          </button>
        </div>
      </form>
    </div>
  )
}
