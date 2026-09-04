"""Accounts and Broker Connections Router.

Enforces strict multi-tenant isolation:
All operations require authenticated JWT and strictly partition by owner_id (user_id).
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from core.models import BrokerConnection, BrokerConnectionCreate, User
from core.security import decode_access_token, security_scheme
from storage.tables.repositories import BrokerConnectionRepository, UserRepository

logger = logging.getLogger("wealthvault.api.accounts")

router = APIRouter(prefix="/accounts", tags=["Accounts & Broker Connections"])


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> str:
    """FastAPI dependency to extract and validate internal JWT session.

    Returns:
        The validated user_id from the token subject claim ('sub').

    Raises:
        HTTPException: 401 if token is absent, malformed, or expired.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or invalid Bearer token format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token=credentials.credentials)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token missing user identity claim (sub).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id


@router.get(
    "/me",
    response_model=User,
    summary="Get Authenticated User Profile",
    description="Validates current session token and returns caller profile.",
)
async def get_me(
    current_user_id: str = Depends(get_current_user),
) -> User:
    """Return user profile for authenticated session."""
    user_repo = UserRepository()
    try:
        user = await user_repo.get_user(user_id=current_user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found.",
            )
        return user
    finally:
        await user_repo.close()


@router.get(
    "/",
    response_model=List[BrokerConnection],
    summary="List Broker Connections",
    description="Retrieve all broker connection sessions belonging strictly to the authenticated user.",
)
async def list_accounts(
    current_user_id: str = Depends(get_current_user),
) -> List[BrokerConnection]:
    """List broker connections for authenticated caller."""
    repo = BrokerConnectionRepository()
    try:
        connections = await repo.list_connections(owner_id=current_user_id)
        return connections
    finally:
        await repo.close()


@router.post(
    "/",
    response_model=BrokerConnection,
    status_code=status.HTTP_201_CREATED,
    summary="Create Broker Connection",
    description="Establish a new broker connection session partitioned strictly under the authenticated user.",
)
async def create_account(
    payload: BrokerConnectionCreate,
    current_user_id: str = Depends(get_current_user),
) -> BrokerConnection:
    """Create a broker connection for authenticated caller."""
    repo = BrokerConnectionRepository()
    try:
        connection = await repo.create_connection(
            owner_id=current_user_id,
            broker_name=payload.broker_name,
        )
        return connection
    finally:
        await repo.close()


@router.get(
    "/{connection_id}",
    response_model=BrokerConnection,
    summary="Get Broker Connection",
    description="Retrieve a specific connection owned by the authenticated caller.",
)
async def get_account(
    connection_id: str,
    current_user_id: str = Depends(get_current_user),
) -> BrokerConnection:
    """Get single connection with tenant boundary check."""
    repo = BrokerConnectionRepository()
    try:
        connection = await repo.get_connection(
            owner_id=current_user_id,
            connection_id=connection_id,
        )
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Broker connection '{connection_id}' not found.",
            )
        return connection
    finally:
        await repo.close()


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Broker Connection",
    description="Remove a broker connection session owned by the authenticated caller.",
)
async def delete_account(
    connection_id: str,
    current_user_id: str = Depends(get_current_user),
) -> None:
    """Delete connection with tenant boundary check."""
    repo = BrokerConnectionRepository()
    try:
        deleted = await repo.delete_connection(
            owner_id=current_user_id,
            connection_id=connection_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Broker connection '{connection_id}' not found.",
            )
    finally:
        await repo.close()
