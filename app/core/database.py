from typing import Generator

from app.core.config import settings
from sqlmodel import Session, SQLModel, create_engine


def get_engine():
    return create_engine(
        settings.database_url,
        connect_args=(
            {"check_same_thread": False}
            if settings.database_url.startswith("sqlite")
            else {}
        ),
        echo=settings.debug,
        pool_pre_ping=not settings.database_url.startswith("sqlite"),
    )


def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine) as session:
        yield session


def create_db_tables(engine=None) -> None:
    if engine is None:
        engine = get_engine()
    SQLModel.metadata.create_all(engine)
