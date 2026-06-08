"""Expense schemas."""

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class ExpenseType(str, Enum):
    """Whether an expense was a need or a want."""

    NEED = "need"
    WANT = "want"


class ExpenseSort(str, Enum):
    """Sort order for listing expenses."""

    DATE_ASC = "date_asc"
    DATE_DESC = "date_desc"


class ExpenseCreate(BaseModel):
    """Schema for creating an expense."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category_id: UUID
    date: date_type
    description: str | None = Field(default=None, max_length=255)
    type: ExpenseType


class ExpenseUpdate(BaseModel):
    """Schema for partially updating an expense."""

    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category_id: UUID | None = None
    date: date_type | None = None
    description: str | None = Field(default=None, max_length=255)
    type: ExpenseType | None = None


class ExpenseResponse(BaseModel):
    """Schema returned to clients."""

    id: UUID
    tracker_id: UUID
    category_id: UUID
    amount: Decimal
    date: date_type
    description: str | None
    type: ExpenseType
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
