"""User router."""

import logging

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from modules.users.schema import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user=Depends(get_current_user),
):
    """Get current user information."""
    return UserResponse.model_validate(current_user)
