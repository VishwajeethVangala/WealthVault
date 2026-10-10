"""WealthVault API routers package."""

from apps.api.routers.accounts import router as accounts_router
from apps.api.routers.analytics import router as analytics_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.health import router as health_router
from apps.api.routers.history import router as history_router
from apps.api.routers.portfolio import router as portfolio_router
from apps.api.routers.signals import router as signals_router
from apps.api.routers.targets import router as targets_router

__all__ = ["health_router", "auth_router", "accounts_router", "portfolio_router", "analytics_router", "targets_router", "history_router", "signals_router"]
