"""Refresh token service - business logic."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session

from app.core.config import settings
from app.core.security import hash_token
from modules.refresh_tokens import repo as refresh_repo
from modules.refresh_tokens.model import RefreshToken


def store_refresh_token(session: Session, user_id, token: str) -> RefreshToken:
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    return refresh_repo.create_refresh_token(session, user_id, token_hash, expires_at)


def revoke_by_token(session: Session, token: str) -> bool:
    token_hash = hash_token(token)
    rt = refresh_repo.get_refresh_token_by_hash(session, token_hash)
    if not rt:
        return False
    refresh_repo.revoke_refresh_token(session, rt)
    return True


def get_by_token(session: Session, token: str) -> RefreshToken | None:
    token_hash = hash_token(token)
    return refresh_repo.get_refresh_token_by_hash(session, token_hash)


def is_token_usable(rt: RefreshToken) -> bool:
    """A stored refresh token is usable if it is not revoked and not expired."""
    expires_at = rt.expires_at
    if expires_at.tzinfo is None:
        # SQLite returns naive datetimes; stored values are UTC.
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return not rt.revoked and expires_at > datetime.now(timezone.utc)


def mark_replaced(session: Session, rt: RefreshToken, new_token_id: UUID) -> None:
    """Revoke a rotated-out token and link it to its replacement."""
    refresh_repo.mark_replaced(session, rt, new_token_id)
