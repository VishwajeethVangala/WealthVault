"""Sending push messages (Android and browsers) through Firebase Cloud Messaging (HTTP v1).

Only a type and an id are ever sent. The phone or browser then asks WealthVault's own server for the text of the notification,
so stock names and amounts never pass through Google's push service.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aiohttp
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from core.config import get_settings

logger = logging.getLogger("wealthvault.push.fcm")

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
OK, UNREGISTERED, FAILED = "ok", "unregistered", "failed"


class FcmSender:
    def __init__(self, info: Dict[str, Any]) -> None:
        self.project_id: str = info["project_id"]
        self._creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])

    async def _access_token(self) -> str:
        if not self._creds.valid:
            await asyncio.get_running_loop().run_in_executor(None, self._creds.refresh, Request())
        return str(self._creds.token)

    async def send(self, device_token: str, data: Dict[str, str]) -> str:
        """Deliver one data message. Returns OK, UNREGISTERED (the phone no longer has the app: forget the token) or FAILED."""
        body = {
            "message": {
                "token": device_token,
                "data": {k: str(v) for k, v in data.items()},
                "android": {"priority": "HIGH", "ttl": "3600s"},
                # browsers: deliver at once, and drop it after an hour like on a phone
                "webpush": {"headers": {"Urgency": "high", "TTL": "3600"}},
            }
        }
        try:
            token = await self._access_token()
            url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
                async with http.post(url, json=body, headers={"Authorization": f"Bearer {token}"}) as resp:
                    if resp.status == 200:
                        return OK
                    text = await resp.text()
                    if resp.status in (400, 404) and ("UNREGISTERED" in text or "NOT_FOUND" in text or "INVALID_ARGUMENT" in text):
                        return UNREGISTERED
                    logger.warning("FCM send failed (%s): %s", resp.status, text[:300])
                    return FAILED
        except Exception as exc:
            logger.warning("FCM send error: %s", exc)
            return FAILED


_sender: Optional[FcmSender] = None
_checked = False


def get_sender() -> Optional[FcmSender]:
    """The sender, or None when no Firebase key is configured (push is then simply off)."""
    global _sender, _checked
    if _checked:
        return _sender
    _checked = True
    raw = get_settings().FCM_SERVICE_ACCOUNT_JSON.strip()
    if not raw:
        return None
    try:
        _sender = FcmSender(json.loads(raw))
    except Exception as exc:  # a bad key must never stop the app from starting
        logger.error("FCM_SERVICE_ACCOUNT_JSON is set but unusable: %s", exc)
        _sender = None
    return _sender
