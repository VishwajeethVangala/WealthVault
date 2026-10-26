"""Groww Trade API (the deployed site's Groww connection): TOTP sign-in each day, holdings, and every way it can fail.

The requests follow Groww's documentation: POST /v1/token/api/access with the TOTP token as the bearer and
{"key_type": "totp", "totp": code}, then GET /v1/holdings/user with X-API-VERSION 1.0."""

import asyncio
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
from cryptography.fernet import Fernet

os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from aiohttp import web
from aiohttp.test_utils import TestServer

import providers.brokers.groww as groww
from core.models import AssetClass, BrokerStatus
from core.portfolio.normalization import NormalizationService
from core.totp import generate_totp

SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # a test seed
TOTP_TOKEN = "eyJ-test-totp-token"

HOLDINGS = {
    "status": "SUCCESS",
    "payload": {
        "holdings": [
            {"isin": "INE0PTN01011", "trading_symbol": "MONEYVIEW", "quantity": 941, "average_price": 43.79, "pledge_quantity": 0.0, "demat_locked_quantity": 0.0,
             "groww_locked_quantity": 0.0, "repledge_quantity": 0.0, "t1_quantity": 0.0, "demat_free_quantity": 941.0, "corporate_action_additional_quantity": 0, "active_demat_transfer_quantity": 0},
            {"isin": "INE002A01018", "trading_symbol": "RELIANCE", "quantity": 10, "average_price": 1100.0, "pledge_quantity": 2.0, "demat_locked_quantity": 0.0,
             "groww_locked_quantity": 0.0, "repledge_quantity": 0.0, "t1_quantity": 3.0, "demat_free_quantity": 5.0, "corporate_action_additional_quantity": 0, "active_demat_transfer_quantity": 0},
        ]
    },
}


class FakeRepo:
    def __init__(self, creds):
        self.creds, self.session, self.saved = creds, None, []

    async def get_credentials(self, owner, conn):
        return self.creds

    async def get_session(self, owner, conn):
        return self.session or None

    async def save_session(self, owner, conn, session):
        self.session = session
        self.saved.append(session)


class FakeGroww:
    """Groww's API: records what it was asked and answers as configured."""

    def __init__(self, token_status=200, holdings_status=200, holdings=HOLDINGS):
        self.token_status, self.holdings_status, self.holdings = token_status, holdings_status, holdings
        self.token_calls, self.holding_calls = [], []

    async def run(self, body):
        async def token(request):
            self.token_calls.append({"auth": request.headers.get("Authorization"), "body": await request.json()})
            if self.token_status != 200:
                return web.json_response({"error": {"message": "key not approved"}}, status=self.token_status)
            return web.json_response({"token": f"ACCESS{len(self.token_calls)}", "expiry": "x"})

        async def holdings(request):
            self.holding_calls.append({"auth": request.headers.get("Authorization"), "version": request.headers.get("X-API-VERSION")})
            return web.json_response(self.holdings, status=self.holdings_status)

        app = web.Application()
        app.router.add_post("/v1/token/api/access", token)
        app.router.add_get("/v1/holdings/user", holdings)
        async with TestServer(app) as server:
            groww.BASE_URL = str(server.make_url("")).rstrip("/")
            return await body()


def provider(creds, repo=None):
    p = groww.GrowwProvider("u", "c")
    p._repo = repo or FakeRepo(creds)
    return p


def run(coro):
    return asyncio.run(coro)


TOTP_CREDS = {"api_key": TOTP_TOKEN, "totp_secret": SECRET}


class TotpSignInTests(unittest.TestCase):
    def test_the_sign_in_follows_groww_documentation(self):
        api = FakeGroww()
        before = generate_totp(SECRET)
        run(api.run(lambda: provider(TOTP_CREDS).get_holdings()))
        after = generate_totp(SECRET)
        call = api.token_calls[0]
        self.assertEqual(call["auth"], f"Bearer {TOTP_TOKEN}")  # the TOTP token is the bearer
        self.assertEqual(call["body"]["key_type"], "totp")
        self.assertIn(call["body"]["totp"], {before, after})  # a 6 digit code made from the secret just now
        self.assertEqual(len(call["body"]["totp"]), 6)
        self.assertEqual(api.holding_calls[0], {"auth": "Bearer ACCESS1", "version": "1.0"})

    def test_a_secret_pasted_with_spaces_or_lowercase_still_signs_in(self):
        api = FakeGroww()
        spaced = " ".join(SECRET[i : i + 4] for i in range(0, len(SECRET), 4)).lower()
        run(api.run(lambda: provider({"api_key": TOTP_TOKEN, "totp_secret": spaced}).get_holdings()))
        self.assertEqual(api.token_calls[0]["body"]["key_type"], "totp")

    def test_one_sign_in_serves_the_whole_day(self):
        api = FakeGroww()

        async def twice():
            p = provider(TOTP_CREDS)
            await p.get_holdings()
            await p.get_holdings()

        run(api.run(twice))
        self.assertEqual(len(api.token_calls), 1)  # Groww allows 150 token requests a day; we use one
        self.assertEqual(len(api.holding_calls), 2)

    def test_the_day_after_it_signs_in_again_by_itself(self):
        api = FakeGroww()
        repo = FakeRepo(TOTP_CREDS)

        async def two_days():
            await provider(TOTP_CREDS, repo).get_holdings()
            repo.session["expires_at"] = time.time() - 5  # the 06:00 IST expiry has passed
            await provider(TOTP_CREDS, repo).get_holdings()

        run(api.run(two_days))
        self.assertEqual(len(api.token_calls), 2)
        self.assertEqual(api.holding_calls[1]["auth"], "Bearer ACCESS2")

    def test_the_token_is_kept_until_the_next_0600_ist(self):
        from datetime import datetime

        ist = groww.IST
        self.assertEqual(datetime.fromtimestamp(groww.next_token_expiry(datetime(2026, 10, 27, 5, 0, tzinfo=ist)), ist).day, 27)
        self.assertEqual(datetime.fromtimestamp(groww.next_token_expiry(datetime(2026, 10, 27, 7, 0, tzinfo=ist)), ist).day, 28)

    def test_a_key_with_nothing_to_sign_in_with_asks_for_the_secret(self):
        api = FakeGroww()
        status = run(api.run(lambda: provider({"api_key": TOTP_TOKEN}).get_account_status()))
        self.assertEqual(status["status"], "auth_required")
        self.assertEqual(api.token_calls, [])  # nothing is sent to Groww without something to sign in with

    def test_no_credentials_asks_for_them(self):
        status = run(provider(None).get_account_status())
        self.assertEqual(status["status"], "auth_required")

    def test_a_refused_sign_in_says_so_and_points_to_the_keys_page(self):
        api = FakeGroww(token_status=403)
        status = run(api.run(lambda: provider(TOTP_CREDS).get_account_status()))
        self.assertEqual(status["status"], "auth_required")
        self.assertIn("did not issue a token", status["message"])
        self.assertEqual(status["auth_url"], groww.APPROVAL_URL)


class HoldingsTests(unittest.TestCase):
    def test_holdings_are_returned_as_sent(self):
        rows = run(FakeGroww().run(lambda: provider(TOTP_CREDS).get_holdings()))
        self.assertEqual([r["trading_symbol"] for r in rows], ["MONEYVIEW", "RELIANCE"])

    def test_an_empty_portfolio_is_an_empty_list(self):
        api = FakeGroww(holdings={"status": "SUCCESS", "payload": {"holdings": []}})
        self.assertEqual(run(api.run(lambda: provider(TOTP_CREDS).get_holdings())), [])

    def test_a_failure_reply_is_an_error_and_never_an_empty_portfolio(self):
        for reply in ({"status": "FAILURE", "error": {"code": "GA001", "message": "bad"}}, {"error": "x"}, {}):
            api = FakeGroww(holdings=reply)
            with self.assertRaises(RuntimeError, msg=str(reply)):
                run(api.run(lambda: provider(TOTP_CREDS).get_holdings()))

    def test_a_server_error_is_an_error(self):
        api = FakeGroww(holdings_status=500, holdings={"status": "FAILURE"})
        with self.assertRaises(RuntimeError):
            run(api.run(lambda: provider(TOTP_CREDS).get_holdings()))

    def test_a_rejected_session_clears_the_saved_token_and_asks_to_sign_in_again(self):
        api = FakeGroww(holdings_status=403, holdings={"status": "FAILURE"})
        repo = FakeRepo(TOTP_CREDS)
        with self.assertRaises(groww.GrowwAuthRequiredError):
            run(api.run(lambda: provider(TOTP_CREDS, repo).get_holdings()))
        self.assertEqual(repo.session, {})  # the next sync signs in afresh instead of reusing a dead token

    def test_the_rows_become_holdings_with_settling_and_pledged_counted_once(self):
        raw = run(FakeGroww().run(lambda: provider(TOTP_CREDS).get_holdings()))
        held = NormalizationService().normalize_holdings(raw, "groww", "u", "c")
        by = {h.instrument_symbol: h for h in held}
        self.assertEqual(by["MONEYVIEW"].quantity, 941.0)
        self.assertEqual(by["RELIANCE"].quantity, 10.0)  # 5 free + 3 settling + 2 pledged, as Groww's own sample adds up
        self.assertEqual(by["RELIANCE"].asset_class, AssetClass.EQUITY)
        self.assertEqual(by["MONEYVIEW"].isin, None)  # equities carry no fund ISIN


class SyncTests(unittest.TestCase):
    """The route that syncs every broker: a Groww failure must keep what is stored."""

    def setUp(self):
        from apps.api.routers import portfolio

        self.portfolio = portfolio
        self.conn = SimpleNamespace(broker_name="groww", connection_id="c")
        self.repo = SimpleNamespace(update_status=AsyncMock())

    def pull(self, provider_cls):
        with patch.dict(self.portfolio.CREDENTIAL_BROKERS, {"groww": (provider_cls, groww.GrowwAuthRequiredError)}), \
                patch.object(self.portfolio, "archive_broker_payload", AsyncMock(return_value="blob")):
            return run(self.portfolio._pull_credential_broker("u", self.conn, __import__("datetime").datetime.now(), NormalizationService(), self.repo))

    def test_a_good_pull_is_connected_and_normalized(self):
        class Good:
            def __init__(self, owner_id, connection_id):
                pass

            async def get_holdings(self):
                return HOLDINGS["payload"]["holdings"]

        result = self.pull(Good)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(self.repo.update_status.await_args.kwargs["status"], BrokerStatus.CONNECTED)

    def test_a_login_problem_returns_none_so_stored_holdings_are_kept_and_marks_auth_required(self):
        class Needs:
            def __init__(self, owner_id, connection_id):
                pass

            async def get_holdings(self):
                raise groww.GrowwAuthRequiredError("sign in again")

        self.assertIsNone(self.pull(Needs))
        self.assertEqual(self.repo.update_status.await_args.kwargs["status"], BrokerStatus.AUTH_REQUIRED)

    def test_any_other_failure_also_returns_none(self):
        class Broken:
            def __init__(self, owner_id, connection_id):
                pass

            async def get_holdings(self):
                raise RuntimeError("Groww is down")

        self.assertIsNone(self.pull(Broken))
        self.assertEqual(self.repo.update_status.await_args.kwargs["status"], BrokerStatus.PROVIDER_ERROR)


class StaticIpTests(unittest.TestCase):
    def test_a_rejected_token_request_keeps_groww_wording_so_an_ip_block_is_visible(self):
        # if Groww refuses by IP address its message is shown to the user as is
        api = FakeGroww(token_status=403)
        status = run(api.run(lambda: provider(TOTP_CREDS).get_account_status()))
        self.assertIn("key not approved", status["message"])


if __name__ == "__main__":
    unittest.main()
