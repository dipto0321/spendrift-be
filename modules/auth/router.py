"""Auth router."""

import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
)
from app.middleware.rate_limit import limiter
from modules.auth.schema import LoginSchema, RegisterSchema, TokenResponse
from modules.auth.service import authenticate_user, register_user
from modules.refresh_tokens import service as refresh_service
from modules.refresh_tokens.schema import SignOutRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    signup_data: RegisterSchema,
    session: Annotated[Session, Depends(get_session)],
):
    """Register a new user and return tokens."""
    logger.info(f"Registration attempt for email: {signup_data.email}")

    # Create user through service
    user = register_user(session, signup_data)

    # Create token pair
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(
        data={"sub": user.email},
    )

    # Persist refresh token hash for revocation/rotation
    try:
        refresh_service.store_refresh_token(session, user.id, refresh_token)
    except Exception:
        # non-fatal for now (logging would be better)
        logger.exception("Failed to persist refresh token")

    logger.info(f"User registered successfully: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginSchema,
    session: Annotated[Session, Depends(get_session)],
):
    """Authenticate user and return tokens."""
    logger.info(f"Login attempt for email: {login_data.email}")

    user = authenticate_user(session, login_data.email, login_data.password)
    if not user:
        logger.warning(f"Failed login attempt for email: {login_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create token pair
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(
        data={"sub": user.email},
    )

    # Persist refresh token hash for revocation/rotation
    try:
        refresh_service.store_refresh_token(session, user.id, refresh_token)
    except Exception:
        logger.exception("Failed to persist refresh token")

    logger.info(f"User logged in successfully: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    body: SignOutRequest = Body(...),
):
    """Revoke a refresh token (logout). Expects JSON: {"refresh_token": "..."}."""
    token = body.refresh_token

    # revoke if exists (safe to call even if token unknown)
    try:
        refresh_service.revoke_by_token(session, token)
    except Exception:
        # log but do not reveal details
        logger.exception("Failed to revoke refresh token")

    # clear cookie for browser flow (idempotent)
    response.delete_cookie(
        "refresh_token", path="/", secure=True, httponly=True, samesite="lax"
    )

    return None  # 204 No Content
