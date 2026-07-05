"""User preferences service - business logic."""

from uuid import UUID

from sqlmodel import Session

from modules.preferences import repo as preferences_repo
from modules.preferences.model import UserPreference
from modules.preferences.schema import PreferencesUpdate


def get_or_create_preferences(session: Session, user_id: UUID) -> UserPreference:
    """Fetch the user's preferences, lazily creating a default row on first read."""
    preference = preferences_repo.get_by_user_id(session, user_id)
    if preference is None:
        preference = preferences_repo.create_default(session, user_id)
    return preference


def update_preferences(
    session: Session, user_id: UUID, data: PreferencesUpdate
) -> UserPreference:
    """Apply a partial update, creating a default row first if none exists."""
    preference = get_or_create_preferences(session, user_id)
    update_data = data.model_dump(exclude_unset=True)
    return preferences_repo.update(session, preference, update_data)
