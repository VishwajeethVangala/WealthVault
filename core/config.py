"""Application configuration using Pydantic BaseSettings.

Loads settings from environment variables and a local .env file.
Adheres to 12-factor application design, preventing secret leakage and
allowing zero-code transition from local ASGI to production Azure App Service.
"""

from functools import lru_cache
from typing import List
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
