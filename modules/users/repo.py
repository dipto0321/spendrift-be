"""User repository - data access."""
from modules.users.model import User
from modules.users.schema import UserCreate
from sqlmodel import Session, select


def create_user(db: Session, user_create: UserCreate, password_hash: str) -> User:
    """Create a new user."""
    user = User(
        email=user_create.email,
        hashed_password=password_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str | None) -> User | None:
    """Get user by email."""
    if email is None:
        return None
    return db.exec(select(User).where(User.email == email)).first()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """Get user by ID."""
    return db.get(User, user_id)
