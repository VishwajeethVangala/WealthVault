"""Target Allocation Router.

Each user's target asset mix lives in Azure Table Storage (partitioned by owner),
and drives the allocation-drift signals on the dashboard.
"""

import logging

from fastapi import APIRouter, Depends, status

from apps.api.routers.accounts import get_current_user
from core.models import TargetAllocation, TargetAllocationUpdate
from storage.tables.repositories import TargetAllocationRepository

logger = logging.getLogger("wealthvault.api.targets")

router = APIRouter(prefix="/portfolio/targets", tags=["Target Allocation"])


@router.get(
    "",
    response_model=TargetAllocation,
    status_code=status.HTTP_200_OK,
    summary="Get Target Allocation",
    description="Returns the caller's target asset mix. Empty when none has been set.",
)
async def get_targets(current_user_id: str = Depends(get_current_user)) -> TargetAllocation:
    return await TargetAllocationRepository().get_targets(owner_id=current_user_id)


@router.put(
    "",
    response_model=TargetAllocation,
    status_code=status.HTTP_200_OK,
    summary="Set Target Allocation",
    description="Replaces the caller's target asset mix. Percentages must be 0-100 and total at most 100.",
)
async def put_targets(
    payload: TargetAllocationUpdate,
    current_user_id: str = Depends(get_current_user),
) -> TargetAllocation:
    saved = await TargetAllocationRepository().save_targets(owner_id=current_user_id, targets=payload.targets)
    logger.info("Saved target allocation for user %s: %s", current_user_id, saved.targets)
    return saved
