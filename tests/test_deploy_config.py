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
