"""Budget threshold alerts service - business logic.

Computed entirely from existing Budgets/CategoryBudgets/Expenses data —
no new table. Reuses the category-spend aggregation already built for
category_budgets rather than duplicating the query.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

from modules.budgets import repo as budget_repo
from modules.budgets import service as budget_service
from modules.categories import repo as category_repo
from modules.category_budgets import repo as category_budget_repo
from modules.expenses import repo as expense_repo
from modules.trackers import service as tracker_service

from .schema import BudgetAlertItem, BudgetAlertLevel

WARNING_THRESHOLD = 80
EXCEEDED_THRESHOLD = 100


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _level_for(percentage: int) -> BudgetAlertLevel:
    if percentage >= EXCEEDED_THRESHOLD:
        return BudgetAlertLevel.EXCEEDED
    if percentage >= WARNING_THRESHOLD:
        return BudgetAlertLevel.WARNING
    return BudgetAlertLevel.OK


def get_budget_alerts(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    month: str | None = None,
) -> list[BudgetAlertItem]:
    """Per-category threshold status (ok/warning/exceeded) for a month.

    Empty list if no budget exists for the month, or the budget has no
    category allocations set up yet.
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    month = month or _current_month()

    budget = budget_repo.get_budget_by_month(session, tracker_id, month)
    if budget is None:
        return []

    allocations = category_budget_repo.list_by_budget(session, budget.id)
    if not allocations:
        return []

    start, end = budget_service.month_bounds(budget.month)
    category_ids = [row.category_id for row in allocations]
    actual_by_category = expense_repo.sum_expenses_amount_by_category(
        session, tracker_id, category_ids, start, end
    )

    result = []
    for row in allocations:
        category = category_repo.get_category_by_id(session, row.category_id)
        actual = actual_by_category.get(row.category_id, Decimal("0"))
        percentage = (
            round(actual / row.allocated_amount * 100)
            if row.allocated_amount > 0
            else 0
        )
        result.append(
            BudgetAlertItem(
                category_id=row.category_id,
                category_name=category.name if category else "",
                spent=actual,
                limit=row.allocated_amount,
                percentage=percentage,
                level=_level_for(percentage),
            )
        )
    return result
