"""Watchlist tests: adding, listing with signal enrichment, updating notes, and removing."""
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import watchlist
from apps.api.routers.accounts import get_current_user


def _client():
    app = FastAPI()
    app.include_router(watchlist.router)
    app.dependency_overrides[get_current_user] = lambda: "google_111"
    return TestClient(app)


def test_watchlist_add_and_list_enriched():
    items = []
    repo = AsyncMock()
    repo.add_item = AsyncMock(
        side_effect=lambda owner_id, symbol, name=None, notes=None, target_price=None, price_when_added=None: items.append({
            "symbol": symbol,
            "name": name or symbol.split(":")[-1],
            "notes": notes or "",
            "target_price": target_price,
            "price_when_added": price_when_added or 0.0,
            "added_at": "2026-11-14T10:00:00Z",
        }) or items[-1]
    )
    repo.list_items = AsyncMock(side_effect=lambda owner_id: items)

    cache = AsyncMock()
    cache.get_many = AsyncMock(return_value={
        "NSE:TATAMOTORS": {
            "name": "Tata Motors Limited",
            "momentum": {"last_price": 950.0, "trend_verdict": "Strong Uptrend", "trend_score": 5},
            "ath": {"state": "IN_POSITION"},
        }
    })

    with patch.object(watchlist, "WatchlistRepository", lambda: repo), patch.object(watchlist, "SignalCacheRepository", lambda: cache):
        c = _client()

        # Add stock without exchange prefix -> normalized to NSE:TATAMOTORS
        r1 = c.post("/watchlist", json={"symbol": "TATAMOTORS", "notes": "Breakout radar", "target_price": 980.0, "price_when_added": 900.0})
        assert r1.status_code == 201
        data1 = r1.json()
        assert data1["symbol"] == "NSE:TATAMOTORS"
        assert data1["notes"] == "Breakout radar"
        assert data1["target_price"] == 980.0
        assert data1["price_when_added"] == 900.0

        # Add second stock with explicit BSE prefix
        r2 = c.post("/watchlist", json={"symbol": "BSE:500209", "name": "INFOSYS", "price_when_added": 1800.0})
        assert r2.status_code == 201
        data2 = r2.json()
        assert data2["symbol"] == "BSE:500209"
        assert data2["name"] == "INFOSYS"

        # List watchlist -> enriched with cached signal
        r_list = c.get("/watchlist")
        assert r_list.status_code == 200
        res = r_list.json()
        assert res["count"] == 2
        items_out = res["items"]
        assert len(items_out) == 2

        tata = next(it for it in items_out if it["symbol"] == "NSE:TATAMOTORS")
        assert tata["last_price"] == 950.0
        assert tata["trend_verdict"] == "Strong Uptrend"
        assert tata["trend_score"] == 5
        assert tata["signal_state"] == "IN_POSITION"
        # pct_since_added: (950 - 900) / 900 * 100 = 5.56%
        assert tata["pct_since_added"] == 5.56


def test_watchlist_remove():
    repo = AsyncMock()
    repo.remove_item = AsyncMock(return_value=True)

    with patch.object(watchlist, "WatchlistRepository", lambda: repo):
        c = _client()
        r = c.delete("/watchlist/TATAMOTORS")
        assert r.status_code == 200
        assert r.json()["status"] == "removed"
        assert r.json()["symbol"] == "NSE:TATAMOTORS"
        repo.remove_item.assert_awaited_with(owner_id="google_111", symbol="NSE:TATAMOTORS")


def test_watchlist_empty_symbol_rejected():
    c = _client()
    r = c.post("/watchlist", json={"symbol": "   "})
    assert r.status_code == 422
