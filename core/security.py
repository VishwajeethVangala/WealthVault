"""Security, tenant validation, and authorization helpers.

Provides building blocks for multi-tenant isolation, Google OAuth ID token verification,
and internal session JWT encoding and decoding.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from fastapi.security import HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
import jwt

from core.config import get_settings

logger = logging.getLogger("wealthvault.core.security")

security_scheme = HTTPBearer(auto_error=False)

# Safe characters for Azure Table partition/row keys (no forward slash, backslash, hash, question mark, control chars)
_DISALLOWED_KEY_CHARS = re.compile(r'[\/\\#?\x00-\x1f\x7f-\x9f]')


def sanitize_key(key: str) -> str:
    """Validate and sanitize Azure Table PartitionKey / RowKey.

    Azure Table storage disallows: /, \\, #, ?, and control characters.
    """
    if not key or not key.strip():
        raise ValueError("Storage key cannot be empty or whitespace.")
    if _DISALLOWED_KEY_CHARS.search(key):
        raise ValueError(
            f"Storage key contains invalid characters (disallowed: /, \\, #, ?, and control characters): '{key}'"
        )
    return key.strip()


def validate_tenant_access(request_user_id: str, target_user_id: str) -> None:
    """Ensure that the authenticated user only accesses their own partition."""
    if request_user_id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access prohibited. Operation denied.",
        )


def verify_google_id_token(credential: str, client_id: Optional[str] = None) -> Dict[str, Any]:
    """Verify a Google OAuth 2.0 ID token and extract user claims.

    Args:
        credential: The raw JWT credential string from Google Sign-In.
        client_id: The expected Google OAuth Client ID (audience).
                   Defaults to settings.GOOGLE_CLIENT_ID if not provided.

    Returns:
        Dictionary of token payload claims (sub, email, name, picture, etc.).

    Raises:
        HTTPException: If the token is invalid, expired, or verification fails.
    """
    settings = get_settings()
    expected_audience = client_id if client_id is not None else (settings.GOOGLE_CLIENT_ID or None)

    try:
        request = google_requests.Request()
        id_info = id_token.verify_oauth2_token(
            id_token=credential,
            request=request,
            audience=expected_audience,
        )
        return id_info
    except ValueError as exc:
        logger.warning("Google ID token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google ID token verification failed: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        logger.error("Unexpected error verifying Google ID token: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate with Google Identity Services.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Encode internal JWT access token with expiration.

    Args:
        data: Claims to encode (e.g., {'sub': user_id, 'email': email}).
        expires_delta: Optional custom token lifetime.

    Returns:
        Signed JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(
        to_encode,
        key=settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate internal JWT access token.

    Args:
        token: Signed JWT access token string.

    Returns:
        Decoded token claims dictionary.

    Raises:
        HTTPException: If token is expired, invalid, or malformed.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            key=settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid JWT access token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
