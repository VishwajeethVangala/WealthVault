"""Each sign-in notes whether it came from the Android app or a browser, and which build."""

import asyncio

from core.client_info import describe
from storage.tables.repositories import UserRepository


def test_the_app_is_told_apart_from_a_browser():
    app = describe("WealthVault-Android/0.3.18 (Pixel 8; Android 15)")
    assert (app["platform"], app["app_version"], app["device"]) == ("app", "0.3.18", "Pixel 8; Android 15")
    old_app = describe("okhttp/4.12.0")  # a build from before the version was sent
    assert (old_app["platform"], old_app["app_version"]) == ("app", "")
    web = describe("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36")
    assert web["platform"] == "web" and web["user_agent"].startswith("Mozilla")
    assert describe(None)["platform"] == "unknown"
    assert len(describe("x" * 1000)["user_agent"]) == 200


class FakeUsers(UserRepository):
    def __init__(self):
        self.row = {"user_id": "u", "email": "a@b.c"}

    async def get_entity(self, user_id, entity_id):
        return dict(self.row)

    async def upsert_entity(self, user_id, entity_id, data, mode="merge"):
        self.row.update(data)


def test_first_sign_in_is_kept_and_the_latest_and_a_count_are_updated():
    users = FakeUsers()
    asyncio.run(users.record_sign_in("u", describe("WealthVault-Android/0.3.17 (Pixel 8; Android 15)")))
    asyncio.run(users.record_sign_in("u", describe("Mozilla/5.0 Chrome/130")))
    row = users.row
    assert row["login_count"] == 2 and row["email"] == "a@b.c"
    assert (row["first_platform"], row["first_app_version"]) == ("app", "0.3.17")  # never overwritten
    assert (row["last_platform"], row["last_app_version"]) == ("web", "")
