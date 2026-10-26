"""Persistent Groww Model Context Protocol (MCP) Client.

Direct Streamable HTTP JSON-RPC client to https://mcp.groww.in/mcp.
Implements OAuth 2.0 PKCE flow, persistent token storage on disk (DATA_DIR/groww_tokens_*.json),
RFC 7591 dynamic client registration, MCP protocol initialization, automatic token refreshing,
and an integrated local redirect listener on port 52155 for Groww's desktop OAuth flow.
"""

import asyncio
import base64
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

import aiohttp

from core.config import data_dir, get_settings, public_base_url
from core.market_data.scope import require_owner, scoped_key

logger = logging.getLogger("wealthvault.mcp.groww")

LOCAL_CALLBACK_PORT = 52155
LOCAL_REDIRECT = f"http://localhost:{LOCAL_CALLBACK_PORT}/oauth/callback"
PENDING_TTL_SECONDS = 600.0  # a login link older than this is refused
LINK_REUSE_SECONDS = 300.0  # asking for a link again inside this window hands back the same one
MAX_PENDING = 20


def default_redirect_uri() -> str:
    """Where Groww sends the browser after login. A deployed server (PUBLIC_BASE_URL set) is reached at its own
    address; a local run uses the loopback listener below, the address Groww's desktop flow is registered for."""
    base = public_base_url()
    return f"{base}/api/v1/portfolio/oauth/groww/callback" if base else LOCAL_REDIRECT


def _page(title: str, message: str, ok: bool) -> str:
    """The small result page shown after login. Everything dynamic is escaped: error text arrives in the URL."""
    colour, tint = ("#00d09c", "#ecfdf5") if ok else ("#b91c1c", "#fef2f2")
    mark = "&#10003;" if ok else "&#10005;"
    script = (
        "<script>if(window.opener){try{window.opener.postMessage('groww_authorized','*')}catch(e){}}"
        "setTimeout(function(){try{window.close()}catch(e){}},2500)</script>"
        if ok
        else ""
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>" + html.escape(title) + "</title></head>"
        "<body style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;display:flex;"
        f"align-items:center;justify-content:center;height:80vh;background:{tint}\">"
        "<div style='background:white;padding:40px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.08);"
        "text-align:center;max-width:480px'>"
        f"<div style='font-size:28px;font-weight:bold;color:{colour}'>{mark}</div>"
        f"<h2 style='color:{colour};margin:8px 0'>{html.escape(title)}</h2>"
        f"<p style='color:#64748b;font-size:14px;line-height:1.5'>{html.escape(message)}</p>{script}</div></body></html>"
    )


async def complete_authorization(
    code: Optional[str], state: Optional[str], error: Optional[str] = None, error_description: Optional[str] = None
) -> Tuple[int, str]:
    """Finish a Groww login for either callback (the loopback listener or the app's own route).

    Only a login this server started is accepted: the state must name a client here and be one of its live,
    unexpired requests. Returns (HTTP status, page)."""
    if error:
        logger.warning("Groww authorization returned error: %s (%s)", error, error_description)
        return 400, _page("Groww authorization failed", f"{error}: {error_description or ''}. Close this tab and try again from WealthVault.", False)
    if not code:
        return 400, _page("Groww authorization failed", "No authorization code came back from Groww.", False)
    conn_key = state.split("::")[0] if state and "::" in state else ""
    client = GrowwMCPClient.find(conn_key) if conn_key else None
    if client is None or not client.owns_state(state):
        return 400, _page("This login link has expired", "Start the Groww connection again from WealthVault.", False)
    try:
        await client.exchange_code(code, state)
    except Exception as exc:
        logger.error("Groww token exchange failed for %s: %s", client.connection_id, exc)
        return 502, _page("Groww did not accept the login", "Close this tab and connect again from WealthVault.", False)
    if client.owner_id and client.connection_id:
        try:
            from datetime import datetime, timezone

            from core.models import BrokerStatus
            from storage.tables.repositories import BrokerConnectionRepository

            await BrokerConnectionRepository().update_status(
                owner_id=client.owner_id,
                connection_id=client.connection_id,
                status=BrokerStatus.CONNECTED,
                last_sync_time=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.warning("Could not update Groww connection status: %s", exc)
    return 200, _page("Groww connected", "Your WealthVault session is authenticated. Close this tab and sync to bring in your Groww holdings.", True)


class GrowwRegistrationError(RuntimeError):
    """Groww would not register a login client for this server's address, so no working login link can be made."""


class GrowwAuthRequiredError(Exception):
    """Raised when Groww session requires interactive OAuth authorization."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class GrowwMCPClient:
    """Persistent HTTP OAuth client for Groww MCP server, isolated per connection ID."""

    _instances: Dict[str, "GrowwMCPClient"] = {}
    _local_server: Optional[asyncio.Server] = None

    def __init__(
        self,
        server_url: str = "https://mcp.groww.in/mcp",
        token_endpoint: str = "https://api.groww.in/oauth2/v1/token",
        authorization_endpoint: str = "https://groww.in/oauth/authorize",
        registration_endpoint: str = "https://api.groww.in/oauth2/v1/register",
        connection_id: str = "conn_groww_live",
        owner_id: Optional[str] = None,
    ) -> None:
        self.server_url = server_url
        self.token_endpoint = token_endpoint
        self.authorization_endpoint = authorization_endpoint
        self.registration_endpoint = registration_endpoint
        self.connection_id = connection_id
        self.owner_id = owner_id
        safe_id = scoped_key(connection_id, owner_id, "conn_groww_live")
        self.client_key = safe_id
        self.tokens_file = data_dir() / f"groww_tokens_{safe_id}.json"

        # Backwards compatibility / single-user fallback
        if owner_id is None and (connection_id == "conn_groww_live" or "default" in connection_id) and not self.tokens_file.exists() and (data_dir() / "groww_tokens.json").exists():
            self.tokens_file = data_dir() / "groww_tokens.json"

        self.client_id: str = get_settings().GROWW_CLIENT_ID
        self.client_secret: str = get_settings().GROWW_CLIENT_SECRET
        # The authorization server only redirects to the address the client was registered with
        self.redirect_uri: str = default_redirect_uri()
        self.scope: str = ""

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: float = 0.0

        self._pending_verifier: Optional[str] = None
        self._pending_state: Optional[str] = None
        self._pending_verifiers: Dict[str, Dict[str, Any]] = {}
        self._last_link: Optional[Tuple[str, float, str]] = None  # (state, created, url)
        self._lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._request_counter: int = 0
        self._initialized: bool = False

        self._load_client_info()
        if public_base_url():  # a deployed host always wins over a saved local redirect
            self.redirect_uri = default_redirect_uri()
            # A client id is only good for the address it was registered with. One set in settings or a file says nothing
            # about this server's address, and using it sends Groww a login it rejects ("Invalid redirect URL").
            if self.client_id:
                logger.warning("Ignoring the configured Groww client id: it is not known to be registered for %s", self.redirect_uri)
            self.client_id, self.client_secret = "", ""
        self._apply_registered_client()
        self._load_tokens()

    @classmethod
    def get_instance(cls, connection_id: str = "conn_groww_live", owner_id: Optional[str] = None) -> "GrowwMCPClient":
        safe_id = scoped_key(connection_id, owner_id, "conn_groww_live")
        if safe_id not in cls._instances:
            cls._instances[safe_id] = GrowwMCPClient(connection_id=connection_id, owner_id=owner_id)
        return cls._instances[safe_id]

    @classmethod
    def find(cls, client_key: str) -> Optional["GrowwMCPClient"]:
        """The client that issued an OAuth state, or None. Never creates one."""
        return cls._instances.get(re.sub(r"[^a-zA-Z0-9_-]", "_", client_key or ""))

    @classmethod
    async def ensure_local_callback_server(cls, port: int = LOCAL_CALLBACK_PORT) -> None:
        """Listen on the loopback port Groww's desktop login redirects to. Only for a local run: a deployed server is
        reached at its own address, where the app's /oauth/groww/callback route takes the redirect."""
        if cls._local_server is not None or public_base_url():
            return
        reasons = {200: "OK", 400: "Bad Request", 404: "Not Found", 502: "Bad Gateway"}

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            status, body = 404, _page("Not found", "Nothing is served at this address.", False)
            try:
                line = (await asyncio.wait_for(reader.readline(), timeout=5.0)).decode("utf-8", errors="ignore").strip().split()
                if len(line) >= 2 and line[0].upper() == "GET":
                    parsed = urllib.parse.urlparse(line[1])
                    if parsed.path == "/oauth/callback":
                        q = urllib.parse.parse_qs(parsed.query)
                        status, body = await complete_authorization(
                            q.get("code", [None])[0], q.get("state", [None])[0], q.get("error", [None])[0], q.get("error_description", [None])[0]
                        )
            except Exception as exc:
                logger.debug("Error in Groww callback listener: %s", exc)
            try:
                data = body.encode("utf-8")
                writer.write(
                    (
                        f"HTTP/1.1 {status} {reasons.get(status, 'OK')}\r\nContent-Type: text/html; charset=utf-8\r\n"
                        "X-Content-Type-Options: nosniff\r\nCache-Control: no-store\r\nConnection: close\r\n"
                        f"Content-Length: {len(data)}\r\n\r\n"
                    ).encode("ascii")
                    + data
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        try:
            cls._local_server = await asyncio.start_server(handle, "127.0.0.1", port)
            logger.info("Groww local OAuth redirect listener started on 127.0.0.1:%d", port)
        except OSError as exc:
            # another WealthVault on this machine already holds the port, so Groww's redirect lands on that one
            logger.warning("Groww login redirect port %d is already in use (%s): connect Groww from the server that holds it", port, exc)

    @classmethod
    async def close_all(cls) -> None:
        if cls._local_server is not None:
            try:
                cls._local_server.close()
                await cls._local_server.wait_closed()
            except Exception as exc:
                logger.debug("Error closing Groww local server: %s", exc)
            cls._local_server = None

        for client in list(cls._instances.values()):
            try:
                await client.close()
            except Exception as exc:
                logger.debug("Error closing Groww client: %s", exc)

    def _load_client_info(self) -> None:
        client_file = data_dir() / "groww_client.json"
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
                    self.registration_endpoint = data.get("registration_endpoint", self.registration_endpoint)
            except Exception as exc:
                logger.warning("Could not load Groww client info: %s", exc)

    _registry_lock = asyncio.Lock()

    @staticmethod
    def _is_local_redirect(uri: str) -> bool:
        host = urllib.parse.urlparse(uri).hostname or ""
        return host in ("127.0.0.1", "localhost", "::1")

    @staticmethod
    def _registry_file() -> Path:
        return data_dir() / "groww_oauth_clients.json"

    def _read_registry(self) -> Dict[str, Any]:
        try:
            return json.loads(self._registry_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _apply_registered_client(self) -> None:
        """Use the client registered for exactly this redirect address.

        A loopback address (a local run) may also reuse a client registered for another loopback address: an installed
        app's login may come back on any local port (RFC 8252, 7.3), and Groww has accepted that. A public address never
        borrows another address's client, and an entry saved before the address was recorded with it is not trusted."""
        registry = self._read_registry()
        entry = registry.get(self.redirect_uri)
        if self._is_local_redirect(self.redirect_uri):
            entry = entry or next((e for k, e in registry.items() if k != "default" and self._is_local_redirect(k)), None) or registry.get("default")
        elif entry and entry.get("registered_for") != self.redirect_uri:
            entry = None
        if entry and entry.get("client_id"):
            self.client_id = entry["client_id"]
            self.client_secret = entry.get("client_secret", "")

    async def ensure_client(self) -> None:
        """Make sure an OAuth client exists for this redirect address, registering one via RFC 7591 if needed."""
        if self.client_id:
            return
        async with GrowwMCPClient._registry_lock:
            self._apply_registered_client()
            if self.client_id:
                return
            payload = {
                "client_name": "WealthVault",
                "redirect_uris": [self.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_basic",
            }
            if self.scope:
                payload["scope"] = self.scope

            async with self._get_http_session().post(self.registration_endpoint, json=payload) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400 or not isinstance(data, dict) or not data.get("client_id"):
                    detail = {k: v for k, v in data.items() if "secret" not in k} if isinstance(data, dict) else data
                    raise GrowwRegistrationError(f"Groww client registration failed ({resp.status}): {detail}")
            echoed = data.get("redirect_uris")
            logger.info(
                "Groww registration for %s returned client %s named %r with redirect addresses %s",
                self.redirect_uri, data["client_id"], data.get("client_name"), echoed,
            )
            # RFC 7591: the reply lists the addresses the client was registered with. One that leaves ours out cannot
            # complete a login here, so it is not saved and the reason is shown instead of a dead login link.
            if isinstance(echoed, list) and self.redirect_uri not in echoed:
                raise GrowwRegistrationError(
                    f"Groww registered client {data['client_id']} for {echoed}, not for this server's address {self.redirect_uri}"
                )
            registry = self._read_registry()
            client_info = {
                "client_id": data["client_id"],
                "client_secret": data.get("client_secret", ""),
                "registered_for": self.redirect_uri,
                "client_name": data.get("client_name"),
            }
            registry[self.redirect_uri] = client_info
            if self._is_local_redirect(self.redirect_uri):
                registry["default"] = client_info
            path = self._registry_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            logger.info("Registered a Groww OAuth client for %s (client_id=%s)", self.redirect_uri, data["client_id"])
            self._apply_registered_client()

    def _load_tokens(self) -> None:
        if self.tokens_file.exists():
            try:
                with open(self.tokens_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
                    self.expires_at = float(data.get("expires_at") or 0.0)
                    logger.info("Loaded Groww tokens for %s from disk (expires in %ds)", self.connection_id, max(0, int(self.expires_at - time.time())))
            except Exception as exc:
                logger.warning("Could not load Groww tokens for %s: %s", self.connection_id, exc)

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
            logger.info("Saved Groww tokens for %s to disk successfully.", self.connection_id)
        except Exception as exc:
            logger.warning("Failed to save Groww tokens for %s: %s", self.connection_id, exc)

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
        self._initialized = False
        try:
            if self.tokens_file.exists():
                self.tokens_file.unlink()
        except Exception as exc:
            logger.debug("Failed to unlink tokens file for %s: %s", self.connection_id, exc)

    def owns_state(self, state: Optional[str]) -> bool:
        """True when `state` is a login request this client issued and it has not expired."""
        entry = self._pending_verifiers.get(state or "")
        return bool(entry) and time.time() - entry["created_at"] <= PENDING_TTL_SECONDS

    def _prune_pending(self) -> None:
        now = time.time()
        for st in [k for k, v in self._pending_verifiers.items() if now - v["created_at"] > PENDING_TTL_SECONDS]:
            del self._pending_verifiers[st]
        while len(self._pending_verifiers) > MAX_PENDING:
            del self._pending_verifiers[min(self._pending_verifiers, key=lambda k: self._pending_verifiers[k]["created_at"])]

    def get_authorization_url(self) -> str:
        """OAuth 2.0 PKCE login link. Asking again within a few minutes returns the same link, so a page that
        re-checks status every minute does not pile up unused login requests."""
        self._prune_pending()
        if self._last_link:
            state, created, url = self._last_link
            if state in self._pending_verifiers and time.time() - created < LINK_REUSE_SECONDS and f"client_id={urllib.parse.quote(self.client_id)}&" in url:
                return url

        raw_verifier = os.urandom(32)
        code_verifier = base64.urlsafe_b64encode(raw_verifier).rstrip(b"=").decode("ascii")
        challenge_bytes = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")

        nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode("ascii")
        state = f"{self.client_key}::{nonce}"
        self._pending_verifier = code_verifier
        self._pending_state = state
        self._pending_verifiers[state] = {"verifier": code_verifier, "created_at": time.time()}

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        if self.scope:
            params["scope"] = self.scope

        auth_url = f"{self.authorization_endpoint}?{urllib.parse.urlencode(params)}"
        self._last_link = (state, time.time(), auth_url)
        logger.info("Generated Groww PKCE authorization link for %s", self.connection_id)

        try:
            loop = asyncio.get_running_loop()
            if self.__class__._local_server is None and not public_base_url():
                loop.create_task(self.__class__.ensure_local_callback_server(LOCAL_CALLBACK_PORT))
        except RuntimeError:
            pass

        return auth_url

    async def exchange_code(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens using HTTP Basic Auth or POST body."""
        http = self._get_http_session()
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        # the code is only worth exchanging for a login this client started and that is still live
        if not self.owns_state(state):
            raise RuntimeError("Groww login request is unknown or has expired")
        payload["code_verifier"] = self._pending_verifiers[state]["verifier"]

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json",
        }

        auth = None
        if self.client_id and self.client_secret:
            auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        elif self.client_id:
            payload["client_id"] = self.client_id

        try:
            async with http.post(self.token_endpoint, headers=headers, data=payload, auth=auth) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    err = data.get("error_description") or data.get("error") or str(data)
                    raise RuntimeError(f"Groww token exchange failed ({resp.status}): {err}")

                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token") or self.refresh_token
                expires_in = int(data.get("expires_in", 86400))
                self.expires_at = time.time() + expires_in
                self._initialized = False
                self._pending_verifiers.pop(state, None)  # a login link works once
                self._last_link = None
                self._save_tokens()
                logger.info("Successfully exchanged code for Groww tokens. Valid for %ds.", expires_in)
                return data
        except Exception as exc:
            logger.error("Groww token exchange error: %s", exc)
            raise

    async def refresh_access_token(self) -> bool:
        """Refresh expired access token using stored refresh token."""
        if not self.refresh_token:
            return False

        http = self._get_http_session()
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json",
        }

        auth = None
        if self.client_id and self.client_secret:
            auth = aiohttp.BasicAuth(self.client_id, self.client_secret)
        elif self.client_id:
            payload["client_id"] = self.client_id

        try:
            async with http.post(self.token_endpoint, headers=headers, data=payload, auth=auth) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 200 and "access_token" in data:
                    self.access_token = data["access_token"]
                    if "refresh_token" in data:
                        self.refresh_token = data["refresh_token"]
                    expires_in = int(data.get("expires_in") or 86400)
                    self.expires_at = time.time() + expires_in
                    self._initialized = False
                    self._save_tokens()
                    logger.info("Refreshed Groww access token successfully.")
                    return True
                logger.warning("Failed to refresh Groww token (%d): %s", resp.status, data)
                return False
        except Exception as exc:
            logger.warning("Groww token refresh exception: %s", exc)
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
        raise GrowwAuthRequiredError(
            "Groww authorization is required. Please authorize via the link.",
            auth_url=auth_url,
        )

    async def ensure_initialized(self) -> None:
        """Initialize MCP session with server if not already done."""
        if self._initialized:
            return
        token = await self.ensure_valid_token()
        http = self._get_http_session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "WealthVault/1.0.0",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        }
        init_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "WealthVault", "version": "1.0.0"},
            },
        }
        try:
            async with http.post(self.server_url, headers=headers, json=init_payload) as resp:
                pass
            notif_payload = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
            async with http.post(self.server_url, headers=headers, json=notif_payload) as resp:
                pass
            self._initialized = True
        except Exception as exc:
            logger.warning("Groww MCP initialization warning: %s", exc)

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invoke a Groww MCP tool via direct HTTP JSON-RPC 2.0 with Bearer auth."""
        token = await self.ensure_valid_token()
        await self.ensure_initialized()

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
                    logger.info("Groww 401 received. Attempting token refresh...")
                    refreshed = await self.refresh_access_token()
                    if refreshed:
                        self._initialized = False
                        await self.ensure_initialized()
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        async with http.post(self.server_url, headers=headers, json=payload) as retry_resp:
                            raw_text = await retry_resp.text()
                            content_type = retry_resp.headers.get("Content-Type", "")
                    else:
                        await self.ensure_client()
                        raise GrowwAuthRequiredError(
                            "Groww session expired. Please re-authorize.",
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
                        raise RuntimeError(f"Groww tool '{name}' failed: {text}")

                    try:
                        return json.loads(text)
                    except Exception:
                        return text
                elif "error" in data:
                    raise RuntimeError(f"Groww MCP error: {data['error']}")
                return data
        except (GrowwAuthRequiredError, RuntimeError):
            raise
        except Exception as exc:
            logger.error("Groww call_tool error (%s): %s", name, exc)
            raise

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all tools exposed by the Groww MCP server."""
        token = await self.ensure_valid_token()
        await self.ensure_initialized()
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
            "method": "tools/list",
            "params": {},
        }
        async with http.post(self.server_url, headers=headers, json=payload) as resp:
            raw_text = await resp.text()
            data = None
            if "data:" in raw_text:
                for line in raw_text.splitlines():
                    line = line.strip()
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            break
                        except Exception:
                            continue
            if data is None:
                data = json.loads(raw_text)
            result = data.get("result", {})
            return result.get("tools", [])

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None


def get_groww_mcp_client(connection_id: str = "conn_groww_live", owner_id: Optional[str] = None) -> GrowwMCPClient:
    """Retrieve persistent instance of GrowwMCPClient for the specified connection ID."""
    require_owner(owner_id)
    return GrowwMCPClient.get_instance(connection_id=connection_id, owner_id=owner_id)


async def login_link(client: "GrowwMCPClient") -> Tuple[Optional[str], Optional[str]]:
    """(login link, None), or (None, why no link can be made). Never raises: a broken Groww login must not take the
    Brokers page down with it."""
    try:
        await client.ensure_client()
        return client.get_authorization_url(), None
    except Exception as exc:
        logger.error("Groww login link could not be made for %s: %s", client.connection_id, exc)
        return None, f"Groww login can't be started: {exc}"
