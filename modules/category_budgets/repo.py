"""Category budget allocation repository - data access."""

from uuid import UUID

from sqlmodel import Session, func, select

from .model import CategoryBudget
from .schema import CategoryAllocationInput


def list_by_budget(session: Session, budget_id: UUID) -> list[CategoryBudget]:
    """List all allocations for a budget."""
    return list(
        session.exec(
            select(CategoryBudget).where(CategoryBudget.budget_id == budget_id)
        ).all()
    )


def count_by_category(session: Session, category_id: UUID) -> int:
    """Count allocations currently assigned to a category."""
    return session.exec(
        select(func.count())
        .select_from(CategoryBudget)
        .where(CategoryBudget.category_id == category_id)
    ).one()


def replace_allocations(
    session: Session, budget_id: UUID, items: list[CategoryAllocationInput]
) -> list[CategoryBudget]:
    """Full replace: delete a budget's existing allocations, insert the new set."""
    for existing in list_by_budget(session, budget_id):
        session.delete(existing)

    rows = [
        CategoryBudget(
            budget_id=budget_id,
            category_id=item.category_id,
            allocated_amount=item.allocated_amount,
        )
        for item in items
    ]
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows
