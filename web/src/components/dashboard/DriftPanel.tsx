import React from 'react'
import { PieChart } from 'lucide-react'
import { pct, tone } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { CLASS_COLOR, CLASS_LABEL } from '../holdings/holdingsModel'
import type { DriftRow } from './metrics'

/** Each class's weight against its target, and the rupees that would close the gap at today's total. */
export const DriftPanel: React.FC<{ rows: DriftRow[]; hasTargets: boolean; onEdit: () => void }> = ({ rows, hasTargets, onEdit }) => {
  const { compact } = useMoney()
  const max = Math.max(...rows.flatMap((r) => [r.weight, r.target]), 1)
  return (
    <section className="card bx-panel" aria-label="Allocation against target">
      <header className="bx-ph">
        <div>
          <h2 className="card-t">Allocation and targets</h2>
          <p className="card-s">{hasTargets ? 'Weight against target, and what closes the gap' : 'Set targets to see how far each class has drifted'}</p>
        </div>
        <button className="btn btn-sm" type="button" onClick={onEdit}>
          <PieChart size={16} strokeWidth={1.75} /> {hasTargets ? 'Edit targets' : 'Set targets'}
        </button>
      </header>
      <div className="bx-drift">
        {rows.map((r) => (
          <div className="bx-dr" key={r.cls}>
            <span className="n">
              <span className="dot" style={{ background: CLASS_COLOR[r.cls] }} aria-hidden="true" />
              {CLASS_LABEL[r.cls]}
            </span>
            <span className="bar" aria-hidden="true">
              <i style={{ width: `${(r.weight / max) * 100}%`, background: CLASS_COLOR[r.cls] }} />
              {r.target > 0 && <b style={{ left: `${(r.target / max) * 100}%` }} title={`Target ${r.target}%`} />}
            </span>
            <span className="w num">
              {r.weight.toFixed(1)}%{r.target > 0 && <small> / {r.target.toFixed(0)}%</small>}
            </span>
            <span className={`mv num ${r.target > 0 ? tone(r.move) : ''}`}>
              {r.target > 0 ? (Math.abs(r.move) < 1000 ? 'on target' : `${r.move > 0 ? 'Add' : 'Trim'} ${compact(Math.abs(r.move))}`) : '—'}
            </span>
            {r.target > 0 && Math.abs(r.drift) >= 0.1 && <span className="sr">{pct(r.drift, 1)} against target</span>}
          </div>
        ))}
      </div>
      {hasTargets && <p className="bx-fine">Add and Trim are rupees at today&apos;s total. Selling to rebalance can trigger tax, so treat it as a guide.</p>}
    </section>
  )
}
