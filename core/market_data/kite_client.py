"""Persistent OAuth 2.1 PKCE + Streamable HTTP MCP client for Zerodha Kite."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import logging
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx

from core.config import data_dir, public_base_url
from core.market_data.scope import require_owner, scoped_key

logger = logging.getLogger("wealthvault.mcp.kite")

KITE_MCP_URL = "https://mcp.kite.trade/mcp"
LOCAL_REDIRECT_URI = "http://127.0.0.1:8000/api/v1/portfolio/oauth/kite/callback"
_DEFAULT_AUTHORIZATION_ENDPOINT = "https://mcp.kite.trade/authorize"
_DEFAULT_TOKEN_ENDPOINT = "https://mcp.kite.trade/token"
_DEFAULT_REGISTRATION_ENDPOINT = "https://mcp.kite.trade/register"
_DEFAULT_SCOPE = "default"
_DEFAULT_TIMEOUT = 15.0

LINK_REUSE_SECONDS = 300.0
PENDING_TTL_SECONDS = 600.0
MAX_PENDING = 20
_METADATA_TTL_SECONDS = 3600.0
KITE_USER_AGENT = "WealthVault/1.0.0"

_RATE_LIMIT_PHRASES = ("rate limit", "too many requests", "429")
_EXPLICIT_LOGIN_PHRASES = (
    "log in first",
    "please log in",
    "login first",
    "using the login tool",
    "no bearer token",
    "missing bearer token",
    "invalid bearer token",
    "invalid_token",
    "invalid token",
    "token expired",
    "session expired",
    "kite session expired",
    "unauthorized",
    "unauthenticated",
)
_AMBIGUOUS_AUTH_PHRASES = ("session", "login", "expired", "401", "auth", "token", "enctoken", "api_key")
_SESSION_RETRY_PHRASES = ("invalid session id", "session not found", "missing session", "not initialized")


class KiteRateLimitError(RuntimeError):
    """Raised when Zerodha Kite MCP rejects a request due to rate limiting."""

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class KiteToolError(RuntimeError):
    """Kite answered and confirmed the login is alive, but this tool call failed."""


class KiteRegistrationError(RuntimeError):
    """Kite would not register an OAuth client for this server's redirect URI."""


class KiteAuthRequiredError(Exception):
    """Raised when Kite MCP session requires interactive OAuth 2.1 authorization."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class _TokenRejectedError(Exception):
    """Internal signal that the server rejected the current Bearer access token."""


def default_redirect_uri() -> str:
    """Return the OAuth callback URL for Kite based on PUBLIC_BASE_URL or loopback default."""
    base = public_base_url()
    return f"{base}/api/v1/portfolio/oauth/kite/callback" if base else LOCAL_REDIRECT_URI


def _oauth_clients_file() -> Path:
    return data_dir() / "kite_oauth_clients.json"


def _is_rate_limit_error(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _RATE_LIMIT_PHRASES)


def _is_explicit_login_error(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _EXPLICIT_LOGIN_PHRASES)


def _is_auth_error(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _AMBIGUOUS_AUTH_PHRASES)


def _is_session_reset_error(status_code: int, text: str) -> bool:
    if status_code not in (400, 404, 200):
        return False
    low = text.lower()
    return any(p in low for p in _SESSION_RETRY_PHRASES)


def _parse_mcp_response(resp: httpx.Response) -> Dict[str, Any]:
    """Parse a Streamable HTTP MCP response encoded as JSON or Server-Sent Events."""
    text = (resp.text or "").strip()
    if not text:
        return {}
    content_type = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type or text.startswith("event:") or text.startswith("data:"):
        parsed_events: List[Dict[str, Any]] = []
        data_lines: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.rstrip("\r")
            if not line:
                if data_lines:
                    payload_str = "\n".join(data_lines).strip()
                    data_lines.clear()
                    if payload_str and payload_str != "[DONE]":
                        try:
                            obj = json.loads(payload_str)
                            if isinstance(obj, dict):
                                parsed_events.append(obj)
                        except json.JSONDecodeError:
                            pass
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            payload_str = "\n".join(data_lines).strip()
            if payload_str and payload_str != "[DONE]":
                try:
                    obj = json.loads(payload_str)
                    if isinstance(obj, dict):
                        parsed_events.append(obj)
                except json.JSONDecodeError:
                    pass
        for event in reversed(parsed_events):
            if "result" in event or "error" in event:
                return event
        return parsed_events[-1] if parsed_events else {}
    return resp.json()


def _extract_error_text(result: Dict[str, Any], raw_data: Optional[Dict[str, Any]] = None) -> str:
    content = result.get("content") or []
    parts: List[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
    if parts:
        return " ".join(parts).strip()
    sc = result.get("structuredContent")
    if isinstance(sc, dict) and sc:
        return json.dumps(sc)
    if isinstance(raw_data, dict) and isinstance(raw_data.get("error"), dict):
        return str(raw_data["error"].get("message", raw_data["error"]))
    return "Unknown MCP tool error"


def _extract_tool_payload(result: Dict[str, Any]) -> Any:
    """Extract normalized JSON payload from structuredContent or text content blocks."""
    content = result.get("content") or []
    texts: List[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text") is not None:
                texts.append(str(block["text"]))
            elif isinstance(block, str):
                texts.append(block)

    structured = result.get("structuredContent")
    if isinstance(structured, (dict, list)) and (structured or not texts):
        return structured

    if not texts:
        return {}

    joined = "\n".join(texts).strip()
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]

    parsed_items: List[Any] = []
    for text in texts:
        try:
            parsed_items.append(json.loads(text))
        except json.JSONDecodeError:
            return joined
    if len(parsed_items) == 1:
        return parsed_items[0]
    return parsed_items


def _callback_page(title: str, message: str, ok: bool) -> str:
    """Render sanitized HTML response after Zerodha Kite OAuth callback."""
    colour, tint = ("#059669", "#ecfdf5") if ok else ("#b91c1c", "#fef2f2")
    mark = "&#10003;" if ok else "&#10005;"
    script = (
        "<script>if(window.opener){try{window.opener.postMessage('kite_authorized','*')}catch(e){}}"
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


async def complete_kite_authorization(
    code: Optional[str],
    state: Optional[str],
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> Tuple[int, str]:
    """Complete a Zerodha Kite OAuth 2.1 authorization code redirect and persist tokens."""
    if error:
        logger.warning("Kite authorization returned error: %s (%s)", error, error_description)
        detail = f"{error}: {error_description or ''}".strip(": ")
        return 400, _callback_page(
            "Zerodha Kite authorization failed",
            f"{detail}. Close this tab and try again from WealthVault.",
            False,
        )
    if not code:
        return 400, _callback_page(
            "Zerodha Kite authorization failed",
            "No authorization code came back from Zerodha Kite.",
            False,
        )

    client = KiteMCPClient.find_by_state(state)
    if client is None:
        return 400, _callback_page(
            "This Kite login link has expired",
            "Start the Zerodha Kite connection again from WealthVault.",
            False,
        )

    try:
        await client.exchange_code(code=code, state=state or "")
    except Exception as exc:
        logger.error("Kite token exchange failed for %s: %s", client.connection_id, exc)
        return 502, _callback_page(
            "Zerodha Kite did not accept the login",
            "Close this tab and connect again from WealthVault.",
            False,
        )

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
            logger.warning("Could not update Kite connection status: %s", exc)

    return 200, _callback_page(
        "Zerodha Kite connected",
        "Your WealthVault session is authenticated. Close this tab and sync to bring in your Zerodha holdings.",
        True,
    )


class KiteMCPClient:
    """Persistent OAuth 2.1 PKCE + Streamable HTTP client for Zerodha Kite MCP, isolated per tenant connection."""

    _instances: Dict[str, "KiteMCPClient"] = {}

    def __init__(
        self,
        mcp_url: str = KITE_MCP_URL,
        connection_id: str = "conn_zerodha_live",
        owner_id: Optional[str] = None,
    ) -> None:
        self.mcp_url = mcp_url
        base = mcp_url[:-4] if mcp_url.endswith("/mcp") else mcp_url.rstrip("/")
        self._metadata_url = f"{base}/.well-known/oauth-authorization-server"
        self._protected_resource_url = f"{base}/.well-known/oauth-protected-resource"
        self._resource = mcp_url

        self.connection_id = connection_id
        self.owner_id = owner_id
        safe_id = scoped_key(connection_id, owner_id, "conn_zerodha_live")
        self.client_key = safe_id
        self.session_file = data_dir() / f"kite_session_{safe_id}.json"
        if (
            owner_id is None
            and (connection_id == "conn_zerodha_live" or "default" in connection_id)
            and not self.session_file.exists()
            and (data_dir() / "kite_session.json").exists()
        ):
            self.session_file = data_dir() / "kite_session.json"

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[float] = None
        self.token_type: str = "Bearer"
        self.session_id: Optional[str] = None
        self.is_authenticated: bool = False
        self.auth_url: Optional[str] = None

        self._oauth_client_id: Optional[str] = None
        self._oauth_redirect_uri: Optional[str] = None
        self._pending_verifiers: Dict[str, Tuple[str, float, str]] = {}
        self._last_link: Optional[Tuple[str, float, str, str]] = None
        self._metadata_cache: Optional[Tuple[Dict[str, Any], float]] = None

        self._initialized: bool = False
        self._initialized_token: Optional[str] = None
        self._req_id: int = 0
        self._http: Optional[httpx.AsyncClient] = None

        self._auth_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()

        self._load_saved_session()

    @property
    def redirect_uri(self) -> str:
        """Current OAuth callback URI matching PUBLIC_BASE_URL or local default."""
        return default_redirect_uri()

    @classmethod
    def find(cls, client_key: str) -> Optional["KiteMCPClient"]:
        """Look up an active Kite client instance by scoped client key."""
        return cls._instances.get(client_key)

    @classmethod
    def find_by_state(cls, state: Optional[str]) -> Optional["KiteMCPClient"]:
        """Locate the client instance that issued an unexpired OAuth PKCE state."""
        if not state:
            return None
        for instance in list(cls._instances.values()):
            if instance.owns_state(state):
                return instance
        if "::" in state:
            candidate = cls._instances.get(state.split("::", 1)[0])
            if candidate and candidate.owns_state(state):
                return candidate
        return None

    def owns_state(self, state: Optional[str]) -> bool:
        """Return True when this client issued and still holds an unexpired verifier for state."""
        if not state or state not in self._pending_verifiers:
            return False
        _, created_at, _ = self._pending_verifiers[state]
        if time.time() - created_at > PENDING_TTL_SECONDS:
            self._pending_verifiers.pop(state, None)
            return False
        return True

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _get_http_session(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(_DEFAULT_TIMEOUT),
                follow_redirects=True,
                headers={"User-Agent": KITE_USER_AGENT},
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    @classmethod
    async def close_all(cls) -> None:
        for instance in list(cls._instances.values()):
            await instance.close()
        cls._instances.clear()

    def _load_saved_session(self) -> None:
        if not self.session_file.exists():
            return
        try:
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load saved Kite session for %s: %s", self.connection_id, exc)
            return

        access_token = data.get("access_token")
        # Legacy files stored mcp-session-id without an OAuth Bearer access_token.
        if not isinstance(access_token, str) or not access_token.strip():
            self.access_token = None
            self.refresh_token = None
            self.expires_at = None
            self.session_id = None
            self.is_authenticated = False
            logger.info(
                "Ignored legacy tokenless Kite session file for %s; OAuth 2.1 authorization required",
                self.connection_id,
            )
            return

        self.access_token = access_token.strip()
        refresh_token = data.get("refresh_token")
        self.refresh_token = refresh_token.strip() if isinstance(refresh_token, str) and refresh_token.strip() else None
        raw_exp = data.get("expires_at")
        self.expires_at = float(raw_exp) if isinstance(raw_exp, (int, float)) else None
        self.token_type = str(data.get("token_type") or "Bearer")
        self.session_id = data.get("session_id")
        self.is_authenticated = bool(data.get("is_authenticated", True))
        logger.info("Loaded persistent Kite OAuth session for %s (authenticated: %s)", self.connection_id, self.is_authenticated)

    def _save_session(self) -> None:
        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_id": self.session_id,
                "is_authenticated": self.is_authenticated,
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
                "token_type": self.token_type,
                "connection_id": self.connection_id,
                "owner_id": self.owner_id,
                "updated_at": time.time(),
            }
            self.session_file.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save Kite session for %s: %s", self.connection_id, exc)

    def _clear_auth_state(self, *, save: bool = True) -> None:
        had_state = bool(self.access_token or self.refresh_token or self.is_authenticated or self.session_id)
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.session_id = None
        self._initialized = False
        self._initialized_token = None
        self.is_authenticated = False
        if save and had_state:
            self._save_session()

    def _load_cached_oauth_client(self, redirect_uri: str) -> Optional[str]:
        if self._oauth_client_id and self._oauth_redirect_uri == redirect_uri:
            return self._oauth_client_id
        clients_path = _oauth_clients_file()
        if not clients_path.exists():
            return None
        try:
            data = json.loads(clients_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        entry = data.get(redirect_uri)
        if isinstance(entry, dict) and entry.get("redirect_uri") == redirect_uri and entry.get("client_id"):
            self._oauth_client_id = str(entry["client_id"])
            self._oauth_redirect_uri = redirect_uri
            return self._oauth_client_id
        return None

    def _save_cached_oauth_client(self, redirect_uri: str, client_id: str) -> None:
        clients_path = _oauth_clients_file()
        try:
            clients_path.parent.mkdir(parents=True, exist_ok=True)
            existing: Dict[str, Any] = {}
            if clients_path.exists():
                try:
                    loaded = json.loads(clients_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        existing = loaded
                except Exception:
                    existing = {}
            existing[redirect_uri] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "registered_at": time.time(),
            }
            clients_path.write_text(json.dumps(existing), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to cache Kite OAuth client registration: %s", exc)

    async def _discover_oauth_endpoints(self) -> Dict[str, Any]:
        """Discover Kite OAuth 2.1 endpoints with fallback to published production metadata."""
        now = time.time()
        if self._metadata_cache and (now - self._metadata_cache[1]) < _METADATA_TTL_SECONDS:
            return self._metadata_cache[0]

        endpoints: Dict[str, Any] = {
            "authorization_endpoint": _DEFAULT_AUTHORIZATION_ENDPOINT,
            "token_endpoint": _DEFAULT_TOKEN_ENDPOINT,
            "registration_endpoint": _DEFAULT_REGISTRATION_ENDPOINT,
            "scope": _DEFAULT_SCOPE,
            "resource": self._resource,
        }
        http = self._get_http_session()
        try:
            res_meta = await http.get(self._protected_resource_url, headers={"Accept": "application/json"})
            if res_meta.status_code == 200:
                pr = res_meta.json()
                if isinstance(pr, dict):
                    if pr.get("resource"):
                        endpoints["resource"] = str(pr["resource"])
                    scopes = pr.get("scopes_supported")
                    if isinstance(scopes, list) and scopes:
                        endpoints["scope"] = str(scopes[0])
        except Exception as exc:
            logger.debug("Using fallback Kite protected-resource metadata: %s", exc)

        try:
            auth_meta = await http.get(self._metadata_url, headers={"Accept": "application/json"})
            if auth_meta.status_code == 200:
                meta = auth_meta.json()
                if isinstance(meta, dict):
                    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
                        if meta.get(key):
                            endpoints[key] = str(meta[key])
        except Exception as exc:
            logger.debug("Using fallback Kite authorization-server metadata: %s", exc)

        self._metadata_cache = (endpoints, now)
        return endpoints

    async def ensure_client(self) -> str:
        """Ensure an RFC 7591 public OAuth client ID is registered for the active redirect URI."""
        target_redirect = self.redirect_uri
        cached = self._load_cached_oauth_client(target_redirect)
        if cached:
            return cached

        async with self._auth_lock:
            target_redirect = self.redirect_uri
            cached = self._load_cached_oauth_client(target_redirect)
            if cached:
                return cached

            endpoints = await self._discover_oauth_endpoints()
            reg_url = endpoints["registration_endpoint"]
            payload = {
                "client_name": "WealthVault",
                "redirect_uris": [target_redirect],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            }
            http = self._get_http_session()
            try:
                resp = await http.post(
                    reg_url,
                    json=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            except Exception as exc:
                raise KiteRegistrationError(f"Could not contact Kite OAuth registration endpoint: {exc}") from exc

            if resp.status_code not in (200, 201):
                raise KiteRegistrationError(
                    f"Kite OAuth client registration failed ({resp.status_code}): {(resp.text or '')[:300]}"
                )
            try:
                body = resp.json()
            except Exception as exc:
                raise KiteRegistrationError(f"Kite OAuth registration returned invalid JSON: {exc}") from exc

            client_id = body.get("client_id") if isinstance(body, dict) else None
            if not client_id:
                raise KiteRegistrationError("Kite OAuth registration response did not include client_id")

            self._oauth_client_id = str(client_id)
            self._oauth_redirect_uri = target_redirect
            self._save_cached_oauth_client(target_redirect, self._oauth_client_id)
            return self._oauth_client_id

    def get_authorization_url(self, force_new: bool = False) -> str:
        """Generate (or reuse within 5 minutes) a PKCE S256 authorization URL for Zerodha Kite."""
        target_redirect = self.redirect_uri
        client_id = self._load_cached_oauth_client(target_redirect)
        if not client_id:
            raise KiteRegistrationError("Kite OAuth client is not registered yet; await ensure_client() first")

        now = time.time()
        # Evict expired verifiers and cap memory at MAX_PENDING.
        self._pending_verifiers = {
            k: v for k, v in self._pending_verifiers.items() if now - v[1] <= PENDING_TTL_SECONDS
        }
        if (
            not force_new
            and self._last_link is not None
            and (now - self._last_link[1]) < LINK_REUSE_SECONDS
            and self._last_link[2] in self._pending_verifiers
            and self._last_link[3] == target_redirect
        ):
            self.auth_url = self._last_link[0]
            return self.auth_url

        if len(self._pending_verifiers) >= MAX_PENDING:
            oldest = min(self._pending_verifiers.items(), key=lambda kv: kv[1][1])[0]
            self._pending_verifiers.pop(oldest, None)

        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        nonce = secrets.token_urlsafe(24)
        state = f"{self.client_key}::{nonce}"
        self._pending_verifiers[state] = (verifier, now, target_redirect)

        meta = self._metadata_cache[0] if self._metadata_cache else {}
        auth_endpoint = meta.get("authorization_endpoint", _DEFAULT_AUTHORIZATION_ENDPOINT)
        scope = meta.get("scope", _DEFAULT_SCOPE)
        resource = meta.get("resource", self._resource)

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": target_redirect,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": scope,
            "state": state,
            "resource": resource,
        }
        url = f"{auth_endpoint}?{urlencode(params)}"
        self.auth_url = url
        self._last_link = (url, now, state, target_redirect)
        return url

    async def _prepare_auth_url(self, *, force_new: bool = False) -> Optional[str]:
        """Ensure DCR client is ready and build a PKCE authorization URL without raising on setup hiccups."""
        try:
            await self.ensure_client()
            async with self._auth_lock:
                return self.get_authorization_url(force_new=force_new)
        except Exception as exc:
            logger.warning("Could not prepare Kite authorization URL for %s: %s", self.connection_id, exc)
            return self.auth_url

    async def exchange_code(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange an OAuth authorization code and PKCE verifier for a Bearer access token."""
        entry = self._pending_verifiers.pop(state, None)
        if not entry:
            raise ValueError("Invalid or unknown OAuth state for Kite login")
        verifier, created_at, redirect_uri = entry
        if time.time() - created_at > PENDING_TTL_SECONDS:
            raise ValueError("Kite login link expired before authorization completed")
        self._last_link = None

        client_id = self._load_cached_oauth_client(redirect_uri) or await self.ensure_client()
        endpoints = await self._discover_oauth_endpoints()
        token_url = endpoints["token_endpoint"]
        resource = endpoints.get("resource", self._resource)

        form = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "resource": resource,
        }
        http = self._get_http_session()
        resp = await http.post(
            token_url,
            data=form,
            headers={"Accept": "application/json", "User-Agent": KITE_USER_AGENT},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Kite token endpoint returned {resp.status_code}: {(resp.text or '')[:300]}")

        data = resp.json()
        access_token = data.get("access_token") if isinstance(data, dict) else None
        if not access_token:
            raise RuntimeError("Kite token response did not include an access_token")

        self.access_token = str(access_token)
        refresh_token = data.get("refresh_token")
        self.refresh_token = str(refresh_token) if refresh_token else None
        expires_in = data.get("expires_in")
        self.expires_at = time.time() + float(expires_in) if isinstance(expires_in, (int, float)) else None
        self.token_type = str(data.get("token_type") or "Bearer")
        self.is_authenticated = True
        self.auth_url = None
        self.session_id = None
        self._initialized = False
        self._initialized_token = None
        self._save_session()

        try:
            await self.ensure_initialized(self.access_token)
        except Exception as exc:
            logger.warning("Kite token stored, deferred MCP initialize note: %s", exc)
        return data

    async def refresh_access_token(self) -> Optional[str]:
        """Attempt an OAuth 2.1 refresh_token grant if Kite issued a refresh token."""
        async with self._refresh_lock:
            if not self.refresh_token:
                return None
            redirect_uri = self._oauth_redirect_uri or self.redirect_uri
            client_id = self._load_cached_oauth_client(redirect_uri) or await self.ensure_client()
            endpoints = await self._discover_oauth_endpoints()
            token_url = endpoints["token_endpoint"]
            resource = endpoints.get("resource", self._resource)

            http = self._get_http_session()
            try:
                resp = await http.post(
                    token_url,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "refresh_token": self.refresh_token,
                        "resource": resource,
                    },
                    headers={"Accept": "application/json", "User-Agent": KITE_USER_AGENT},
                )
            except Exception as exc:
                logger.warning("Kite token refresh failed for %s: %s", self.connection_id, exc)
                return None

            if resp.status_code != 200:
                if resp.status_code in (400, 401, 403):
                    self._clear_auth_state(save=True)
                return None

            try:
                data = resp.json()
            except Exception:
                return None
            new_access = data.get("access_token") if isinstance(data, dict) else None
            if not new_access:
                return None

            self.access_token = str(new_access)
            if data.get("refresh_token"):
                self.refresh_token = str(data["refresh_token"])
            expires_in = data.get("expires_in")
            if isinstance(expires_in, (int, float)):
                self.expires_at = time.time() + float(expires_in)
            self.is_authenticated = True
            self.session_id = None
            self._initialized = False
            self._initialized_token = None
            self._save_session()
            return self.access_token

    async def get_valid_access_token(self) -> Optional[str]:
        """Return a usable Bearer token, refreshing beforehand if close to expiry."""
        if not self.access_token:
            return None
        if self.expires_at is not None and time.time() >= (self.expires_at - 60.0):
            if self.refresh_token:
                refreshed = await self.refresh_access_token()
                if refreshed:
                    return refreshed
            if time.time() >= self.expires_at:
                self._clear_auth_state(save=True)
                return None
        return self.access_token

    async def _raise_auth_required(self, reason: str, *, clear_tokens: bool = True, force_new_link: bool = False) -> None:
        if clear_tokens:
            self._clear_auth_state(save=True)
        auth_url = await self._prepare_auth_url(force_new=force_new_link)
        raise KiteAuthRequiredError(f"{reason} Please authorize at: {auth_url}", auth_url=auth_url)

    async def ensure_initialized(self, access_token: Optional[str] = None) -> None:
        """Perform the MCP initialize handshake using the Bearer OAuth access token."""
        token = access_token or self.access_token
        if not token:
            await self._raise_auth_required("Zerodha Kite session is not authenticated.")

        token_rejected = False
        rate_limit_msg: Optional[str] = None

        async with self._init_lock:
            if self._initialized and self._initialized_token == token:
                return

            http = self._get_http_session()
            init_headers = {
                "Authorization": f"{self.token_type} {token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": KITE_USER_AGENT,
            }
            init_payload = {
                "jsonrpc": "2.0",
                "id": self._next_req_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "WealthVault", "version": "1.0.0"},
                },
            }
            resp = await http.post(self.mcp_url, headers=init_headers, json=init_payload)

            if resp.status_code in (401, 403):
                token_rejected = True
            elif resp.status_code == 429:
                rate_limit_msg = "Kite MCP HTTP 429 rate limit during initialize"
            elif resp.status_code >= 400:
                raise RuntimeError(f"Kite MCP initialize failed ({resp.status_code}): {(resp.text or '')[:200]}")
            else:
                session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
                session_changed = bool(session_id and session_id != self.session_id)
                if session_id:
                    self.session_id = session_id
                self._initialized = True
                self._initialized_token = token
                if session_changed:
                    self._save_session()

                notif_headers = dict(init_headers)
                if self.session_id:
                    notif_headers["mcp-session-id"] = self.session_id
                try:
                    await http.post(
                        self.mcp_url,
                        headers=notif_headers,
                        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    )
                except Exception:
                    pass

        if rate_limit_msg:
            raise KiteRateLimitError(rate_limit_msg)
        if token_rejected:
            raise _TokenRejectedError()

    async def ensure_connected(self) -> None:
        """Ensure an active Bearer MCP session or prepare an OAuth 2.1 login URL."""
        token = await self.get_valid_access_token()
        if token:
            try:
                await self.ensure_initialized(token)
                return
            except _TokenRejectedError:
                if self.refresh_token:
                    new_tok = await self.refresh_access_token()
                    if new_tok:
                        try:
                            await self.ensure_initialized(new_tok)
                            return
                        except _TokenRejectedError:
                            pass
                self._clear_auth_state(save=True)
        await self._prepare_auth_url()

    async def reset_session(self) -> str:
        """Clear local Kite tokens and persisted session state without outbound network calls."""
        self._clear_auth_state(save=False)
        self.auth_url = None
        self._last_link = None
        self._pending_verifiers.clear()
        try:
            if self.session_file.exists():
                self.session_file.unlink()
        except Exception:
            pass
        return ""

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        _retry_session_errors: bool = True,
        _confirm: bool = True,
    ) -> Any:
        """Execute an MCP tool call on https://mcp.kite.trade/mcp with OAuth 2.1 Bearer authentication."""
        token = await self.get_valid_access_token()
        if not token:
            await self._raise_auth_required("Zerodha Kite session expired.")

        try:
            await self.ensure_initialized(token)
        except _TokenRejectedError:
            if _retry_session_errors and self.refresh_token:
                new_tok = await self.refresh_access_token()
                if new_tok:
                    return await self.call_tool(
                        name,
                        arguments=arguments,
                        _retry_session_errors=False,
                        _confirm=_confirm,
                    )
            await self._raise_auth_required("Zerodha Kite Bearer token rejected during handshake.")

        http = self._get_http_session()
        headers = {
            "Authorization": f"{self.token_type} {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": KITE_USER_AGENT,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_req_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }

        resp = await http.post(self.mcp_url, headers=headers, json=payload)

        if resp.status_code == 429:
            raise KiteRateLimitError("Kite MCP HTTP 429 rate limit")

        if resp.status_code in (401, 403):
            logger.warning("Kite MCP rejected Bearer token (%s) on '%s'.", resp.status_code, name)
            if _retry_session_errors and self.refresh_token:
                new_tok = await self.refresh_access_token()
                if new_tok:
                    return await self.call_tool(
                        name,
                        arguments=arguments,
                        _retry_session_errors=False,
                        _confirm=_confirm,
                    )
            await self._raise_auth_required("Zerodha Kite session expired.")

        if _is_session_reset_error(resp.status_code, resp.text or "") and _retry_session_errors:
            logger.info("Kite MCP transport session reset (%s); re-initializing...", resp.status_code)
            self.session_id = None
            self._initialized = False
            self._initialized_token = None
            return await self.call_tool(
                name,
                arguments=arguments,
                _retry_session_errors=False,
                _confirm=_confirm,
            )

        if resp.status_code >= 400:
            raise RuntimeError(f"Kite MCP HTTP {resp.status_code}: {(resp.text or '')[:300]}")

        data = _parse_mcp_response(resp)

        if "error" in data:
            err_msg = str(data["error"].get("message", data["error"])) if isinstance(data["error"], dict) else str(data["error"])
            if _is_rate_limit_error(err_msg):
                raise KiteRateLimitError(err_msg)
            if _is_session_reset_error(200, err_msg) and _retry_session_errors:
                self.session_id = None
                self._initialized = False
                self._initialized_token = None
                return await self.call_tool(
                    name,
                    arguments=arguments,
                    _retry_session_errors=False,
                    _confirm=_confirm,
                )
            if _is_auth_error(err_msg):
                await self._raise_auth_required(f"Kite session error: {err_msg}")
            raise KiteToolError(f"MCP error calling {name}: {err_msg}")

        result = data.get("result", {}) if isinstance(data, dict) else {}
        if isinstance(result, dict) and result.get("isError"):
            err_msg = _extract_error_text(result, data if isinstance(data, dict) else None)
            if _is_rate_limit_error(err_msg):
                raise KiteRateLimitError(err_msg)

            is_profile_probe = (name == "portfolio" and (arguments or {}).get("mode") == "profile") or name == "get_profile"

            if not _is_explicit_login_error(err_msg) and self.is_authenticated and _confirm and not is_profile_probe:
                try:
                    probe = await self.call_tool("portfolio", {"mode": "profile"}, _confirm=False)
                except KiteAuthRequiredError:
                    raise
                except Exception:
                    probe = None
                if isinstance(probe, dict) and probe:
                    raise KiteToolError(f"Kite could not complete '{name}' (the login is live): {err_msg}")

            if _is_explicit_login_error(err_msg) or _is_auth_error(err_msg) or not _confirm or is_profile_probe:
                await self._raise_auth_required(f"Kite session expired ({err_msg}).")

            raise KiteToolError(f"Kite could not complete '{name}': {err_msg}")

        return _extract_tool_payload(result if isinstance(result, dict) else {})

    async def get_profile(self) -> Dict[str, Any]:
        """Fetch the authenticated Zerodha Kite profile using grouped portfolio(mode='profile')."""
        res = await self.call_tool("portfolio", {"mode": "profile"})
        if isinstance(res, dict):
            inner = res.get("data")
            if isinstance(inner, dict):
                return inner
            return res
        return {}

    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Fetch all Zerodha demat holdings with full details across paginated pages."""
        all_holdings: List[Dict[str, Any]] = []
        offset = 0
        limit = 500
        for _page in range(50):
            res = await self.call_tool(
                "portfolio",
                {"mode": "holdings", "type": "full", "from": offset, "limit": limit},
            )
            if isinstance(res, list):
                all_holdings.extend([h for h in res if isinstance(h, dict)])
                break
            if isinstance(res, dict):
                page_items = res.get("data")
                if page_items is None:
                    page_items = res.get("holdings")
                if isinstance(page_items, list):
                    all_holdings.extend([h for h in page_items if isinstance(h, dict)])
                pagination = res.get("pagination") if isinstance(res.get("pagination"), dict) else {}
                has_more = bool(pagination.get("has_more"))
                returned = pagination.get("returned")
                step = (
                    int(returned)
                    if isinstance(returned, int) and returned > 0
                    else (len(page_items) if isinstance(page_items, list) else 0)
                )
                if not has_more or step <= 0:
                    break
                offset += step
            else:
                break
        return all_holdings

    async def get_mf_holdings(self) -> List[Dict[str, Any]]:
        """Fetch Zerodha Coin mutual fund holdings using mutual_funds(mode='holdings')."""
        res = await self.call_tool("mutual_funds", {"mode": "holdings"})
        if isinstance(res, list):
            return [h for h in res if isinstance(h, dict)]
        if isinstance(res, dict):
            for key in ("data", "holdings"):
                items = res.get(key)
                if isinstance(items, list):
                    return [h for h in items if isinstance(h, dict)]
        return []

    async def _call_market_quotes(self, mode: str, instruments: List[str]) -> Dict[str, Any]:
        if not instruments:
            return {}
        merged: Dict[str, Any] = {}
        for i in range(0, len(instruments), 500):
            batch = instruments[i : i + 500]
            res = await self.call_tool("market", {"mode": mode, "instruments": batch})
            if isinstance(res, dict):
                payload = res["data"] if isinstance(res.get("data"), dict) else res
                merged.update(payload)
        return merged

    async def get_quotes(self, instruments: List[str]) -> Dict[str, Any]:
        """Fetch full market quote snapshots via market(mode='quote')."""
        return await self._call_market_quotes("quote", instruments)

    async def get_ltp(self, instruments: List[str]) -> Dict[str, Any]:
        """Fetch last traded prices via market(mode='ltp')."""
        return await self._call_market_quotes("ltp", instruments)

    async def search_instruments(self, query: str, filter_on: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search instruments via market(mode='search', verbosity='full')."""
        args: Dict[str, Any] = {
            "mode": "search",
            "query": query,
            "search_mode": "search",
            "verbosity": "full",
            "limit": 100,
        }
        if filter_on:
            args["filter_on"] = filter_on
        res = await self.call_tool("market", args)
        if isinstance(res, list):
            return [r for r in res if isinstance(r, dict)]
        if isinstance(res, dict) and isinstance(res.get("data"), list):
            return [r for r in res["data"] if isinstance(r, dict)]
        return []

    async def get_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str = "day",
    ) -> Any:
        """Fetch historical OHLC candles via market(mode='historical')."""
        args = {
            "mode": "historical",
            "instrument_token": int(instrument_token),
            "from_date": from_date,
            "to_date": to_date,
            "interval": interval,
        }
        return await self.call_tool("market", args)


def get_kite_mcp_client(connection_id: str = "conn_zerodha_live", owner_id: Optional[str] = None) -> KiteMCPClient:
    """Get or instantiate an isolated persistent KiteMCPClient for one signed-in user's connection."""
    require_owner(owner_id)
    key = scoped_key(connection_id, owner_id, "conn_zerodha_live")
    if key not in KiteMCPClient._instances:
        KiteMCPClient._instances[key] = KiteMCPClient(connection_id=connection_id, owner_id=owner_id)
    return KiteMCPClient._instances[key]
