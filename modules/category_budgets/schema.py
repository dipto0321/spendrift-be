"""Category budget allocation schemas."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryAllocationInput(BaseModel):
    """One category's allocation within a full-replace PUT payload."""

    category_id: UUID
    allocated_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class CategoryAllocationResponse(BaseModel):
    """A category's allocation plus its actual spend for the budget's month."""

    category_id: UUID
    category_name: str
    category_color: str
    allocated_amount: Decimal
    actual_amount: Decimal
    percentage_used: int = Field(
        description="actual_amount / allocated_amount * 100, rounded. Not capped at 100 — overspend is signal, not noise."
    )
