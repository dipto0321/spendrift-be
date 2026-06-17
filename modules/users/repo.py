"""User repository - data access."""

from uuid import UUID

from sqlmodel import Session, select

from modules.users.model import User, UserAvatar
from modules.users.schema import UserCreate


def create_user(session: Session, user_create: UserCreate, password_hash: str) -> User:
    user = User(
        email=user_create.email, hashed_password=password_hash, name=user_create.name
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_user_by_email(session: Session, email: str | None) -> User | None:
    if email is None:
        return None
    return session.exec(select(User).where(User.email == email)).first()


def get_user_by_id(session: Session, user_id: UUID) -> User | None:
    return session.get(User, user_id)


def update_user_profile(session: Session, user: User, name: str, email: str) -> User:
    user.name = name
    user.email = email
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user_password(session: Session, user: User, new_hashed_password: str) -> User:
    user.hashed_password = new_hashed_password
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# --- avatar ---

def get_current_avatar(session: Session, user_id: UUID) -> UserAvatar | None:
    return session.exec(
        select(UserAvatar).where(UserAvatar.user_id == user_id)
    ).first()


def set_avatar(
    session: Session,
    user: User,
    file_key: str,
    content_type: str,
    size_bytes: int,
) -> UserAvatar:
    """Replace the avatar record and update the file key cache on the user row."""
    existing = get_current_avatar(session, user.id)
    if existing:
        session.delete(existing)
        session.flush()

    avatar = UserAvatar(
        user_id=user.id,
        file_key=file_key,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    session.add(avatar)

    user.avatar_file_key = file_key
    session.add(user)
    session.commit()
    session.refresh(user)
    return avatar


def remove_avatar(session: Session, user: User) -> User:
    """Delete the avatar record and clear the file key on the user row."""
    existing = get_current_avatar(session, user.id)
    if existing:
        session.delete(existing)

    user.avatar_file_key = None
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
