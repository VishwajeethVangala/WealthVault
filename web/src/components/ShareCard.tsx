import React, { useState } from 'react'
import { Share2 } from 'lucide-react'
import { shareApp } from '../utils/share'

const NOTE: Record<string, string> = {
  copied: 'Message copied. Paste it into WhatsApp, an email or anywhere else.',
  failed: 'Could not share or copy here. Try again from a phone.',
}

/** The Account page card that shares WealthVault with a friend. */
export const ShareCard: React.FC = () => {
  const [note, setNote] = useState('')
  return (
    <section className="card">
      <h2 className="card-t">
        <Share2 size={16} strokeWidth={1.75} aria-hidden="true" /> Share WealthVault
      </h2>
      <p className="card-s">Send the app to a friend over WhatsApp or any other app. Nothing about your portfolio is included.</p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 12 }}>
        <button
          className="btn btn-primary"
          type="button"
          onClick={async () => {
            const result = await shareApp('account')
            setNote(NOTE[result] ?? '')
          }}
        >
          <Share2 size={16} strokeWidth={1.75} aria-hidden="true" />
          Share WealthVault
        </button>
        {note && (
          <span className="sub" role="status" style={{ margin: 0 }}>
            {note}
          </span>
        )}
      </div>
    </section>
  )
}
