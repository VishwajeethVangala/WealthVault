import React from 'react'
import { InfoTip } from './InfoTip'
import type { DayCoverage } from '../utils/dayCoverage'

/** "All N reporting", or how many do and a (i) naming the ones that do not and why. */
export const DayCoverageNote: React.FC<{ coverage: DayCoverage }> = ({ coverage }) => {
  if (coverage.missing.length === 0) return <span>All {coverage.total} reporting</span>
  return (
    <span>
      {coverage.reporting} of {coverage.total} reporting
      <InfoTip label="Which holdings have no 1-day change">
        <strong>{coverage.missing.length} holdings have no 1-day change</strong>
        {coverage.reasons.map((r) => (
          <span key={r} className="infotip-line">
            {r}
          </span>
        ))}
        <span className="infotip-line infotip-names">
          {coverage.missing
            .slice(0, 8)
            .map((m) => m.sym)
            .join(', ')}
          {coverage.missing.length > 8 ? ` and ${coverage.missing.length - 8} more` : ''}
        </span>
        <span className="infotip-line">Their change is left out of the 1-day total rather than counted as zero.</span>
      </InfoTip>
    </span>
  )
}
