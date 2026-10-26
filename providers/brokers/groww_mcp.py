"""Groww Broker Provider Implementation via Groww MCP.

Connects to the official Groww Model Context Protocol server (https://mcp.groww.in/mcp)
using OAuth2 PKCE flow, returning demat holdings and account status.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from core.market_data.groww_client import GrowwAuthRequiredError, get_groww_mcp_client, login_link
from providers.brokers.base import BrokerProvider

logger = logging.getLogger("wealthvault.providers.groww")

# columns asked for beyond the defaults; the parts of the net quantity are kept so it can be checked
HOLDING_COLUMNS = [
    "quantity",
    "average_price",
    "t1_quantity",
    "demat_free_quantity",
    "pledge_quantity",
    "demat_locked_quantity",
    "groww_locked_quantity",
    "title",
]


class GrowwMCPProvider(BrokerProvider):
    """Groww through its MCP server (OAuth PKCE). Works only where Groww allows the login to come back: a run on the
    same machine as the browser (localhost:52155), not a deployed server. The deployed site uses the Trade API provider."""

    def __init__(
        self,
        credentials: Optional[Dict[str, Any]] = None,
        server_url: str = "https://mcp.groww.in/mcp",
        timeout_seconds: float = 45.0,
        connection_id: str = "conn_groww_live",
        owner_id: Optional[str] = None,
    ) -> None:
        super().__init__(credentials)
        self.owner_id = owner_id
        self.server_url = server_url
        self.timeout = timeout_seconds
        self.connection_id = connection_id

    @property
    def client(self) -> Any:
        return get_groww_mcp_client(connection_id=self.connection_id, owner_id=self.owner_id)

    async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
        """Verify broker connection."""
        if credentials:
            self.credentials.update(credentials)
        status = await self.get_account_status()
        return status.get("status") == "success"

    async def get_account_status(self) -> Dict[str, Any]:
        """Fetch account and OAuth connection status."""
        client = self.client
        if client.is_authenticated():
            return {
                "status": "success",
                "profile": {
                    "broker": "GROWW",
                    "account_id": self.credentials.get("account_id", "GROWW_LIVE"),
                    "status": "active",
                },
            }

        auth_url, problem = await login_link(client)
        return {
            "status": "auth_required",
            "message": problem or "Groww OAuth authorization required",
            "auth_url": auth_url,
        }

    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Demat equity holdings (stocks, ETFs, SGBs) from Groww MCP.

        Groww's MCP has no mutual fund holdings: its get_mutualfund_details answers "GROWWMCP doesn't support mutual
        fund details", so mutual funds held on Groww cannot be imported. Prices in the reply are text such as
        '48.13 Thousands', so only quantities and average price are used; prices come from quote enrichment."""
        client = self.client
        try:
            raw = await client.call_tool("get_equity_portfolio_holdings", {"extra_cols": HOLDING_COLUMNS})
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raise RuntimeError(f"unexpected reply: {raw[:120]}")
            inner = raw.get("result", raw) if isinstance(raw, dict) else raw
            rows = inner.get("holdings") if isinstance(inner, dict) else inner
            # an error or notice reply must not turn into a fake holding, or wipe a real portfolio as "empty"
            if not isinstance(rows, list):
                raise RuntimeError(f"unexpected reply: {str(inner)[:120]}")
            return [r for r in rows if isinstance(r, dict)]
        except GrowwAuthRequiredError:
            raise
        except Exception as exc:
            logger.error("Groww live holdings retrieval failed: %s", exc)
            raise RuntimeError(f"Groww live MCP communication failure: {exc}") from exc

    async def get_transactions(self) -> List[Dict[str, Any]]:
        return []
