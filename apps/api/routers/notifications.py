"""Push notification endpoints used by the Android app.

- POST /api/v1/notifications/devices           register this phone's push token for the signed-in user
- POST /api/v1/notifications/devices/remove    forget it (on sign-out)
- GET/PUT /api/v1/notifications/prefs          which kinds the person wants
- GET  /api/v1/notifications/{id}              the text of a notification (the push itself carries only the id)
- POST /api/v1/notifications/test              send a test to the caller's own phones
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.routers.accounts import get_current_user
from core.push.service import Ports, send_test
from storage.tables.repositories import DeviceTokenRepository, NotificationPrefsRepository, NotificationRepository

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class DeviceBody(BaseModel):
    token: str = Field(..., min_length=20, max_length=4096)


class PrefsBody(BaseModel):
    holdings_ath: bool = True
    stage2_ath: bool = True
    networth_daily: bool = True
    networth_weekly: bool = True
    us_stocks: bool = True
    kite_login: bool = True


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(body: DeviceBody, current_user_id: str = Depends(get_current_user)) -> None:
    await DeviceTokenRepository().add(current_user_id, body.token.strip())


@router.post("/devices/remove", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(body: DeviceBody, current_user_id: str = Depends(get_current_user)) -> None:
    await DeviceTokenRepository().remove(current_user_id, body.token.strip())


@router.get("/prefs")
async def get_prefs(current_user_id: str = Depends(get_current_user)) -> Dict[str, bool]:
    return await NotificationPrefsRepository().get(current_user_id)


@router.put("/prefs")
async def put_prefs(body: PrefsBody, current_user_id: str = Depends(get_current_user)) -> Dict[str, bool]:
    return await NotificationPrefsRepository().save(current_user_id, body.model_dump())


@router.post("/test")
async def test_notification(current_user_id: str = Depends(get_current_user)) -> Dict[str, int]:
    ports = Ports()
    if ports.sender is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Push notifications are not set up on the server yet.")
    delivered = await send_test(ports, current_user_id)
    if delivered == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No phone is registered for this account yet. Open the app once with notifications allowed.")
    return {"delivered": delivered}


@router.get("/{notification_id}")
async def get_notification(notification_id: str, current_user_id: str = Depends(get_current_user)) -> Dict[str, str]:
    row = await NotificationRepository().get(current_user_id, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {k: str(row.get(k, "")) for k in ("kind", "title", "body", "body_masked", "public_title", "route", "extra", "created_at")}
