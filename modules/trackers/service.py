"""Tracker service - business logic."""

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel import Session

from modules.trackers import repo as tracker_repo
from modules.trackers.model import Tracker
from modules.trackers.schema import TrackerCreate, TrackerUpdate

logger = logging.getLogger(__name__)


def get_tracker_or_404(
    session: Session, tracker_id: UUID, user_id: UUID
) -> Tracker:
    """Fetch a tracker, enforcing ownership. 404 if missing or not owned."""
    tracker = tracker_repo.get_tracker_by_id(session, tracker_id)
    if not tracker or tracker.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tracker not found"
        )
    return tracker


def list_trackers(session: Session, user_id: UUID) -> list[Tracker]:
    """List every tracker owned by the user."""
    return tracker_repo.list_trackers_by_user(session, user_id)


def create_tracker(
    session: Session, user_id: UUID, data: TrackerCreate
) -> Tracker:
    """Create a tracker for the user."""
    tracker = tracker_repo.create_tracker(session, user_id, data)
    logger.info("Tracker created: %s for user %s", tracker.id, user_id)
    return tracker


def update_tracker(
    session: Session, tracker_id: UUID, user_id: UUID, data: TrackerUpdate
) -> Tracker:
    """Update a tracker the user owns."""
    tracker = get_tracker_or_404(session, tracker_id, user_id)
    return tracker_repo.update_tracker(session, tracker, data)


def delete_tracker(session: Session, tracker_id: UUID, user_id: UUID) -> None:
    """Delete a tracker the user owns."""
    tracker = get_tracker_or_404(session, tracker_id, user_id)
    tracker_repo.delete_tracker(session, tracker)
    logger.info("Tracker deleted: %s for user %s", tracker_id, user_id)