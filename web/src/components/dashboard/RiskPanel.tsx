import React, { useEffect, useState } from 'react'
import { fetchPortfolioRisk, type PortfolioRiskResponse } from '../../utils/api'
import { pct, tone, weight } from '../../utils/format'
import { useMoney } from '../../utils/useMoney'
import { SINGLE_POSITION_LIMIT_PCT } from '../../utils/dayChange'
import type { Instrument } from '../holdings/holdingsModel'

interface Props {
  concentration: { top1: Instrument | null; top1Pct: number; top5Pct: number; top10Pct: number; count: number }
  drawdown: { current: number; worst: number; days: number } | null
  usdPct: number
}

const Stat: React.FC<{ label: string; value: string; note: string; tone?: string; title?: string }> = ({ label, value, note, tone: t, title }) => (
  <div className="bx-stat" title={title}>
    <span className="bx-mini">{label}</span>
    <span className={`bx-sv num ${t ?? ''}`}>{value}</span>
    <span className="bx-sn">{note}</span>
  </div>
)

export const RiskPanel: React.FC<Props> = ({ concentration, drawdown, usdPct }) => {
  const { compact } = useMoney()
  const [data, setData] = useState<PortfolioRiskResponse | null>(null)

  useEffect(() => {
    fetchPortfolioRisk()
      .then(setData)
      .catch(() => setData(null))
  }, [])

  const r = data?.risk
  const varRupees = r && data ? (r.var95_1d_pct / 100) * data.equity_value : null

  return (
    <section className="card bx-panel" aria-label="Risk">
      <header className="bx-ph">
        <div>
          <h2 className="card-t">Risk</h2>
          <p className="card-s">How your Indian stocks would have behaved at today&apos;s weights</p>
        </div>
      </header>

      {r ? (
        <div className="bx-stats">
          <Stat
            label="Beta vs Nifty"
            value={r.beta == null ? '—' : r.beta.toFixed(2)}
            note={r.beta == null ? '' : r.beta > 1.05 ? 'moves more than the market' : r.beta < 0.95 ? 'moves less than the market' : 'moves with the market'}
            title="1.0 moves with the Nifty; 1.3 moves 30% more"
          />
          <Stat label="Volatility" value={`${r.volatility_pct}%`} note={`Nifty ${r.benchmark_volatility_pct}% a year`} />
          <Stat label="1-day loss, 95% of days" value={`−${r.var95_1d_pct}%`} note={varRupees != null ? `about ${compact(varRupees)} on your stocks` : ''} tone="neg" title="On 19 days in 20 the daily loss was smaller than this" />
          <Stat label="Worst fall from a peak" value={`${r.max_drawdown_pct}%`} note={`over ${r.days} trading days`} tone="neg" />
          <Stat label="Best / worst day" value={`${pct(r.best_day_pct)} / ${pct(r.worst_day_pct)}`} note={`${r.positive_days_pct}% of days were up`} />
          <Stat label="Move with the market" value={r.correlation == null ? '—' : r.correlation.toFixed(2)} note="1.0 = identical to the Nifty" />
        </div>
      ) : (
        <p className="empty-s">
          {data
            ? `Beta and volatility need stored price history for your stocks (${data.measured_stocks} of ${data.total_stocks} have it). Press Refresh Momentum Stocks on the Signals page once.`
            : 'Risk figures are not available right now.'}
        </p>
      )}
      {r && r.coverage_pct < 100 && <p className="bx-fine">Measured on {r.coverage_pct}% of your Indian stock value ({data?.measured_stocks} of {data?.total_stocks} stocks).</p>}
      {r && r.high_beta.length > 0 && (
        <p className="bx-fine">
          Highest beta: {r.high_beta.map((h) => `${h.name} ${h.beta.toFixed(1)}`).join(', ')}.
        </p>
      )}

      <div className="bx-conc">
        <p className="bx-who-h">Concentration</p>
        {[
          { label: 'Largest position', value: concentration.top1Pct, name: concentration.top1?.sym, limit: SINGLE_POSITION_LIMIT_PCT, scale: 40 },
          { label: 'Top 5', value: concentration.top5Pct, scale: 100 },
          { label: 'Top 10', value: concentration.top10Pct, scale: 100 },
          { label: 'US dollar exposure', value: usdPct, scale: 100 },
        ].map((row) => (
          <div className="bx-conc-r" key={row.label}>
            <span className="l">
              {row.label}
              {row.name ? <small> · {row.name.length > 18 ? `${row.name.slice(0, 17)}…` : row.name}</small> : null}
            </span>
            <span className="t" aria-hidden="true">
              <i className={row.limit && row.value > row.limit ? 'warn' : ''} style={{ width: `${Math.min(100, (row.value / row.scale) * 100)}%` }} />
              {row.limit && <b style={{ left: `${(row.limit / row.scale) * 100}%` }} title={`${row.limit}% limit`} />}
            </span>
            <span className={`v num ${row.limit && row.value > row.limit ? 'neg' : ''}`}>{weight(row.value, 1)}</span>
          </div>
        ))}
        {drawdown && (
          <div className="bx-conc-r">
            <span className="l">Down from peak</span>
            <span className="t" aria-hidden="true">
              <i className="neg" style={{ width: `${Math.min(100, Math.abs(drawdown.current) * 4)}%` }} />
            </span>
            <span className={`v num ${tone(drawdown.current)}`}>{pct(drawdown.current, 1)}</span>
          </div>
        )}
      </div>
    </section>
  )
}
