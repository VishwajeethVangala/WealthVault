"""Persistent INDmoney Model Context Protocol (MCP) Client.

Direct Streamable HTTP JSON-RPC client to https://mcp.indmoney.com/mcp.
Implements OAuth 2.0 PKCE flow, persistent token storage on disk (DATA_DIR/indmoney_tokens.json),
and automatic token refreshing, eliminating child processes, port collisions, and unwanted browser popups.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional
import urllib.parse

import aiohttp

from core.config import data_dir, get_settings, public_base_url
from core.market_data.scope import require_owner, scoped_key

logger = logging.getLogger("wealthvault.mcp.indmoney")



class IndmoneyRateLimitError(RuntimeError):
    """INDmoney limits each tool to a number of calls per hour (get_family_asset_holdings: 250 'cost units', 3 per
    call). Past it the server answers with a notice, not an error status, which must never be read as data."""

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class IndmoneyAuthRequiredError(Exception):
    """Raised when INDmoney session requires interactive OAuth authorization."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class IndmoneyMCPClient:
    """Persistent HTTP OAuth client for INDmoney MCP server, isolated per connection ID."""

    _instances: Dict[str, "IndmoneyMCPClient"] = {}

    def __init__(
        self,
        server_url: str = "https://mcp.indmoney.com/mcp",
        token_endpoint: str = "https://mcp.indmoney.com/token",
        authorization_endpoint: str = "https://mcp.indmoney.com/authorize",
        connection_id: str = "conn_indmoney_live",
        owner_id: Optional[str] = None,
    ) -> None:
        self.server_url = server_url
        self.token_endpoint = token_endpoint
        self.authorization_endpoint = authorization_endpoint
        self.connection_id = connection_id
        self.owner_id = owner_id
        safe_id = scoped_key(connection_id, owner_id, "conn_indmoney_live")
        self.client_key = safe_id
        self.tokens_file = data_dir() / f"indmoney_tokens_{safe_id}.json"
        # Backwards compatibility for the original single-user tokens file, never for an owned client
        if owner_id is None and (connection_id == "conn_indmoney_live" or "default" in connection_id) and not self.tokens_file.exists() and (data_dir() / "indmoney_tokens.json").exists():
            self.tokens_file = data_dir() / "indmoney_tokens.json"

        self.client_id: str = get_settings().INDMONEY_CLIENT_ID
        self.client_secret: str = get_settings().INDMONEY_CLIENT_SECRET
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
        self._blocked_until: Dict[str, float] = {}  # tool -> time.monotonic() until which INDmoney said to wait

        self.registration_endpoint = "https://mcp.indmoney.com/register"
        self._load_client_info()
        base = public_base_url()
        if base:  # a deployed host always wins over a saved localhost redirect
            self.redirect_uri = f"{base}/api/v1/portfolio/oauth/indmoney/callback"
        self._apply_registered_client()
        self._load_tokens()

    @classmethod
    def get_instance(cls, connection_id: str = "conn_indmoney_live", owner_id: Optional[str] = None) -> "IndmoneyMCPClient":
        safe_id = scoped_key(connection_id, owner_id, "conn_indmoney_live")
        if safe_id not in cls._instances:
            cls._instances[safe_id] = IndmoneyMCPClient(connection_id=connection_id, owner_id=owner_id)
        return cls._instances[safe_id]

    @classmethod
    def find(cls, client_key: str) -> Optional["IndmoneyMCPClient"]:
        """The client that issued an OAuth state, or None. Never creates one."""
        return cls._instances.get(re.sub(r"[^a-zA-Z0-9_-]", "_", client_key or ""))

    @classmethod
    async def close_all(cls) -> None:
        for client in list(cls._instances.values()):
            try:
                await client.close()
            except Exception as exc:
                logger.debug("Error closing INDmoney client: %s", exc)

    def _load_client_info(self) -> None:
        client_file = data_dir() / "indmoney_client.json"
        if client_file.exists():
            try:
                with open(client_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.client_id = data.get("client_id", self.client_id)
                    self.client_secret = data.get("client_secret", self.client_secret)
                    self.redirect_uri = data.get("redirect_uri", self.redirect_uri)
                    self.server_url = data.get("server_url", self.server_url)
                    self.token_endpoint = data.get("token_endpoint", self.token_endpoint)
                    self.authorization_endpoint = data.get("authorization_endpoint", self.authorization_endpoint)
            except Exception as exc:
                logger.warning("Could not load INDmoney client info: %s", exc)

    # --- OAuth client registration ------------------------------------------------------------------
    # INDmoney issues OAuth clients through open registration (RFC 7591) and binds each to the redirect
    # addresses it was registered with. The localhost client from local setup cannot be used on a deployed
    # host, so the app registers one for its own address once and keeps it in DATA_DIR.

    _registry_lock = asyncio.Lock()

    @staticmethod
    def _is_local_redirect(uri: str) -> bool:
        host = urllib.parse.urlparse(uri).hostname or ""
        return host in ("127.0.0.1", "localhost", "::1")

    @staticmethod
    def _registry_file() -> Path:
        return data_dir() / "indmoney_oauth_clients.json"

    def _read_registry(self) -> Dict[str, Any]:
        try:
            return json.loads(self._registry_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _apply_registered_client(self) -> None:
        """Use the client registered for this redirect address, if the address is not a local one."""
        if self._is_local_redirect(self.redirect_uri):
            return
        entry = self._read_registry().get(self.redirect_uri)
        if entry and entry.get("client_id"):
            self.client_id = entry["client_id"]
            self.client_secret = entry.get("client_secret", "")
        else:  # whatever is configured belongs to the localhost client and would be rejected here
            self.client_id, self.client_secret = "", ""

    async def ensure_client(self) -> None:
        """Make sure an OAuth client exists for this redirect address, registering one if needed."""
        if self.client_id or self._is_local_redirect(self.redirect_uri):
            return
        async with IndmoneyMCPClient._registry_lock:
            self._apply_registered_client()  # another request may have registered it meanwhile
            if self.client_id:
                return
            payload = {
                "client_name": "WealthVault",
                "redirect_uris": [self.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
                "scope": self.scope,
            }
            async with self._get_http_session().post(self.registration_endpoint, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400 or not data.get("client_id"):
                    raise RuntimeError(f"INDmoney client registration failed ({resp.status}): {data}")
            registry = self._read_registry()
            registry[self.redirect_uri] = {"client_id": data["client_id"], "client_secret": data.get("client_secret", "")}
            path = self._registry_file()
            path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            logger.info("Registered an INDmoney OAuth client for %s", self.redirect_uri)
            self._apply_registered_client()

    def _load_tokens(self) -> None:
        if self.tokens_file.exists():
            try:
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    self.expires_at = float(data.get("expires_at") or 0.0)
                    logger.info("Loaded INDmoney tokens for %s from disk (expires in %ds)", self.connection_id, max(0, int(self.expires_at - time.time())))
            except Exception as exc:
                logger.warning("Could not load INDmoney tokens for %s: %s", self.connection_id, exc)

    def _save_tokens(self) -> None:
        try:
            self.tokens_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tokens_file, "w", encoding="utf-8") as f:
                json.dump({
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.expires_at,
                    "updated_at": time.time(),
                }, f, indent=2)
            logger.info("Saved INDmoney tokens for %s to disk successfully.", self.connection_id)
        except Exception as exc:
            logger.warning("Failed to save INDmoney tokens for %s: %s", self.connection_id, exc)

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

    def reset_tokens(self) -> None:
        """Clear tokens and remove persisted tokens file for this connection."""
        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0.0
        try:
            if self.tokens_file.exists():
                self.tokens_file.unlink()
        except Exception as exc:
            logger.debug("Failed to unlink tokens file for %s: %s", self.connection_id, exc)

    def get_authorization_url(self) -> str:
        """Generate OAuth 2.0 PKCE authorization URL pointing to WealthVault callback."""
        raw_verifier = os.urandom(32)
        code_verifier = base64.urlsafe_b64encode(raw_verifier).rstrip(b"=").decode("ascii")
        challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")

        nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
        state = f"{self.client_key}::{nonce}"
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
                    expires_in = int(data.get("expires_in") or 86400)
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

        await self.ensure_client()
        auth_url = self.get_authorization_url()
        raise IndmoneyAuthRequiredError(
            "INDmoney authorization is required. Please authorize via the link.",
            auth_url=auth_url,
        )

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invoke an INDmoney MCP tool via direct HTTP JSON-RPC 2.0 with Bearer auth."""
        wait = self._blocked_until.get(name, 0.0) - time.monotonic()
        if wait > 0:  # told to wait: asking again only spends the calls that the wait is for
            raise IndmoneyRateLimitError(f"INDmoney rate limit on '{name}': try again in {int(wait) + 1}s", retry_after=wait)
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
                        await self.ensure_client()
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
                        parsed = json.loads(text)
                    except Exception:
                        return text
                    if isinstance(parsed, dict) and "rate_limit" in str(parsed.get("error", "")).lower():
                        retry = min(3600.0, max(1.0, float(parsed.get("retry_after_seconds") or 60)))
                        self._blocked_until[name] = time.monotonic() + retry
                        logger.warning("INDmoney rate limit on %s: %s", name, parsed.get("message"))
                        raise IndmoneyRateLimitError(str(parsed.get("message") or "INDmoney rate limit exceeded"), retry_after=retry)
                    return parsed
                elif "error" in data:
                    raise RuntimeError(f"INDmoney MCP error: {data['error']}")
                return data
        except (IndmoneyAuthRequiredError, RuntimeError):  # (the rate limit error is a RuntimeError)
            raise
        except Exception as exc:
            logger.error("INDmoney call_tool error (%s): %s", name, exc)
            raise

    async def get_family_asset_holdings(self, asset: str = "overall", complete: bool = True) -> Dict[str, Any]:
        """Retrieve overall family asset holdings from INDmoney MCP.

        `complete` also asks for each capped member's full list (one more call each); price refreshes that only need
        the top holdings pass False, because the calls are limited per hour."""
        data = await self.call_tool("get_family_asset_holdings", {"asset": asset})
        # anything that is not a holdings reply is an error, never an empty portfolio: an empty one would wipe the
        # stored holdings on the next sync
        if not isinstance(data, dict) or not (
            "family_asset_holdings" in data
            or "family_asset_holdings" in (data.get("overall") if isinstance(data.get("overall"), dict) else {})
            or "family_asset_holdings" in (data.get("data") if isinstance(data.get("data"), dict) else {})
        ):
            raise RuntimeError(f"INDmoney returned no holdings: {str(data)[:160]}")
        return await self._complete_capped_lists(data, asset) if complete else data

    async def _complete_capped_lists(self, data: Dict[str, Any], asset: str) -> Dict[str, Any]:
        """INDmoney's whole-family view lists only each member's top 25 holdings by value and says how many it left
        out (`holdings_omitted`). For every member with omitted holdings, ask again for that member alone, which
        returns the complete list, and put it in place of the capped one."""
        members = data.get("family_asset_holdings")
        if not isinstance(members, list):
            return data
        for member in members:
            if not isinstance(member, dict) or not member.get("holdings_omitted"):
                continue
            name, kind = member.get("name"), member.get("asset")
            if not name or not kind:
                continue
            try:
                full = await self.call_tool("get_family_asset_holdings", {"asset": kind, "family_member": name})
            except Exception as exc:  # keep the capped list rather than lose the whole sync
                logger.warning("INDmoney full %s list for %s not read: %s", kind, name, exc)
                continue
            for entry in (full.get("family_asset_holdings") or []) if isinstance(full, dict) else []:
                if isinstance(entry, dict) and entry.get("name") == name and entry.get("asset") == kind and isinstance(entry.get("holdings"), list):
                    if len(entry["holdings"]) > len(member.get("holdings") or []):
                        member["holdings"] = entry["holdings"]
                        member.pop("holdings_omitted", None)
                    break
        return data

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None


def get_indmoney_mcp_client(connection_id: str = "conn_indmoney_live", owner_id: Optional[str] = None) -> IndmoneyMCPClient:
    """Retrieve persistent instance of IndmoneyMCPClient for the specified connection ID."""
    require_owner(owner_id)
    return IndmoneyMCPClient.get_instance(connection_id=connection_id, owner_id=owner_id)
