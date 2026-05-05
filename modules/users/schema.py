"""User schemas."""
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    """User creation schema."""
    
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response schema."""
    
    id: str
    email: EmailStr
    is_active: bool

    class Config:
        from_attributes = True
