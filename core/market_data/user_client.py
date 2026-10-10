"""Pick the Kite MCP client that should serve a user's market-data calls."""

from core.market_data.kite_client import KiteMCPClient, get_kite_mcp_client
from core.models import BrokerStatus
from storage.tables.repositories import BrokerConnectionRepository


async def get_user_kite_client(owner_id: str) -> KiteMCPClient:
    """Use the caller's own Zerodha connection, preferring one with a logged-in Kite session.

    Falls back to the default client when the user has no Zerodha connection.
    """
    connections = await BrokerConnectionRepository().list_connections(owner_id=owner_id)
    zerodha = [c for c in connections if c.broker_name.lower().strip() == "zerodha"]
    if not zerodha:
        return get_kite_mcp_client()
    clients = [(c, get_kite_mcp_client(c.connection_id)) for c in zerodha]
    for _, client in clients:
        if client.is_authenticated:
            return client
    preferred = next((c for c in zerodha if c.status == BrokerStatus.CONNECTED), zerodha[0])
    return get_kite_mcp_client(preferred.connection_id)
