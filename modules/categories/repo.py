"""Category repository - data access."""

from uuid import UUID

from sqlmodel import Session, select

from .model import Category
from .schema import CategoryCreate, CategoryUpdate


def create_category(
    session: Session, tracker_id: UUID, data: CategoryCreate
) -> Category:
    """Persist a new category for the given tracker."""
    category = Category(
        tracker_id=tracker_id,
        name=data.name,
        color=data.color,
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def get_category_by_id(session: Session, category_id: UUID) -> Category | None:
    """Get a category by its ID."""
    return session.exec(select(Category).where(Category.id == category_id)).first()


def get_category_by_name(
    session: Session, tracker_id: UUID, name: str
) -> Category | None:
    """Get a category by its name within a specific tracker workspace."""
    return session.exec(
        select(Category)
        .where(Category.tracker_id == tracker_id)
        .where(Category.name == name)
    ).first()


def list_categories_by_tracker(
    session: Session, tracker_id: UUID
) -> list[Category]:
    """List all categories belonging to a tracker."""
    return list(
        session.exec(
            select(Category).where(Category.tracker_id == tracker_id)
        ).all()
    )


def update_category(
    session: Session, category: Category, data: CategoryUpdate
) -> Category:
    """Apply a partial update to an existing category."""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, category: Category) -> None:
    """Delete a category."""
    session.delete(category)
    session.commit()
