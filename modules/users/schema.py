"""User schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """User creation schema."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str


class UserProfileUpdate(BaseModel):
    """Schema for updating name and/or email."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class UserPasswordUpdate(BaseModel):
    """Schema for changing the current user's password."""

    current_password: str
    new_password: str = Field(min_length=8)


class UserAvatarUpdate(BaseModel):
    """Schema for updating or removing the avatar.

    Set avatar_url to a data-URL string to upload, or null to remove.
    """

    avatar_url: str | None = None


class UserResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    name: str
    email: EmailStr
    is_active: bool
    avatar_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
