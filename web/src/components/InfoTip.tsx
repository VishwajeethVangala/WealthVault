import React, { useEffect, useRef, useState } from 'react'
import { Info } from 'lucide-react'

/** A small (i) that opens a note on tap or click, so it works on touch screens where hover does not. */
export const InfoTip: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <span className="infotip" ref={ref}>
      <button type="button" className="infotip-btn" aria-label={label} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Info size={14} strokeWidth={1.75} />
      </button>
      {open && (
        <span className="infotip-pop" role="note">
          {children}
        </span>
      )}
    </span>
  )
}
