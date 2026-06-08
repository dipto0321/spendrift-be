"""Tracker repository - data access."""

from typing import Sequence
from uuid import UUID

from sqlmodel import Session, select

from modules.trackers.model import Tracker
from modules.trackers.schema import TrackerCreate, TrackerUpdate


def create_tracker(session: Session, user_id: UUID, create: TrackerCreate) -> Tracker:
    """Persist a new tracker for the given `user_id`."""
    tracker = Tracker(
        user_id=user_id,
        name=create.name,
        currency=create.currency,
    )
    session.add(tracker)
    session.commit()
    session.refresh(tracker)
    return tracker


def get_tracker_by_id(session: Session, tracker_id: UUID) -> Tracker | None:
    """Get a tracker by its ID."""
    return session.exec(select(Tracker).where(Tracker.id == tracker_id)).first()


def list_trackers_by_user(session: Session, user_id: UUID) -> Sequence[Tracker]:
    """List all trackers belonging to a user."""
    return session.exec(select(Tracker).where(Tracker.user_id == user_id)).all()


def update_tracker(
    session: Session, tracker: Tracker, update: TrackerUpdate
) -> Tracker:
    """Apply a partial update to an existing tracker."""
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tracker, field, value)
    session.add(tracker)
    session.commit()
    session.refresh(tracker)
    return tracker


def delete_tracker(session: Session, tracker: Tracker) -> None:
    """Delete a tracker."""
    session.delete(tracker)
    session.commit()
