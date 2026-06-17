"""User router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.users import service as user_service
from modules.users.model import User
from modules.users.schema import (
    UserAvatarUpdate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get the authenticated user's profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
def update_profile(
    data: UserProfileUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update the authenticated user's name and email."""
    updated = user_service.update_profile(session, current_user, data)
    return UserResponse.model_validate(updated)


@router.patch("/me/password", response_model=UserResponse)
def update_password(
    data: UserPasswordUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Change the authenticated user's password."""
    updated = user_service.update_password(session, current_user, data)
    return UserResponse.model_validate(updated)


@router.patch("/me/avatar", response_model=UserResponse)
def update_avatar(
    data: UserAvatarUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Set or remove the authenticated user's avatar."""
    updated = user_service.update_avatar(session, current_user, data)
    return UserResponse.model_validate(updated)
