"""Portfolio Aggregation and Metrics Engine.

Calculates consolidated financial metrics (total current value, total cost basis,
total unrealized PnL, percentage return, and asset class allocations) from a list
of canonical Holding entities, constructing immutable PortfolioSnapshot records.
"""

from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional

from core.models import AssetClass, Holding, PortfolioSnapshot

logger = logging.getLogger("wealthvault.portfolio.aggregation")


class PortfolioAggregationService:
    """Service that computes consolidated financial analytics and portfolio snapshots."""

    def calculate_snapshot(
        self,
        owner_id: str,
        holdings: List[Holding],
        as_of_date: Optional[str] = None,
        calculation_version: str = "v1",
    ) -> PortfolioSnapshot:
        """Calculate a point-in-time consolidated portfolio snapshot from canonical holdings.

        Args:
            owner_id: User identifier of the tenant owner.
            holdings: List of canonical Holding entities for this user.
            as_of_date: Date string (YYYY-MM-DD), defaults to current UTC date.
            calculation_version: Schema version of the analytics calculation.

        Returns:
            A fully calculated PortfolioSnapshot instance.
        """
        date_str = as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snapshot_id = f"snapshot_{date_str}"

        if not holdings:
            return PortfolioSnapshot(
                snapshot_id=snapshot_id,
                owner_id=owner_id,
                as_of_date=date_str,
                calculation_version=calculation_version,
                total_current_value=0.0,
                total_invested_value=0.0,
                total_unrealized_pnl=0.0,
                total_pnl_percentage=0.0,
                asset_allocation={},
                holdings_count=0,
            )

        total_current_value = 0.0
        total_invested_value = 0.0
        allocation_totals: Dict[str, float] = defaultdict(float)

        for h in holdings:
            current_val = float(h.current_value)
            # Cost basis: quantity * average_price
            invested_val = float(h.quantity) * float(h.average_price)

            total_current_value += current_val
            total_invested_value += invested_val

            # Group by canonical asset class name
            asset_key = h.asset_class.value if isinstance(h.asset_class, AssetClass) else str(h.asset_class)
            allocation_totals[asset_key] += current_val

        # Financial totals
        total_current_value = round(total_current_value, 2)
        total_invested_value = round(total_invested_value, 2)
        total_unrealized_pnl = round(total_current_value - total_invested_value, 2)

        if total_invested_value > 0:
            total_pnl_percentage = round((total_unrealized_pnl / total_invested_value) * 100.0, 2)
        else:
            total_pnl_percentage = 0.0

        # Asset allocation mapping
        asset_allocation: Dict[str, Dict[str, float]] = {}
        for asset_class_name, abs_val in allocation_totals.items():
            rounded_abs = round(abs_val, 2)
            pct = round((rounded_abs / total_current_value * 100.0), 2) if total_current_value > 0 else 0.0
            asset_allocation[asset_class_name] = {
                "absolute_value": rounded_abs,
                "percentage_weight": pct,
            }

        snapshot = PortfolioSnapshot(
            snapshot_id=snapshot_id,
            owner_id=owner_id,
            as_of_date=date_str,
            calculation_version=calculation_version,
            total_current_value=total_current_value,
            total_invested_value=total_invested_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_pnl_percentage=total_pnl_percentage,
            asset_allocation=asset_allocation,
            holdings_count=len(holdings),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            "Computed snapshot for user %s: Total Value=₹%s, PnL=₹%s (%s%%) across %d holdings",
            owner_id,
            f"{total_current_value:,.2f}",
            f"{total_unrealized_pnl:,.2f}",
            total_pnl_percentage,
            len(holdings),
        )
        return snapshot
