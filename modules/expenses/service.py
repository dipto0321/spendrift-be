"""Expense service - business logic."""

import logging
from datetime import date as date_type
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from modules.categories import repo as category_repo
from modules.expenses import repo as expense_repo
from modules.expenses.model import Expense
from modules.expenses.schema import (
    ExpenseCreate,
    ExpenseSort,
    ExpenseUpdate,
)
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)


def _validate_category(session: Session, tracker_id: UUID, category_id: UUID) -> None:
    """Ensure the category exists and belongs to this tracker workspace."""
    category = category_repo.get_category_by_id(session, category_id)
    if not category or category.tracker_id != tracker_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category does not belong to this tracker",
        )


def get_expense_or_404(
    session: Session, tracker_id: UUID, expense_id: UUID, user_id: UUID
) -> Expense:
    """Fetch an expense, enforcing tracker ownership and scope.

    404 if missing, not owned, or not belonging to the tracker.
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    expense = expense_repo.get_expense_by_id(session, expense_id)
    if not expense or expense.tracker_id != tracker_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found"
        )
    return expense


def list_expenses(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    *,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    category_ids: list[UUID] | None = None,
    expense_type: str | None = None,
    search: str | None = None,
    sort: ExpenseSort = ExpenseSort.DATE_DESC,
    limit: int = 50,
    offset: int = 0,
) -> list[Expense]:
    """List expenses for a tracker the user owns, with optional filters."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    return expense_repo.list_expenses(
        session,
        tracker_id,
        start_date=start_date,
        end_date=end_date,
        category_ids=category_ids,
        expense_type=expense_type,
        search=search,
        sort=sort,
        limit=limit,
        offset=offset,
    )


def create_expense(
    session: Session, tracker_id: UUID, user_id: UUID, data: ExpenseCreate
) -> Expense:
    """Create an expense in a tracker the user owns."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    _validate_category(session, tracker_id, data.category_id)

    expense = expense_repo.create_expense(session, tracker_id, data)
    logger.info(
        "Expense created: %s under tracker %s for user %s",
        expense.id,
        tracker_id,
        user_id,
    )
    return expense


def update_expense(
    session: Session,
    tracker_id: UUID,
    expense_id: UUID,
    user_id: UUID,
    data: ExpenseUpdate,
) -> Expense:
    """Update an expense the user owns."""
    expense = get_expense_or_404(session, tracker_id, expense_id, user_id)

    if data.category_id is not None and data.category_id != expense.category_id:
        _validate_category(session, tracker_id, data.category_id)

    return expense_repo.update_expense(session, expense, data)


def delete_expense(
    session: Session, tracker_id: UUID, expense_id: UUID, user_id: UUID
) -> None:
    """Delete an expense the user owns."""
    expense = get_expense_or_404(session, tracker_id, expense_id, user_id)
    expense_repo.delete_expense(session, expense)
    logger.info(
        "Expense deleted: %s from tracker %s by user %s",
        expense_id,
        tracker_id,
        user_id,
    )
