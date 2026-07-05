"""Budget router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.budgets import service as budget_service
from modules.budgets.schema import (
    MONTH_PATTERN,
    BudgetCreate,
    BudgetCurrentResponse,
    BudgetResponse,
    BudgetStatusResponse,
    BudgetUpdate,
)
from modules.users.model import User

router = APIRouter(prefix="/trackers/{tracker_id}/budgets", tags=["Budgets"])


@router.get("/current", response_model=BudgetCurrentResponse | None)
def get_current_budget(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    response: Response,
    month: str | None = Query(
        default=None,
        pattern=MONTH_PATTERN,
        description="Month to look up (YYYY-MM); defaults to the current month",
    ),
):
    """Get the budget + computed status for a month in one call.

    Registered before `/{budget_id}` so the literal `current` segment isn't
    matched as a budget UUID. Returns 204 if no budget exists for the month.
    """
    result = budget_service.get_current_budget(
        session, tracker_id, current_user.id, month=month
    )
    if result is None:
        response.status_code = status.HTTP_204_NO_CONTENT
    return result


@router.get("", response_model=list[BudgetResponse])
def list_budgets(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
):
    """List budgets for a tracker workspace, optionally filtered by month."""
    return budget_service.list_budgets(
        session, tracker_id, current_user.id, month=month
    )


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_budget(
    tracker_id: UUID,
    data: BudgetCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a budget in a tracker (one budget per month)."""
    return budget_service.create_budget(session, tracker_id, current_user.id, data)


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget(
    tracker_id: UUID,
    budget_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a single budget the current user owns."""
    return budget_service.get_budget_or_404(
        session, tracker_id, budget_id, current_user.id
    )


@router.get("/{budget_id}/status", response_model=BudgetStatusResponse)
def get_budget_status(
    tracker_id: UUID,
    budget_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get computed spending status for a budget's month."""
    return budget_service.get_budget_status(
        session, tracker_id, budget_id, current_user.id
    )


@router.patch("/{budget_id}", response_model=BudgetResponse)
def update_budget(
    tracker_id: UUID,
    budget_id: UUID,
    data: BudgetUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update a budget the current user owns."""
    return budget_service.update_budget(
        session, tracker_id, budget_id, current_user.id, data
    )


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    tracker_id: UUID,
    budget_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete a budget the current user owns."""
    budget_service.delete_budget(session, tracker_id, budget_id, current_user.id)
