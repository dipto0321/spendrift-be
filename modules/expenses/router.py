"""Expense router."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.core.database import get_session
from modules.expenses import service as expense_service
from modules.expenses.schema import (
    ExpenseCreate,
    ExpenseResponse,
    ExpenseSort,
    ExpenseType,
    ExpenseUpdate,
)
from modules.users.model import User
from app.core.security import get_current_user

router = APIRouter(prefix="/trackers/{tracker_id}/expenses", tags=["Expenses"])


def _parse_category_ids(category_ids: str | None) -> list[UUID] | None:
    """Parse a comma-separated category_ids query string into UUIDs."""
    if not category_ids:
        return None
    try:
        return [UUID(c.strip()) for c in category_ids.split(",") if c.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="category_ids must be a comma-separated list of UUIDs",
        ) from exc


@router.get("", response_model=list[ExpenseResponse])
def list_expenses(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    response: Response,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category_ids: str | None = Query(
        default=None, description="Comma-separated category IDs"
    ),
    type: ExpenseType | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: ExpenseSort = Query(default=ExpenseSort.DATE_DESC),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List expenses for a tracker workspace, with optional filters.

    Paginated: returns at most `limit` rows starting at `offset`. The total
    number of matching rows (ignoring limit/offset) is set on the
    X-Total-Count response header so clients can build pagination UI.
    """
    parsed_category_ids = _parse_category_ids(category_ids)
    expense_type = type.value if type else None

    total = expense_service.count_expenses(
        session,
        tracker_id,
        current_user.id,
        start_date=start_date,
        end_date=end_date,
        category_ids=parsed_category_ids,
        expense_type=expense_type,
        search=search,
    )
    response.headers["X-Total-Count"] = str(total)

    return expense_service.list_expenses(
        session,
        tracker_id,
        current_user.id,
        start_date=start_date,
        end_date=end_date,
        category_ids=parsed_category_ids,
        expense_type=expense_type,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    tracker_id: UUID,
    data: ExpenseCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create an expense in a tracker."""
    return expense_service.create_expense(
        session, tracker_id, current_user.id, data
    )


@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    tracker_id: UUID,
    expense_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a single expense the current user owns."""
    return expense_service.get_expense_or_404(
        session, tracker_id, expense_id, current_user.id
    )


@router.patch("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    tracker_id: UUID,
    expense_id: UUID,
    data: ExpenseUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update an expense the current user owns."""
    return expense_service.update_expense(
        session, tracker_id, expense_id, current_user.id, data
    )


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    tracker_id: UUID,
    expense_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete an expense the current user owns."""
    expense_service.delete_expense(
        session, tracker_id, expense_id, current_user.id
    )
