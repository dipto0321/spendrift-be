"""User service - business logic."""

import logging

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.security import get_password_hash, verify_password
from modules.users import repo as user_repo
from modules.users.model import User
from modules.users.schema import UserAvatarUpdate, UserPasswordUpdate, UserProfileUpdate

logger = logging.getLogger(__name__)


def update_profile(
    session: Session, user: User, data: UserProfileUpdate
) -> User:
    """Update name and/or email, enforcing email uniqueness."""
    if data.email != user.email:
        existing = user_repo.get_user_by_email(session, data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with that email already exists.",
            )
    return user_repo.update_user_profile(session, user, data.name, data.email)


def update_password(
    session: Session, user: User, data: UserPasswordUpdate
) -> User:
    """Change password after verifying the current one."""
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    return user_repo.update_user_password(
        session, user, get_password_hash(data.new_password)
    )


def update_avatar(
    session: Session, user: User, data: UserAvatarUpdate
) -> User:
    """Set or remove the user's avatar."""
    return user_repo.update_user_avatar(session, user, data.avatar_url)
