"""Shared domain types, aliases, and common data models for WealthVault."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Core Type Aliases
UserId = str
EntityId = str
EntityDict = Dict[str, Any]


class HealthCheckResponse(BaseModel):
    """Schema for API health status check endpoint."""

    status: str = Field(..., description="API operational status: healthy, degraded, or unhealthy")
    environment: str = Field(..., description="Current deployment environment tier")
    app: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    storage: Dict[str, Any] = Field(..., description="Status of backing storage systems")


class TableEntityModel(BaseModel):
    """Base schema for Azure Table Storage entities.

    Enforces strict multi-tenant boundary:
    PartitionKey represents user_id / tenant owner.
    RowKey represents the unique entity identifier.
    """

    PartitionKey: str = Field(..., description="Multi-tenant boundary (User ID / Owner ID)")
    RowKey: str = Field(..., description="Unique entity identifier within the user's partition")
