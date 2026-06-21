"""Budget schemas."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class SavingsHealth(str, Enum):
    """Traffic-light health of a budget's savings outlook."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class BudgetCreate(BaseModel):
    """Schema for creating a budget."""

    name: str = Field(min_length=1, max_length=100)
    monthly_limit: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    savings_target: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    month: str = Field(pattern=MONTH_PATTERN, description="Format: YYYY-MM")


class BudgetUpdate(BaseModel):
    """Schema for partially updating a budget."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    monthly_limit: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    savings_target: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )
    month: str | None = Field(default=None, pattern=MONTH_PATTERN)


class BudgetResponse(BaseModel):
    """Schema returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tracker_id: UUID
    name: str
    monthly_limit: Decimal
    savings_target: Decimal
    month: str
    created_at: datetime
    updated_at: datetime


class BudgetStatusResponse(BaseModel):
    """Computed spending status for a budget's month."""

    spent: Decimal
    remaining: Decimal
    savings_progress: int = Field(description="0-100")
    savings_health: SavingsHealth
    is_over_budget: bool
