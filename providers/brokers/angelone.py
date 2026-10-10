"""Angel One SmartAPI provider (direct REST, https://apiconnect.angelone.in).

Auth: SmartAPI app key + client code + PIN + a TOTP generated from the user's TOTP seed. The
JWT session is cached (encrypted) and reused until it expires, then re-created.
Holdings come with last traded price and previous close, so no external quotes are needed.
"""

import logging
import socket
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from core.totp import generate_totp
from providers.brokers.base import BrokerProvider
from storage.tables.repositories import BrokerCredentialRepository

logger = logging.getLogger("wealthvault.providers.angelone")

BASE_URL = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
LOGIN_MPIN_PATH = "/rest/auth/angelbroking/user/v1/loginByMPIN"
HOLDINGS_PATH = "/rest/secure/angelbroking/portfolio/v1/getAllHolding"
SESSION_TTL_SECONDS = 20 * 3600  # SmartAPI JWTs last until end of day; re-login well before that


class AngelOneAuthRequiredError(Exception):
    """Credentials are missing, wrong, or the login was rejected."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _mac_address() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))


class AngelOneProvider(BrokerProvider):
    """Angel One provider; credentials live encrypted in Azure Table Storage per user and connection."""

    def __init__(self, owner_id: str, connection_id: str, timeout_seconds: float = 30.0) -> None:
        super().__init__()
        self.owner_id = owner_id
        self.connection_id = connection_id
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._repo = BrokerCredentialRepository()

    @staticmethod
    def _headers(api_key: str, jwt: Optional[str] = None) -> Dict[str, str]:
        local_ip = _local_ip()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": local_ip,
            "X-ClientPublicIP": local_ip,
            "X-MACAddress": _mac_address(),
            "X-PrivateKey": api_key,
        }
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        return headers

    async def _login(self, creds: Dict[str, str]) -> str:
        required = ("api_key", "client_code", "pin", "totp_secret")
        missing = [f for f in required if not creds.get(f)]
        if missing:
            raise AngelOneAuthRequiredError(f"Missing Angel One credentials: {', '.join(missing)}.")

        body = {"clientcode": creds["client_code"], "password": creds["pin"], "totp": generate_totp(creds["totp_secret"])}
        async with aiohttp.ClientSession(timeout=self.timeout) as http:
            async with http.post(f"{BASE_URL}{LOGIN_PATH}", headers=self._headers(creds["api_key"]), json=body) as resp:
                data = await resp.json(content_type=None) or {}

            # Newer accounts are told to switch to MPIN login (error AB7001); retry on that endpoint
            if not data.get("status") and data.get("errorcode") == "AB7001":
                mpin_body = {
                    "clientcode": creds["client_code"],
                    "mpin": creds["pin"],
                    "totp": generate_totp(creds["totp_secret"]),
                }
                async with http.post(
                    f"{BASE_URL}{LOGIN_MPIN_PATH}", headers=self._headers(creds["api_key"]), json=mpin_body
                ) as resp:
                    data = await resp.json(content_type=None) or {}

        jwt = (data.get("data") or {}).get("jwtToken")
        if not data.get("status") or not jwt:
            raise AngelOneAuthRequiredError(
                f"Angel One login failed: {data.get('message') or 'no response'} (code {data.get('errorcode') or 'n/a'}). "
                "Check client code, PIN, TOTP secret and that your SmartAPI app key is active."
            )
        await self._repo.save_session(
            self.owner_id, self.connection_id, {"jwt": jwt, "expires_at": time.time() + SESSION_TTL_SECONDS}
        )
        return jwt

    async def _session(self, force_login: bool = False) -> Tuple[Dict[str, str], str]:
        creds = await self._repo.get_credentials(self.owner_id, self.connection_id)
        if not creds:
            raise AngelOneAuthRequiredError("Angel One credentials are not set. Add them on the Brokers page.")
        if not force_login:
            session = await self._repo.get_session(self.owner_id, self.connection_id)
            if session and session.get("jwt") and float(session.get("expires_at", 0)) > time.time():
                return creds, session["jwt"]
        return creds, await self._login(creds)

    async def _get(self, path: str) -> Dict[str, Any]:
        for attempt in (0, 1):
            creds, jwt = await self._session(force_login=attempt == 1)
            async with aiohttp.ClientSession(timeout=self.timeout) as http:
                async with http.get(f"{BASE_URL}{path}", headers=self._headers(creds["api_key"], jwt)) as resp:
                    data = await resp.json(content_type=None) or {}
                    if resp.status in (401, 403) or data.get("errorcode") in ("AG8001", "AG8002", "AB8050"):
                        continue  # stale session: log in again once
                    if not data.get("status"):
                        raise RuntimeError(f"Angel One API error on {path}: {data.get('message')} ({data.get('errorcode')})")
                    return data
        raise AngelOneAuthRequiredError("Angel One rejected the session after re-login. Check your credentials.")

    # --- BrokerProvider ---

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        return (await self.get_account_status()).get("status") == "success"

    async def get_account_status(self) -> Dict[str, Any]:
        try:
            creds, _ = await self._session()
            return {"status": "success", "data": {"broker": "ANGELONE", "user_id": creds.get("client_code")}}
        except AngelOneAuthRequiredError as exc:
            return {"status": "auth_required", "message": str(exc), "auth_url": exc.auth_url}

    async def get_holdings(self) -> List[Dict[str, Any]]:
        data = await self._get(HOLDINGS_PATH)
        block = data.get("data")
        if isinstance(block, dict):
            return list(block.get("holdings") or [])
        return list(block or [])

    async def get_transactions(self) -> List[Dict[str, Any]]:
        return []
