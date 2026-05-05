"""Auth service - business logic."""
import logging

from app.core.security import get_password_hash, verify_password
from fastapi import HTTPException
from modules.auth.schema import RegisterSchema
from modules.users.model import User
from modules.users.repo import create_user, get_user_by_email
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session

logger = logging.getLogger(__name__)


def register_user(db: Session, user_create: RegisterSchema) -> User:
    """Register a new user."""
    try:
        existing_user = get_user_by_email(db, user_create.email)
        if existing_user:
            raise HTTPException(
                status_code=400, detail="User with this email already exists"
            )

        password_hash = get_password_hash(user_create.password)
        return create_user(db, user_create, password_hash)

    except HTTPException:
        raise

    except IntegrityError as e:
        db.rollback()
        logger.error(
            f"Database integrity error during user registration: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=409, detail="User registration failed due to conflicting data"
        ) from e

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error during user registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=503, detail="Database service temporarily unavailable"
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error during user registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred during registration"
        ) from e


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Authenticate user with email and password."""
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user
