"""Push notifications: which ATH calls go to whom, once, and that the push itself carries no text.

Everything here runs on in-memory fakes: no storage account, no Firebase."""

import asyncio
from datetime import date
from types import SimpleNamespace as NS

from core.push import fcm
from core.push.calls import ath_events, call_message, event_key, reversed_message
from core.push.service import Ports, inr, networth_daily_message, networth_weekly_message, notify_calls, send_kite_reminders, send_networth, send_test, send_to_user

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
        base = {k: True for k in ("holdings_ath", "stage2_ath", "networth_daily", "networth_weekly", "kite_login")}
        base.update(self.off.get(owner, {}))
        return base


class FakeNotes:
    def __init__(self):
        self.rows = {}

    async def create(self, owner, kind, title, body, body_masked, public_title, route):
        nid = f"n{len(self.rows)}"
        self.rows[(owner, nid)] = dict(kind=kind, title=title, body=body, body_masked=body_masked, public_title=public_title, route=route)
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
