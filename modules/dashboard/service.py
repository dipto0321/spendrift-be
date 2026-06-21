"""Dashboard service - aggregation queries.

Aggregations live here (not in a repo) per the project convention for
report-style queries.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, func, select

from modules.budgets import repo as budget_repo
from modules.budgets import service as budget_service
from modules.categories.model import Category
from modules.dashboard.schema import (
    BudgetSnapshot,
    CategorySpend,
    DashboardResponse,
    NeedsWantsSplit,
)
from modules.expenses.model import Expense
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)

TOP_CATEGORIES_LIMIT = 5


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _needs_wants_split(
    session: Session, tracker_id: UUID, start, end
) -> NeedsWantsSplit:
    rows = session.exec(
        select(Expense.type, func.sum(Expense.amount))
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.date >= start)
        .where(Expense.date < end)
        .group_by(Expense.type)
    ).all()
    totals = {row[0]: Decimal(row[1]) for row in rows}
    needs = totals.get("need", Decimal("0"))
    wants = totals.get("want", Decimal("0"))
    total = needs + wants

    if total > 0:
        needs_pct = round(needs / total * 100)
        wants_pct = 100 - needs_pct
    else:
        needs_pct = wants_pct = 0

    return NeedsWantsSplit(
        needs_total=needs,
        wants_total=wants,
        needs_percentage=needs_pct,
        wants_percentage=wants_pct,
    )


def _top_categories(
    session: Session, tracker_id: UUID, start, end, total_spent: Decimal
) -> list[CategorySpend]:
    rows = session.exec(
        select(
            Category.id,
            Category.name,
            Category.color,
            func.sum(Expense.amount).label("total"),
        )
        .join(Expense, Expense.category_id == Category.id)  # type: ignore[arg-type]
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.date >= start)
        .where(Expense.date < end)
        .group_by(Category.id, Category.name, Category.color)
        .order_by(func.sum(Expense.amount).desc())
        .limit(TOP_CATEGORIES_LIMIT)
    ).all()

    return [
        CategorySpend(
            category_id=row[0],
            name=row[1],
            color=row[2],
            total=Decimal(row[3]),
            percentage=(
                round(Decimal(row[3]) / total_spent * 100) if total_spent > 0 else 0
            ),
        )
        for row in rows
    ]


def _budget_snapshot(
    session: Session, tracker_id: UUID, user_id: UUID, month: str
) -> BudgetSnapshot | None:
    budget = budget_repo.get_budget_by_month(session, tracker_id, month)
    if budget is None:
        return None

    status = budget_service.get_budget_status(
        session, tracker_id, budget.id, user_id
    )
    return BudgetSnapshot(
        budget_id=budget.id,
        name=budget.name,
        monthly_limit=budget.monthly_limit,
        savings_target=budget.savings_target,
        spent=status.spent,
        remaining=status.remaining,
        savings_progress=status.savings_progress,
        savings_health=status.savings_health,
        is_over_budget=status.is_over_budget,
    )


def get_dashboard(
    session: Session, tracker_id: UUID, user_id: UUID, month: str | None = None
) -> DashboardResponse:
    """Build the dashboard summary for one month of a tracker the user owns."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    month = month or _current_month()
    start, end = budget_service.month_bounds(month)

    total_spent, expense_count = session.exec(
        select(func.sum(Expense.amount), func.count())
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.date >= start)
        .where(Expense.date < end)
    ).one()
    total_spent = Decimal(total_spent) if total_spent is not None else Decimal("0")

    return DashboardResponse(
        month=month,
        total_spent=total_spent,
        expense_count=expense_count,
        needs_wants=_needs_wants_split(session, tracker_id, start, end),
        top_categories=_top_categories(
            session, tracker_id, start, end, total_spent
        ),
        budget=_budget_snapshot(session, tracker_id, user_id, month),
    )
