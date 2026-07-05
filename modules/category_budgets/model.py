"""Category budget allocation model."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel, UniqueConstraint


class CategoryBudget(SQLModel, table=True):
    """Per-category allocation of a budget's monthly_limit.

    One allocation per (budget, category) pair, enforced by a unique
    constraint. Deleting the parent budget cascades to its allocations.
    """

    __tablename__: ClassVar[str] = "category_budgets"
    __table_args__ = (
        UniqueConstraint(
            "budget_id",
            "category_id",
            name="uq_category_budgets_budget_id_category_id",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    budget_id: UUID = Field(foreign_key="budgets.id", ondelete="CASCADE")
    category_id: UUID = Field(foreign_key="categories.id")
    allocated_amount: Decimal = Field(max_digits=12, decimal_places=2)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
