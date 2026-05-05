"""User model."""
from uuid import uuid4

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """User model."""
    
    __tablename__ = "users"
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: str(__import__('datetime').datetime.now()), index=True)
