"""Tracker schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrackerCreate(BaseModel):
    """Schema for creating a tracker."""

    name: str = Field(max_length=100)
    currency: str = Field(max_length=10)


class TrackerUpdate(BaseModel):
    """Schema for partially updating a tracker."""

    name: str | None = Field(default=None, max_length=100)
    currency: str | None = Field(default=None, max_length=10)


class TrackerResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    name: str
    currency: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True