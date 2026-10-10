"""Tests for the credential-based brokers (Groww, Angel One): crypto, TOTP, login + holdings flows.

The brokers' HTTP APIs are replaced by a local aiohttp server and the Azure credential table by an
in-memory fake, so no network or Azure access is needed.
"""

import asyncio
import os
import time
import unittest

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography.fernet import Fernet

os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from core.config import get_settings

get_settings.cache_clear()

import providers.brokers.angelone as angelone
import providers.brokers.groww as groww
from core.credentials import CredentialStoreError, decrypt_json, encrypt_json
from core.portfolio.normalization import NormalizationService
from core.totp import generate_totp


class FakeCredentialRepo:
    """In-memory stand-in for BrokerCredentialRepository."""

    def __init__(self, creds):
        self.creds = creds
        self.session = None

    async def get_credentials(self, owner, conn):
        return self.creds

    async def get_session(self, owner, conn):
        return self.session or None

    async def save_session(self, owner, conn, session):
        self.session = session


class CryptoAndTotpTests(unittest.TestCase):
    def test_totp_matches_rfc6238_vector(self):
        self.assertEqual(generate_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at=59, digits=8), "94287082")

    def test_totp_ignores_spaces_and_case(self):
        clean = generate_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at=1111111109, digits=8)
        messy = generate_totp("gezd gnbv gy3t qojq gezd gnbv gy3t qojq", at=1111111109, digits=8)
        self.assertEqual(clean, "07081804")  # RFC 6238 test vector for T=1111111109
        self.assertEqual(messy, clean)

    def test_encrypt_roundtrip_hides_plaintext(self):
        token = encrypt_json({"pin": "1234"})
        self.assertNotIn("1234", token)
        self.assertEqual(decrypt_json(token), {"pin": "1234"})

    def test_wrong_key_is_reported(self):
        token = encrypt_json({"a": "b"})
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        get_settings.cache_clear()
        with self.assertRaises(CredentialStoreError):
            decrypt_json(token)


class GrowwTests(unittest.TestCase):
    def test_checksum_is_sha256_of_secret_plus_timestamp(self):
        import hashlib

        self.assertEqual(groww.approval_checksum("sec", "17"), hashlib.sha256(b"sec17").hexdigest())

    def test_token_expiry_is_next_6am_ist(self):
        from datetime import datetime

        before = datetime(2026, 10, 10, 5, 0, tzinfo=groww.IST)
        after = datetime(2026, 10, 10, 7, 0, tzinfo=groww.IST)
        self.assertEqual(datetime.fromtimestamp(groww.next_token_expiry(before), groww.IST).day, 10)
        self.assertEqual(datetime.fromtimestamp(groww.next_token_expiry(after), groww.IST).day, 11)

    def test_normalizes_holdings_without_prices(self):
        h = NormalizationService().normalize_holdings(
            [{"isin": "INE545U01014", "trading_symbol": "reliance", "quantity": 10, "average_price": 100}], "groww", "u", "c"
        )[0]
        self.assertEqual(h.instrument_symbol, "RELIANCE")
        self.assertEqual(h.current_value, 1000.0)
        self.assertEqual(h.data_freshness, "cached")

    def test_token_then_holdings_flow(self):
        calls = {"token_body": None, "holdings_auth": None}

        async def token(request):
            calls["token_body"] = await request.json()
            return web.json_response({"token": "TKN", "expiry": "x"})

        async def holdings(request):
            calls["holdings_auth"] = request.headers.get("Authorization")
            return web.json_response(
                {"status": "SUCCESS", "payload": {"holdings": [{"trading_symbol": "ABB", "quantity": 2, "average_price": 5}]}}
            )

        async def run():
            app = web.Application()
            app.router.add_post("/v1/token/api/access", token)
            app.router.add_get("/v1/holdings/user", holdings)
            async with TestServer(app) as server:
                groww.BASE_URL = str(server.make_url("")).rstrip("/")
                p = groww.GrowwProvider("u", "c")
                p._repo = FakeCredentialRepo({"api_key": "K", "api_secret": "S"})
                rows = await p.get_holdings()
                # second call reuses the cached token (no second token request)
                calls["token_body"] = None
                await p.get_holdings()
                return rows

        rows = asyncio.run(run())
        self.assertEqual(rows[0]["trading_symbol"], "ABB")
        self.assertEqual(calls["holdings_auth"], "Bearer TKN")
        self.assertIsNone(calls["token_body"])

    def test_missing_credentials_requires_auth(self):
        async def run():
            p = groww.GrowwProvider("u", "c")
            p._repo = FakeCredentialRepo(None)
            return await p.get_account_status()

        self.assertEqual(asyncio.run(run())["status"], "auth_required")

    def test_unapproved_key_points_to_approval_page(self):
        async def deny(request):
            return web.json_response({"error": "not approved"}, status=403)

        async def run():
            app = web.Application()
            app.router.add_post("/v1/token/api/access", deny)
            async with TestServer(app) as server:
                groww.BASE_URL = str(server.make_url("")).rstrip("/")
                p = groww.GrowwProvider("u", "c")
                p._repo = FakeCredentialRepo({"api_key": "K", "totp_secret": "GEZDGNBVGY3TQOJQ"})
                return await p.get_account_status()

        res = asyncio.run(run())
        self.assertEqual(res["status"], "auth_required")
        self.assertIn("approved", res["message"])
        self.assertEqual(res["auth_url"], groww.APPROVAL_URL)


class AngelOneTests(unittest.TestCase):
    CREDS = {"api_key": "AK", "client_code": "A123", "pin": "1234", "totp_secret": "GEZDGNBVGY3TQOJQ"}

    def test_normalizes_holdings_with_prices(self):
        h = NormalizationService().normalize_holdings(
            {"holdings": [{"tradingsymbol": "INFY-EQ", "isin": "I", "quantity": 5, "averageprice": 1400, "ltp": 1500, "close": 1480, "profitandloss": 500}]},
            "angelone",
            "u",
            "c",
        )[0]
        self.assertEqual((h.instrument_symbol, h.current_value, h.pnl, h.day_pnl), ("INFY", 7500.0, 500.0, 100.0))

    def test_login_then_holdings_and_session_reuse(self):
        seen = {"logins": 0, "headers": None, "body": None}

        async def login(request):
            seen["logins"] += 1
            seen["body"] = await request.json()
            seen["headers"] = dict(request.headers)
            return web.json_response({"status": True, "data": {"jwtToken": "JWT", "refreshToken": "R", "feedToken": "F"}})

        async def holdings(request):
            self.assertEqual(request.headers["Authorization"], "Bearer JWT")
            return web.json_response({"status": True, "data": {"holdings": [{"tradingsymbol": "ABB-EQ", "quantity": 1}]}})

        async def run():
            app = web.Application()
            app.router.add_post(angelone.LOGIN_PATH, login)
            app.router.add_get(angelone.HOLDINGS_PATH, holdings)
            async with TestServer(app) as server:
                angelone.BASE_URL = str(server.make_url("")).rstrip("/")
                p = angelone.AngelOneProvider("u", "c")
                p._repo = FakeCredentialRepo(dict(self.CREDS))
                await p.get_holdings()
                return await p.get_holdings()

        rows = asyncio.run(run())
        self.assertEqual(rows[0]["tradingsymbol"], "ABB-EQ")
        self.assertEqual(seen["logins"], 1)
        self.assertEqual(seen["body"]["clientcode"], "A123")
        self.assertEqual(seen["body"]["password"], "1234")
        self.assertEqual(len(seen["body"]["totp"]), 6)
        self.assertEqual(seen["headers"]["X-PrivateKey"], "AK")

    def test_mpin_fallback_when_password_login_is_refused(self):
        async def login(request):
            return web.json_response({"status": False, "message": "switch to MPIN", "errorcode": "AB7001"})

        async def mpin(request):
            body = await request.json()
            self.assertEqual(body["mpin"], "1234")
            return web.json_response({"status": True, "data": {"jwtToken": "J2"}})

        async def run():
            app = web.Application()
            app.router.add_post(angelone.LOGIN_PATH, login)
            app.router.add_post(angelone.LOGIN_MPIN_PATH, mpin)
            async with TestServer(app) as server:
                angelone.BASE_URL = str(server.make_url("")).rstrip("/")
                p = angelone.AngelOneProvider("u", "c")
                p._repo = FakeCredentialRepo(dict(self.CREDS))
                return await p.get_account_status()

        self.assertEqual(asyncio.run(run())["status"], "success")

    def test_bad_login_reports_broker_message(self):
        async def login(request):
            return web.json_response({"status": False, "message": "Invalid totp", "errorcode": "AB1050"})

        async def run():
            app = web.Application()
            app.router.add_post(angelone.LOGIN_PATH, login)
            async with TestServer(app) as server:
                angelone.BASE_URL = str(server.make_url("")).rstrip("/")
                p = angelone.AngelOneProvider("u", "c")
                p._repo = FakeCredentialRepo(dict(self.CREDS))
                return await p.get_account_status()

        res = asyncio.run(run())
        self.assertEqual(res["status"], "auth_required")
        self.assertIn("Invalid totp", res["message"])

    def test_missing_field_is_named(self):
        async def run():
            p = angelone.AngelOneProvider("u", "c")
            p._repo = FakeCredentialRepo({"api_key": "AK"})
            return await p.get_account_status()

        res = asyncio.run(run())
        self.assertIn("client_code", res["message"])


if __name__ == "__main__":
    unittest.main()
