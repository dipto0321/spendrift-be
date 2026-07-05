"""Budget service - business logic."""

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from modules.budgets import repo as budget_repo
from modules.budgets.model import Budget
from modules.budgets.schema import (
    BudgetCreate,
    BudgetCurrentResponse,
    BudgetStatusResponse,
    BudgetUpdate,
    SavingsHealth,
)
from modules.expenses import repo as expense_repo
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_budget_or_404(
    session: Session, tracker_id: UUID, budget_id: UUID, user_id: UUID
) -> Budget:
    """Fetch a budget, enforcing tracker ownership and scope.

    404 if missing, not owned, or not belonging to this tracker.
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    budget = budget_repo.get_budget_by_id(session, budget_id)
    if not budget or budget.tracker_id != tracker_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )
    return budget


def list_budgets(
    session: Session, tracker_id: UUID, user_id: UUID, month: str | None = None
) -> list[Budget]:
    """List budgets for a tracker the user owns, optionally for one month."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    return budget_repo.list_budgets_by_tracker(session, tracker_id, month=month)


def create_budget(
    session: Session, tracker_id: UUID, user_id: UUID, data: BudgetCreate
) -> Budget:
    """Create a budget in a tracker the user owns (one per month)."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    existing = budget_repo.get_budget_by_month(session, tracker_id, data.month)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A budget for {data.month} already exists in this tracker.",
        )

    budget = budget_repo.create_budget(session, tracker_id, data)
    logger.info(
        "Budget created: %s under tracker %s for user %s",
        budget.id,
        tracker_id,
        user_id,
    )
    return budget


def update_budget(
    session: Session,
    tracker_id: UUID,
    budget_id: UUID,
    user_id: UUID,
    data: BudgetUpdate,
) -> Budget:
    """Update a budget the user owns."""
    budget = get_budget_or_404(session, tracker_id, budget_id, user_id)

    if data.month is not None and data.month != budget.month:
        existing = budget_repo.get_budget_by_month(session, tracker_id, data.month)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A budget for {data.month} already exists in this tracker.",
            )

    return budget_repo.update_budget(session, budget, data)


def delete_budget(
    session: Session, tracker_id: UUID, budget_id: UUID, user_id: UUID
) -> None:
    """Delete a budget the user owns."""
    budget = get_budget_or_404(session, tracker_id, budget_id, user_id)
    budget_repo.delete_budget(session, budget)
    logger.info(
        "Budget deleted: %s from tracker %s by user %s",
        budget_id,
        tracker_id,
        user_id,
    )


def month_bounds(month: str) -> tuple[date, date]:
    """First day of the month and first day of the next month."""
    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def _savings_health(
    spent: Decimal, monthly_limit: Decimal, savings_target: Decimal
) -> SavingsHealth:
    """Traffic-light health, mirroring the frontend's getSavingsHealth."""
    if monthly_limit <= 0:
        return SavingsHealth.YELLOW

    if spent > monthly_limit:
        return SavingsHealth.RED

    remaining = monthly_limit - spent
    spent_percentage = (spent / monthly_limit) * 100

    if savings_target > 0 and remaining >= savings_target:
        return SavingsHealth.GREEN
    if spent_percentage < 80:
        return SavingsHealth.GREEN
    if spent_percentage < 95:
        return SavingsHealth.YELLOW
    return SavingsHealth.RED


def _compute_status(session: Session, tracker_id: UUID, budget: Budget) -> dict:
    """Shared spending-status math for a budget's month.

    Returns a dict of the BudgetStatusResponse/BudgetCurrentResponse
    overlapping fields (spent, remaining, savings_progress, savings_health,
    is_over_budget) so both response shapes can be built from one place.
    """
    start, end = month_bounds(budget.month)
    spent = expense_repo.sum_expenses_amount(session, tracker_id, start, end)

    remaining = budget.monthly_limit - spent

    if budget.savings_target > 0:
        raw_progress = (remaining / budget.savings_target) * 100
        savings_progress = max(0, min(100, round(raw_progress)))
    else:
        # No savings target set: staying within budget counts as on track.
        savings_progress = 100 if remaining >= 0 else 0

    return {
        "spent": spent,
        "remaining": remaining,
        "savings_progress": savings_progress,
        "savings_health": _savings_health(
            spent, budget.monthly_limit, budget.savings_target
        ),
        "is_over_budget": spent > budget.monthly_limit,
    }


def get_budget_status(
    session: Session, tracker_id: UUID, budget_id: UUID, user_id: UUID
) -> BudgetStatusResponse:
    """Compute spending status for a budget's month."""
    budget = get_budget_or_404(session, tracker_id, budget_id, user_id)
    return BudgetStatusResponse(**_compute_status(session, tracker_id, budget))


def get_current_budget(
    session: Session,
    tracker_id: UUID,
    user_id: UUID,
    month: str | None = None,
) -> BudgetCurrentResponse | None:
    """Fetch the budget for a month (default: current UTC month) plus its
    computed status in one call, avoiding a list-then-status round trip.

    Returns None if no budget exists for that month.
    """
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    month = month or _current_month()

    budget = budget_repo.get_budget_by_month(session, tracker_id, month)
    if budget is None:
        return None

    return BudgetCurrentResponse(
        id=budget.id,
        tracker_id=budget.tracker_id,
        name=budget.name,
        monthly_limit=budget.monthly_limit,
        savings_target=budget.savings_target,
        month=budget.month,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
        **_compute_status(session, tracker_id, budget),
    )
