"""Tracker schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TrackerCreate(BaseModel):
    """Schema for creating a tracker."""

    name: str = Field(min_length=1, max_length=100)
    currency: str = Field(
        min_length=3, max_length=3, description="ISO 4217 code, e.g. USD"
    )

    @field_validator("currency")
    @classmethod
    def _currency_alpha_upper(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()


class TrackerUpdate(BaseModel):
    """Schema for partially updating a tracker."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def _currency_alpha_upper(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v.upper()


class TrackerResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    name: str
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)