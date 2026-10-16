"""Erase everything WealthVault holds about one user.

Called from the in-app "Delete my account" action. Google Play requires apps with sign-in to offer this.
Market data that is the same for every user (prices, signals, the symbol map) is not personal and is kept.
"""

import logging
import re
from typing import Any, Dict

from core.config import data_dir
from core.market_data.indmoney_client import IndmoneyMCPClient
from core.market_data.kite_client import KiteMCPClient
from storage.blobs.archive import purge_owner_blobs
from storage.tables.repositories import (
    BrokerConnectionRepository,
    BrokerCredentialRepository,
    HoldingsRepository,
    SnapshotsRepository,
    TargetAllocationRepository,
    UserRepository,
)

logger = logging.getLogger("wealthvault.account_deletion")


def _prefix(owner_id: str) -> str:
    """Start of every client key and session file name that belongs to this user (see scope.scoped_key)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{owner_id}__")


async def _forget_broker_sessions(owner_id: str) -> int:
    """Close this user's live broker clients and delete their saved login files."""
    prefix = _prefix(owner_id)
    removed = 0
    for client_cls in (KiteMCPClient, IndmoneyMCPClient):
        for key in [k for k in client_cls._instances if k.startswith(prefix)]:
            client = client_cls._instances.pop(key)
            try:
                await client.close()
            except Exception as exc:
                logger.debug("Closing %s: %s", key, exc)
    folder = data_dir()
    if folder.exists():
        for path in folder.glob(f"*_{prefix}*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("Could not delete %s: %s", path.name, exc)
    return removed


async def delete_user_data(owner_id: str) -> Dict[str, Any]:
    """Delete the user's holdings, history, targets, broker connections, saved logins and profile.

    The profile goes last, so a failure part-way leaves the account able to sign in and try again.
    """
    removed: Dict[str, Any] = {}
    for label, repo in (
        ("holdings", HoldingsRepository()),
        ("snapshots", SnapshotsRepository()),
        ("targets", TargetAllocationRepository()),
        ("credentials", BrokerCredentialRepository()),
        ("connections", BrokerConnectionRepository()),
    ):
        try:
            removed[label] = await repo.delete_partition(owner_id)
        finally:
            await repo.close()
    removed["session_files"] = await _forget_broker_sessions(owner_id)
    try:
        removed["archived_payloads"] = await purge_owner_blobs(owner_id)
    except Exception as exc:
        logger.warning("Could not purge archived payloads for %s: %s", owner_id, exc)
        removed["archived_payloads"] = 0
    users = UserRepository()
    try:
        removed["profile"] = await users.delete_partition(owner_id)
    finally:
        await users.close()
    logger.info("Deleted account %s: %s", owner_id, removed)
    return removed
