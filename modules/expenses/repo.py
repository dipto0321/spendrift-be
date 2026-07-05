"""Expense repository - data access."""

from datetime import date as date_type
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, func, select

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


def _apply_filters(
    statement,
    tracker_id: UUID,
    *,
    start_date: date_type | None,
    end_date: date_type | None,
    category_ids: list[UUID] | None,
    expense_type: str | None,
    search: str | None,
):
    """Apply the shared WHERE clauses used by both list_expenses and
    count_expenses, so the two can never drift out of sync."""
    statement = statement.where(Expense.tracker_id == tracker_id)

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

    return statement


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
    limit: int = 50,
    offset: int = 0,
) -> list[Expense]:
    """List expenses for a tracker, with optional filters, sorting, paging."""
    statement = _apply_filters(
        select(Expense),
        tracker_id,
        start_date=start_date,
        end_date=end_date,
        category_ids=category_ids,
        expense_type=expense_type,
        search=search,
    )

    if sort == ExpenseSort.DATE_ASC:
        statement = statement.order_by(Expense.date.asc())  # type: ignore[attr-defined]
    else:
        statement = statement.order_by(Expense.date.desc())  # type: ignore[attr-defined]

    statement = statement.offset(offset).limit(limit)

    return list(session.exec(statement).all())


def count_expenses(
    session: Session,
    tracker_id: UUID,
    *,
    start_date: date_type | None = None,
    end_date: date_type | None = None,
    category_ids: list[UUID] | None = None,
    expense_type: str | None = None,
    search: str | None = None,
) -> int:
    """Count expenses matching the same filters as list_expenses (no paging)."""
    statement = _apply_filters(
        select(func.count()).select_from(Expense),
        tracker_id,
        start_date=start_date,
        end_date=end_date,
        category_ids=category_ids,
        expense_type=expense_type,
        search=search,
    )
    return session.exec(statement).one()


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


def sum_expenses_amount(
    session: Session,
    tracker_id: UUID,
    start_date: date_type,
    end_date: date_type,
) -> Decimal:
    """Sum expense amounts for a tracker in [start_date, end_date).

    Simple single-value aggregate kept in the repo so services never
    build SQL directly.
    """
    total = session.exec(
        select(func.sum(Expense.amount))
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.date >= start_date)
        .where(Expense.date < end_date)
    ).one()
    return Decimal(total) if total is not None else Decimal("0")


def sum_expenses_amount_by_category(
    session: Session,
    tracker_id: UUID,
    category_ids: list[UUID],
    start_date: date_type,
    end_date: date_type,
) -> dict[UUID, Decimal]:
    """Sum expense amounts per category for a tracker in [start_date, end_date).

    One grouped query instead of one sum() call per category.
    """
    if not category_ids:
        return {}

    rows = session.exec(
        select(Expense.category_id, func.sum(Expense.amount))
        .where(Expense.tracker_id == tracker_id)
        .where(Expense.category_id.in_(category_ids))  # type: ignore[attr-defined]
        .where(Expense.date >= start_date)
        .where(Expense.date < end_date)
        .group_by(Expense.category_id)  # type: ignore[arg-type]
    ).all()
    return {row[0]: Decimal(row[1]) for row in rows}


def count_expenses_by_category(session: Session, category_id: UUID) -> int:
    """Count expenses currently assigned to a category."""
    return session.exec(
        select(func.count()).select_from(Expense).where(
            Expense.category_id == category_id
        )
    ).one()


def delete_expense(session: Session, expense: Expense) -> None:
    """Delete an expense."""
    session.delete(expense)
    session.commit()
