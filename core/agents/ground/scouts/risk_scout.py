"""Risk Scout: Portfolio Capital & Drawdown Exposure Agent.

Audits individual portfolio holdings against risk boundaries:
- Hard stop-loss breach (P&L <= -7.5%)
- Deep drawdown breach (P&L <= -15.0%)
- Over-concentration ceiling (Weight > 15.0%)
"""

import logging
from typing import Any, Dict, Optional

from core.agents.ground.contracts import RiskIntelReport

logger = logging.getLogger("wealthvault.agents.ground.risk_scout")


class RiskScout:
    """Scout for portfolio risk limits, cost-basis P&L, and concentration."""

    def evaluate_holding(
        self,
        holding: Dict[str, Any],
        total_portfolio_value: float,
    ) -> RiskIntelReport:
        symbol = str(holding.get("tradingsymbol") or holding.get("symbol") or "UNKNOWN").strip().upper()
        avg_price = float(holding.get("average_price") or holding.get("avg_price") or 0.0)
        cur_price = float(holding.get("last_price") or holding.get("current_price") or avg_price)
        qty = int(holding.get("quantity") or 0)
        broker = str(holding.get("broker") or holding.get("source") or "Zerodha Kite")

        pnl_pct = 0.0
        if avg_price > 0:
            pnl_pct = ((cur_price - avg_price) / avg_price) * 100.0

        current_value = cur_price * qty
        weight_pct = 0.0
        if total_portfolio_value > 0:
            weight_pct = (current_value / total_portfolio_value) * 100.0

        stop_loss_breach = pnl_pct <= -7.5
        deep_drawdown_breach = pnl_pct <= -15.0
        over_concentration = weight_pct > 15.0

        # Build human-readable audit summary
        notes = []
        if stop_loss_breach:
            notes.append(f"Hard Stop Breach ({pnl_pct:+.1f}%)")
        if deep_drawdown_breach:
            notes.append(f"Severe Drawdown ({pnl_pct:+.1f}%)")
        if over_concentration:
            notes.append(f"Over-concentrated ({weight_pct:.1f}% portfolio weight)")

        if not notes:
            if pnl_pct >= 0:
                summary = f"Normal Operating Range (+{pnl_pct:.1f}%), {weight_pct:.1f}% weight in {broker}."
            else:
                margin_to_stop = abs(pnl_pct - (-7.5))
                summary = f"Capital Safe ({pnl_pct:.1f}%), {margin_to_stop:.1f}% margin to -7.5% stop-loss."
        else:
            summary = " | ".join(notes)

        return RiskIntelReport(
            symbol=symbol,
            current_price=cur_price,
            average_price=avg_price,
            quantity=qty,
            pnl_pct=round(pnl_pct, 2),
            portfolio_weight_pct=round(weight_pct, 2),
            stop_loss_breach=stop_loss_breach,
            deep_drawdown_breach=deep_drawdown_breach,
            over_concentration=over_concentration,
            broker_source=broker,
            status="COMPLETED",
            summary=summary,
        )
