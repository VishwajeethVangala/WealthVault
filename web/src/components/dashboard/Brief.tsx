import React from 'react'
import { Sparkles } from 'lucide-react'

/** A few plain sentences written from the numbers on the page, so the day can be read in ten seconds. */
export const Brief: React.FC<{ lines: string[] }> = ({ lines }) =>
  lines.length === 0 ? null : (
    <section className="bx-brief card" aria-label="Today in brief">
      <Sparkles size={18} strokeWidth={1.75} className="ic" aria-hidden="true" />
      <div>
        <h2 className="bx-brief-t">Today in brief</h2>
        <ul>
          {lines.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </div>
    </section>
  )
