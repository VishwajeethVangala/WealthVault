"""Feedback Router.

The "Send feedback" form in the app and on the web. Each message is kept in Azure Table Storage under the
sender's own partition (so deleting an account deletes its feedback too), with the sender's email so a reply
can be sent. Read them in the Azure portal: the storage account's Tables, table "feedback".

- POST /api/v1/feedback   send a message
- GET  /api/v1/feedback   the messages you have sent
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from apps.api.routers.accounts import get_current_user
from storage.tables.repositories import FeedbackRepository, UserRepository

logger = logging.getLogger("wealthvault.api.feedback")

router = APIRouter(prefix="/feedback", tags=["Feedback"])

MAX_MESSAGE = 2000


class FeedbackRequest(BaseModel):
    category: Literal["idea", "problem", "praise", "other"] = "other"
    message: str = Field(..., description="What the person wants to tell us")
    platform: Literal["android", "web"] = "web"
    app_version: Optional[str] = Field(default=None, max_length=32)

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Write a message first.")
        if len(v) > MAX_MESSAGE:
            raise ValueError(f"Keep it under {MAX_MESSAGE} characters.")
        return v


@router.post("", status_code=status.HTTP_201_CREATED, summary="Send feedback")
async def send_feedback(payload: FeedbackRequest, current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    users, repo = UserRepository(), FeedbackRepository()
    try:
        user = await users.get_user(current_user_id)
        saved = await repo.save_feedback(
            owner_id=current_user_id,
            category=payload.category,
            message=payload.message,
            platform=payload.platform,
            app_version=payload.app_version,
            email=user.email if user else None,
        )
    except Exception as exc:
        logger.error("Could not save feedback from %s: %s", current_user_id, exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Feedback could not be saved right now. Please try again.")
    finally:
        await users.close()
        await repo.close()
    logger.info("Feedback from %s (%s, %s)", current_user_id, payload.category, payload.platform)
    return {"status": "received", "id": saved["id"]}


@router.get("", status_code=status.HTTP_200_OK, summary="The feedback you have sent")
async def my_feedback(current_user_id: str = Depends(get_current_user)) -> List[Dict[str, Any]]:
    repo = FeedbackRepository()
    try:
        return await repo.list_feedback(current_user_id)
    finally:
        await repo.close()
