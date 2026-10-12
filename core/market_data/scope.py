"""Broker client identity: one client (and one set of session/token files) per user connection.

A connection id such as "conn_zerodha_live" is the same string for every user's first connection, so a
client keyed by it alone would be shared between users. Scoping by owner keeps each user's broker
session private.
"""

import re
from typing import Optional


def require_owner(owner_id: Optional[str]) -> None:
    """In production a broker client without an owner would be shared by everyone, so refuse to build one."""
    if owner_id is None:
        from core.config import get_settings

        if get_settings().is_production:
            raise RuntimeError("A broker client was requested without a user; refusing to use a shared session.")


def scoped_key(connection_id: Optional[str], owner_id: Optional[str], default: str) -> str:
    """Filesystem- and dict-safe key for an (owner, connection) pair."""
    conn = connection_id or default
    raw = f"{owner_id}__{conn}" if owner_id else conn
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
