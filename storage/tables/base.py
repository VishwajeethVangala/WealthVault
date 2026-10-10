"""Asynchronous Azure Table Storage abstraction.

Wraps azure.data.tables.aio.TableServiceClient and enforces strict multi-tenant isolation:
- PartitionKey is strictly reserved for user_id / owner_id (tenant boundary).
- RowKey represents the unique entity identifier.
- All query operations strictly scope to the calling user's partition.
- Uses native async clients with proper resource cleanup.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.data.tables import UpdateMode
from azure.data.tables.aio import TableClient, TableServiceClient

from core.config import get_settings
from core.security import sanitize_key

logger = logging.getLogger("wealthvault.storage.tables")


# Process-wide shared Azure clients. Repositories are created per request; giving each its own
# aiohttp-backed client leaked connections (never closed on most paths), which surfaced as
# "SSL shutdown timed out" errors when they were garbage collected, plus a create_table
# round-trip on every request.
_shared_service_clients: Dict[Tuple[str, int], TableServiceClient] = {}
_ready_tables: Set[Tuple[str, str]] = set()


def _loop_key() -> int:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


async def close_shared_table_clients() -> None:
    """Close all shared Azure Table clients (call on application shutdown)."""
    clients = list(_shared_service_clients.values())
    _shared_service_clients.clear()
    _ready_tables.clear()
    for client in clients:
        try:
            await client.close()
        except Exception as exc:
            logger.debug("Error closing shared table service client: %s", exc)


class BaseTableStorage:
    """Base asynchronous storage client for Azure Table Storage with multi-tenant enforcement."""

    def __init__(
        self,
        table_name: str,
        connection_string: Optional[str] = None,
    ) -> None:
        """Initialize BaseTableStorage.

        Args:
            table_name: Target Azure Table name.
            connection_string: Optional Azure Storage connection string.
                               Defaults to AZURE_STORAGE_CONNECTION_STRING from settings.
        """
        self.table_name = table_name
        self._connection_string = connection_string or get_settings().AZURE_STORAGE_CONNECTION_STRING
        self._service_client: Optional[TableServiceClient] = None
        self._table_client: Optional[TableClient] = None
        self._initialized = False

    @property
    def service_client(self) -> TableServiceClient:
        """Return lazily initialized TableServiceClient."""
        key = (self._connection_string, _loop_key())
        client = _shared_service_clients.get(key)
        if client is None:
            client = TableServiceClient.from_connection_string(conn_str=self._connection_string)
            _shared_service_clients[key] = client
        self._service_client = client
        return client

    async def get_table_client(self) -> TableClient:
        """Return initialized TableClient, creating table if it does not already exist."""
        if self._table_client is None:
            self._table_client = self.service_client.get_table_client(self.table_name)

        ready_key = (self._connection_string, self.table_name)
        if ready_key not in _ready_tables:
            try:
                await self._table_client.create_table()
                logger.info("Created table: %s", self.table_name)
            except HttpResponseError as exc:
                # 409 Conflict indicates the table already exists, which is expected
                if exc.status_code != 409:
                    raise
            _ready_tables.add(ready_key)

        return self._table_client

    async def upsert_entity(
        self,
        user_id: str,
        entity_id: str,
        data: Dict[str, Any],
        mode: Union[str, UpdateMode] = "merge",
    ) -> Dict[str, Any]:
        """Upsert an entity enforcing multi-tenant PartitionKey and RowKey isolation.

        Args:
            user_id: Multi-tenant boundary identifier (sets PartitionKey).
            entity_id: Unique entity identifier within the user partition (sets RowKey).
            data: Arbitrary entity fields to store.
            mode: Upsert mode: 'merge' (default) or 'replace'.

        Returns:
            The entity dictionary that was written.
        """
        valid_user_id = sanitize_key(user_id)
        valid_entity_id = sanitize_key(entity_id)

        update_mode = (
            UpdateMode.REPLACE
            if (isinstance(mode, str) and mode.lower() == "replace") or mode == UpdateMode.REPLACE
            else UpdateMode.MERGE
        )

        entity = dict(data)
        entity["PartitionKey"] = valid_user_id
        entity["RowKey"] = valid_entity_id

        client = await self.get_table_client()
        await client.upsert_entity(entity=entity, mode=update_mode)
        return entity

    async def get_entity(
        self,
        user_id: str,
        entity_id: str,
        select: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve an entity strictly by user_id partition and entity_id row key.

        Args:
            user_id: Tenant partition key.
            entity_id: Entity row key.
            select: Optional list of property names to return.

        Returns:
            Dictionary of entity properties if found, or None if not found.
        """
        valid_user_id = sanitize_key(user_id)
        valid_entity_id = sanitize_key(entity_id)

        client = await self.get_table_client()
        try:
            entity = await client.get_entity(
                partition_key=valid_user_id,
                row_key=valid_entity_id,
                select=select,
            )
            return dict(entity)
        except ResourceNotFoundError:
            return None

    async def query_entities(
        self,
        user_id: str,
        filter_query: Optional[str] = None,
        select: Optional[List[str]] = None,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query entities scoped exclusively to the given user's partition.

        Guarantees that callers cannot cross the multi-user tenant boundary.

        Args:
            user_id: Tenant partition key.
            filter_query: Optional additional OData filter expression.
            select: Optional list of property names to project.
            max_results: Optional limit on the number of results returned.

        Returns:
            List of entity dictionaries.
        """
        valid_user_id = sanitize_key(user_id)

        # Enforce PartitionKey restriction
        partition_filter = f"PartitionKey eq '{valid_user_id}'"
        if filter_query and filter_query.strip():
            composite_filter = f"({partition_filter}) and ({filter_query.strip()})"
        else:
            composite_filter = partition_filter

        client = await self.get_table_client()
        query_stream = client.query_entities(
            query_filter=composite_filter,
            select=select,
            results_per_page=max_results,
        )

        results: List[Dict[str, Any]] = []
        async for item in query_stream:
            results.append(dict(item))
            if max_results is not None and len(results) >= max_results:
                break

        return results

    async def delete_entity(self, user_id: str, entity_id: str) -> bool:
        """Delete an entity within the user's partition.

        Args:
            user_id: Tenant partition key.
            entity_id: Entity row key.

        Returns:
            True if deleted, False if entity did not exist.
        """
        valid_user_id = sanitize_key(user_id)
        valid_entity_id = sanitize_key(entity_id)

        client = await self.get_table_client()
        try:
            await client.delete_entity(
                partition_key=valid_user_id,
                row_key=valid_entity_id,
            )
            return True
        except ResourceNotFoundError:
            return False

    async def check_connection(self) -> bool:
        """Lightweight check to verify Azure Table Storage connectivity and credentials."""
        try:
            # Query table list lightly to verify connectivity
            tables = self.service_client.list_tables(results_per_page=1)
            async for _ in tables:
                break
            return True
        except Exception as exc:
            logger.error("Azure Table Storage health check failed: %s", exc, exc_info=True)
            return False

    async def close(self) -> None:
        """Detach from the shared Azure Table clients.

        The underlying connection pool is shared process-wide and is closed once on
        application shutdown (see close_shared_table_clients), so this only drops references.
        """
        self._table_client = None
        self._service_client = None

    async def __aenter__(self) -> "BaseTableStorage":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit with connection closure."""
        await self.close()
