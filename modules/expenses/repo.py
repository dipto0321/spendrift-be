"""Expense repository - data access."""

from datetime import date as date_type
from uuid import UUID

from sqlmodel import Session, select

from .model import Expense
from .schema import ExpenseCreate, ExpenseSort, ExpenseType, ExpenseUpdate


def create_expense(
    session: Session, tracker_id: UUID, data: ExpenseCreate
) -> Expense:
    """Persist a new expense for the given tracker."""
    expense = Expense(
        tracker_id=tracker_id,
        category_id=data.category_id,
        amount=data.amount,
        date=data.date,
        description=data.description,
        type=data.type.value,
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


def get_expense_by_id(session: Session, expense_id: UUID) -> Expense | None:
    """Get an expense by its ID."""
    return session.exec(select(Expense).where(Expense.id == expense_id)).first()


def list_expenses(
    session: Session,
    tracker_id: UUID,
    *,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    category_ids: list[UUID] | None = None,
    expense_type: str | None = None,
    search: str | None = None,
    sort: ExpenseSort = ExpenseSort.DATE_DESC,
) -> list[Expense]:
    """List expenses for a tracker, applying optional filters and sorting."""
    statement = select(Expense).where(Expense.tracker_id == tracker_id)

    if start_date is not None:
        statement = statement.where(Expense.date >= start_date)
    if end_date is not None:
        statement = statement.where(Expense.date <= end_date)
    if category_ids:
        statement = statement.where(Expense.category_id.in_(category_ids))  # type: ignore[attr-defined]
    if expense_type is not None:
        statement = statement.where(Expense.type == expense_type)
    if search:
        statement = statement.where(Expense.description.ilike(f"%{search}%"))  # type: ignore[union-attr]

    if sort == ExpenseSort.DATE_ASC:
        statement = statement.order_by(Expense.date.asc())  # type: ignore[attr-defined]
    else:
        statement = statement.order_by(Expense.date.desc())  # type: ignore[attr-defined]

    return list(session.exec(statement).all())


def update_expense(
    session: Session, expense: Expense, data: ExpenseUpdate
) -> Expense:
    """Apply a partial update to an existing expense."""
    update_data = data.model_dump(exclude_unset=True)
    if "type" in update_data and update_data["type"] is not None:
        # Normalize enum -> stored string value
        update_data["type"] = ExpenseType(update_data["type"]).value
    for field, value in update_data.items():
        setattr(expense, field, value)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return expense


def count_expenses_by_category(session: Session, category_id: UUID) -> int:
    """Count expenses currently assigned to a category."""
    return len(
        session.exec(
            select(Expense).where(Expense.category_id == category_id)
        ).all()
    )


def delete_expense(session: Session, expense: Expense) -> None:
    """Delete an expense."""
    session.delete(expense)
    session.commit()
