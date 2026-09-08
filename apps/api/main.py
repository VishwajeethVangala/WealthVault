"""WealthVault API Main Application Entrypoint.

Configures the ASGI application instance, middleware, lifespan lifecycle,
authentication, account management, and unified SPA frontend serving.
Fully compliant with local Uvicorn development and production Gunicorn
deployment on Azure App Service (Linux).
"""

import logging
from pathlib import Path
import sys
from typing import Optional

# Ensure project root is in sys.path when running directly (python apps/api/main.py)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from apps.api.routers import accounts_router, auth_router, health_router, portfolio_router
from core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wealthvault.api")


def _register_frontend_method() -> None:
    """Attach native frontend SPA serving capability to FastAPI."""

    def frontend(
        self: FastAPI,
        path: str = "/",
        directory: str = "dist",
        fallback: str = "index.html",
    ) -> None:
        """Serve client-side single page applications (React/Vite) from local dist directory.

        Registered after API routers so client routes do not swallow API endpoints.
        """
        target_dir = (ROOT_DIR / directory).resolve() if not Path(directory).is_absolute() else Path(directory)
        target_dir.mkdir(parents=True, exist_ok=True)

        fallback_file = target_dir / fallback
        if not fallback_file.exists():
            fallback_file.write_text(
                "<!DOCTYPE html><html><body><h1>WealthVault Frontend Stub</h1></body></html>",
                encoding="utf-8",
            )

        # Mount /assets if Vite assets directory exists
        assets_dir = target_dir / "assets"
        if assets_dir.exists():
            self.mount("/assets", StaticFiles(directory=str(assets_dir)), name="spa_assets")

        @self.get(f"{path.rstrip('/')}/", include_in_schema=False)
        @self.get(path, include_in_schema=False)
        async def serve_root():
            return FileResponse(str(fallback_file))

        @self.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa_route(full_path: str):
            # Check if requesting static asset directly inside dist
            candidate = target_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(str(candidate))
            # Client-side route fallback to index.html
            return FileResponse(str(fallback_file))

    FastAPI.frontend = frontend


_register_frontend_method()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for async startup and shutdown events."""
    settings = get_settings()
    logger.info(
        "Starting %s [Environment: %s, Version: %s]",
        settings.APP_NAME,
        settings.ENVIRONMENT,
        settings.APP_VERSION,
    )
    
    # Initialize persistent Kite MCP bridge
    from core.market_data.kite_client import get_kite_mcp_client
    kite_client = get_kite_mcp_client()
    try:
        asyncio.create_task(kite_client.ensure_connected())
    except Exception as exc:
        logger.warning("Could not pre-initialize Kite MCP bridge: %s", exc)

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)
    try:
        await kite_client.close()
    except Exception as exc:
        logger.debug("Error closing Kite MCP client: %s", exc)


def create_application() -> FastAPI:
    """Factory creating and configuring the ASGI FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="WealthVault Multi-User Financial Intelligence Platform API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    # Health checks available at both root /health and versioned /api/v1/health
    app.include_router(health_router)
    app.include_router(health_router, prefix=settings.API_V1_PREFIX)
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(accounts_router, prefix=settings.API_V1_PREFIX)
    app.include_router(portfolio_router, prefix=settings.API_V1_PREFIX)

    # Native frontend serving attached after all API routers to prevent route swallowing
    app.frontend("/", directory="dist", fallback="index.html")

    return app


app = create_application()


if __name__ == "__main__":
    uvicorn.run(
        "apps.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        app_dir=str(ROOT_DIR),
    )
