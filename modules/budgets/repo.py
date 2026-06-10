"""Budget repository - data access."""

from uuid import UUID

from sqlmodel import Session, select

from .model import Budget
from .schema import BudgetCreate, BudgetUpdate


def create_budget(session: Session, tracker_id: UUID, data: BudgetCreate) -> Budget:
    """Persist a new budget for the given tracker."""
    budget = Budget(
        tracker_id=tracker_id,
        name=data.name,
        monthly_limit=data.monthly_limit,
        savings_target=data.savings_target,
        month=data.month,
    )
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return budget


def get_budget_by_id(session: Session, budget_id: UUID) -> Budget | None:
    """Get a budget by its ID."""
    return session.exec(select(Budget).where(Budget.id == budget_id)).first()


def get_budget_by_month(
    session: Session, tracker_id: UUID, month: str
) -> Budget | None:
    """Get the budget for a given month within a tracker workspace."""
    return session.exec(
        select(Budget)
        .where(Budget.tracker_id == tracker_id)
        .where(Budget.month == month)
    ).first()


def list_budgets_by_tracker(
    session: Session, tracker_id: UUID, month: str | None = None
) -> list[Budget]:
    """List budgets belonging to a tracker, optionally filtered by month."""
    statement = select(Budget).where(Budget.tracker_id == tracker_id)
    if month is not None:
        statement = statement.where(Budget.month == month)
    statement = statement.order_by(Budget.month.desc())  # type: ignore[attr-defined]
    return list(session.exec(statement).all())


def update_budget(session: Session, budget: Budget, data: BudgetUpdate) -> Budget:
    """Apply a partial update to an existing budget."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(budget, field, value)
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return budget


def delete_budget(session: Session, budget: Budget) -> None:
    """Delete a budget."""
    session.delete(budget)
    session.commit()
