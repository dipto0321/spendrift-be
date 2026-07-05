"""Category budget allocation router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.category_budgets import service as category_budget_service
from modules.category_budgets.schema import (
    CategoryAllocationInput,
    CategoryAllocationResponse,
)
from modules.users.model import User

router = APIRouter(
    prefix="/trackers/{tracker_id}/budgets/{budget_id}/category-allocations",
    tags=["Category Budgets"],
)


@router.get("", response_model=list[CategoryAllocationResponse])
def list_allocations(
    tracker_id: UUID,
    budget_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List a budget's per-category allocations with actual spend."""
    return category_budget_service.get_allocations(
        session, tracker_id, budget_id, current_user.id
    )


@router.put("", response_model=list[CategoryAllocationResponse])
def replace_allocations(
    tracker_id: UUID,
    budget_id: UUID,
    data: list[CategoryAllocationInput],
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Replace all of a budget's category allocations in one call (full replace)."""
    return category_budget_service.replace_allocations(
        session, tracker_id, budget_id, current_user.id, data
    )
