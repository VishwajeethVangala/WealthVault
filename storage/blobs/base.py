"""Asynchronous Azure Blob Storage abstraction.

Wraps azure.storage.blob.aio.BlobServiceClient and provides tenant-scoped blob operations:
- Blob paths are structured with tenant isolation: {user_id}/{blob_name}.
- Uses native async clients with proper resource cleanup.
"""

import logging
from typing import AsyncGenerator, Optional
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.storage.blob.aio import BlobServiceClient, ContainerClient

from core.config import get_settings
from core.security import sanitize_key

logger = logging.getLogger("wealthvault.storage.blobs")


class BaseBlobStorage:
    """Base asynchronous storage client for Azure Blob Storage with tenant scoping."""

    def __init__(
        self,
        container_name: str,
        connection_string: Optional[str] = None,
    ) -> None:
        """Initialize BaseBlobStorage.

        Args:
            container_name: Target Azure Blob container name.
            connection_string: Optional Azure Storage connection string.
        """
        self.container_name = container_name
        self._connection_string = connection_string or get_settings().AZURE_STORAGE_CONNECTION_STRING
        self._service_client: Optional[BlobServiceClient] = None
        self._container_client: Optional[ContainerClient] = None
        self._initialized = False

    @property
    def service_client(self) -> BlobServiceClient:
        """Return lazily initialized BlobServiceClient."""
        if self._service_client is None:
            self._service_client = BlobServiceClient.from_connection_string(
                conn_str=self._connection_string
            )
        return self._service_client

    async def get_container_client(self) -> ContainerClient:
        """Return initialized ContainerClient, creating container if missing."""
        if self._container_client is None:
            self._container_client = self.service_client.get_container_client(self.container_name)

        if not self._initialized:
            try:
                await self._container_client.create_container()
                logger.info("Created blob container: %s", self.container_name)
            except HttpResponseError as exc:
                if exc.status_code != 409:  # 409 Conflict if already exists
                    raise
            self._initialized = True

        return self._container_client

    def _format_blob_name(self, user_id: str, blob_name: str) -> str:
        """Format blob name enforcing user directory hierarchy."""
        valid_user_id = sanitize_key(user_id)
        clean_blob_name = blob_name.lstrip("/")
        return f"{valid_user_id}/{clean_blob_name}"

    async def upload_blob(
        self,
        user_id: str,
        blob_name: str,
        data: bytes,
        overwrite: bool = True,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload raw bytes to user-scoped blob path.

        Args:
            user_id: Tenant user identifier.
            blob_name: Name of target blob within user folder.
            data: Binary payload.
            overwrite: Whether to overwrite existing blob.
            content_type: Optional MIME content type.

        Returns:
            The full scoped blob path.
        """
        scoped_path = self._format_blob_name(user_id, blob_name)
        container = await self.get_container_client()
        blob_client = container.get_blob_client(scoped_path)

        kwargs = {"overwrite": overwrite}
        if content_type:
            from azure.storage.blob import ContentSettings
            kwargs["content_settings"] = ContentSettings(content_type=content_type)

        await blob_client.upload_blob(data, **kwargs)
        return scoped_path

    async def download_blob(self, user_id: str, blob_name: str) -> Optional[bytes]:
        """Download raw bytes from user-scoped blob.

        Args:
            user_id: Tenant user identifier.
            blob_name: Target blob name.

        Returns:
            Binary data or None if not found.
        """
        scoped_path = self._format_blob_name(user_id, blob_name)
        container = await self.get_container_client()
        blob_client = container.get_blob_client(scoped_path)
        try:
            stream = await blob_client.download_blob()
            return await stream.readall()
        except ResourceNotFoundError:
            return None

    async def delete_blob(self, user_id: str, blob_name: str) -> bool:
        """Delete user-scoped blob."""
        scoped_path = self._format_blob_name(user_id, blob_name)
        container = await self.get_container_client()
        blob_client = container.get_blob_client(scoped_path)
        try:
            await blob_client.delete_blob()
            return True
        except ResourceNotFoundError:
            return False

    async def check_connection(self) -> bool:
        """Check Blob storage connectivity."""
        try:
            containers = self.service_client.list_containers(results_per_page=1)
            async for _ in containers:
                break
            return True
        except Exception as exc:
            logger.error("Azure Blob Storage health check failed: %s", exc, exc_info=True)
            return False

    async def close(self) -> None:
        """Close blob service connections."""
        if self._container_client is not None:
            try:
                await self._container_client.close()
            except Exception as exc:
                logger.debug("Error closing container client: %s", exc)
            finally:
                self._container_client = None

        if self._service_client is not None:
            try:
                await self._service_client.close()
            except Exception as exc:
                logger.debug("Error closing blob service client: %s", exc)
            finally:
                self._service_client = None

        self._initialized = False

    async def __aenter__(self) -> "BaseBlobStorage":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
