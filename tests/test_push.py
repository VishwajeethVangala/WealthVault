"""Push notifications: which strategy calls go to whom, once, and that the push itself carries no text.

Everything here runs on in-memory fakes: no storage account, no Firebase."""

import asyncio
from datetime import date
from types import SimpleNamespace as NS

from core.push import fcm
from core.push.calls import ath_events, call_message, event_key, reversed_message
from core.push.service import (
    Ports, day_detail, inr, networth_daily_message, networth_weekly_message, notify_calls, send_kite_reminders, send_networth, send_test,
    send_to_user, send_us_digest, us_digest_message,
)

TODAY = "2026-10-29"


def run(coro):
    return asyncio.run(coro)


class FakeDevices:
    def __init__(self, tokens):
        self.t = {o: list(v) for o, v in tokens.items()}

    async def owners(self):
        return sorted(o for o, v in self.t.items() if v)

    async def tokens(self, owner):
        return list(self.t.get(owner, []))

    async def remove(self, owner, token):
        self.t[owner].remove(token)


class FakePrefs:
    def __init__(self, off=None):
        self.off = off or {}

    async def get(self, owner):
        base = {k: True for k in ("holdings_ath", "stage2_ath", "networth_daily", "networth_weekly", "us_stocks", "kite_login")}
        base.update(self.off.get(owner, {}))
        return base


class FakeNotes:
    def __init__(self):
        self.rows = {}

    async def create(self, owner, kind, title, body, body_masked, public_title, route, extra=""):
        nid = f"n{len(self.rows)}"
        self.rows[(owner, nid)] = dict(kind=kind, title=title, body=body, body_masked=body_masked, public_title=public_title, route=route, extra=extra)
        return nid


class FakeSent:
    def __init__(self):
        self.rows = {}

    async def has(self, owner, key):
        return (owner, key) in self.rows

    async def mark(self, owner, key, **fields):
        row = {"status": "sent", "RowKey": key}
        row.update(fields)
        self.rows[(owner, key)] = row

    async def with_prefix(self, owner, prefix):
        return [dict(r) for (o, k), r in self.rows.items() if o == owner and k.startswith(prefix)]


class FakeSender:
    def __init__(self, results=None):
        self.sent = []
        self.results = results or {}

    async def send(self, token, data):
        self.sent.append((token, data))
        return self.results.get(token, fcm.OK)


def ports(tokens, off=None, sender=None):
    return Ports(devices=FakeDevices(tokens), prefs=FakePrefs(off), notes=FakeNotes(), sent=FakeSent(), sender=sender or FakeSender())


def buy_row(day=TODAY):
    return {"ath": {"state": "IN_POSITION", "entry_date": day, "call": {"entry_date": day}, "exits": []}}


def sell_row(day=TODAY):
    return {"ath": {"state": "FLAT", "exits": [{"exit_date": day}]}}


def flat_row():
    return {"ath": {"state": "FLAT", "exits": []}}


# --- what counts as a call --------------------------------------------------------------------------------------


def test_only_calls_that_fired_today_count_and_names_are_cleaned():
    rows = {"NSE:RELIANCE": buy_row(), "NSE:TCS": buy_row("2026-10-20"), "NSE:INFY": sell_row(), "NSE:OLD": sell_row("2026-10-01"), "NSE:MTARTECH-BE": buy_row()}
    got = {(e["name"], e["side"]) for e in ath_events(rows, TODAY)}
    assert got == {("RELIANCE", "buy"), ("INFY", "sell"), ("MTARTECH", "buy")}


def test_wording_is_neutral_and_the_lock_screen_text_names_no_stock():
    msg = call_message("h", ath_events({"NSE:RELIANCE": buy_row()}, TODAY))
    text = (msg["title"] + msg["body"]).lower()
    assert "reliance" in text and "buy" not in text.replace("buyer", "") and "sell" not in text
    assert "reliance" not in msg["public_title"].lower()
    many = call_message("s", ath_events({f"NSE:S{i}": buy_row() for i in range(7)}, TODAY))
    assert "7 calls" in many["body"] and "and 3 more" in many["body"]


# --- who gets what ------------------------------------------------------------------------------------------------


def test_holdings_calls_go_only_to_the_owner_and_stage2_calls_to_everyone_but_not_twice():
    p = ports({"alice": ["ta"], "bob": ["tb"]})
    rows = {"NSE:RELIANCE": buy_row(), "NSE:ZOMATO": buy_row()}
    held = {"alice": {"NSE:RELIANCE"}, "bob": set()}
    stage2 = ["NSE:RELIANCE", "NSE:ZOMATO"]
    run(notify_calls(p, TODAY, rows, held, stage2))
    by_owner = {}
    for (owner, _nid), n in p.notes.rows.items():
        by_owner.setdefault(owner, []).append(n)
    alice = sorted(n["kind"] for n in by_owner["alice"])
    bob = sorted(n["kind"] for n in by_owner["bob"])
    assert alice == ["ath_h", "ath_s"]  # her holding as a holding, the other Stage 2 stock as Stage 2
    assert bob == ["ath_s"]  # Bob does not hold RELIANCE, so he sees both under Stage 2
    alice_s = next(n for n in by_owner["alice"] if n["kind"] == "ath_s")
    assert "RELIANCE" not in alice_s["body"] and "ZOMATO" in alice_s["body"]
    bob_s = by_owner["bob"][0]
    assert "RELIANCE" in bob_s["body"] and "ZOMATO" in bob_s["body"]
    holding_msg = next(n for n in by_owner["alice"] if n["kind"] == "ath_h")
    assert "RELIANCE" in holding_msg["body"]
    assert not any("RELIANCE" in n["body"] for n in by_owner["alice"] if n["kind"] == "ath_s")


def test_a_call_is_sent_once_per_day_and_several_at_one_refresh_are_one_message():
    p = ports({"alice": ["ta"]})
    rows = {"NSE:A": buy_row(), "NSE:B": buy_row(), "NSE:C": sell_row()}
    held = {"alice": set(rows)}
    run(notify_calls(p, TODAY, rows, held, []))
    assert len(p.sender.sent) == 1  # grouped
    run(notify_calls(p, TODAY, rows, held, []))
    assert len(p.sender.sent) == 1  # nothing new
    rows["NSE:D"] = buy_row()
    held["alice"].add("NSE:D")
    run(notify_calls(p, TODAY, rows, held, []))
    assert len(p.sender.sent) == 2  # only D was new
    assert list(p.notes.rows.values())[-1]["body"].startswith("D:")  # a single call is worded as one


def test_a_switched_off_kind_is_not_sent_and_not_marked_so_it_still_goes_when_switched_on():
    p = ports({"alice": ["ta"]}, off={"alice": {"holdings_ath": False}})
    rows = {"NSE:A": buy_row()}
    run(notify_calls(p, TODAY, rows, {"alice": {"NSE:A"}}, []))
    assert p.sender.sent == [] and p.sent.rows == {}
    p.prefs.off = {}
    run(notify_calls(p, TODAY, rows, {"alice": {"NSE:A"}}, []))
    assert len(p.sender.sent) == 1


def test_the_closing_refresh_follows_up_on_a_call_that_did_not_hold():
    p = ports({"alice": ["ta"]})
    held = {"alice": {"NSE:A", "NSE:B"}}
    run(notify_calls(p, TODAY, {"NSE:A": buy_row(), "NSE:B": buy_row()}, held, []))
    assert len(p.sender.sent) == 1
    # by the close B has fallen back; A still stands
    run(notify_calls(p, TODAY, {"NSE:A": buy_row(), "NSE:B": flat_row()}, held, [], final=True))
    assert len(p.sender.sent) == 2
    follow = list(p.notes.rows.values())[-1]
    assert follow["kind"] == "ath_reversed" and "B" in follow["body"] and "did not hold" in follow["body"]
    run(notify_calls(p, TODAY, {"NSE:A": buy_row(), "NSE:B": flat_row()}, held, [], final=True))
    assert len(p.sender.sent) == 2  # told once


# --- the push carries no text ---------------------------------------------------------------------------------------


def test_the_push_message_holds_only_a_type_and_an_id():
    p = ports({"alice": ["ta"]})
    run(notify_calls(p, TODAY, {"NSE:RELIANCE": buy_row()}, {"alice": {"NSE:RELIANCE"}}, []))
    token, data = p.sender.sent[0]
    assert token == "ta" and set(data) == {"type", "id"}
    assert "RELIANCE" not in str(data)


def test_a_phone_that_no_longer_has_the_app_is_forgotten_and_other_phones_still_get_it():
    p = ports({"alice": ["gone", "ok"]}, sender=FakeSender({"gone": fcm.UNREGISTERED}))
    delivered = run(send_to_user(p, "alice", "test", None, {"title": "t", "body": "b", "public_title": "p"}))
    assert delivered == 1 and p.devices.t["alice"] == ["ok"]


def test_nothing_is_sent_when_push_is_not_configured_or_the_person_has_no_phone():
    assert run(send_test(Ports(devices=FakeDevices({"a": ["t"]}), prefs=FakePrefs(), notes=FakeNotes(), sent=FakeSent(), sender=None), "a")) == 0
    assert run(send_test(ports({"a": []}), "a")) == 0


# --- net worth and the Kite reminder ---------------------------------------------------------------------------------


def test_rupees_use_indian_grouping_and_the_masked_text_has_no_amount():
    assert inr(1234567.8) == "₹12,34,568" and inr(-5000) == "−₹5,000" and inr(999) == "₹999"
    msg = networth_daily_message({"total": 4523000.0, "day": 18000.0, "day_pct": 0.4})
    assert "₹45,23,000" in msg["body"] and "₹" not in msg["body_masked"] and "₹" not in msg["public_title"]
    weekly = networth_weekly_message(4600000.0, 4500000.0, "2026-10-22")
    assert "₹46,00,000" in weekly["body"] and "+2.22%" in weekly["body"] and "₹" not in weekly["body_masked"]


class FakeHoldings:
    def __init__(self, by_owner):
        self.by = by_owner

    async def get_holdings(self, owner_id):
        return self.by.get(owner_id, [])


class FakeSnapshots:
    def __init__(self, snaps):
        self.snaps = snaps

    async def list_snapshots(self, owner, limit=30):
        return self.snaps.get(owner, [])


def holding(value, day=0.0):
    return NS(current_value=value, day_pnl=day)


def test_daily_net_worth_goes_once_a_day_and_weekly_waits_for_a_week_old_snapshot():
    p = ports({"alice": ["ta"], "bob": ["tb"]})
    repo = FakeHoldings({"alice": [holding(1000000.0, 5000.0)], "bob": []})
    assert run(send_networth(p, repo, FakeSnapshots({}), date(2026, 10, 29), weekly=False)) == 1  # Bob has no holdings
    assert run(send_networth(p, repo, FakeSnapshots({}), date(2026, 10, 29), weekly=False)) == 0  # not again today
    assert run(send_networth(p, repo, FakeSnapshots({}), date(2026, 11, 1), weekly=True)) == 0  # no snapshot a week old
    snaps = {"alice": [NS(as_of_date="2026-10-24", total_current_value=950000.0)]}
    assert run(send_networth(p, repo, FakeSnapshots(snaps), date(2026, 11, 1), weekly=True)) == 1


def test_the_kite_reminder_goes_only_to_people_who_need_a_login_and_only_once():
    p = ports({"alice": ["ta"], "bob": ["tb"]})

    async def needs(owner):
        return owner == "alice"

    assert run(send_kite_reminders(p, date(2026, 10, 29), needs)) == 1
    assert [t for t, _ in p.sender.sent] == ["ta"]
    assert run(send_kite_reminders(p, date(2026, 10, 29), needs)) == 0


# --- richer content and where a tap lands ------------------------------------------------------------------------------


def rich_buy():
    return {"ath": {"state": "IN_POSITION", "entry_date": TODAY, "call": {"entry_date": TODAY, "close": 2980.0, "prior_ath": 2950.0, "above_ath_pct": 1.02, "above_dma_pct": 12.3}, "exits": []}}


def test_a_single_call_opens_the_strategy_page_on_that_stock_and_quotes_its_numbers():
    ev = ath_events({"NSE:RELIANCE": rich_buy()}, TODAY)
    msg = call_message("h", ev, {"NSE:RELIANCE": {"qty": 40.0, "pnl_pct": 18.0}})
    assert msg["route"] == "strategy:NSE:RELIANCE" and msg["title"] == "Strategy calls · your holdings"
    assert "2,980.00" in msg["body"] and "2,950.00" in msg["body"] and "You hold 40 shares, +18.0% overall." in msg["body"]
    assert "40" not in msg["body_masked"] and "You hold this stock, +18.0% overall." in msg["body_masked"]
    assert msg["extra"]["actions"][0] == {"label": "Open strategy", "route": "strategy:NSE:RELIANCE"}
    group = call_message("s", ath_events({"NSE:A": buy_row(), "NSE:B": buy_row()}, TODAY))
    assert group["route"] == "strategy" and group["title"] == "Strategy calls · Stage 2 list"


def test_the_notification_text_is_stored_with_its_extra_and_the_push_still_carries_no_text():
    p = ports({"alice": ["ta"]})
    run(notify_calls(p, TODAY, {"NSE:RELIANCE": rich_buy()}, {"alice": {"NSE:RELIANCE"}}, [], held_info={"alice": {"NSE:RELIANCE": {"qty": 5.0, "pnl_pct": 2.0}}}))
    note = next(iter(p.notes.rows.values()))
    assert "RELIANCE" in note["body"] and '"strategy:NSE:RELIANCE"' in note["extra"]
    assert set(p.sender.sent[0][1]) == {"type", "id"}


def h(sym, cls, value, day, day_pct=None):
    return NS(instrument_symbol=sym, asset_class=cls, current_value=value, day_pnl=day, day_change_percentage=day_pct)


def test_the_daily_message_compares_with_nifty_names_the_movers_and_keeps_amounts_out_of_the_masked_text():
    hs = [h("RELIANCE", "EQUITY", 102100.0, 2100.0, 2.1), h("INFY", "EQUITY", 98700.0, -1300.0, -1.3), h("FUND", "MUTUAL_FUND", 50000.0, 50.0, 0.1)]
    t = {"total": 250800.0, "day": 850.0, "day_pct": 0.34}
    msg = networth_daily_message(t, detail=day_detail(hs), nifty=-0.23)
    assert "you beat it by 0.57%" in msg["body"] and "Best: RELIANCE +2.10%" in msg["body"] and "Drag: INFY −1.30%" in msg["body"]
    assert "Stocks" in msg["body"] and "MF" in msg["body"]
    assert "₹" in msg["body"] and "₹" not in msg["body_masked"] and "₹" not in msg["title"]
    assert msg["extra"]["tone"] == "up" and msg["route"] == "overview"
    bare = networth_daily_message(t)  # no Nifty and no detail: still a complete message
    assert "Nifty" not in bare["body"]


async def _value(v):
    return v


def test_the_weekly_message_carries_an_indexed_line_with_no_amounts():
    snaps = [NS(as_of_date=d, total_current_value=v) for d, v in [("2026-10-22", 100000.0), ("2026-10-24", 101000.0), ("2026-10-28", 100500.0)]]
    p = ports({"alice": ["ta"]})
    repo = FakeHoldings({"alice": [holding(102000.0, 0.0)]})
    run(send_networth(p, repo, FakeSnapshots({"alice": snaps}), date(2026, 11, 1), weekly=True, nifty=lambda o, since: _value(0.5)))
    note = next(iter(p.notes.rows.values()))
    assert '"series":[100.0,99.5,100.99]' in note["extra"] and "Nifty this week" in note["body"] and "₹" not in note["body_masked"]


def test_a_failing_nifty_lookup_only_drops_that_line():
    async def broken(owner, since):
        raise RuntimeError("no quote")

    p = ports({"alice": ["ta"]})
    repo = FakeHoldings({"alice": [holding(1000000.0, 5000.0)]})
    assert run(send_networth(p, repo, FakeSnapshots({}), date(2026, 10, 29), weekly=False, nifty=broken)) == 1
    assert "Nifty" not in next(iter(p.notes.rows.values()))["body"]


def test_the_kite_reminder_opens_the_brokers_page():
    p = ports({"alice": ["ta"]})

    async def needs(owner):
        return True

    run(send_kite_reminders(p, date(2026, 10, 29), needs))
    note = next(iter(p.notes.rows.values()))
    assert note["route"] == "brokers" and '"Log in to Kite"' in note["extra"]


# --- the US stocks look ---------------------------------------------------------------------------------------------------


def test_the_us_message_compares_with_the_s_and_p_and_hides_the_amount_when_masked():
    rows = [{"ticker": "NVDA", "pct": 2.4, "value": 300000.0}, {"ticker": "TSLA", "pct": -1.9, "value": 100000.0}]
    msg = us_digest_message(rows, 0.5)
    assert msg["title"].startswith("US stocks") and "Best: NVDA +2.40%" in msg["body"] and "Drag: TSLA −1.90%" in msg["body"]
    assert "S&P 500 (SPY)" in msg["body"] and "1 of 2 stocks up" in msg["body"]
    assert "₹" in msg["body"] and "₹" not in msg["body_masked"]


def test_the_us_look_goes_once_a_day_only_to_people_with_us_stocks_who_want_it():
    p = ports({"alice": ["ta"], "bob": ["tb"], "cara": ["tc"]}, off={"cara": {"us_stocks": False}})

    def us(sym):
        return h(sym, "US_STOCKS", 200000.0, 0.0)

    repo = FakeHoldings({"alice": [us("NVDA (NVIDIA Corporation)")], "bob": [h("TCS", "EQUITY", 1000.0, 0.0)], "cara": [us("AAPL")]})

    async def quotes(owner, holdings):
        return {"NVDA": {"day_change_pct": 1.2}, "AAPL": {"day_change_pct": 0.3}, "SPY": {"day_change_pct": 0.4}}

    assert run(send_us_digest(p, repo, date(2026, 10, 29), quotes)) == 1
    assert run(send_us_digest(p, repo, date(2026, 10, 29), quotes)) == 0
    assert [t for t, _ in p.sender.sent] == ["ta"]
