"""User router."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from app.core.storage import get_storage
from app.core.storage.base import StorageBackend
from modules.users import service as user_service
from modules.users.model import User
from modules.users.schema import UserPasswordUpdate, UserProfileUpdate, UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    return user_service.build_user_response(current_user, storage)


@router.patch("/me", response_model=UserResponse)
def update_profile(
    data: UserProfileUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    updated = user_service.update_profile(session, current_user, data)
    return user_service.build_user_response(updated, storage)


@router.patch("/me/password", response_model=UserResponse)
def update_password(
    data: UserPasswordUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    updated = user_service.update_password(session, current_user, data)
    return user_service.build_user_response(updated, storage)


@router.post("/me/avatar", response_model=UserResponse, status_code=status.HTTP_200_OK)
async def upload_avatar(
    file: UploadFile,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    updated = await user_service.upload_avatar(session, current_user, file, storage)
    return user_service.build_user_response(updated, storage)


@router.delete("/me/avatar", response_model=UserResponse)
def remove_avatar(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    storage: Annotated[StorageBackend, Depends(get_storage)],
):
    updated = user_service.delete_avatar(session, current_user, storage)
    return user_service.build_user_response(updated, storage)
