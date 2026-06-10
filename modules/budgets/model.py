"""Budget model."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel, UniqueConstraint


class Budget(SQLModel, table=True):
    """A monthly budget belongs to a tracker (workspace scope).

    One budget per month per tracker, enforced by a unique constraint.
    """

    __tablename__: ClassVar[str] = "budgets"
    __table_args__ = (
        UniqueConstraint("tracker_id", "month", name="uq_budgets_tracker_id_month"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tracker_id: UUID = Field(foreign_key="trackers.id", ondelete="CASCADE")
    name: str = Field(max_length=100)
    monthly_limit: Decimal = Field(max_digits=12, decimal_places=2)
    savings_target: Decimal = Field(max_digits=12, decimal_places=2)
    month: str = Field(max_length=7)  # "YYYY-MM"
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
