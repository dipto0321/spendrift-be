"""Category router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from modules.categories import service as category_service
from modules.categories.schema import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from modules.users.model import User
from modules.users.router import get_current_user

router = APIRouter(prefix="/trackers/{tracker_id}/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all categories for a tracker workspace."""
    return category_service.list_categories(
        session, tracker_id, current_user.id
    )


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    tracker_id: UUID,
    data: CategoryCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a custom category in a tracker."""
    return category_service.create_category(
        session, tracker_id, current_user.id, data
    )


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    tracker_id: UUID,
    category_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get details of a category."""
    return category_service.get_category_or_404(
        session, tracker_id, category_id, current_user.id
    )


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    tracker_id: UUID,
    category_id: UUID,
    data: CategoryUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update a category's name or color."""
    return category_service.update_category(
        session, tracker_id, category_id, current_user.id, data
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    tracker_id: UUID,
    category_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete a category from a tracker."""
    category_service.delete_category(
        session, tracker_id, category_id, current_user.id
    )
