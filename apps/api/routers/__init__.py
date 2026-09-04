"""WealthVault API routers package."""

from apps.api.routers.accounts import router as accounts_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.health import router as health_router
from apps.api.routers.portfolio import router as portfolio_router

__all__ = ["health_router", "auth_router", "accounts_router", "portfolio_router"]
