"""User service - business logic."""

import logging
import mimetypes
import uuid

from fastapi import HTTPException, UploadFile, status
from sqlmodel import Session

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.core.storage.base import StorageBackend
from modules.users import repo as user_repo
from modules.users.model import User
from modules.users.schema import UserPasswordUpdate, UserProfileUpdate, UserResponse

logger = logging.getLogger(__name__)

_MAX_AVATAR_BYTES = 1 * 1024 * 1024  # 1 MB
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def build_user_response(user: User, storage: StorageBackend) -> UserResponse:
    """Build a UserResponse, converting the stored file key to a presigned URL."""
    avatar_url: str | None = None
    if user.avatar_file_key:
        avatar_url = storage.generate_presigned_url(
            user.avatar_file_key, settings.storage_presign_expiry
        )
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        avatar_url=avatar_url,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def update_profile(session: Session, user: User, data: UserProfileUpdate) -> User:
    if data.email != user.email:
        existing = user_repo.get_user_by_email(session, data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with that email already exists.",
            )
    return user_repo.update_user_profile(session, user, data.name, data.email)


def update_password(session: Session, user: User, data: UserPasswordUpdate) -> User:
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    return user_repo.update_user_password(
        session, user, get_password_hash(data.new_password)
    )


async def upload_avatar(
    session: Session,
    user: User,
    file: UploadFile,
    storage: StorageBackend,
) -> User:
    content_type = file.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{content_type}'. Allowed: JPEG, PNG, WebP, GIF.",
        )

    data = await file.read()
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar must be 1 MB or smaller.",
        )

    ext = mimetypes.guess_extension(content_type) or ".bin"
    if ext == ".jpe":
        ext = ".jpg"  # mimetypes returns .jpe for image/jpeg

    old_file_key = user.avatar_file_key
    file_key = f"{settings.storage_env}/avatars/{user.id}/{uuid.uuid4()}{ext}"

    storage.upload(file_key, data, content_type)

    if old_file_key:
        try:
            storage.delete(old_file_key)
        except Exception:
            logger.warning("Failed to delete old avatar from storage: %s", old_file_key)

    user_repo.set_avatar(session, user, file_key, content_type, len(data))
    return session.get(User, user.id) or user


def delete_avatar(session: Session, user: User, storage: StorageBackend) -> User:
    if user.avatar_file_key:
        try:
            storage.delete(user.avatar_file_key)
        except Exception:
            logger.warning("Failed to delete avatar from storage: %s", user.avatar_file_key)

    return user_repo.remove_avatar(session, user)
