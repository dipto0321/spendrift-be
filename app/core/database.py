from functools import lru_cache
from typing import Generator

from sqlmodel import Session, create_engine

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine():
    """Create the engine once and reuse it (and its connection pool).

    PostgreSQL only: the test suite builds its own in-memory SQLite
    engine in tests/conftest.py and overrides get_session.
    """
    return create_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session

