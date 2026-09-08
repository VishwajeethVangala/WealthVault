"""Persistent INDmoney Model Context Protocol (MCP) Client.

Direct Streamable HTTP JSON-RPC client to https://mcp.indmoney.com/mcp.
Implements OAuth 2.0 PKCE flow, persistent token storage on disk (storage/blobs/indmoney_tokens.json),
and automatic token refreshing, eliminating child processes, port collisions, and unwanted browser popups.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.parse

import aiohttp

logger = logging.getLogger("wealthvault.mcp.indmoney")

CLIENT_FILE = Path("storage/blobs/indmoney_client.json")
TOKENS_FILE = Path("storage/blobs/indmoney_tokens.json")


class IndmoneyAuthRequiredError(Exception):
    """Raised when INDmoney session requires interactive OAuth authorization."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class IndmoneyMCPClient:
    """Singleton persistent HTTP OAuth client for INDmoney MCP server."""

    _instance: Optional["IndmoneyMCPClient"] = None

    def __init__(
        self,
        server_url: str = "https://mcp.indmoney.com/mcp",
        token_endpoint: str = "https://mcp.indmoney.com/token",
        authorization_endpoint: str = "https://mcp.indmoney.com/authorize",
    ) -> None:
        self.server_url = server_url
        self.token_endpoint = token_endpoint
        self.authorization_endpoint = authorization_endpoint
        self.client_id: str = "dfed4e00-5c2a-4aec-ae9e-53afff3637a2"
        self.client_secret: str = "6f392883326629bd269c7425981ea90d853c1e3275ce1c62c525706f255c9c41"
        self.redirect_uri: str = "http://127.0.0.1:8000/api/v1/portfolio/oauth/indmoney/callback"
        self.scope: str = "portfolio:read"

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: float = 0.0

        self._pending_verifier: Optional[str] = None
        self._pending_state: Optional[str] = None
        self._pending_verifiers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._request_counter: int = 0

        self._load_client_info()
        self._load_tokens()

    @classmethod
    def get_instance(cls) -> "IndmoneyMCPClient":
        if cls._instance is None:
            cls._instance = IndmoneyMCPClient()
        return cls._instance

    def _load_client_info(self) -> None:
        if CLIENT_FILE.exists():
            try:
                with open(CLIENT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.client_id = data.get("client_id", self.client_id)
                    self.client_secret = data.get("client_secret", self.client_secret)
                    self.redirect_uri = data.get("redirect_uri", self.redirect_uri)
                    self.server_url = data.get("server_url", self.server_url)
                    self.token_endpoint = data.get("token_endpoint", self.token_endpoint)
                    self.authorization_endpoint = data.get("authorization_endpoint", self.authorization_endpoint)
            except Exception as exc:
                logger.warning("Could not load INDmoney client info: %s", exc)

    def _load_tokens(self) -> None:
        if TOKENS_FILE.exists():
            try:
                with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    self.expires_at = float(data.get("expires_at", 0.0))
                    logger.info("Loaded INDmoney tokens from disk (expires in %ds)", max(0, int(self.expires_at - time.time())))
            except Exception as exc:
                logger.warning("Could not load INDmoney tokens: %s", exc)

    def _save_tokens(self) -> None:
        try:
            TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                    "updated_at": time.time(),
                }, f, indent=2)
            logger.info("Saved INDmoney tokens to disk successfully.")
        except Exception as exc:
            logger.warning("Failed to save INDmoney tokens: %s", exc)

    def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=45.0)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def is_authenticated(self) -> bool:
        """Check if an access token is available and currently valid or refreshable."""
        if not self.access_token:
            return False
        if time.time() < self.expires_at:
            return True
        return bool(self.refresh_token)

    def get_authorization_url(self) -> str:
        """Generate OAuth 2.0 PKCE authorization URL pointing to WealthVault callback."""
        raw_verifier = os.urandom(32)
        code_verifier = base64.urlsafe_b64encode(raw_verifier).rstrip(b"=").decode("ascii")
        challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")

        state = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
        self._pending_verifier = code_verifier
        self._pending_state = state
        self._pending_verifiers[state] = {
            "verifier": code_verifier,
            "created_at": time.time(),
        }

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": self.scope,
            "state": state,
            "resource": self.server_url,
        }
        query_string = urllib.parse.urlencode(params)
        auth_url = f"{self.authorization_endpoint}?{query_string}"
        logger.info("Generated INDmoney PKCE authorization URL: %s", auth_url)
        return auth_url

    async def exchange_code(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        http = self._get_http_session()
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        verifier = None
        if state and state in self._pending_verifiers:
            verifier = self._pending_verifiers[state]["verifier"]
        elif self._pending_verifier:
            verifier = self._pending_verifier

        if verifier:
            payload["code_verifier"] = verifier

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json",
        }

        try:
            async with http.post(self.token_endpoint, headers=headers, data=payload) as resp:
                data = await resp.json()
                if resp.status != 200:
                    err = data.get("error_description") or data.get("error") or str(data)
                    raise RuntimeError(f"Token exchange failed ({resp.status}): {err}")

                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token") or self.refresh_token
                expires_in = int(data.get("expires_in", 86400))
                self.expires_at = time.time() + expires_in
                self._save_tokens()
                logger.info("Successfully exchanged code for INDmoney tokens. Valid for %ds.", expires_in)
                return data
        except Exception as exc:
            logger.error("INDmoney token exchange error: %s", exc)
            raise

    async def refresh_access_token(self) -> bool:
        """Refresh expired access token using stored refresh token."""
        if not self.refresh_token:
            return False

        http = self._get_http_session()
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json",
        }

        try:
            async with http.post(self.token_endpoint, headers=headers, data=payload) as resp:
                data = await resp.json()
                if resp.status == 200 and "access_token" in data:
                    self.access_token = data["access_token"]
                    if "refresh_token" in data:
                        self.refresh_token = data["refresh_token"]
                    expires_in = int(data.get("expires_in", 86400))
                    self.expires_at = time.time() + expires_in
                    self._save_tokens()
                    logger.info("Refreshed INDmoney access token successfully.")
                    return True
                logger.warning("Failed to refresh INDmoney token (%d): %s", resp.status, data)
                return False
        except Exception as exc:
            logger.warning("INDmoney token refresh exception: %s", exc)
            return False

    async def ensure_valid_token(self) -> str:
        """Return valid access token, auto-refreshing if expired or raising auth required."""
        if self.access_token and (time.time() < (self.expires_at - 60)):
            return self.access_token

        # Try to refresh
        if self.refresh_token:
            success = await self.refresh_access_token()
            if success and self.access_token:
                return self.access_token

        auth_url = self.get_authorization_url()
        raise IndmoneyAuthRequiredError(
            "INDmoney authorization is required. Please authorize via the link.",
            auth_url=auth_url,
        )

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invoke an INDmoney MCP tool via direct HTTP JSON-RPC 2.0 with Bearer auth."""
        token = await self.ensure_valid_token()

        http = self._get_http_session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {},
            },
        }

        try:
            async with http.post(self.server_url, headers=headers, json=payload) as resp:
                if resp.status == 401:
                    logger.info("INDmoney 401 received. Attempting token refresh...")
                    refreshed = await self.refresh_access_token()
                    if refreshed:
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        async with http.post(self.server_url, headers=headers, json=payload) as retry_resp:
                            raw_text = await retry_resp.text()
                            content_type = retry_resp.headers.get("Content-Type", "")
                    else:
                        raise IndmoneyAuthRequiredError(
                            "INDmoney session expired. Please re-authorize.",
                            auth_url=self.get_authorization_url(),
                        )
                else:
                    raw_text = await resp.text()
                    content_type = resp.headers.get("Content-Type", "")

                data = None
                if "text/event-stream" in content_type or "data:" in raw_text:
                    for line in raw_text.splitlines():
                        line_str = line.strip()
                        if line_str.startswith("data:"):
                            json_part = line_str[5:].strip()
                            try:
                                data = json.loads(json_part)
                                break
                            except Exception:
                                continue

                if data is None:
                    try:
                        data = json.loads(raw_text)
                    except Exception:
                        data = {"text": raw_text}

                if "result" in data:
                    res_obj = data["result"]
                    content = res_obj.get("content", [])
                    text = ""
                    if content and isinstance(content, list):
                        text = content[0].get("text", "")

                    if res_obj.get("isError"):
                        raise RuntimeError(f"INDmoney tool '{name}' failed: {text}")

                    try:
                        return json.loads(text)
                    except Exception:
                        return text
                elif "error" in data:
                    raise RuntimeError(f"INDmoney MCP error: {data['error']}")
                return data
        except (IndmoneyAuthRequiredError, RuntimeError):
            raise
        except Exception as exc:
            logger.error("INDmoney call_tool error (%s): %s", name, exc)
            raise

    async def get_family_asset_holdings(self, asset: str = "overall") -> Dict[str, Any]:
        """Retrieve overall family asset holdings from INDmoney MCP."""
        data = await self.call_tool("get_family_asset_holdings", {"asset": asset})
        return data if isinstance(data, dict) else {}

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None


def get_indmoney_mcp_client() -> IndmoneyMCPClient:
    """Retrieve global singleton instance of IndmoneyMCPClient."""
    return IndmoneyMCPClient.get_instance()
