"""replace_holdings must write new rows before deleting old ones and never empty the table first."""

import asyncio
from types import SimpleNamespace

from storage.tables.repositories import HoldingsRepository


def _holding(hid):
    return SimpleNamespace(holding_id=hid)


def test_replace_writes_before_deleting_and_removes_only_stale_rows():
    repo = HoldingsRepository.__new__(HoldingsRepository)
    calls = []

    async def query_entities(user_id):
        return [{"RowKey": "a"}, {"RowKey": "b"}]

    async def upsert_holdings(owner_id, holdings):
        calls.append(("upsert", [h.holding_id for h in holdings]))
        return len(holdings)

    async def delete_entity(user_id, entity_id):
        calls.append(("delete", entity_id))
        return True

    repo.query_entities = query_entities
    repo.upsert_holdings = upsert_holdings
    repo.delete_entity = delete_entity

    count = asyncio.run(repo.replace_holdings("u", [_holding("a"), _holding("c")]))

    assert count == 2
    assert calls == [("upsert", ["a", "c"]), ("delete", "b")]


def test_replace_with_failing_write_deletes_nothing():
    repo = HoldingsRepository.__new__(HoldingsRepository)
    deleted = []

    async def query_entities(user_id):
        return [{"RowKey": "a"}]

    async def upsert_holdings(owner_id, holdings):
        raise RuntimeError("storage down")

    async def delete_entity(user_id, entity_id):
        deleted.append(entity_id)

    repo.query_entities = query_entities
    repo.upsert_holdings = upsert_holdings
    repo.delete_entity = delete_entity

    try:
        asyncio.run(repo.replace_holdings("u", [_holding("x")]))
    except RuntimeError:
        pass
    assert deleted == []
