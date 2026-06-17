"""User models."""

from datetime import datetime, timezone
from typing import ClassVar, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, SQLModel


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=100, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    # Stores the R2/S3 file key for the current avatar (e.g. "dev/avatars/uid/uuid.jpg").
    # Null when no avatar is set. The API always converts this to a presigned URL before
    # returning it to clients — the raw file key is never exposed.
    avatar_file_key: Optional[str] = Field(
        default=None, sa_column=Column("avatar_file_key", Text, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
    )


class UserAvatar(SQLModel, table=True):
    """Tracks uploaded avatar files so old R2 objects can be deleted and metadata kept."""

    __tablename__: ClassVar[str] = "user_avatars"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE", index=True)
    file_key: str = Field(max_length=500)
    content_type: str = Field(max_length=100)
    size_bytes: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )
