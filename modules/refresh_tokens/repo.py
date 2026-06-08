"""Refresh token repository - data access."""

from datetime import datetime
from uuid import UUID

from sqlmodel import Session, select

from modules.refresh_tokens.model import RefreshToken


def create_refresh_token(
    session: Session, user_id: UUID, token_hash: str, expires_at: datetime
) -> RefreshToken:
    rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    session.add(rt)
    session.commit()
    session.refresh(rt)
    return rt


def get_refresh_token_by_hash(session: Session, token_hash: str) -> RefreshToken | None:
    return session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).first()


def revoke_refresh_token(session: Session, rt: RefreshToken) -> None:
    rt.revoked = True
    session.add(rt)
    session.commit()
