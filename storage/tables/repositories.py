"""Domain repositories for Azure Table Storage.

Implements UserRepository and BrokerConnectionRepository with strict
multi-tenant partitioning:
- For BrokerConnectionRepository: PartitionKey MUST strictly be owner_id (user_id), RowKey is connection_id.
- For UserRepository: PartitionKey is user_id, RowKey is 'profile'.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from azure.data.tables import UpdateMode
from core.models import AssetClass, BrokerConnection, BrokerStatus, Holding, PortfolioSnapshot, User
from core.security import sanitize_key
from storage.tables.base import BaseTableStorage

logger = logging.getLogger("wealthvault.storage.repositories")


class UserRepository(BaseTableStorage):
    """Azure Table repository managing User identities and profiles."""

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="users", connection_string=connection_string)

    async def get_user(self, user_id: str) -> Optional[User]:
        """Retrieve user profile by user_id.

        Args:
            user_id: Unique user identifier (PartitionKey).

        Returns:
            User model instance or None if not found.
        """
        data = await self.get_entity(user_id=user_id, entity_id="profile")
        if not data:
            return None
        return User(
            user_id=data["user_id"],
            email=data["email"],
            name=data["name"],
            created_at=data.get("created_at", ""),
            picture=data.get("picture"),
        )

    async def save_user(self, user: User) -> User:
        """Create or update a user profile.

        Args:
            user: User entity to persist.

        Returns:
            The persisted User entity.
        """
        payload = user.model_dump()
        await self.upsert_entity(
            user_id=user.user_id,
            entity_id="profile",
            data=payload,
            mode="merge",
        )
        return user


def _parse_broker_status(val: Any) -> BrokerStatus:
    """Safely parse BrokerStatus from string or enum."""
    if isinstance(val, BrokerStatus):
        return val
    clean_val = str(val).replace("BrokerStatus.", "").strip()
    return BrokerStatus(clean_val)


class BrokerConnectionRepository(BaseTableStorage):
    """Azure Table repository managing broker connections and sessions.

    Critical Security Invariant:
    PartitionKey MUST strictly be owner_id (user_id).
    RowKey is connection_id.
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="brokerconnections", connection_string=connection_string)

    async def create_connection(
        self,
        owner_id: str,
        broker_name: str,
        connection_id: Optional[str] = None,
        status: BrokerStatus = BrokerStatus.CONNECTED,
    ) -> BrokerConnection:
        """Create a new broker connection enforcing PartitionKey == owner_id.

        Args:
            owner_id: User ID of tenant owner (PartitionKey).
            broker_name: Name/identifier of the broker platform.
            connection_id: Optional custom connection ID (RowKey), auto-generated if omitted.
            status: Initial connection status.

        Returns:
            The created BrokerConnection entity.
        """
        conn_id = connection_id or f"conn_{uuid.uuid4().hex[:12]}"
        connection = BrokerConnection(
            connection_id=conn_id,
            owner_id=owner_id,
            broker_name=broker_name.lower().strip(),
            status=status,
            last_sync_time=None,
        )

        await self.upsert_entity(
            user_id=owner_id,
            entity_id=conn_id,
            data=connection.model_dump(mode="json"),
            mode="replace",
        )
        return connection

    async def get_connection(
        self,
        owner_id: str,
        connection_id: str,
    ) -> Optional[BrokerConnection]:
        """Fetch a specific broker connection enforcing tenant PartitionKey boundary.

        Args:
            owner_id: User ID of tenant owner.
            connection_id: Target connection ID.

        Returns:
            BrokerConnection if found, else None.
        """
        data = await self.get_entity(user_id=owner_id, entity_id=connection_id)
        if not data:
            return None
        return BrokerConnection(
            connection_id=data["connection_id"],
            owner_id=data["owner_id"],
            broker_name=data["broker_name"],
            status=_parse_broker_status(data["status"]),
            last_sync_time=data.get("last_sync_time"),
        )

    async def list_connections(self, owner_id: str) -> List[BrokerConnection]:
        """List all broker connections for the specified user partition.

        Strictly scoped to PartitionKey == owner_id.

        Args:
            owner_id: User ID of tenant owner.

        Returns:
            List of BrokerConnection entities owned by this user.
        """
        items = await self.query_entities(user_id=owner_id)
        connections: List[BrokerConnection] = []
        for item in items:
            if str(item.get("connection_id", "")).startswith("_meta"):
                continue
            try:
                connections.append(
                    BrokerConnection(
                        connection_id=item["connection_id"],
                        owner_id=item["owner_id"],
                        broker_name=item["broker_name"],
                        status=_parse_broker_status(item["status"]),
                        last_sync_time=item.get("last_sync_time"),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed broker connection record: %s", exc)
        return connections

    async def is_tenant_initialized(self, owner_id: str) -> bool:
        """Check if tenant has been initialized with default broker configuration."""
        data = await self.get_entity(user_id=owner_id, entity_id="_meta_initialized")
        return data is not None

    async def mark_tenant_initialized(self, owner_id: str) -> None:
        """Record tenant initialization marker in broker connections table."""
        await self.upsert_entity(
            user_id=owner_id,
            entity_id="_meta_initialized",
            data={
                "connection_id": "_meta_initialized",
                "owner_id": owner_id,
                "broker_name": "_meta",
                "status": "INITIALIZED",
                "initialized_at": datetime.now(timezone.utc).isoformat(),
            },
            mode="replace",
        )

    async def update_status(
        self,
        owner_id: str,
        connection_id: str,
        status: BrokerStatus,
        last_sync_time: Optional[str] = None,
    ) -> BrokerConnection:
        """Update connection status and last sync time, auto-creating if not found."""
        conn = await self.get_connection(owner_id=owner_id, connection_id=connection_id)
        if not conn:
            # Infer broker name from connection_id
            b_name = "zerodha" if "zerodha" in connection_id.lower() else "indmoney" if "indmoney" in connection_id.lower() else "broker"
            conn = BrokerConnection(
                connection_id=connection_id,
                owner_id=owner_id,
                broker_name=b_name,
                status=status,
                last_sync_time=last_sync_time,
            )
        else:
            conn.status = status
            if last_sync_time is not None:
                conn.last_sync_time = last_sync_time

        await self.upsert_entity(
            user_id=owner_id,
            entity_id=connection_id,
            data=conn.model_dump(mode="json"),
            mode="replace",
        )
        return conn

    async def delete_connection(self, owner_id: str, connection_id: str) -> bool:
        """Delete broker connection strictly within owner partition."""
        return await self.delete_entity(user_id=owner_id, entity_id=connection_id)


class HoldingsRepository(BaseTableStorage):
    """Azure Table repository managing canonical user portfolio holdings.

    PartitionKey = owner_id
    RowKey = holding_id
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="holdings", connection_string=connection_string)

    async def upsert_holdings(self, owner_id: str, holdings: List[Holding]) -> int:
        """Batch async upsert for canonical Holding records.

        Args:
            owner_id: User ID of tenant owner.
            holdings: List of canonical Holding entities to persist.

        Returns:
            Count of holdings successfully persisted.
        """
        if not holdings:
            return 0

        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)

        # Chunk holdings into batches of max 100 entities (Azure Table Transaction limit)
        total_upserted = 0
        chunk_size = 100

        for i in range(0, len(holdings), chunk_size):
            chunk = holdings[i : i + chunk_size]
            batch_ops = []
            for h in chunk:
                entity = h.model_dump(mode="json")
                entity["PartitionKey"] = sanitized_owner
                entity["RowKey"] = sanitize_key(h.holding_id)
                batch_ops.append(("upsert", entity, {"mode": UpdateMode.REPLACE}))

            try:
                await client.submit_transaction(batch_ops)
                total_upserted += len(chunk)
            except Exception as exc:
                logger.info("Batch transaction note (%s), executing concurrent upserts", exc)
                tasks = [
                    self.upsert_entity(
                        user_id=owner_id,
                        entity_id=h.holding_id,
                        data=h.model_dump(mode="json"),
                        mode="replace",
                    )
                    for h in chunk
                ]
                await asyncio.gather(*tasks)
                total_upserted += len(chunk)

        logger.info("Upserted %d holdings for user %s", total_upserted, owner_id)
        return total_upserted

    async def get_holdings(
        self,
        owner_id: str,
        asset_class: Optional[str] = None,
    ) -> List[Holding]:
        """Query all holdings for user, optionally filtered by asset class.

        Args:
            owner_id: User ID of tenant owner.
            asset_class: Optional filter by AssetClass enum value.

        Returns:
            List of canonical Holding objects.
        """
        filter_expr = f"asset_class eq '{asset_class.upper()}'" if asset_class else None
        items = await self.query_entities(user_id=owner_id, filter_query=filter_expr)
        results: List[Holding] = []
        for item in items:
            try:
                results.append(
                    Holding(
                        holding_id=item["holding_id"],
                        owner_id=item["owner_id"],
                        connection_id=item["connection_id"],
                        instrument_symbol=item["instrument_symbol"],
                        asset_class=AssetClass(item["asset_class"]),
                        quantity=float(item["quantity"]),
                        average_price=float(item["average_price"]),
                        current_value=float(item["current_value"]),
                        current_price=float(item["current_price"]) if item.get("current_price") is not None else None,
                        pnl=float(item["pnl"]) if item.get("pnl") is not None else None,
                        currency=item.get("currency", "INR"),
                    )
                )
            except Exception as exc:
                logger.warning("Error parsing holding record: %s", exc)
        return results

    async def delete_holding(self, owner_id: str, holding_id: str) -> bool:
        """Delete a holding entity within tenant partition."""
        return await self.delete_entity(user_id=owner_id, entity_id=holding_id)

    async def clear_holdings(self, owner_id: str) -> int:
        """Purge all holding entities for the given owner.
        
        Ensures idempotent re-sync by removing stale or duplicate records
        before freshly normalized holdings are written.
        """
        existing = await self.query_entities(user_id=owner_id)
        if not existing:
            return 0

        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)
        deleted_count = 0
        chunk_size = 100

        for i in range(0, len(existing), chunk_size):
            chunk = existing[i : i + chunk_size]
            batch_ops = []
            for item in chunk:
                batch_ops.append((
                    "delete",
                    {"PartitionKey": sanitized_owner, "RowKey": item["RowKey"]},
                ))

            try:
                await client.submit_transaction(batch_ops)
                deleted_count += len(chunk)
            except Exception as exc:
                logger.info("Batch delete transaction note (%s), deleting concurrently", exc)
                tasks = [
                    self.delete_entity(user_id=owner_id, entity_id=item["RowKey"])
                    for item in chunk
                ]
                await asyncio.gather(*tasks)
                deleted_count += len(chunk)

        logger.info("Cleared %d existing holdings for user %s", deleted_count, owner_id)
        return deleted_count

    async def delete_holdings_by_connection(
        self,
        owner_id: str,
        connection_id: str,
        broker_name: str,
    ) -> int:
        """Purge all holding entities belonging to a specific broker/connection.

        Args:
            owner_id: Tenant user ID.
            connection_id: Connection ID (e.g. conn_zerodha_live).
            broker_name: Name of broker platform (e.g. zerodha, indmoney).

        Returns:
            Number of holding entities deleted.
        """
        existing = await self.query_entities(user_id=owner_id)
        if not existing:
            return 0

        broker_clean = broker_name.lower().strip()
        conn_clean = connection_id.lower().strip()
        tag_clean = broker_clean[:3]

        to_delete = []
        for item in existing:
            item_conn = str(item.get("connection_id", "")).lower()
            item_row = str(item.get("RowKey", "")).lower()

            is_match = (
                item_conn == conn_clean
                or broker_clean in item_conn
                or item_row.startswith(f"hld_{tag_clean}")
                or (broker_clean == "zerodha" and (item_row.startswith("hld_zk") or "zerodha" in item_conn))
                or (broker_clean == "indmoney" and (item_row.startswith("hld_ind") or "indmoney" in item_conn))
            )
            if is_match:
                to_delete.append(item)

        if not to_delete:
            return 0

        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)
        deleted_count = 0
        chunk_size = 100

        for i in range(0, len(to_delete), chunk_size):
            chunk = to_delete[i : i + chunk_size]
            batch_ops = []
            for item in chunk:
                batch_ops.append((
                    "delete",
                    {"PartitionKey": sanitized_owner, "RowKey": item["RowKey"]},
                ))

            try:
                await client.submit_transaction(batch_ops)
                deleted_count += len(chunk)
            except Exception as exc:
                logger.info("Batch delete transaction note (%s), deleting concurrently", exc)
                tasks = [
                    self.delete_entity(user_id=owner_id, entity_id=item["RowKey"])
                    for item in chunk
                ]
                await asyncio.gather(*tasks)
                deleted_count += len(chunk)

        logger.info(
            "Purged %d holdings for broker %s (connection: %s, user: %s)",
            deleted_count,
            broker_clean,
            conn_clean,
            owner_id,
        )
        return deleted_count


class SnapshotsRepository(BaseTableStorage):
    """Azure Table repository managing historical daily portfolio snapshots.

    PartitionKey = owner_id
    RowKey = snapshot_{YYYY-MM-DD}
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="portfoliosnapshots", connection_string=connection_string)

    async def save_snapshot(self, snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
        """Persist a daily snapshot entity.

        Args:
            snapshot: The PortfolioSnapshot instance to store.

        Returns:
            The stored PortfolioSnapshot.
        """
        row_key = snapshot.snapshot_id
        if not row_key.startswith("snapshot_"):
            row_key = f"snapshot_{snapshot.as_of_date}"

        payload = snapshot.model_dump(mode="json")
        # Azure Tables cannot store nested dicts directly, serialize to JSON string
        payload["asset_allocation_json"] = json.dumps(payload.pop("asset_allocation", {}))

        await self.upsert_entity(
            user_id=snapshot.owner_id,
            entity_id=row_key,
            data=payload,
            mode="replace",
        )
        logger.info("Saved portfolio snapshot %s for user %s", row_key, snapshot.owner_id)
        return snapshot

    async def get_snapshot(self, owner_id: str, as_of_date: str) -> Optional[PortfolioSnapshot]:
        """Fetch snapshot for a specific date (YYYY-MM-DD)."""
        clean_date = as_of_date.replace("snapshot_", "").strip()
        row_key = f"snapshot_{clean_date}"
        data = await self.get_entity(user_id=owner_id, entity_id=row_key)
        if not data:
            return None
        return self._parse_snapshot(data)

    async def get_latest_snapshot(self, owner_id: str) -> Optional[PortfolioSnapshot]:
        """Retrieve the most recent portfolio snapshot for owner."""
        snapshots = await self.list_snapshots(owner_id=owner_id, limit=1)
        return snapshots[0] if snapshots else None

    async def list_snapshots(self, owner_id: str, limit: int = 30) -> List[PortfolioSnapshot]:
        """List historical snapshots sorted descending by date."""
        items = await self.query_entities(user_id=owner_id)
        parsed_list = []
        for item in items:
            parsed = self._parse_snapshot(item)
            if parsed:
                parsed_list.append(parsed)

        parsed_list.sort(key=lambda s: s.as_of_date, reverse=True)
        return parsed_list[:limit]

    def _parse_snapshot(self, data: Dict[str, Any]) -> Optional[PortfolioSnapshot]:
        """Parse raw table entity into canonical PortfolioSnapshot."""
        try:
            alloc_json = data.get("asset_allocation_json")
            if alloc_json:
                alloc = json.loads(alloc_json)
            else:
                alloc = data.get("asset_allocation", {})
                if isinstance(alloc, str):
                    alloc = json.loads(alloc)

            return PortfolioSnapshot(
                snapshot_id=data["snapshot_id"],
                owner_id=data["owner_id"],
                as_of_date=data["as_of_date"],
                calculation_version=data.get("calculation_version", "v1"),
                total_current_value=float(data["total_current_value"]),
                total_invested_value=float(data["total_invested_value"]),
                total_unrealized_pnl=float(data["total_unrealized_pnl"]),
                total_pnl_percentage=float(data["total_pnl_percentage"]),
                asset_allocation=alloc,
                holdings_count=int(data.get("holdings_count", 0)),
                created_at=data.get("created_at", ""),
            )
        except Exception as exc:
            logger.warning("Error parsing portfolio snapshot record: %s", exc)
            return None

