import React from 'react'
import { Link } from 'react-router-dom'

/** A stock name that opens that stock in the Momentum view; plain text when there is no such view. */
export const StockLink: React.FC<{ href: string | null; title?: string; className?: string; children: React.ReactNode }> = ({ href, title, className, children }) =>
  href ? (
    <Link className={`sg-link ${className ?? ''}`} to={href} title={title ?? 'Open in Momentum'}>
      {children}
    </Link>
  ) : (
    <>{children}</>
  )
