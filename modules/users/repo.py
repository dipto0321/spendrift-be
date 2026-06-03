"""User repository - data access."""
from uuid import UUID

from modules.users.model import User
from modules.users.schema import UserCreate
from sqlmodel import Session, select


def create_user(session: Session, user_create: UserCreate, password_hash: str) -> User:
    """Create a new user."""
    user = User(
        email=user_create.email,
        hashed_password=password_hash,
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
