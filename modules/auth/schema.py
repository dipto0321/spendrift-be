"""Auth schemas."""

from pydantic import BaseModel, Field, EmailStr
from modules.users.schema import UserCreate


class RegisterSchema(UserCreate):
    """User registration schema extending `UserCreate` with validation."""

    password: str = Field(
        min_length=8, description="Password must be at least 8 characters"
    )


class LoginSchema(BaseModel):
    """User login schema."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
