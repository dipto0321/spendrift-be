
"""Tracker router."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core.database import get_session
from modules.trackers import service as tracker_service
from modules.trackers.schema import (
    TrackerCreate,
    TrackerResponse,
    TrackerUpdate,
)
from modules.users.model import User
from app.core.security import get_current_user

router = APIRouter()


@router.get("", response_model=list[TrackerResponse])
def list_trackers(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all trackers owned by the current user."""
    return tracker_service.list_trackers(session, current_user.id)


@router.post(
    "", response_model=TrackerResponse, status_code=status.HTTP_201_CREATED
)
def create_tracker(
    data: TrackerCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new tracker."""
    return tracker_service.create_tracker(session, current_user.id, data)


@router.get("/{tracker_id}", response_model=TrackerResponse)
def get_tracker(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get a single tracker the current user owns."""
    return tracker_service.get_tracker_or_404(
        session, tracker_id, current_user.id
    )


@router.patch("/{tracker_id}", response_model=TrackerResponse)
def update_tracker(
    tracker_id: UUID,
    data: TrackerUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update a tracker the current user owns."""
    return tracker_service.update_tracker(
        session, tracker_id, current_user.id, data
    )


@router.delete("/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracker(
    tracker_id: UUID,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Delete a tracker the current user owns."""
    tracker_service.delete_tracker(session, tracker_id, current_user.id)