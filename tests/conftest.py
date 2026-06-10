"""Shared pytest fixtures.

Spins up an in-memory SQLite database per test, overrides the `get_session`
dependency so the app and the test setup share the same engine, and provides
authenticated-user / tracker fixtures built through the real service layer.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

# Import every model so SQLModel.metadata is fully populated before create_all.
from modules.categories.model import Category  # noqa: F401
from modules.categories import repo as category_repo
from modules.expenses.model import Expense  # noqa: F401
from modules.refresh_tokens.model import RefreshToken  # noqa: F401
from modules.trackers.model import Tracker
from modules.trackers.schema import TrackerCreate
from modules.trackers import service as tracker_service
from modules.users.model import User

from app.core.database import get_session
from app.core.security import create_access_token, get_password_hash
from app.main import app


@event.listens_for(Engine, "connect")
def _enable_sqlite_fks(dbapi_connection, connection_record):
    """Enforce foreign keys on SQLite (off by default)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(name="engine")
def engine_fixture() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine: Engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine: Engine) -> Generator[TestClient, None, None]:
    def get_session_override() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    # Disable rate limiting in tests; limits are per-IP and every test
    # request comes from the same client address.
    app.state.limiter.enabled = False
    with TestClient(app) as client:
        yield client
    app.state.limiter.enabled = True
    app.dependency_overrides.clear()


def _make_user(session: Session, name: str, email: str) -> User:
    user = User(
        name=name,
        email=email,
        hashed_password=get_password_hash("password123"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="user")
def user_fixture(session: Session) -> User:
    return _make_user(session, "Alice", "alice@example.com")


@pytest.fixture(name="other_user")
def other_user_fixture(session: Session) -> User:
    return _make_user(session, "Bob", "bob@example.com")


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(user: User) -> dict[str, str]:
    return _auth_headers(user)


@pytest.fixture(name="other_auth_headers")
def other_auth_headers_fixture(other_user: User) -> dict[str, str]:
    return _auth_headers(other_user)


@pytest.fixture(name="tracker")
def tracker_fixture(session: Session, user: User) -> Tracker:
    """A tracker owned by `user`, with the 10 default categories seeded."""
    return tracker_service.create_tracker(
        session, user.id, TrackerCreate(name="Main", currency="USD")
    )


@pytest.fixture(name="category_id")
def category_id_fixture(session: Session, tracker: Tracker) -> str:
    """Return the id of a seeded category in `tracker`."""
    categories = category_repo.list_categories_by_tracker(session, tracker.id)
    return str(categories[0].id)
