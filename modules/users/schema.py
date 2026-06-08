"""User schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    """User creation schema."""

    name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response schema."""

    id: UUID
    name: str
    email: EmailStr
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
