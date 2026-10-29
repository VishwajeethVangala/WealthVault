"""Application configuration using Pydantic BaseSettings.

Loads settings from environment variables and a local .env file.
Adheres to 12-factor application design, preventing secret leakage and
allowing zero-code transition from local ASGI to production Azure App Service.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """WealthVault platform settings and environment configuration."""

    # Environment tier
    ENVIRONMENT: str = Field(default="development", description="Deployment tier (development, staging, production)")

    # Azure Storage Connection
    AZURE_STORAGE_CONNECTION_STRING: str = Field(
        ...,
        description="Azure Storage account connection string for Table and Blob services",
    )

    # API Metadata
    APP_NAME: str = Field(default="WealthVault", description="Application service name")
    APP_VERSION: str = Field(default="0.1.0", description="API Version")
    API_V1_PREFIX: str = Field(default="/api/v1", description="Prefix for V1 REST endpoints")

    # CORS settings
    ALLOWED_ORIGINS: List[str] = Field(
        default=["*"],
        description="Allowed CORS origin hosts",
    )

    # Google Identity & Security
    # In .env: GOOGLE_CLIENT_ID="<your-client-id>.apps.googleusercontent.com"
    GOOGLE_CLIENT_ID: str = Field(
        default="",
        description="Google OAuth 2.0 Client ID for verifying ID tokens",
    )

    # JWT Session Token Configuration
    # In .env: JWT_SECRET="<generate-a-strong-random-secret-key>"
    JWT_SECRET: str = Field(
        default="wealthvault-dev-secret-key-replace-with-strong-key-in-prod",
        description="Secret key used for signing internal JWT tokens",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Algorithm used for signing JWT access tokens",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24 * 7,  # 7 days
        description="JWT access token expiry lifetime in minutes",
    )

    # Encryption key for broker credentials stored in Azure Table Storage (Fernet, urlsafe base64, 32 bytes)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    INDMONEY_CLIENT_ID: str = Field(default="", description="INDmoney MCP OAuth client id")
    INDMONEY_CLIENT_SECRET: str = Field(default="", description="INDmoney MCP OAuth client secret")
    GROWW_CLIENT_ID: str = Field(default="", description="Groww MCP OAuth client id")
    GROWW_CLIENT_SECRET: str = Field(default="", description="Groww MCP OAuth client secret")
    CREDENTIAL_ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet key used to encrypt per-user broker credentials at rest",
    )

    # Where broker sessions and tokens are written. Point at a persistent folder in Azure (e.g. /home/data).
    DATA_DIR: str = Field(default="storage/blobs", description="Directory for broker session and token files")
    # Public https origin of this deployment (no trailing slash); builds the INDmoney OAuth redirect. Blank keeps localhost.
    PUBLIC_BASE_URL: str = Field(default="", description="Public base URL, e.g. https://wealthvault.azurewebsites.net")
    # Fixed outbound public IP registered with Angel One SmartAPI; blank sends this machine's IP
    ANGELONE_PUBLIC_IP: str = Field(default="", description="Static public IP registered with Angel One")
    # Shown on the privacy page as the contact for questions and data requests
    SUPPORT_EMAIL: str = Field(default="", description="Contact email shown on the privacy page")
    # Store-review demo login (off unless both are set); opens one sample account, see core/demo_account.py
    DEMO_USERNAME: str = Field(default="", description="Username of the app-store reviewer demo login")
    DEMO_PASSWORD: str = Field(default="", description="Password of the app-store reviewer demo login")
    # Refresh Momentum Stocks on a timer during NSE market hours (see apps/api/auto_refresh.py).
    # Unset = on in production, off elsewhere (a local server shares the same Azure tables).
    AUTO_REFRESH_ENABLED: Optional[bool] = Field(default=None, description="Run the market-hours auto refresh")
    AUTO_REFRESH_MINUTES: int = Field(default=15, ge=5, le=120, description="Minutes between auto refreshes")
    FCM_SERVICE_ACCOUNT_JSON: str = Field(default="", description="Firebase service account key (JSON) used to send Android push notifications")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @property
    def is_development(self) -> bool:
        """Check if current environment is development."""
        return self.ENVIRONMENT.lower() in ("development", "dev", "local")

    @property
    def is_production(self) -> bool:
        """Check if current environment is production."""
        return self.ENVIRONMENT.lower() in ("production", "prod")


DEFAULT_JWT_SECRET = "wealthvault-dev-secret-key-replace-with-strong-key-in-prod"


def public_base_url() -> str:
    """PUBLIC_BASE_URL as a clean origin: https:// added when only a host was entered, no trailing slash."""
    raw = get_settings().PUBLIC_BASE_URL.strip().rstrip("/")
    if raw and "://" not in raw:
        raw = "https://" + raw
    return raw


def data_dir() -> "Path":
    """Folder for broker session/token files (created on first use)."""
    path = Path(get_settings().DATA_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def production_problems(s: "Settings") -> List[str]:
    """Settings that must not stay at their development defaults in production."""
    problems: List[str] = []
    if s.JWT_SECRET == DEFAULT_JWT_SECRET or len(s.JWT_SECRET) < 32:
        problems.append("JWT_SECRET must be a random secret of at least 32 characters")
    if not s.CREDENTIAL_ENCRYPTION_KEY:
        problems.append("CREDENTIAL_ENCRYPTION_KEY is not set")
    if not s.GOOGLE_CLIENT_ID:
        problems.append("GOOGLE_CLIENT_ID is not set")
    if "*" in s.ALLOWED_ORIGINS:
        problems.append('ALLOWED_ORIGINS must list your site, not "*"')
    return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
