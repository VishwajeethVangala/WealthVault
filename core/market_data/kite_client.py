"""Persistent Kite Model Context Protocol (MCP) Client.

Maintains a long-running stdio bridge to https://mcp.kite.trade/mcp.
Prevents session recreation on every API request, preserves the active session_id,
and enables zero-latency calls for holdings, profile, and real-time market quotes.
"""

import asyncio
import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger("wealthvault.mcp.kite")

def _resolve_mcp_command(server_url: str) -> tuple[str, list[str]]:
    """Resolve mcp-remote executable or npx fallback."""
    remote_bin = (
        shutil.which("mcp-remote.cmd")
        or shutil.which("mcp-remote")
        or shutil.which("npx.cmd")
        or "npx"
    )
    if "mcp-remote" in remote_bin.lower():
        return remote_bin, [server_url]
    return remote_bin, ["-y", "mcp-remote", server_url]


def _extract_text_or_json(result: Any) -> Any:
    """Extract string or parsed JSON from CallToolResult."""
    if hasattr(result, "content") and result.content:
        for item in result.content:
            text = getattr(item, "text", None)
            if text:
                import json
                try:
                    return json.loads(text)
                except Exception:
                    return text
    return str(result) if result is not None else None


class KiteAuthRequiredError(Exception):
    """Raised when Kite MCP session requires daily interactive OAuth login."""

    def __init__(self, message: str, auth_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.auth_url = auth_url


class KiteMCPClient:
    """Singleton persistent client for Zerodha Kite MCP server."""

    _instance: Optional["KiteMCPClient"] = None

    def __init__(self, server_url: str = "https://mcp.kite.trade/mcp") -> None:
        self.server_url = server_url
        self.session: Optional[ClientSession] = None
        self._client_cm = None
        self._session_cm = None
        self._lock = asyncio.Lock()
        self.auth_url: Optional[str] = None
        self.session_id: Optional[str] = None
        self.is_authenticated: bool = False
        self._starting: bool = False

    @classmethod
    def get_instance(cls) -> "KiteMCPClient":
        if cls._instance is None:
            cls._instance = KiteMCPClient()
        return cls._instance

    async def ensure_connected(self) -> None:
        """Ensure the persistent stdio bridge to Kite MCP is active and initialized."""
        if self.session is not None:
            return

        async with self._lock:
            if self.session is not None:
                return

            logger.info("Initializing persistent Kite MCP bridge to %s...", self.server_url)
            cmd, args = _resolve_mcp_command(self.server_url)
            server_params = StdioServerParameters(
                command=cmd,
                args=args,
                env=dict(os.environ),
            )

            try:
                self._client_cm = stdio_client(server_params)
                read, write = await self._client_cm.__aenter__()
                self._session_cm = ClientSession(read, write)
                self.session = await self._session_cm.__aenter__()
                await self.session.initialize()
                logger.info("Persistent Kite MCP bridge established successfully.")

                # Probe login tool to capture persistent session_id and auth_url
                res = await self.session.call_tool("login", arguments={})
                text = _extract_text_or_json(res) or ""
                match = re.search(r"https?://mcp\.kite\.trade/authorize\S+", str(text))
                if match:
                    self.auth_url = match.group(0).rstrip(")")
                    m_id = re.search(r"session_id=([^%&]+)", self.auth_url)
                    self.session_id = m_id.group(1) if m_id else None
                    logger.info("Kite MCP persistent session_id: %s, auth_url: %s", self.session_id, self.auth_url)
            except Exception as exc:
                logger.error("Failed to start persistent Kite MCP bridge: %s", exc)
                await self.close()
                raise

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Invoke an MCP tool on the persistent session with auto-reconnect."""
        await self.ensure_connected()
        assert self.session is not None

        try:
            res = await self.session.call_tool(name, arguments=arguments or {})
            extracted = _extract_text_or_json(res)

            # Check if session needs login or failed authorization
            is_auth_error = False
            if isinstance(extracted, str):
                lower_str = extracted.lower()
                if "log in first" in lower_str or (
                    lower_str.startswith("failed to ") and ("execute" in lower_str or "get" in lower_str)
                ):
                    is_auth_error = True

            if hasattr(res, "is_error") and res.is_error:
                is_auth_error = True

            if is_auth_error:
                self.is_authenticated = False
                try:
                    login_res = await self.session.call_tool("login", arguments={})
                    login_text = _extract_text_or_json(login_res) or ""
                    match = re.search(r"https?://mcp\.kite\.trade/authorize\S+", str(login_text))
                    if match:
                        self.auth_url = match.group(0).rstrip(")")
                except Exception as login_err:
                    logger.debug("Failed to refresh login URL: %s", login_err)

                raise KiteAuthRequiredError(
                    f"Zerodha Kite MCP session requires daily login ({extracted}). Authorize at: {self.auth_url}",
                    auth_url=self.auth_url,
                )

            self.is_authenticated = True
            return extracted
        except KiteAuthRequiredError:
            raise
        except Exception as exc:
            logger.warning("Error during Kite MCP call_tool(%s): %s", name, exc)
            if "closed" in str(exc).lower() or "terminated" in str(exc).lower():
                await self.close()
            raise

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
        return data if isinstance(data, dict) else {}

    async def close(self) -> None:
        """Gracefully terminate persistent session and child process."""
        self.session = None
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None
        if self._client_cm:
            try:
                await self._client_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_cm = None
        logger.info("Persistent Kite MCP bridge closed.")


def get_kite_mcp_client() -> KiteMCPClient:
    """Retrieve global singleton instance of KiteMCPClient."""
    return KiteMCPClient.get_instance()
