"""Category schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    """Schema for creating a category."""

    name: str = Field(max_length=100)
    color: str = Field(max_length=50)


class CategoryUpdate(BaseModel):
    """Schema for partially updating a category."""

    name: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=50)


class CategoryResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    tracker_id: UUID
    name: str
    color: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
