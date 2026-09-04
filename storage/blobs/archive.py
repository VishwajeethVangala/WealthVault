"""Azure Blob Storage Archiving Service.

Archives raw broker API and MCP responses into Azure Blob Storage
for immutable audit trails, debugging, and historical re-normalization.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional, Union
from azure.core.exceptions import HttpResponseError
from azure.storage.blob.aio import BlobServiceClient

from core.config import get_settings

logger = logging.getLogger("wealthvault.storage.blobs.archive")

DEFAULT_CONTAINER = "raw-broker-payloads"


class BlobArchivalService:
    """Asynchronous service for archiving raw broker payloads into Azure Blob Storage."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        container_name: str = DEFAULT_CONTAINER,
    ) -> None:
        self.connection_string = connection_string or get_settings().AZURE_STORAGE_CONNECTION_STRING
        self.container_name = container_name
        self._service_client: Optional[BlobServiceClient] = None
        self._container_initialized = False

    @property
    def service_client(self) -> BlobServiceClient:
        """Return lazily initialized async BlobServiceClient."""
        if self._service_client is None:
            self._service_client = BlobServiceClient.from_connection_string(self.connection_string)
        return self._service_client

    async def _ensure_container(self) -> None:
        """Ensure destination container exists."""
        if not self._container_initialized:
            container_client = self.service_client.get_container_client(self.container_name)
            try:
                await container_client.create_container()
                logger.info("Created blob container: %s", self.container_name)
            except HttpResponseError as exc:
                if exc.status_code != 409:  # 409 Conflict: container already exists
                    raise
            self._container_initialized = True

    async def archive_broker_payload(
        self,
        owner_id: str,
        connection_id: str,
        raw_data: Union[Dict[str, Any], list],
        timestamp: Optional[datetime] = None,
    ) -> str:
        """Archive raw broker payload under {owner_id}/{connection_id}/{YYYY-MM-DD_HHMMSS}.json.

        Args:
            owner_id: User tenant ID.
            connection_id: Identifier of the broker connection.
            raw_data: The raw JSON dictionary or list payload returned by broker/MCP.
            timestamp: Optional datetime, defaults to current UTC time.

        Returns:
            The blob path (e.g., 'raw-broker-payloads/{owner_id}/{connection_id}/2026-09-03_180523.json').
        """
        await self._ensure_container()

        ts = timestamp or datetime.now(timezone.utc)
        formatted_time = ts.strftime("%Y-%m-%d_%H%M%S")
        blob_name = f"{owner_id}/{connection_id}/{formatted_time}.json"

        container_client = self.service_client.get_container_client(self.container_name)
        blob_client = container_client.get_blob_client(blob_name)

        serialized_data = json.dumps(raw_data, indent=2, default=str)

        await blob_client.upload_blob(
            serialized_data,
            overwrite=True,
            content_type="application/json",
        )

        full_path = f"{self.container_name}/{blob_name}"
        logger.info("Archived raw payload to: %s", full_path)
        return full_path

    async def close(self) -> None:
        """Release underlying HTTP client connections."""
        if self._service_client:
            await self._service_client.close()
            self._service_client = None
            self._container_initialized = False

    async def __aenter__(self) -> "BlobArchivalService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# Module-level convenience function
async def archive_broker_payload(
    owner_id: str,
    connection_id: str,
    raw_data: Union[Dict[str, Any], list],
    timestamp: Optional[datetime] = None,
) -> str:
    """Convenience helper to archive a broker payload using the default service."""
    service = BlobArchivalService()
    try:
        return await service.archive_broker_payload(
            owner_id=owner_id,
            connection_id=connection_id,
            raw_data=raw_data,
            timestamp=timestamp,
        )
    finally:
        await service.close()
