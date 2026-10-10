"""Groww Trade API provider (direct REST, https://api.groww.in).

Auth: a daily access token, obtained from the user's API key plus either their API secret
(checksum flow) or a TOTP seed, or supplied directly. Tokens expire daily at 06:00 IST.

Groww's holdings payload has quantity and average price but no prices; live prices are an
add-on plan, so prices and day change are filled in by the shared Kite quote enrichment.
"""

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiohttp

from core.totp import generate_totp
from providers.brokers.base import BrokerProvider
from storage.tables.repositories import BrokerCredentialRepository

logger = logging.getLogger("wealthvault.providers.groww")

BASE_URL = "https://api.groww.in"
IST = timezone(timedelta(hours=5, minutes=30))
APPROVAL_URL = "https://groww.in/trade-api/api-keys"


class GrowwAuthRequiredError(Exception):
    """Credentials are missing/invalid, or the API key needs today's approval on Groww."""

    def __init__(self, message: str, auth_url: Optional[str] = APPROVAL_URL) -> None:
        super().__init__(message)
        self.auth_url = auth_url


def next_token_expiry(now: Optional[datetime] = None) -> float:
    """Epoch seconds of the next 06:00 IST, when Groww access tokens lapse."""
    now_ist = (now or datetime.now(IST)).astimezone(IST)
    expiry = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)
    if expiry <= now_ist:
        expiry += timedelta(days=1)
    return expiry.timestamp()


def approval_checksum(api_secret: str, timestamp: str) -> str:
    """SHA-256 of the API secret concatenated with the epoch-seconds timestamp."""
    return hashlib.sha256((api_secret + timestamp).encode("utf-8")).hexdigest()


class GrowwProvider(BrokerProvider):
    """Groww provider; credentials live encrypted in Azure Table Storage per user and connection."""

    def __init__(self, owner_id: str, connection_id: str, timeout_seconds: float = 30.0) -> None:
        super().__init__()
        self.owner_id = owner_id
        self.connection_id = connection_id
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._repo = BrokerCredentialRepository()

    # --- auth ---

    async def _access_token(self) -> str:
        creds = await self._repo.get_credentials(self.owner_id, self.connection_id)
        if not creds:
            raise GrowwAuthRequiredError("Groww credentials are not set. Add them on the Brokers page.", auth_url=None)

        session = await self._repo.get_session(self.owner_id, self.connection_id)
        if session and session.get("token") and float(session.get("expires_at", 0)) - 60 > time.time():
            return session["token"]

        direct = creds.get("access_token")
        api_key = creds.get("api_key")
        if not api_key:
            if direct:
                return direct
            raise GrowwAuthRequiredError("Add your Groww API key (or a daily access token).", auth_url=None)

        if creds.get("api_secret"):
            ts = str(int(time.time()))
            body = {"key_type": "approval", "checksum": approval_checksum(creds["api_secret"], ts), "timestamp": ts}
        elif creds.get("totp_secret"):
            body = {"key_type": "totp", "totp": generate_totp(creds["totp_secret"])}
        elif direct:
            return direct
        else:
            raise GrowwAuthRequiredError("Add your Groww API secret or TOTP secret.", auth_url=None)

        async with aiohttp.ClientSession(timeout=self.timeout) as http:
            async with http.post(
                f"{BASE_URL}/v1/token/api/access",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                json=body,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200 or not data or not data.get("token"):
                    detail = (data or {}).get("error") or (data or {}).get("message") or data
                    raise GrowwAuthRequiredError(
                        f"Groww did not issue a token (HTTP {resp.status}: {detail}). "
                        f"Make sure the API key is approved for today at {APPROVAL_URL}."
                    )

        await self._repo.save_session(
            self.owner_id, self.connection_id, {"token": data["token"], "expires_at": next_token_expiry()}
        )
        return data["token"]

    async def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        token = await self._access_token()
        async with aiohttp.ClientSession(timeout=self.timeout) as http:
            async with http.get(
                f"{BASE_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "X-API-VERSION": "1.0"},
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status in (401, 403):
                    # Drop the cached token so the next call re-authenticates
                    await self._repo.save_session(self.owner_id, self.connection_id, {})
                    raise GrowwAuthRequiredError(f"Groww rejected the session (HTTP {resp.status}). Re-approve your API key.")
                if resp.status != 200 or (data or {}).get("status") != "SUCCESS":
                    raise RuntimeError(f"Groww API error on {path} (HTTP {resp.status}): {data}")
                return data

    # --- BrokerProvider ---

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        return (await self.get_account_status()).get("status") == "success"

    async def get_account_status(self) -> Dict[str, Any]:
        try:
            await self._access_token()
            return {"status": "success", "data": {"broker": "GROWW"}}
        except GrowwAuthRequiredError as exc:
            return {"status": "auth_required", "message": str(exc), "auth_url": exc.auth_url}

    async def get_holdings(self) -> List[Dict[str, Any]]:
        data = await self._get("/v1/holdings/user")
        return list((data.get("payload") or {}).get("holdings") or [])

    async def get_transactions(self) -> List[Dict[str, Any]]:
        return []
