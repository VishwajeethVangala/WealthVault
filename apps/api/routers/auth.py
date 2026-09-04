"""Google Identity and Authentication Router.

Provides endpoints for verifying Google OAuth ID tokens and issuing internal session JWTs.
"""

import logging
from fastapi import APIRouter, HTTPException, status

from core.config import get_settings
from core.models import GoogleAuthRequest, TokenResponse, User
from core.security import create_access_token, sanitize_key, verify_google_id_token
from storage.tables.repositories import UserRepository

logger = logging.getLogger("wealthvault.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/config",
    summary="Get Public Auth Configuration",
    description="Returns public OAuth client identifiers for Google Identity integration.",
)
async def get_auth_config():
    """Return public client ID configuration."""
    settings = get_settings()
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID,
        "environment": settings.ENVIRONMENT,
    }


@router.post(
    "/google",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate with Google Identity Services",
    description="Verifies the Google OAuth ID token, provisions user if new, and issues an internal JWT session token.",
)
async def authenticate_google(payload: GoogleAuthRequest) -> TokenResponse:
    """Authenticate via Google ID token credential."""
    # 1. Verify Google OAuth token
    id_info = verify_google_id_token(credential=payload.credential)

    google_sub = id_info.get("sub")
    email = id_info.get("email")
    name = id_info.get("name") or id_info.get("given_name") or email.split("@")[0]
    picture = id_info.get("picture")

    if not google_sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google ID token missing essential identity claims (sub, email).",
        )

    # Multi-tenant user_id derived deterministically from Google sub
    user_id = sanitize_key(f"google_{google_sub}")

    user_repo = UserRepository()
    try:
        # 2. Check if user already exists
        user = await user_repo.get_user(user_id=user_id)
        if not user:
            # 3. Create new user entity
            user = User(
                user_id=user_id,
                email=email,
                name=name,
                picture=picture,
            )
            await user_repo.save_user(user=user)
            logger.info("Created new user: %s (%s)", user_id, email)
        else:
            # Update name/picture if changed
            if (picture and user.picture != picture) or (name and user.name != name):
                user.name = name
                user.picture = picture
                await user_repo.save_user(user=user)
    finally:
        await user_repo.close()

    # 4. Generate internal JWT containing user_id in 'sub' claim
    token_claims = {
        "sub": user.user_id,
        "email": user.email,
        "name": user.name,
    }
    access_token = create_access_token(data=token_claims)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user,
    )
