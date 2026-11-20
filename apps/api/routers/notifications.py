"""Push notification endpoints used by the Android app.

- POST /api/v1/notifications/devices           register this phone's push token for the signed-in user
- POST /api/v1/notifications/devices/remove    forget it (on sign-out)
- GET/PUT /api/v1/notifications/prefs          which kinds the person wants
- GET  /api/v1/notifications/{id}              the text of a notification (the push itself carries only the id)
- POST /api/v1/notifications/test              send a test to the caller's own phones
"""

from typing import Any, Dict, List

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


@router.get("/feed")
async def get_notifications_feed(current_user_id: str = Depends(get_current_user)) -> Dict[str, Any]:
    """Return in-app notification cards for the top right bell dropdown."""
    from typing import Any, List
    from storage.tables.repositories import HoldingsRepository, SignalCacheRepository
    from apps.api.routers.signals import _equity_symbol_map
    from core.push.calls import display_name

    holdings_repo = HoldingsRepository()
    holdings = await holdings_repo.get_holdings(owner_id=current_user_id)
    symbol_map = await _equity_symbol_map(holdings, None)

    held_info: Dict[str, Dict[str, float]] = {}
    for h in holdings:
        inst = symbol_map.get(h.instrument_symbol)
        if not inst:
            continue
        key = inst.upper() if ":" in inst else f"NSE:{inst.upper()}"
        row = held_info.setdefault(key, {"qty": 0.0, "cost": 0.0, "val": 0.0})
        row["qty"] += h.quantity
        row["cost"] += h.quantity * h.average_price
        row["val"] += h.current_value or (h.quantity * h.average_price)

    wanted = list(held_info.keys())
    if not wanted:
        return {"items": [], "count": 0}

    cached = await SignalCacheRepository().get_many(wanted)
    items: List[Dict[str, Any]] = []

    for sid, row in cached.items():
        name = display_name(sid, row)
        pos = held_info.get(sid, {})
        qty = pos.get("qty", 0)
        cost = pos.get("cost", 0)
        val = pos.get("val", 0)
        pnl_pct = ((val / cost - 1.0) * 100.0) if cost > 0 else 0.0

        # 1. Supertrend Signals
        st = row.get("supertrend") or {}
        if st:
            direction = st.get("direction")
            st_val = st.get("supertrend") or 0.0
            cushion = st.get("cushion_pct")
            last_sig = st.get("last_signal")

            if direction is not None and direction > 0:
                # Bearish / Sell Call
                items.append({
                    "id": f"st-sell-{sid}",
                    "type": "sell_call",
                    "strategy": "SuperTrend",
                    "symbol": name,
                    "instrument": sid,
                    "severity": "danger",
                    "title": f"SELL ALERT · {name}",
                    "subtitle": f"Broke below Supertrend support (₹{st_val:,.2f})",
                    "detail": f"Trend turned red. You hold {qty:g} shares ({pnl_pct:+.1f}%). Strategy says exit.",
                    "url": f"/strategy?tab=supertrend&symbol={name}",
                    "timestamp": row.get("as_of") or "Latest",
                })
            elif cushion is not None and 0 <= cushion < 1.5:
                # Near support warning
                items.append({
                    "id": f"st-warn-{sid}",
                    "type": "warning",
                    "strategy": "SuperTrend",
                    "symbol": name,
                    "instrument": sid,
                    "severity": "warning",
                    "title": f"NEAR SUPPORT · {name}",
                    "subtitle": f"Only {cushion:.1f}% cushion above support (₹{st_val:,.2f})",
                    "detail": f"Watching closely. A daily close below ₹{st_val:,.2f} triggers an exit.",
                    "url": f"/strategy?tab=supertrend&symbol={name}",
                    "timestamp": row.get("as_of") or "Latest",
                })
            elif last_sig == "BUY" or (st.get("call") and st.get("call", {}).get("signal_date") == row.get("as_of")):
                items.append({
                    "id": f"st-buy-{sid}",
                    "type": "buy_signal",
                    "strategy": "SuperTrend",
                    "symbol": name,
                    "instrument": sid,
                    "severity": "success",
                    "title": f"BUY SIGNAL · {name}",
                    "subtitle": f"Supertrend green support confirmed (₹{st_val:,.2f})",
                    "detail": "Passed ADX & Volume filters. Ready for entry.",
                    "url": f"/strategy?tab=supertrend&symbol={name}",
                    "timestamp": row.get("as_of") or "Latest",
                })

        # 2. ATH Signals
        ath = row.get("ath") or {}
        if ath:
            if ath.get("last_signal") == "SELL":
                items.append({
                    "id": f"ath-sell-{sid}",
                    "type": "sell_call",
                    "strategy": "ATH Breakout",
                    "symbol": name,
                    "instrument": sid,
                    "severity": "danger",
                    "title": f"EXIT CALL · {name}",
                    "subtitle": "Closed below 200-DMA",
                    "detail": f"DMA trend broken. You hold {qty:g} shares.",
                    "url": f"/strategy?tab=ath&symbol={name}",
                    "timestamp": row.get("as_of") or "Latest",
                })

    severity_order = {"danger": 0, "warning": 1, "success": 2, "info": 3}
    items.sort(key=lambda x: severity_order.get(x["severity"], 9))

    return {"items": items, "count": len(items)}


@router.get("/{notification_id}")
async def get_notification(notification_id: str, current_user_id: str = Depends(get_current_user)) -> Dict[str, str]:
    row = await NotificationRepository().get(current_user_id, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return {k: str(row.get(k, "")) for k in ("kind", "title", "body", "body_masked", "public_title", "route", "extra", "created_at")}
