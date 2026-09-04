"""Health check endpoint router for WealthVault API.

Verifies API operational status and tests live connectivity to Azure Table Storage.
"""

from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from core.config import Settings, get_settings
from core.types import HealthCheckResponse
from storage.tables.base import BaseTableStorage

logger = logging.getLogger("wealthvault.api.health")

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Application and Storage Health Check",
    description="Returns current API status, environment tier, and verifies async Azure Table Storage connectivity.",
)
async def get_health(settings: Settings = Depends(get_settings)):
    """Perform health verification across platform services."""
    storage_status = "unknown"
    table_connected = False
    error_msg = None

    # Lightweight async probe to Azure Table Storage
    table_storage = BaseTableStorage(table_name="healthprobe")
    try:
        table_connected = await table_storage.check_connection()
        storage_status = "connected" if table_connected else "disconnected"
    except Exception as exc:
        logger.error("Health check storage verification exception: %s", exc, exc_info=True)
        storage_status = "error"
        error_msg = str(exc)
    finally:
        await table_storage.close()

    is_overall_healthy = table_connected
    overall_status = "healthy" if is_overall_healthy else "degraded"

    payload = {
        "status": overall_status,
        "environment": settings.ENVIRONMENT,
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": {
            "tables": {
                "status": storage_status,
                "connected": table_connected,
            }
        },
    }

    if error_msg:
        payload["storage"]["tables"]["error"] = error_msg

    http_status = status.HTTP_200_OK if is_overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=http_status, content=payload)
