"""User repository - data access."""

from uuid import UUID

from sqlmodel import Session, select

from modules.users.model import User
from modules.users.schema import UserCreate


def create_user(session: Session, user_create: UserCreate, password_hash: str) -> User:
    """Create a new user."""
    user = User(
        email=user_create.email, hashed_password=password_hash, name=user_create.name
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user_by_email(session: Session, email: str | None) -> User | None:
    """Get user by email."""
    if email is None:
        return None
    return session.exec(select(User).where(User.email == email)).first()


def get_user_by_id(session: Session, user_id: UUID) -> User | None:
    """Get user by ID."""
    return session.get(User, user_id)


def update_user_profile(session: Session, user: User, name: str, email: str) -> User:
    """Update a user's name and email."""
    user.name = name
    user.email = email
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user_password(session: Session, user: User, new_hashed_password: str) -> User:
    """Replace the user's hashed password."""
    user.hashed_password = new_hashed_password
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user_avatar(session: Session, user: User, avatar_url: str | None) -> User:
    """Set or clear the user's avatar URL."""
    user.avatar_url = avatar_url
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
