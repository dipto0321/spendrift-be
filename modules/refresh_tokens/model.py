"""Refresh token model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class RefreshToken(SQLModel, table=True):
    __tablename__: ClassVar[str] = "refresh_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    token_hash: str = Field(max_length=128, index=True)
    expires_at: datetime
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    replaced_by_id: Optional[UUID] = Field(
        default=None, foreign_key="refresh_tokens.id"
    )
