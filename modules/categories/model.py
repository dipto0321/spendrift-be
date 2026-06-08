"""Category model."""

from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel, UniqueConstraint


class Category(SQLModel, table=True):
    """A category belongs to a tracker (workspace scope)."""

    __tablename__: ClassVar[str] = "categories"
    __table_args__ = (
        UniqueConstraint("tracker_id", "name", name="uq_categories_tracker_id_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tracker_id: UUID = Field(foreign_key="trackers.id", ondelete="CASCADE")
    name: str = Field(max_length=100)
    color: str = Field(max_length=50)
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
