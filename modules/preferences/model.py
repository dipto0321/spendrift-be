"""User preferences model."""

from datetime import datetime, timezone
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel


class UserPreference(SQLModel, table=True):
    """One row per user, holding the Settings > Preferences toggles."""

    __tablename__: ClassVar[str] = "user_preferences"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", unique=True)
    budget_alerts_enabled: bool = Field(default=True)
    weekly_summary_enabled: bool = Field(default=True)
    round_amounts_enabled: bool = Field(default=False)
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
