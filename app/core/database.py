from functools import lru_cache
from typing import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine():
    """Create the engine once and reuse it (and its connection pool).

    Creating an engine per request would create a new connection pool per
    request, exhausting database connections under load.
    """
    engine = create_engine(
        settings.database_url,
        connect_args=(
            {"check_same_thread": False}
            if settings.database_url.startswith("sqlite")
            else {}
        ),
        echo=settings.debug,
        pool_pre_ping=not settings.database_url.startswith("sqlite"),
    )

    if settings.database_url.startswith("sqlite"):
        # SQLite ships with foreign key enforcement OFF; without this,
        # ondelete="CASCADE"/"RESTRICT" on our models is silently ignored.
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


def create_db_tables(engine=None) -> None:
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)
