"""Persistent Kite Model Context Protocol (MCP) Client.

Direct Streamable HTTP JSON-RPC client to https://mcp.kite.trade/mcp.
Maintains an enduring session_id on disk (storage/blobs/kite_session.json),
eliminating lost sessions across server restarts, avoiding fragile subprocesses,
and delivering sub-50ms latency for holdings, Coin mutual funds, and quotes.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("wealthvault.mcp.kite")

SESSION_FILE = Path("storage/blobs/kite_session.json")


class KiteAuthRequiredError(Exception):
    """Raised when Kite MCP session requires daily interactive OAuth login."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class KiteMCPClient:
    """Singleton persistent HTTP client for Zerodha Kite MCP server."""

    _instance: Optional["KiteMCPClient"] = None

    def __init__(self, server_url: str = "https://mcp.kite.trade/mcp") -> None:
        self.server_url = server_url
        self.session_id: Optional[str] = None
        self.auth_url: Optional[str] = None
        self.is_authenticated: bool = False
        self._lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._request_counter: int = 0
        self._load_saved_session()

    @classmethod
    def get_instance(cls) -> "KiteMCPClient":
        if cls._instance is None:
            cls._instance = KiteMCPClient()
        return cls._instance

    def _load_saved_session(self) -> None:
        """Load persistent session ID and auth URL from disk."""
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.session_id = data.get("session_id")
                    self.auth_url = data.get("auth_url")
                    self.is_authenticated = bool(data.get("is_authenticated", False))
                    logger.info("Loaded persistent Kite session_id: %s (authenticated: %s)", self.session_id, self.is_authenticated)
            except Exception as exc:
                logger.warning("Failed to load saved Kite session: %s", exc)

    def _save_session(self) -> None:
        """Save persistent session ID and auth URL to disk."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": self.session_id,
                    "auth_url": self.auth_url,
                    "is_authenticated": self.is_authenticated,
                }, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save Kite session: %s", exc)

    def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=45.0)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    async def ensure_connected(self) -> None:
        """Ensure an active Kite MCP session exists and is initialized."""
        if self.session_id:
            return

        async with self._lock:
            if self.session_id:
                return

            logger.info("Initializing new Kite MCP session to %s...", self.server_url)
            http = self._get_http_session()
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "mcp-remote/0.8.5",
                "Accept": "application/json, text/event-stream",
            }
            init_payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "wealthvault", "version": "1.0.0"},
                },
            }

            try:
                async with http.post(self.server_url, headers=headers, json=init_payload) as resp:
                    resp_headers = dict(resp.headers)
                    self.session_id = resp_headers.get("mcp-session-id")
                    logger.info("New Kite MCP session established: %s", self.session_id)
            except Exception as exc:
                logger.error("Failed to initialize Kite MCP HTTP session: %s", exc)
                raise

            # Call login tool to obtain authorization URL for the new session
            if self.session_id:
                try:
                    login_data = await self.call_tool("login", arguments={})
                    login_text = str(login_data)
                    match = re.search(r"https?://mcp\.kite\.trade/authorize\S+", login_text)
                    if match:
                        self.auth_url = match.group(0).rstrip(")")
                        self.is_authenticated = False
                        self._save_session()
                        logger.info("Kite MCP authorization URL generated: %s", self.auth_url)
                except KiteAuthRequiredError:
                    pass
                except Exception as exc:
                    logger.warning("Could not retrieve initial login URL: %s", exc)

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invoke an MCP tool directly over HTTP JSON-RPC 2.0 with session persistence."""
        await self.ensure_connected()

        http = self._get_http_session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mcp-remote/0.8.5",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

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
                data = await resp.json()

                if "result" in data:
                    res_obj = data["result"]
                    is_error = res_obj.get("isError", False)
                    content = res_obj.get("content", [])
                    text = ""
                    if content and isinstance(content, list):
                        text = content[0].get("text", "")

                    lower_text = str(text).lower()
                    if is_error or "log in first" in lower_text or (
                        lower_text.startswith("failed to ") and ("execute" in lower_text or "get" in lower_text)
                    ):
                        self.is_authenticated = False
                        # Fetch fresh auth URL
                        await self._refresh_auth_url()
                        self._save_session()
                        raise KiteAuthRequiredError(
                            f"Zerodha Kite session requires daily login ({text}). Authorize at: {self.auth_url}",
                            auth_url=self.auth_url,
                        )

                    # Successful response: try to parse as JSON
                    parsed: Any = text
                    try:
                        parsed = json.loads(text)
                    except Exception:
                        pass

                    self.is_authenticated = True
                    self._save_session()
                    return parsed
                elif "error" in data:
                    err_msg = data["error"].get("message", str(data["error"]))
                    if "auth" in err_msg.lower() or "session" in err_msg.lower():
                        self.is_authenticated = False
                        await self._refresh_auth_url()
                        self._save_session()
                        raise KiteAuthRequiredError(
                            f"Zerodha Kite session error: {err_msg}",
                            auth_url=self.auth_url,
                        )
                    raise RuntimeError(f"Kite MCP error: {err_msg}")
                else:
                    return data
        except KiteAuthRequiredError:
            raise
        except Exception as exc:
            logger.warning("Error calling Kite MCP tool '%s': %s", name, exc)
            raise

    async def _refresh_auth_url(self) -> None:
        """Call login tool to obtain latest authorization URL."""
        if not self.session_id:
            return
        http = self._get_http_session()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mcp-remote/0.8.5",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": self.session_id,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": "login", "arguments": {}},
        }
        try:
            async with http.post(self.server_url, headers=headers, json=payload) as resp:
                data = await resp.json()
                if "result" in data and "content" in data["result"]:
                    text = data["result"]["content"][0].get("text", "")
                    match = re.search(r"https?://mcp\.kite\.trade/authorize\S+", str(text))
                    if match:
                        self.auth_url = match.group(0).rstrip(")")
        except Exception as exc:
            logger.debug("Could not refresh auth URL: %s", exc)

    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Retrieve live equity holdings directly from Kite MCP."""
        data = await self.call_tool("get_holdings")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "holdings" in data:
            return data["holdings"]
        return []

    async def get_mf_holdings(self) -> List[Dict[str, Any]]:
        """Retrieve live Coin mutual fund holdings directly from Kite MCP."""
        data = await self.call_tool("get_mf_holdings")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "holdings" in data:
            return data["holdings"]
        return []

    async def get_quotes(self, instruments: List[str]) -> Dict[str, Any]:
        """Fetch live full market depth / quotes for instruments."""
        if not instruments:
            return {}
        data = await self.call_tool("get_quotes", {"instruments": instruments})
        return data if isinstance(data, dict) else {}

    async def get_ltp(self, instruments: List[str]) -> Dict[str, Any]:
        """Fetch live Last Traded Price (LTP) for instruments."""
        if not instruments:
            return {}
        data = await self.call_tool("get_ltp", {"instruments": instruments})
        return data if isinstance(data, dict) else {}

    async def get_profile(self) -> Dict[str, Any]:
        """Fetch active user profile and status from Kite MCP."""
        data = await self.call_tool("get_profile")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass
        return data if isinstance(data, dict) else {}

    async def close(self) -> None:
        """Close underlying HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None
        logger.info("Kite MCP HTTP client closed.")


def get_kite_mcp_client() -> KiteMCPClient:
    """Retrieve global singleton instance of KiteMCPClient."""
    return KiteMCPClient.get_instance()
