"""Expense model."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import ClassVar, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index
from sqlmodel import Column, Field, SQLModel


class Expense(SQLModel, table=True):
    """An expense belongs to a tracker (workspace scope) and a category."""

    __tablename__: ClassVar[str] = "expenses"
    __table_args__ = (
        Index("ix_expenses_tracker_id_date", "tracker_id", "date"),
        Index("ix_expenses_tracker_id_category_id", "tracker_id", "category_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tracker_id: UUID = Field(foreign_key="trackers.id", ondelete="CASCADE")
    category_id: UUID = Field(foreign_key="categories.id", ondelete="RESTRICT")
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    date: date
    description: Optional[str] = Field(default=None, max_length=255)
    type: str = Field(max_length=10)  # "need" | "want"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )
