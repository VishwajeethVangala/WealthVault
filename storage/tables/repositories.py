"""Domain repositories for Azure Table Storage.

Implements UserRepository and BrokerConnectionRepository with strict
multi-tenant partitioning:
- For BrokerConnectionRepository: PartitionKey MUST strictly be owner_id (user_id), RowKey is connection_id.
- For UserRepository: PartitionKey is user_id, RowKey is 'profile'.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple
import uuid

from azure.data.tables import UpdateMode
from core.models import AssetClass, BrokerConnection, BrokerStatus, Holding, PortfolioSnapshot, TargetAllocation, User
from core.agents.models import DirectiveCard, DirectiveStatus, TimelineEvent
from core.agents.ground.contracts import GroundStockDossier
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

    async def record_sign_in(self, user_id: str, client: Dict[str, str]) -> None:
        """Note how and when the person signed in, on their profile row (see core.client_info). The first_* fields are
        set once, the first time a sign-in is recorded, so for accounts that existed before this they mean "first seen"."""
        now = datetime.now(timezone.utc).isoformat()
        data = await self.get_entity(user_id=user_id, entity_id="profile") or {}
        fields: Dict[str, Any] = {
            "last_login_at": now,
            "last_platform": client.get("platform", ""),
            "last_app_version": client.get("app_version", ""),
            "last_device": client.get("device", ""),
            "last_user_agent": client.get("user_agent", ""),
            "login_count": int(data.get("login_count") or 0) + 1,
        }
        if not data.get("first_login_at"):
            fields.update(first_login_at=now, first_platform=client.get("platform", ""), first_app_version=client.get("app_version", ""))
        await self.upsert_entity(user_id=user_id, entity_id="profile", data=fields, mode="merge")


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
        account_id: Optional[str] = None,
        account_label: Optional[str] = None,
        status: BrokerStatus = BrokerStatus.CONNECTED,
    ) -> BrokerConnection:
        """Create a new broker connection enforcing PartitionKey == owner_id.

        Args:
            owner_id: User ID of tenant owner (PartitionKey).
            broker_name: Name/identifier of the broker platform.
            connection_id: Optional custom connection ID (RowKey), auto-generated if omitted.
            account_id: Optional broker account / client ID (e.g. SRK113).
            account_label: Optional user alias (e.g. 'Personal Demat', 'Family HUF').
            status: Initial connection status.

        Returns:
            The created BrokerConnection entity.
        """
        conn_id = connection_id or f"conn_{broker_name.lower().strip()}_{uuid.uuid4().hex[:6]}"
        connection = BrokerConnection(
            connection_id=conn_id,
            owner_id=owner_id,
            broker_name=broker_name.lower().strip(),
            account_id=account_id,
            account_label=account_label,
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
            account_id=data.get("account_id"),
            account_label=data.get("account_label"),
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
                        account_id=item.get("account_id"),
                        account_label=item.get("account_label"),
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
        account_id: Optional[str] = None,
        account_label: Optional[str] = None,
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
                account_id=account_id,
                account_label=account_label,
                status=status,
                last_sync_time=last_sync_time,
            )
        else:
            conn.status = status
            if last_sync_time is not None:
                conn.last_sync_time = last_sync_time
            if account_id is not None:
                conn.account_id = account_id
            if account_label is not None:
                conn.account_label = account_label

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
            if item.get("asset_class") == AssetClass.NPS.value:
                continue  # NPS is not tracked: rows stored before it was dropped stay out of every total
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
                        day_pnl=float(item["day_pnl"]) if item.get("day_pnl") is not None else None,
                        day_change_percentage=(
                            float(item["day_change_percentage"]) if item.get("day_change_percentage") is not None else None
                        ),
                        data_freshness=item.get("data_freshness") or "cached",
                        last_price_updated_at=item.get("last_price_updated_at"),
                        currency=item.get("currency", "INR"),
                    )
                )
            except Exception as exc:
                logger.warning("Error parsing holding record: %s", exc)
        return results

    async def delete_holding(self, owner_id: str, holding_id: str) -> bool:
        """Delete a holding entity within tenant partition."""
        return await self.delete_entity(user_id=owner_id, entity_id=holding_id)

    async def replace_holdings(self, owner_id: str, holdings: List[Holding]) -> int:
        """Make the stored holdings equal `holdings` without ever emptying the table first.

        New rows are written before anything is deleted, so a failure part-way leaves the old data
        plus whatever was written, never an empty or half-empty portfolio. Rows that are no longer
        present are deleted at the end.
        """
        existing_keys = {item["RowKey"] for item in await self.query_entities(user_id=owner_id)}
        upserted = await self.upsert_holdings(owner_id=owner_id, holdings=holdings) if holdings else 0
        keep = {sanitize_key(h.holding_id) for h in holdings}
        for key in existing_keys - keep:
            await self.delete_entity(user_id=owner_id, entity_id=key)
        return upserted

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

            # Exact match on connection_id takes priority to isolate multi-account holdings
            if item_conn == conn_clean:
                to_delete.append(item)
            # Legacy fallback only if connection_id was never populated on older holding records
            elif not item_conn and (
                broker_clean in item_row
                or item_row.startswith(f"hld_{tag_clean}")
                or (broker_clean == "zerodha" and item_row.startswith("hld_zk"))
                or (broker_clean == "indmoney" and item_row.startswith("hld_ind"))
            ):
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

            value = float(data["total_current_value"])
            invested = float(data["total_invested_value"])
            pnl = float(data["total_unrealized_pnl"])
            pnl_pct = float(data["total_pnl_percentage"])
            nps = float((alloc.pop(AssetClass.NPS.value, None) or {}).get("absolute_value", 0.0))
            if nps:
                # NPS is no longer tracked: take it out of snapshots stored while it was. Its cost basis was never
                # kept per class, so it is removed at the portfolio's own invested-to-value ratio that day.
                ratio = invested / value if value > 0 else 1.0
                value = max(round(value - nps, 2), 0.0)
                invested = max(round(invested - nps * ratio, 2), 0.0)
                pnl = round(value - invested, 2)
                pnl_pct = round(pnl / invested * 100.0, 2) if invested > 0 else 0.0
                for entry in alloc.values():
                    entry["percentage_weight"] = round(entry.get("absolute_value", 0.0) / value * 100.0, 2) if value > 0 else 0.0
            return PortfolioSnapshot(
                snapshot_id=data["snapshot_id"],
                owner_id=data["owner_id"],
                as_of_date=data["as_of_date"],
                calculation_version=data.get("calculation_version", "v1"),
                total_current_value=value,
                total_invested_value=invested,
                total_unrealized_pnl=pnl,
                total_pnl_percentage=pnl_pct,
                asset_allocation=alloc,
                holdings_count=int(data.get("holdings_count", 0)),
                created_at=data.get("created_at", ""),
            )
        except Exception as exc:
            logger.warning("Error parsing portfolio snapshot record: %s", exc)
            return None



class TargetAllocationRepository(BaseTableStorage):
    """Azure Table repository holding each user's target asset allocation.

    PartitionKey = owner_id
    RowKey = 'default'
    """

    ROW_KEY = "default"

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="targetallocations", connection_string=connection_string)

    async def get_targets(self, owner_id: str) -> TargetAllocation:
        """Return the user's saved targets, or an empty allocation if none were set."""
        data = await self.get_entity(user_id=owner_id, entity_id=self.ROW_KEY)
        if not data:
            return TargetAllocation(owner_id=owner_id)
        try:
            targets = json.loads(data.get("targets_json") or "{}")
        except ValueError:
            targets = {}
        return TargetAllocation(
            owner_id=owner_id,
            targets={str(k): float(v) for k, v in targets.items()},
            updated_at=data.get("updated_at"),
        )

    async def save_targets(self, owner_id: str, targets: Dict[str, float]) -> TargetAllocation:
        """Replace the user's targets."""
        now_iso = datetime.now(timezone.utc).isoformat()
        await self.upsert_entity(
            user_id=owner_id,
            entity_id=self.ROW_KEY,
            data={"owner_id": owner_id, "targets_json": json.dumps(targets), "updated_at": now_iso},
            mode="replace",
        )
        return TargetAllocation(owner_id=owner_id, targets=targets, updated_at=now_iso)


class BrokerCredentialRepository(BaseTableStorage):
    """Azure Table repository holding encrypted broker credentials and cached session tokens.

    PartitionKey = owner_id
    RowKey = connection_id

    `secrets_enc` and `session_enc` are Fernet tokens (see core.credentials). `fields_set` is the
    plaintext list of credential field NAMES (never values) so the UI can show what is saved.
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="brokercredentials", connection_string=connection_string)

    async def save_credentials(self, owner_id: str, connection_id: str, secrets: Dict[str, str]) -> List[str]:
        """Encrypt and store credentials (replacing any previous ones and clearing the cached session)."""
        from core.credentials import encrypt_json

        clean = {k: v.strip() for k, v in secrets.items() if isinstance(v, str) and v.strip()}
        await self.upsert_entity(
            user_id=owner_id,
            entity_id=connection_id,
            data={
                "owner_id": owner_id,
                "connection_id": connection_id,
                "secrets_enc": encrypt_json(clean),
                "session_enc": "",
                "fields_set": ",".join(sorted(clean)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            mode="replace",
        )
        return sorted(clean)

    async def get_credentials(self, owner_id: str, connection_id: str) -> Optional[Dict[str, str]]:
        """Return decrypted credentials, or None if none are stored."""
        from core.credentials import decrypt_json

        data = await self.get_entity(user_id=owner_id, entity_id=connection_id)
        if not data or not data.get("secrets_enc"):
            return None
        return decrypt_json(data["secrets_enc"])

    async def get_fields_set(self, owner_id: str, connection_id: str) -> List[str]:
        """Names of the credential fields that are saved (no values)."""
        data = await self.get_entity(user_id=owner_id, entity_id=connection_id, select=["fields_set"])
        raw = (data or {}).get("fields_set") or ""
        return [f for f in raw.split(",") if f]

    async def get_session(self, owner_id: str, connection_id: str) -> Optional[Dict[str, Any]]:
        """Return the cached decrypted session (tokens + expiry), or None."""
        from core.credentials import CredentialStoreError, decrypt_json

        data = await self.get_entity(user_id=owner_id, entity_id=connection_id, select=["session_enc"])
        if not data or not data.get("session_enc"):
            return None
        try:
            return decrypt_json(data["session_enc"])
        except CredentialStoreError:
            return None

    async def save_session(self, owner_id: str, connection_id: str, session: Dict[str, Any]) -> None:
        """Cache a broker session (tokens + expiry) alongside the credentials."""
        from core.credentials import encrypt_json

        await self.upsert_entity(
            user_id=owner_id,
            entity_id=connection_id,
            data={"session_enc": encrypt_json(session)},
            mode="merge",
        )

    async def delete_credentials(self, owner_id: str, connection_id: str) -> bool:
        return await self.delete_entity(user_id=owner_id, entity_id=connection_id)


class SymbolMapRepository(BaseTableStorage):
    """Azure Table cache mapping broker-specific instrument codes (e.g. INDmoney's INDS03339) to exchange symbols.

    PartitionKey = 'global' (the mapping is the same for every user)
    RowKey = broker instrument code
    `kite_id` is empty when the instrument could not be matched, so it is not searched again every sync.
    """

    PARTITION = "global"

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="symbolmap", connection_string=connection_string)

    async def get_all(self) -> Dict[str, Dict[str, str]]:
        rows = await self.query_entities(user_id=self.PARTITION)
        return {
            r["RowKey"]: {"kite_id": r.get("kite_id", ""), "resolved_at": r.get("resolved_at", "")}
            for r in rows
            if r.get("RowKey")
        }

    async def save(self, code: str, kite_id: str, name: str) -> None:
        await self.upsert_entity(
            user_id=self.PARTITION,
            entity_id=code,
            data={"kite_id": kite_id, "name": name, "resolved_at": datetime.now(timezone.utc).isoformat()},
            mode="replace",
        )


class SignalCacheRepository(BaseTableStorage):
    """Azure Table cache of per-stock analytics signals (momentum, swing, ATH breakout).

    PartitionKey = 'global' (signals depend only on the stock, not the user)
    RowKey = Kite instrument id, e.g. 'NSE:INFY'
    """

    PARTITION = "global"

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="signalcache", connection_string=connection_string)

    async def get_many(self, instrument_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        wanted = set(instrument_ids)
        out: Dict[str, Dict[str, Any]] = {}
        for r in await self.query_entities(user_id=self.PARTITION):
            if r.get("RowKey") in wanted:
                try:
                    row = json.loads(r.get("payload") or "{}")
                except ValueError:
                    continue
                row["computed_at"] = r.get("computed_at", "")
                out[r["RowKey"]] = row
        return out

    async def save(self, instrument_id: str, row: Dict[str, Any]) -> None:
        await self.upsert_entity(
            user_id=self.PARTITION,
            entity_id=instrument_id,
            data={"payload": json.dumps(row), "computed_at": datetime.now(timezone.utc).isoformat()},
            mode="replace",
        )


class UsCandleRepository(BaseTableStorage):
    """Azure Table store of daily US candles, one row per ticker per year plus a 'meta' row.

    PartitionKey = ticker (e.g. 'NVDA')
    RowKey = 'y2025' (candles for that year) or 'meta'
    Candles are [date, open, high, low, close, volume, source] with source 'i' (INDmoney) or 'y' (Yahoo backfill).
    """

    META = "meta"

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="uscandles", connection_string=connection_string)

    async def load(self, ticker: str) -> Tuple[List[List[Any]], Dict[str, Any]]:
        rows = await self.query_entities(user_id=ticker)
        candles: List[List[Any]] = []
        meta: Dict[str, Any] = {}
        for r in rows:
            key = r.get("RowKey", "")
            if key == self.META:
                try:
                    meta = json.loads(r.get("meta_json") or "{}")
                except ValueError:
                    meta = {}
            elif key.startswith("y"):
                try:
                    candles.extend(json.loads(r.get("candles_json") or "[]"))
                except ValueError:
                    continue
        candles.sort(key=lambda c: c[0])
        return candles, meta

    async def save_years(self, ticker: str, candles: List[List[Any]], years: Iterable[str], meta: Dict[str, Any]) -> None:
        by_year: Dict[str, List[List[Any]]] = {}
        for c in candles:
            by_year.setdefault(str(c[0])[:4], []).append(c)
        for y in years:
            await self.upsert_entity(
                user_id=ticker,
                entity_id=f"y{y}",
                data={"candles_json": json.dumps(by_year.get(y, []), separators=(",", ":"))},
                mode="replace",
            )
        await self.upsert_entity(user_id=ticker, entity_id=self.META, data={"meta_json": json.dumps(meta)}, mode="replace")

    async def clear(self, ticker: str) -> None:
        for r in await self.query_entities(user_id=ticker):
            await self.delete_entity(user_id=ticker, entity_id=r["RowKey"])


class IndiaCandleRepository(UsCandleRepository):
    """Same layout as UsCandleRepository for Indian stocks: PartitionKey = Kite instrument token (as text),
    RowKey = 'y2025' or 'meta'; candles carry source 'k' (Kite)."""

    def __init__(self, connection_string: Optional[str] = None) -> None:
        BaseTableStorage.__init__(self, table_name="incandles", connection_string=connection_string)


class ScreenerSnapshotRepository(BaseTableStorage):
    """Azure Table store of what a screener returned on each day, so changes between days can be shown.

    PartitionKey = screener slug
    RowKey = YYYY-MM-DD (UTC date of the fetch; a second fetch the same day replaces the first)
    The JSON is split across `part0..partN` properties because a table property holds at most ~32K characters.
    """

    CHUNK = 30000

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="screenersnapshots", connection_string=connection_string)

    async def save(self, slug: str, day: str, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, separators=(",", ":"))
        parts = {f"part{i}": text[i * self.CHUNK : (i + 1) * self.CHUNK] for i in range(max(1, -(-len(text) // self.CHUNK)))}
        await self.upsert_entity(user_id=slug, entity_id=day, data={"parts": len(parts), **parts}, mode="replace")

    @staticmethod
    def _decode(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            text = "".join(entity.get(f"part{i}", "") for i in range(int(entity.get("parts", 0))))
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    async def latest_two(self, slug: str) -> Tuple[Optional[Tuple[str, Dict[str, Any]]], Optional[Tuple[str, Dict[str, Any]]]]:
        """(most recent day, the day before it) as (date, payload) pairs; either may be None."""
        rows = sorted(await self.query_entities(user_id=slug), key=lambda r: r.get("RowKey", ""), reverse=True)
        out: List[Optional[Tuple[str, Dict[str, Any]]]] = []
        for r in rows[:2]:
            data = self._decode(r)
            out.append((r["RowKey"], data) if data is not None else None)
        while len(out) < 2:
            out.append(None)
        return out[0], out[1]


class FeedbackRepository(BaseTableStorage):
    """Messages people send from the "Send feedback" form.

    PartitionKey = owner_id (so an account deletion removes them)
    RowKey = '<UTC time>_<random>' so a partition lists oldest first
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="feedback", connection_string=connection_string)

    async def save_feedback(
        self,
        owner_id: str,
        category: str,
        message: str,
        platform: str,
        app_version: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        row_id = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
        data = {
            "id": row_id,
            "owner_id": owner_id,
            "email": email or "",
            "category": category,
            "message": message,
            "platform": platform,
            "app_version": app_version or "",
            "created_at": now.isoformat(),
            "status": "new",
        }
        await self.upsert_entity(user_id=owner_id, entity_id=row_id, data=data, mode="replace")
        return data

    async def list_feedback(self, owner_id: str) -> List[Dict[str, Any]]:
        rows = await self.query_entities(user_id=owner_id)
        keys = ("id", "category", "message", "platform", "app_version", "created_at", "status")
        return [{k: r.get(k) for k in keys} for r in sorted(rows, key=lambda r: r.get("RowKey", ""), reverse=True)]


# --- push notifications --------------------------------------------------------------------------------------


class DeviceTokenRepository(BaseTableStorage):
    """The phones signed in as a user, so a push goes to that user's phones only.

    PartitionKey = owner_id
    RowKey = first 40 hex characters of SHA-256 of the FCM token (tokens are long and may hold odd characters)
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="devicetokens", connection_string=connection_string)

    @staticmethod
    def _row(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:40]

    async def add(self, owner_id: str, token: str, platform: str = "android") -> None:
        await self.upsert_entity(
            user_id=owner_id,
            entity_id=self._row(token),
            data={"token": token, "platform": platform, "updated_at": datetime.now(timezone.utc).isoformat()},
            mode="replace",
        )

    async def remove(self, owner_id: str, token: str) -> bool:
        return await self.delete_entity(user_id=owner_id, entity_id=self._row(token))

    async def tokens(self, owner_id: str) -> List[str]:
        return [r["token"] for r in await self.query_entities(user_id=owner_id) if r.get("token")]

    async def owners(self) -> List[str]:
        """Every user with at least one registered phone (the table is small: one row per phone)."""
        client = await self.get_table_client()
        seen: set = set()
        async for e in client.list_entities(select=["PartitionKey"]):
            seen.add(e["PartitionKey"])
        return sorted(seen)


class NotificationPrefsRepository(BaseTableStorage):
    """Which kinds of notification a person wants. PartitionKey = owner_id, RowKey = 'prefs'."""

    KINDS = ("holdings_ath", "stage2_ath", "networth_daily", "networth_weekly", "us_stocks", "kite_login")

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="notifprefs", connection_string=connection_string)

    async def get(self, owner_id: str) -> Dict[str, bool]:
        row = await self.get_entity(user_id=owner_id, entity_id="prefs") or {}
        return {k: bool(row.get(k, True)) for k in self.KINDS}  # everything is on until switched off

    async def save(self, owner_id: str, prefs: Dict[str, bool]) -> Dict[str, bool]:
        clean = {k: bool(prefs.get(k, True)) for k in self.KINDS}
        await self.upsert_entity(user_id=owner_id, entity_id="prefs", data=clean, mode="replace")
        return clean


class NotificationRepository(BaseTableStorage):
    """What each notification says. The push itself carries only an id; the phone asks for the text, so names and
    amounts never pass through Google's push service.

    PartitionKey = owner_id (so an account deletion removes them)
    RowKey = '<UTC time>_<random>'
    """

    KEEP_DAYS = 14

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="notifications", connection_string=connection_string)

    async def create(self, owner_id: str, kind: str, title: str, body: str, body_masked: str, public_title: str, route: str, extra: str = "") -> str:
        now = datetime.now(timezone.utc)
        nid = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
        await self.upsert_entity(
            user_id=owner_id,
            entity_id=nid,
            data={
                "kind": kind, "title": title, "body": body, "body_masked": body_masked,
                "public_title": public_title, "route": route, "extra": extra, "created_at": now.isoformat(),
            },
            mode="replace",
        )
        cutoff = (now - timedelta(days=self.KEEP_DAYS)).strftime("%Y%m%dT%H%M%S")
        for r in await self.query_entities(user_id=owner_id, filter_query=f"RowKey lt '{cutoff}'", select=["RowKey"]):
            await self.delete_entity(user_id=owner_id, entity_id=r["RowKey"])
        return nid

    async def get(self, owner_id: str, nid: str) -> Optional[Dict[str, Any]]:
        return await self.get_entity(user_id=owner_id, entity_id=nid)


class PushSentRepository(BaseTableStorage):
    """What has already been sent to a person, so a call or a summary is never repeated.

    PartitionKey = owner_id
    RowKey = a key such as 'h|2026-10-29|buy|NSE:RELIANCE' (see core/push/service.py)
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="pushsent", connection_string=connection_string)

    async def has(self, owner_id: str, key: str) -> bool:
        return await self.get_entity(user_id=owner_id, entity_id=key, select=["RowKey"]) is not None

    async def mark(self, owner_id: str, key: str, **fields: Any) -> None:
        data = {"sent_at": datetime.now(timezone.utc).isoformat(), "status": "sent"}
        data.update(fields)
        await self.upsert_entity(user_id=owner_id, entity_id=key, data=data, mode="replace")

    async def with_prefix(self, owner_id: str, prefix: str) -> List[Dict[str, Any]]:
        return await self.query_entities(user_id=owner_id, filter_query=f"RowKey ge '{prefix}' and RowKey lt '{prefix}~'")


class WatchlistRepository(BaseTableStorage):
    """User-tracked watchlist symbols (for momentum analysis, setups, and signals).

    PartitionKey = owner_id (so account deletion removes them)
    RowKey = normalized symbol, e.g. 'NSE:TATAMOTORS' or 'BSE:500209'
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="watchlist", connection_string=connection_string)

    async def add_item(
        self,
        owner_id: str,
        symbol: str,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        target_price: Optional[float] = None,
        price_when_added: Optional[float] = None,
    ) -> Dict[str, Any]:
        clean_sym = sanitize_key(symbol.strip().upper())
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "symbol": clean_sym,
            "name": name or clean_sym.split(":")[-1],
            "notes": notes or "",
            "target_price": float(target_price) if target_price is not None else None,
            "price_when_added": float(price_when_added) if price_when_added is not None else None,
            "added_at": now,
        }
        await self.upsert_entity(user_id=owner_id, entity_id=clean_sym, data=data, mode="merge")
        return data

    async def remove_item(self, owner_id: str, symbol: str) -> bool:
        clean_sym = sanitize_key(symbol.strip().upper())
        return await self.delete_entity(user_id=owner_id, entity_id=clean_sym)

    async def get_item(self, owner_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        clean_sym = sanitize_key(symbol.strip().upper())
        return await self.get_entity(user_id=owner_id, entity_id=clean_sym)

    async def list_items(self, owner_id: str) -> List[Dict[str, Any]]:
        rows = await self.query_entities(user_id=owner_id)
        keys = ("symbol", "name", "notes", "target_price", "price_when_added", "added_at")
        items = [{k: r.get(k) for k in keys} for r in rows]
        items.sort(key=lambda r: r.get("added_at") or "", reverse=True)
        return items


class BoardroomRepository(BaseTableStorage):
    """Azure Table repository managing Agent Boardroom directives and timeline events.

    Multi-tenant boundary:
    PartitionKey = owner_id (user_id)
    RowKey = 'dir_' + sanitize_key(directive_id) for directives
             'evt_' + sanitize_key(event_id) for timeline events
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="boardroom", connection_string=connection_string)

    async def upsert_directive(self, owner_id: str, directive: DirectiveCard) -> None:
        """Upsert a single DirectiveCard entity in Azure Table Storage with 100% fidelity.
        
        Enforces 1:1 holding deduplication and preserves user resolution status.
        """
        from core.agents.forensic_crawler import clean_symbol

        act = directive.actions[0] if directive.actions else None
        sym = clean_symbol(act.symbol).upper() if act else ""
        brk = (act.broker or "broker").lower() if act else ""
        act_type = (act.action.value if hasattr(act.action, "value") else str(act.action)).lower() if act else ""

        # Check existing directives for this holding to enforce 1:1 holding and preserve resolution
        existing_directives = await self.list_directives(owner_id=owner_id)
        for existing in existing_directives:
            e_act = existing.actions[0] if existing.actions else None
            e_sym = clean_symbol(e_act.symbol).upper() if e_act else ""
            e_brk = (e_act.broker or "broker").lower() if e_act else ""
            
            # Same directive ID or same (symbol, broker) holding
            is_same_holding = (sym and e_sym == sym and brk and e_brk == brk)
            is_same_id = (existing.directive_id == directive.directive_id)
            
            if is_same_id or is_same_holding:
                if existing.user_status != DirectiveStatus.PENDING_REVIEW:
                    directive.user_status = existing.user_status
                    directive.user_comment = existing.user_comment
                    directive.resolved_at = existing.resolved_at
                if is_same_holding and not is_same_id:
                    # Remove older duplicate card under a different canonical ID
                    await self.delete_directive(owner_id=owner_id, directive_id=existing.directive_id)

        row_key = sanitize_key(f"dir_{directive.directive_id}")
        data = {
            "entity_type": "directive",
            "directive_id": directive.directive_id,
            "title": directive.title,
            "symbol": sym,
            "broker": brk,
            "action": act_type,
            "priority": directive.priority.value if hasattr(directive.priority, "value") else str(directive.priority),
            "user_status": directive.user_status.value if hasattr(directive.user_status, "value") else str(directive.user_status),
            "timestamp": directive.timestamp,
            "resolved_at": directive.resolved_at or "",
            "user_comment": directive.user_comment or "",
            "payload": directive.model_dump_json(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.upsert_entity(user_id=owner_id, entity_id=row_key, data=data, mode="replace")

    async def batch_upsert_directives(self, owner_id: str, directives: List[DirectiveCard]) -> int:
        """Batch upsert directives for a user."""
        if not directives:
            return 0
        from core.agents.forensic_crawler import clean_symbol
        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)

        chunk_size = 100
        total_upserted = 0
        for i in range(0, len(directives), chunk_size):
            chunk = directives[i : i + chunk_size]
            batch_ops = []
            for d in chunk:
                act = d.actions[0] if d.actions else None
                sym = clean_symbol(act.symbol).upper() if act else ""
                brk = (act.broker or "broker").lower() if act else ""
                act_type = (act.action.value if hasattr(act.action, "value") else str(act.action)).lower() if act else ""
                row_key = sanitize_key(f"dir_{d.directive_id}")
                entity = {
                    "PartitionKey": sanitized_owner,
                    "RowKey": row_key,
                    "entity_type": "directive",
                    "directive_id": d.directive_id,
                    "title": d.title,
                    "symbol": sym,
                    "broker": brk,
                    "action": act_type,
                    "priority": d.priority.value if hasattr(d.priority, "value") else str(d.priority),
                    "user_status": d.user_status.value if hasattr(d.user_status, "value") else str(d.user_status),
                    "timestamp": d.timestamp,
                    "resolved_at": d.resolved_at or "",
                    "user_comment": d.user_comment or "",
                    "payload": d.model_dump_json(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                batch_ops.append(("upsert", entity, {"mode": UpdateMode.REPLACE}))

            try:
                await client.submit_transaction(batch_ops)
                total_upserted += len(chunk)
            except Exception as exc:
                logger.info("Batch directive upsert fallback to concurrent: %s", exc)
                tasks = [
                    self.upsert_entity(
                        user_id=owner_id,
                        entity_id=sanitize_key(f"dir_{d.directive_id}"),
                        data={
                            "entity_type": "directive",
                            "directive_id": d.directive_id,
                            "title": d.title,
                            "symbol": clean_symbol(d.actions[0].symbol).upper() if d.actions else "",
                            "broker": (d.actions[0].broker or "broker").lower() if d.actions else "",
                            "action": (d.actions[0].action.value if hasattr(d.actions[0].action, "value") else str(d.actions[0].action)).lower() if d.actions else "",
                            "priority": d.priority.value if hasattr(d.priority, "value") else str(d.priority),
                            "user_status": d.user_status.value if hasattr(d.user_status, "value") else str(d.user_status),
                            "timestamp": d.timestamp,
                            "resolved_at": d.resolved_at or "",
                            "user_comment": d.user_comment or "",
                            "payload": d.model_dump_json(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        mode="replace"
                    )
                    for d in chunk
                ]
                await asyncio.gather(*tasks)
                total_upserted += len(chunk)

        return total_upserted

    async def get_directive(self, owner_id: str, directive_id: str) -> Optional[DirectiveCard]:
        """Fetch a specific directive by directive_id."""
        row_key = sanitize_key(f"dir_{directive_id}")
        entity = await self.get_entity(user_id=owner_id, entity_id=row_key)
        if not entity:
            entity = await self.get_entity(user_id=owner_id, entity_id=sanitize_key(directive_id))
        if not entity:
            return None
        payload = entity.get("payload")
        if payload:
            try:
                return DirectiveCard.model_validate_json(payload)
            except Exception as exc:
                logger.warning("Failed to deserialize DirectiveCard %s: %s", directive_id, exc)
        return None

    async def list_directives(self, owner_id: str, status: Optional[DirectiveStatus] = None) -> List[DirectiveCard]:
        """List all directives for an owner, optionally filtered by status, newest first."""
        filter_expr = "entity_type eq 'directive'"
        if status:
            st_val = status.value if hasattr(status, "value") else str(status)
            filter_expr += f" and user_status eq '{st_val}'"
        entities = await self.query_entities(user_id=owner_id, filter_query=filter_expr)
        results: List[DirectiveCard] = []
        for e in entities:
            payload = e.get("payload")
            if payload:
                try:
                    results.append(DirectiveCard.model_validate_json(payload))
                except Exception as exc:
                    logger.debug("Skipping unparseable directive %s: %s", e.get("RowKey"), exc)
        results.sort(key=lambda d: d.timestamp, reverse=True)
        return results

    async def delete_directive(self, owner_id: str, directive_id: str) -> bool:
        """Delete a directive entity by directive_id."""
        row_key = sanitize_key(f"dir_{directive_id}")
        return await self.delete_entity(user_id=owner_id, entity_id=row_key)

    async def clear_all_directives(self, owner_id: str) -> int:
        """Purge all directive entities for the specified user partition.
        
        Mandated for Phase 3 (The Boss) and fresh audit runs to ensure clean
        in-place execution with zero stale directives or leftover history.
        """
        filter_expr = "entity_type eq 'directive'"
        entities = await self.query_entities(user_id=owner_id, filter_query=filter_expr)
        if not entities:
            return 0
        tasks = [
            self.delete_entity(user_id=owner_id, entity_id=e["RowKey"])
            for e in entities if e.get("RowKey")
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        deleted = sum(1 for r in results if r is True)
        logger.info("Cleared %d directive entities from Azure Table for user %s", deleted, owner_id)
        return deleted

    async def update_directive_status(
        self,
        owner_id: str,
        directive_id: str,
        new_status: DirectiveStatus,
        user_comment: Optional[str] = None
    ) -> Optional[DirectiveCard]:
        """Update a directive's status and add a user action timeline event."""
        directive = await self.get_directive(owner_id=owner_id, directive_id=directive_id)
        if not directive:
            return None
        directive.user_status = new_status
        directive.user_comment = user_comment
        directive.resolved_at = datetime.now(timezone.utc).isoformat()
        await self.upsert_directive(owner_id=owner_id, directive=directive)

        # Log timeline event
        event = TimelineEvent(
            event_id=f"evt_user_{int(datetime.now(timezone.utc).timestamp())}",
            agent_id="user",
            agent_name="Investor (You)",
            event_type="USER_ACTION",
            message=f"Marked directive '{directive.title}' as {new_status.value}. {user_comment or ''}".strip(),
            directive_id=directive_id
        )
        await self.add_timeline_event(owner_id=owner_id, event=event)
        return directive

    async def add_timeline_event(self, owner_id: str, event: TimelineEvent) -> None:
        """Add an event to the public debate timeline."""
        row_key = sanitize_key(f"evt_{event.event_id}")
        data = {
            "entity_type": "timeline",
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "agent_id": event.agent_id,
            "agent_name": event.agent_name,
            "event_type": event.event_type,
            "message": event.message,
            "directive_id": event.directive_id or "",
            "payload": event.model_dump_json(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.upsert_entity(user_id=owner_id, entity_id=row_key, data=data, mode="replace")

    async def batch_add_timeline_events(self, owner_id: str, events: List[TimelineEvent]) -> int:
        """Batch add timeline events."""
        if not events:
            return 0
        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)

        chunk_size = 100
        total_upserted = 0
        for i in range(0, len(events), chunk_size):
            chunk = events[i : i + chunk_size]
            batch_ops = []
            for ev in chunk:
                row_key = sanitize_key(f"evt_{ev.event_id}")
                entity = {
                    "PartitionKey": sanitized_owner,
                    "RowKey": row_key,
                    "entity_type": "timeline",
                    "event_id": ev.event_id,
                    "timestamp": ev.timestamp,
                    "agent_id": ev.agent_id,
                    "agent_name": ev.agent_name,
                    "event_type": ev.event_type,
                    "message": ev.message,
                    "directive_id": ev.directive_id or "",
                    "payload": ev.model_dump_json(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                batch_ops.append(("upsert", entity, {"mode": UpdateMode.REPLACE}))

            try:
                await client.submit_transaction(batch_ops)
                total_upserted += len(chunk)
            except Exception as exc:
                logger.info("Batch timeline event upsert fallback to concurrent: %s", exc)
                tasks = [self.add_timeline_event(owner_id, ev) for ev in chunk]
                await asyncio.gather(*tasks)
                total_upserted += len(chunk)

        return total_upserted

    async def get_timeline(self, owner_id: str, limit: int = 100) -> List[TimelineEvent]:
        """Fetch debate timeline events for an owner, newest first."""
        entities = await self.query_entities(user_id=owner_id, filter_query="entity_type eq 'timeline'")
        events: List[TimelineEvent] = []
        for e in entities:
            payload = e.get("payload")
            if payload:
                try:
                    events.append(TimelineEvent.model_validate_json(payload))
                except Exception as exc:
                    logger.debug("Skipping unparseable timeline event %s: %s", e.get("RowKey"), exc)
        events.sort(key=lambda ev: ev.timestamp, reverse=True)
        return events[:limit]


class GroundDossiersRepository(BaseTableStorage):
    """Azure Table repository managing Ground-Level Scout Swarm dossiers.

    Multi-tenant boundary:
    PartitionKey = owner_id (user_id)
    RowKey = 'dos_' + sanitize_key(clean_symbol)
    """

    ALIASES = {
        "DIACABS": "DIAMONDYD",
        "DIAMONDYD": "DIACABS",
        "BBL": "BHARATBIJLEE",
        "BHARATBIJLEE": "BBL",
        "IND-SWIFT": "INDSWFTLAB",
        "INDSWFT": "INDSWFTLAB",
    }

    def __init__(self, connection_string: Optional[str] = None) -> None:
        super().__init__(table_name="grounddossiers", connection_string=connection_string)

    async def upsert_dossier(self, owner_id: str, dossier: GroundStockDossier) -> None:
        """Upsert a GroundStockDossier in Azure Table Storage with 100% fidelity."""
        from core.agents.forensic_crawler import clean_symbol
        clean = clean_symbol(dossier.symbol).upper()
        row_key = sanitize_key(f"dos_{clean}")

        barrier_st = dossier.barrier_status.value if hasattr(dossier.barrier_status, "value") else str(dossier.barrier_status)
        data = {
            "symbol": clean,
            "company_name": dossier.company_name,
            "barrier_status": barrier_st,
            "completed_scouts": len(dossier.completed_scouts),
            "is_etf": dossier.is_etf,
            "last_updated": dossier.last_updated or "",
            "payload": dossier.model_dump_json(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.upsert_entity(user_id=owner_id, entity_id=row_key, data=data, mode="replace")

    async def batch_upsert_dossiers(self, owner_id: str, dossiers: List[GroundStockDossier]) -> int:
        """Batch upsert GroundStockDossier entities for a user."""
        if not dossiers:
            return 0
        from core.agents.forensic_crawler import clean_symbol
        client = await self.get_table_client()
        sanitized_owner = sanitize_key(owner_id)

        chunk_size = 100
        total_upserted = 0
        for i in range(0, len(dossiers), chunk_size):
            chunk = dossiers[i : i + chunk_size]
            batch_ops = []
            for dos in chunk:
                clean = clean_symbol(dos.symbol).upper()
                row_key = sanitize_key(f"dos_{clean}")
                barrier_st = dos.barrier_status.value if hasattr(dos.barrier_status, "value") else str(dos.barrier_status)
                entity = {
                    "PartitionKey": sanitized_owner,
                    "RowKey": row_key,
                    "symbol": clean,
                    "company_name": dos.company_name,
                    "barrier_status": barrier_st,
                    "completed_scouts": len(dos.completed_scouts),
                    "is_etf": dos.is_etf,
                    "last_updated": dos.last_updated or "",
                    "payload": dos.model_dump_json(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                batch_ops.append(("upsert", entity, {"mode": UpdateMode.REPLACE}))

            try:
                await client.submit_transaction(batch_ops)
                total_upserted += len(chunk)
            except Exception as exc:
                logger.info("Batch dossiers upsert fallback to concurrent: %s", exc)
                tasks = [
                    self.upsert_entity(
                        user_id=owner_id,
                        entity_id=sanitize_key(f"dos_{clean_symbol(dos.symbol).upper()}"),
                        data={
                            "symbol": clean_symbol(dos.symbol).upper(),
                            "company_name": dos.company_name,
                            "barrier_status": dos.barrier_status.value if hasattr(dos.barrier_status, "value") else str(dos.barrier_status),
                            "completed_scouts": len(dos.completed_scouts),
                            "is_etf": dos.is_etf,
                            "last_updated": dos.last_updated or "",
                            "payload": dos.model_dump_json(),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        },
                        mode="replace"
                    )
                    for dos in chunk
                ]
                await asyncio.gather(*tasks)
                total_upserted += len(chunk)

        return total_upserted

    async def get_dossier(self, owner_id: str, symbol: str) -> Optional[GroundStockDossier]:
        """Fetch a specific ground dossier by symbol, supporting dual-listing aliases."""
        from core.agents.forensic_crawler import clean_symbol
        clean = clean_symbol(symbol).upper()
        row_key = sanitize_key(f"dos_{clean}")
        entity = await self.get_entity(user_id=owner_id, entity_id=row_key)
        if not entity and clean in self.ALIASES:
            alt_clean = self.ALIASES[clean]
            entity = await self.get_entity(user_id=owner_id, entity_id=sanitize_key(f"dos_{alt_clean}"))
        if not entity:
            return None
        payload = entity.get("payload")
        if payload:
            try:
                return GroundStockDossier.model_validate_json(payload)
            except Exception as exc:
                logger.warning("Failed to deserialize GroundStockDossier %s: %s", symbol, exc)
        return None

    async def list_dossiers(self, owner_id: str) -> List[GroundStockDossier]:
        """List all ground dossiers for an owner."""
        entities = await self.query_entities(user_id=owner_id)
        dossiers: List[GroundStockDossier] = []
        for e in entities:
            payload = e.get("payload")
            if payload:
                try:
                    dossiers.append(GroundStockDossier.model_validate_json(payload))
                except Exception as exc:
                    logger.debug("Skipping unparseable dossier %s: %s", e.get("RowKey"), exc)
        return dossiers

    async def delete_dossier(self, owner_id: str, symbol: str) -> bool:
        """Delete a specific ground dossier entity for in-place replacement."""
        from core.agents.forensic_crawler import clean_symbol
        clean = clean_symbol(symbol).upper()
        row_key = sanitize_key(f"dos_{clean}")
        return await self.delete_entity(user_id=owner_id, entity_id=row_key)

