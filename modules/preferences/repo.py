"""User preferences repository - data access."""

from uuid import UUID

from sqlmodel import Session, select

from .model import UserPreference


def get_by_user_id(session: Session, user_id: UUID) -> UserPreference | None:
    return session.exec(
        select(UserPreference).where(UserPreference.user_id == user_id)
    ).first()


def create_default(session: Session, user_id: UUID) -> UserPreference:
    preference = UserPreference(user_id=user_id)
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference


def update(
    session: Session, preference: UserPreference, data: dict
) -> UserPreference:
    for field, value in data.items():
        setattr(preference, field, value)
    session.add(preference)
    session.commit()
    session.refresh(preference)
    return preference
