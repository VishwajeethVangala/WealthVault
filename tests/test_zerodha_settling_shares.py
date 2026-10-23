"""Shares Zerodha lists as bought but not yet settled (t1_quantity) are part of the position."""

from core.portfolio.normalization import NormalizationService

KITE_ROWS = [
    # settled and settling shares of the same stock
    {"tradingsymbol": "HFCL-BE", "quantity": 103, "t1_quantity": 75, "average_price": 218.9766, "last_price": 240.07, "pnl": 3754.62, "day_change": -11.48, "day_change_percentage": -4.6},
    # nothing settled yet: still a real position
    {"tradingsymbol": "SOUTHBANK", "quantity": 0, "t1_quantity": 140, "average_price": 55.75, "last_price": 52.57, "pnl": -445.2, "day_change": -3.18, "day_change_percentage": -5.7},
    # no t1 field at all
    {"tradingsymbol": "INFY", "quantity": 10, "average_price": 1500.0, "last_price": 1600.0, "pnl": 1000.0, "day_change": 5.0},
]


def normalize():
    return {h.instrument_symbol: h for h in NormalizationService().normalize_holdings(
        raw_data=KITE_ROWS, broker_name="zerodha", owner_id="u1", connection_id="conn_zerodha_live")}


def test_settling_shares_are_counted():
    h = normalize()["HFCL-BE"]
    assert h.quantity == 178
    assert h.current_value == round(178 * 240.07, 2)
    assert h.pnl == 3754.62  # Kite's own figure covers all 178
    assert h.day_pnl == round(178 * -11.48, 2)


def test_a_position_with_nothing_settled_is_not_zero():
    h = normalize()["SOUTHBANK"]
    assert h.quantity == 140
    assert h.current_value == round(140 * 52.57, 2)


def test_rows_without_t1_are_unchanged():
    h = normalize()["INFY"]
    assert h.quantity == 10
    assert h.current_value == 16000.0
