"""Refresh token service - business logic."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session

from app.core.config import settings
from app.core.security import hash_token
from modules.refresh_tokens import repo as refresh_repo


def store_refresh_token(session: Session, user_id, token: str):
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


def get_by_token(session: Session, token: str):
    token_hash = hash_token(token)
    return refresh_repo.get_refresh_token_by_hash(session, token_hash)
