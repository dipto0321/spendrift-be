"""Auth router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core.database import get_session
from app.middleware.rate_limit import limiter
from modules.auth.schema import (
    LoginSchema,
    RefreshTokenRequest,
    RegisterSchema,
    TokenResponse,
)
from modules.auth.service import (
    authenticate_user,
    issue_token_pair,
    refresh_token_pair,
    register_user,
)
from modules.refresh_tokens import service as refresh_service
from modules.refresh_tokens.schema import SignOutRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def _mask_email(email: str) -> str:
    """Mask an email for logging: 'dipto@x.com' -> 'd***@x.com'."""
    local, _, domain = email.partition("@")
    masked_local = (local[0] + "***") if local else "***"
    return f"{masked_local}@{domain}"


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
    logger.info(f"Registration attempt for email: {_mask_email(signup_data.email)}")

    user = register_user(session, signup_data)
    tokens, _ = issue_token_pair(session, user)

    logger.info(f"User registered successfully: {user.id}")
    return tokens


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginSchema,
    session: Annotated[Session, Depends(get_session)],
):
    """Authenticate user and return tokens."""
    logger.info(f"Login attempt for email: {_mask_email(login_data.email)}")

    user = authenticate_user(session, login_data.email, login_data.password)
    if not user:
        logger.warning(f"Failed login attempt for email: {_mask_email(login_data.email)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    tokens, _ = issue_token_pair(session, user)

    logger.info(f"User logged in successfully: {user.id}")
    return tokens


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    body: RefreshTokenRequest,
    session: Annotated[Session, Depends(get_session)],
):
    """Exchange a valid refresh token for a new token pair (rotation).

    The presented refresh token is revoked and linked to its replacement.
    Reusing an already-rotated token returns 401.
    """
    return refresh_token_pair(session, body.refresh_token)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
@limiter.exempt
async def sign_out(
    session: Annotated[Session, Depends(get_session)],
    body: SignOutRequest = Body(...),
):
    """Revoke a refresh token (logout). Expects JSON: {"refresh_token": "..."}.

    Always returns 204 so the endpoint cannot be used to probe whether a
    token exists; persistence errors still surface as 500. Exempt from the
    global default rate limit — unlimited, same as before this was added.
    """
    refresh_service.revoke_by_token(session, body.refresh_token)
    return None
