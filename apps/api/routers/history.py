"""Portfolio History Router.

Serves the daily portfolio snapshots that every sync already stores, so the dashboard
can chart value against money invested over time.
"""

from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from apps.api.routers.accounts import get_current_user
from storage.tables.repositories import SnapshotsRepository

router = APIRouter(prefix="/portfolio/history", tags=["Portfolio History"])


class HistoryPoint(BaseModel):
    date: str
    value: float
    invested: float


@router.get(
    "",
    response_model=List[HistoryPoint],
    status_code=status.HTTP_200_OK,
    summary="Portfolio value history",
    description="Daily total value and invested amount from stored snapshots, oldest first. "
    "History only exists from the first sync onwards.",
)
async def get_history(
    days: int = Query(365, ge=1, le=3650),
    current_user_id: str = Depends(get_current_user),
) -> List[HistoryPoint]:
    snapshots = await SnapshotsRepository().list_snapshots(owner_id=current_user_id, limit=days)
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    points = [
        HistoryPoint(date=s.as_of_date, value=s.total_current_value, invested=s.total_invested_value)
        for s in snapshots
        if s.as_of_date >= cutoff
    ]
    return sorted(points, key=lambda p: p.date)
