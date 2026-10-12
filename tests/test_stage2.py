"""Chartink reading and snapshot storage rules for the Stage 2 page."""

import asyncio
import json
from contextlib import asynccontextmanager

from core.screeners import chartink
from storage.tables.repositories import ScreenerSnapshotRepository

PAGE = (
    "<html><head><title>Stage 2 Trend Template, Technical Analysis Scanner.</title>"
    '<meta name="csrf-token" content="tok123"></head><body>'
    '<div data="{&quot;atlas_query&quot;:&quot;( {cash} ( daily close &gt; daily sma( close,200 ) ) )&quot;,&quot;x&quot;:1}"></div>'
    "</body></html>"
)


class _Resp:
    def __init__(self, status=200, text="", payload=None):
        self.status, self._text, self._payload = status, text, payload

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        return self._payload


class _Session:
    def __init__(self, *a, **k):
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def get(self, url, headers=None):
        @asynccontextmanager
        async def cm():
            yield _Resp(text=PAGE)

        return cm()

    def post(self, url, data=None, headers=None):
        self.posts.append((data, headers))

        @asynccontextmanager
        async def cm():
            yield _Resp(
                payload={
                    "data": [
                        {"sr": 1, "nsecode": "INFY", "name": "Infosys", "bsecode": "500209", "close": 1500, "per_chg": 1.2, "volume": 10, "sector": "IT"},
                        {"sr": 2, "nsecode": "", "name": "no code"},
                    ]
                }
            )

        return cm()


def test_fetch_screener_reads_clause_posts_it_and_keeps_extra_columns(monkeypatch):
    session = _Session()
    monkeypatch.setattr(chartink.aiohttp, "ClientSession", lambda *a, **k: session)
    result = asyncio.run(chartink.fetch_screener("some-screener"))

    assert result.clause == "( {cash} ( daily close > daily sma( close,200 ) ) )"
    data, headers = session.posts[0]
    assert data["scan_clause"] == result.clause
    assert headers["X-CSRF-TOKEN"] == "tok123"
    assert [r["nsecode"] for r in result.rows] == ["INFY"]  # rows without a symbol are dropped
    assert result.extra_columns == ["sector"]  # a column added on Chartink flows through


def test_fetch_screener_explains_a_changed_page(monkeypatch):
    class _Blank(_Session):
        def get(self, url, headers=None):
            @asynccontextmanager
            async def cm():
                yield _Resp(text="<html><title>x</title></html>")

            return cm()

    monkeypatch.setattr(chartink.aiohttp, "ClientSession", lambda *a, **k: _Blank())
    try:
        asyncio.run(chartink.fetch_screener("x"))
    except chartink.ScreenerError as exc:
        assert "layout may have changed" in str(exc)
    else:
        raise AssertionError("expected ScreenerError")


def test_snapshot_payload_is_split_into_chunks_and_rejoined():
    repo = ScreenerSnapshotRepository.__new__(ScreenerSnapshotRepository)
    saved = {}

    async def upsert_entity(user_id, entity_id, data, mode):
        saved.update(data)

    repo.upsert_entity = upsert_entity
    payload = {"rows": [{"nsecode": f"STOCK{i}", "name": "n" * 40} for i in range(2000)]}  # well over one chunk
    asyncio.run(repo.save("slug", "2026-10-12", payload))

    assert saved["parts"] >= 3
    assert all(len(saved[f"part{i}"]) <= ScreenerSnapshotRepository.CHUNK for i in range(saved["parts"]))
    assert ScreenerSnapshotRepository._decode(saved) == json.loads(json.dumps(payload))
