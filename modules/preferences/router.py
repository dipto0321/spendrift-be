"""User preferences router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import get_current_user
from modules.preferences import service as preferences_service
from modules.preferences.schema import PreferencesResponse, PreferencesUpdate
from modules.users.model import User

router = APIRouter()


@router.get("", response_model=PreferencesResponse)
def get_preferences(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get the current user's preferences, creating defaults if never set."""
    return preferences_service.get_or_create_preferences(session, current_user.id)


@router.put("", response_model=PreferencesResponse)
def update_preferences(
    data: PreferencesUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Partially update the current user's preferences."""
    return preferences_service.update_preferences(session, current_user.id, data)
