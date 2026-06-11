"""Auth service - business logic."""
import logging

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from fastapi import HTTPException
from modules.auth.schema import RegisterSchema, TokenResponse
from modules.refresh_tokens import service as refresh_service
from modules.refresh_tokens.model import RefreshToken
from modules.users.model import User
from modules.users.repo import create_user, get_user_by_email
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session

logger = logging.getLogger(__name__)


def register_user(session: Session, user_create: RegisterSchema) -> User:
    """Register a new user."""
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")

    try:
        existing_user = get_user_by_email(session, user_create.email)
        if existing_user:
            raise HTTPException(
                status_code=400, detail="User with this email already exists"
            )

        password_hash = get_password_hash(user_create.password)
        return create_user(session, user_create, password_hash)

    except HTTPException:
        raise

    except IntegrityError as e:
        session.rollback()
        logger.error(
            f"Database integrity error during user registration: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=409, detail="User registration failed due to conflicting data"
        ) from e

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error during user registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=503, detail="Database service temporarily unavailable"
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error during user registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred during registration"
        ) from e


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Authenticate user with email and password."""
    user = get_user_by_email(session, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def issue_token_pair(session: Session, user: User) -> tuple[TokenResponse, RefreshToken]:
    """Create an access/refresh token pair and persist the refresh token hash.

    Raises HTTPException(503) if the refresh token cannot be persisted, so a
    client is never handed a refresh token that cannot later be validated.
    """
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})

    try:
        stored = refresh_service.store_refresh_token(session, user.id, refresh_token)
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Failed to persist refresh token: {e}", exc_info=True)
        raise HTTPException(
            status_code=503, detail="Could not create session, please try again"
        ) from e

    return (
        TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        ),
        stored,
    )


def refresh_token_pair(session: Session, refresh_token: str) -> TokenResponse:
    """Rotate a refresh token: validate, issue a new pair, revoke the old one."""
    credentials_error = HTTPException(
        status_code=401,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_token(refresh_token, expected_type="refresh")
    if token_data is None or token_data.email is None:
        raise credentials_error

    stored = refresh_service.get_by_token(session, refresh_token)
    if stored is None or not refresh_service.is_token_usable(stored):
        # Includes reuse of an already-rotated (revoked) token.
        raise credentials_error

    user = get_user_by_email(session, token_data.email)
    if user is None or not user.is_active or user.id != stored.user_id:
        raise credentials_error

    tokens, new_stored = issue_token_pair(session, user)
    refresh_service.mark_replaced(session, stored, new_stored.id)
    return tokens
