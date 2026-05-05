"""Auth router."""

import logging
from datetime import timedelta
from typing import Annotated

from app.core.database import get_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
)
from app.middleware.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from modules.auth.schema import LoginSchema, RegisterSchema, TokenResponse
from modules.auth.service import authenticate_user, register_user
from sqlmodel import Session

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

    logger.info(f"User logged in successfully: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
