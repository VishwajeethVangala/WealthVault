import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.market_data import stock_search as ss


def row(exchange, code, name, isin, kind="EQ"):
    return {"exchange": exchange, "tradingsymbol": code, "name": name, "isin": isin, "instrument_type": kind}


ROWS = [
    row("BSE", "RELIANCE", "RELIANCE INDUSTRIES", "INE002A01018"),
    row("NSE", "RELIANCE", "RELIANCE INDUSTRIES", "INE002A01018"),
    row("NSE", "RPOWER", "RELIANCE POWER", "INE614G01033"),
    row("BSE", "RELIABVEN", "RELIABLE VENTURES INDIA", "INE000X"),
    row("BSE", "1015MHFCL27", "", "INE9"),  # a bond with no name
    row("NSE", "RELIANCE24", "RELIANCE FUT", "INF", kind="FUT"),
]


def test_a_stock_on_both_exchanges_appears_once_as_its_nse_listing_and_junk_is_left_out():
    out = ss.rank("reli", ROWS)
    assert [s["instrument"] for s in out] == ["NSE:RELIANCE", "BSE:RELIABVEN", "NSE:RPOWER"]
    assert out[0]["symbol"] == "RELIANCE" and out[1]["symbol"] == "BSE:RELIABVEN"  # BSE-only stocks need the prefix


def test_symbol_matches_come_before_name_matches():
    out = ss.rank("power", [row("NSE", "TATAPOWER", "TATA POWER CO", "a"), row("NSE", "POWERGRID", "POWER GRID CORP", "b")])
    assert out[0]["instrument"] == "NSE:POWERGRID"


def test_under_three_characters_asks_nothing():
    kite = SimpleNamespace(search_instruments=AsyncMock(return_value=ROWS))
    assert asyncio.run(ss.search_stocks(kite, "u", "re")) == []
    assert not kite.search_instruments.called


def test_indmoney_answers_when_kite_cannot():
    ss._cache.clear()
    kite = SimpleNamespace(search_instruments=AsyncMock(side_effect=RuntimeError("down")))
    ind = SimpleNamespace(call_tool=AsyncMock(return_value=[{"ind_key": "INDS1", "name": "Reliance Industries"}, {"ind_key": "INDI1", "name": "NIFTY"}]))
    details = {"INDS1": {"entity_basic": {"symbol": "RELIANCE", "display_name": "Reliance Industries"}}}
    with patch.object(ss, "get_user_indmoney_client", AsyncMock(return_value=ind)), patch.object(ss, "details_for", AsyncMock(return_value=details)):
        out = asyncio.run(ss.search_stocks(kite, "u", "reli"))
    assert out == [{"symbol": "RELIANCE", "instrument": "NSE:RELIANCE", "name": "Reliance Industries", "exchange": "NSE"}]
