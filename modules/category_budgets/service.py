"""Category budget allocation service - business logic."""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from modules.budgets import service as budget_service
from modules.budgets.model import Budget
from modules.categories import repo as category_repo
from modules.category_budgets import repo as category_budget_repo
from modules.category_budgets.model import CategoryBudget
from modules.category_budgets.schema import (
    CategoryAllocationInput,
    CategoryAllocationResponse,
)
from modules.expenses import repo as expense_repo

logger = logging.getLogger(__name__)


def _validate_category_in_tracker(session: Session, tracker_id: UUID, category_id: UUID) -> None:
    """Ensure the category exists and belongs to this tracker workspace."""
    category = category_repo.get_category_by_id(session, category_id)
    if not category or category.tracker_id != tracker_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category {category_id} does not belong to this tracker",
        )


def _build_response(
    session: Session, tracker_id: UUID, budget: Budget, rows: list[CategoryBudget]
) -> list[CategoryAllocationResponse]:
    if not rows:
        return []

    start, end = budget_service.month_bounds(budget.month)
    category_ids = [row.category_id for row in rows]
    actual_by_category = expense_repo.sum_expenses_amount_by_category(
        session, tracker_id, category_ids, start, end
    )

    result = []
    for row in rows:
        category = category_repo.get_category_by_id(session, row.category_id)
        actual = actual_by_category.get(row.category_id, Decimal("0"))
        percentage_used = (
            round(actual / row.allocated_amount * 100)
            if row.allocated_amount > 0
            else 0
        )
        result.append(
            CategoryAllocationResponse(
                category_id=row.category_id,
                category_name=category.name if category else "",
                category_color=category.color if category else "",
                allocated_amount=row.allocated_amount,
                actual_amount=actual,
                percentage_used=percentage_used,
            )
        )
    return result


def get_allocations(
    session: Session, tracker_id: UUID, budget_id: UUID, user_id: UUID
) -> list[CategoryAllocationResponse]:
    """List a budget's per-category allocations with actual spend."""
    budget = budget_service.get_budget_or_404(session, tracker_id, budget_id, user_id)
    rows = category_budget_repo.list_by_budget(session, budget_id)
    return _build_response(session, tracker_id, budget, rows)


def replace_allocations(
    session: Session,
    tracker_id: UUID,
    budget_id: UUID,
    user_id: UUID,
    items: list[CategoryAllocationInput],
) -> list[CategoryAllocationResponse]:
    """Replace all of a budget's category allocations in one call."""
    budget = budget_service.get_budget_or_404(session, tracker_id, budget_id, user_id)

    seen: set[UUID] = set()
    for item in items:
        if item.category_id in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate category_id {item.category_id} in allocations",
            )
        seen.add(item.category_id)
        _validate_category_in_tracker(session, tracker_id, item.category_id)

    rows = category_budget_repo.replace_allocations(session, budget_id, items)
    logger.info(
        "Category allocations replaced for budget %s: %d entries",
        budget_id,
        len(rows),
    )
    return _build_response(session, tracker_id, budget, rows)
