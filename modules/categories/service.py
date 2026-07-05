"""Category service - business logic."""

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from modules.categories import repo as category_repo
from modules.categories.model import Category
from modules.categories.schema import CategoryCreate, CategoryUpdate
from modules.category_budgets import repo as category_budget_repo
from modules.expenses import repo as expense_repo
from modules.trackers import service as tracker_service

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES = [
    {"name": "Uncategorized", "color": "#78716C"},
    {"name": "Groceries", "color": "#22C55E"},
    {"name": "Transport", "color": "#3B82F6"},
    {"name": "Dining", "color": "#F97316"},
    {"name": "Subscriptions", "color": "#8B5CF6"},
    {"name": "Entertainment", "color": "#EC4899"},
    {"name": "Health", "color": "#14B8A6"},
    {"name": "Shopping", "color": "#EAB308"},
    {"name": "Utilities", "color": "#06B6D4"},
    {"name": "Coffee", "color": "#A855F7"},
]


def get_category_or_404(
    session: Session, tracker_id: UUID, category_id: UUID, user_id: UUID
) -> Category:
    """Fetch a category, enforcing tracker ownership and scope.

    404 if missing, not owned, or not belonging to tracker.
    """
    # Verify tracker ownership
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    # Fetch category and verify it belongs to this tracker
    category = category_repo.get_category_by_id(session, category_id)
    if not category or category.tracker_id != tracker_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Category not found"
        )
    return category


def list_categories(
    session: Session, tracker_id: UUID, user_id: UUID
) -> list[Category]:
    """List all categories for a tracker."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)
    return category_repo.list_categories_by_tracker(session, tracker_id)


def create_category(
    session: Session, tracker_id: UUID, user_id: UUID, data: CategoryCreate
) -> Category:
    """Create a new category in a tracker."""
    tracker_service.get_tracker_or_404(session, tracker_id, user_id)

    # Check for name uniqueness within tracker scope
    existing = category_repo.get_category_by_name(session, tracker_id, data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category with name '{data.name}' already exists in this tracker.",
        )

    category = category_repo.create_category(session, tracker_id, data)
    logger.info(
        "Category created: %s under tracker %s for user %s",
        category.id,
        tracker_id,
        user_id,
    )
    return category


def seed_default_categories(session: Session, tracker_id: UUID) -> None:
    """Seed default categories for a newly created tracker workspace."""
    logger.info("Seeding default categories for tracker: %s", tracker_id)
    for cat in DEFAULT_CATEGORIES:
        category_repo.create_category(
            session,
            tracker_id,
            CategoryCreate(name=cat["name"], color=cat["color"]),
        )


def update_category(
    session: Session,
    tracker_id: UUID,
    category_id: UUID,
    user_id: UUID,
    data: CategoryUpdate,
) -> Category:
    """Update a category in a tracker."""
    category = get_category_or_404(session, tracker_id, category_id, user_id)

    # Check name uniqueness if updated
    if data.name and data.name.lower() != category.name.lower():
        existing = category_repo.get_category_by_name(
            session, tracker_id, data.name
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with name '{data.name}' already exists in this tracker.",
            )

    return category_repo.update_category(session, category, data)


def delete_category(
    session: Session, tracker_id: UUID, category_id: UUID, user_id: UUID
) -> None:
    """Delete a category from a tracker.

    409 if any expenses or budget allocations still reference the category
    (the DB-level RESTRICT would otherwise surface as an opaque 500).
    """
    category = get_category_or_404(session, tracker_id, category_id, user_id)

    expense_count = expense_repo.count_expenses_by_category(session, category_id)
    if expense_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Category has {expense_count} expense(s). "
                "Reassign or delete them first."
            ),
        )

    allocation_count = category_budget_repo.count_by_category(session, category_id)
    if allocation_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Category has {allocation_count} budget allocation(s). "
                "Remove them first."
            ),
        )

    category_repo.delete_category(session, category)
    logger.info(
        "Category deleted: %s from tracker %s by user %s",
        category_id,
        tracker_id,
        user_id,
    )
