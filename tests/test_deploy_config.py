"""Deployment settings must default to local behaviour and refuse unsafe production values."""

import os

os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")

from core.config import DEFAULT_JWT_SECRET, Settings, production_problems


def _settings(**kw) -> Settings:
    return Settings(AZURE_STORAGE_CONNECTION_STRING="x", _env_file=None, **kw)


def test_defaults_keep_local_behaviour():
    s = _settings()
    assert s.DATA_DIR == "storage/blobs" and s.PUBLIC_BASE_URL == "" and s.ANGELONE_PUBLIC_IP == ""


def test_production_rejects_dev_defaults():
    problems = production_problems(_settings(ENVIRONMENT="production", CREDENTIAL_ENCRYPTION_KEY="", GOOGLE_CLIENT_ID="", JWT_SECRET=DEFAULT_JWT_SECRET, ALLOWED_ORIGINS=["*"]))
    text = " ".join(problems)
    assert "JWT_SECRET" in text and "CREDENTIAL_ENCRYPTION_KEY" in text and "GOOGLE_CLIENT_ID" in text and "ALLOWED_ORIGINS" in text


def test_production_accepts_real_values():
    s = _settings(
        ENVIRONMENT="production",
        JWT_SECRET="x" * 40,
        CREDENTIAL_ENCRYPTION_KEY="k",
        GOOGLE_CLIENT_ID="id.apps.googleusercontent.com",
        ALLOWED_ORIGINS=["https://wv.azurewebsites.net"],
    )
    assert production_problems(s) == [] and s.JWT_SECRET != DEFAULT_JWT_SECRET


def test_public_base_url_sets_the_indmoney_redirect(monkeypatch, tmp_path):
    from core import config
    from core.market_data.indmoney_client import IndmoneyMCPClient

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://wv.azurewebsites.net/")
    config.get_settings.cache_clear()
    try:
        c = IndmoneyMCPClient(connection_id="conn_x")
        assert c.redirect_uri == "https://wv.azurewebsites.net/api/v1/portfolio/oauth/indmoney/callback"
        assert c.tokens_file.parent == tmp_path
    finally:
        config.get_settings.cache_clear()


def test_a_bare_host_in_public_base_url_still_gives_a_valid_redirect(monkeypatch, tmp_path):
    from core import config
    from core.market_data.indmoney_client import IndmoneyMCPClient

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "wealthvault-abc.centralindia-01.azurewebsites.net")
    config.get_settings.cache_clear()
    try:
        c = IndmoneyMCPClient(connection_id="conn_y")
        assert c.redirect_uri == "https://wealthvault-abc.centralindia-01.azurewebsites.net/api/v1/portfolio/oauth/indmoney/callback"
    finally:
        config.get_settings.cache_clear()


def test_deployed_host_registers_its_own_indmoney_client_once(monkeypatch, tmp_path):
    import asyncio

    from core import config
    from core.market_data import indmoney_client as mod

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://wv.example.net")
    monkeypatch.setenv("INDMONEY_CLIENT_ID", "localhost-client")
    config.get_settings.cache_clear()
    mod.IndmoneyMCPClient._instances.clear()

    calls = []

    class _Resp:
        status = 201

        async def json(self, content_type=None):
            return {"client_id": "new-id", "client_secret": "new-secret"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Http:
        def post(self, url, json=None):
            calls.append((url, json))
            return _Resp()

    try:
        a = mod.IndmoneyMCPClient(connection_id="conn_a", owner_id="u1")
        assert a.client_id == ""  # the localhost client is not used on a deployed host
        monkeypatch.setattr(a, "_get_http_session", lambda: _Http())
        asyncio.run(a.ensure_client())
        assert a.client_id == "new-id" and a.client_secret == "new-secret"
        assert calls[0][1]["redirect_uris"] == ["https://wv.example.net/api/v1/portfolio/oauth/indmoney/callback"]
        assert "client_id=new-id" in a.get_authorization_url()

        b = mod.IndmoneyMCPClient(connection_id="conn_b", owner_id="u2")  # another user reuses the saved client
        assert b.client_id == "new-id"
        asyncio.run(b.ensure_client())
        assert len(calls) == 1
    finally:
        config.get_settings.cache_clear()
        mod.IndmoneyMCPClient._instances.clear()
