"""Category schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    """Schema for creating a category."""

    name: str = Field(min_length=1, max_length=100)
    color: str = Field(
        pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color, e.g. #22C55E"
    )


class CategoryUpdate(BaseModel):
    """Schema for partially updating a category."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class CategoryResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    tracker_id: UUID
    name: str
    color: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
