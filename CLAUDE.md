# FinTracker Backend — Agent Instructions

> This file tells Claude Code / OpenCode / any AI agent exactly how this codebase works.
> Read this before writing any code.

---

## Project at a Glance

**FinTracker** is a personal finance backend. Each user can have multiple **Trackers** (e.g. "Bangladesh Tracker" in BDT, "Europe Tracker" in EUR). Every tracker is an independent workspace with its own expenses, categories, and budgets.

**Stack**: FastAPI · SQLModel · Alembic · PostgreSQL 16 · Pydantic v2 · JWT (Argon2) · SlowAPI · Docker

---

## Current State

| Module     | Status         |
|------------|----------------|
| Auth       | ✅ Complete     |
| Users      | ✅ Complete     |
| Trackers   | ❌ Not started  |
| Categories | ❌ Not started  |
| Expenses   | ❌ Not started  |
| Budgets    | ❌ Not started  |
| Dashboard  | ❌ Not started  |
| Reports    | ❌ Not started  |

---

## The Module Pattern

Every feature lives in `modules/<feature>/` with exactly these files:

```
modules/
└── <feature>/
    ├── model.py    # SQLModel table definition
    ├── schema.py   # Pydantic request/response schemas
    ├── repo.py     # Raw DB queries (no business logic)
    ├── service.py  # Business logic (calls repo)
    └── router.py   # FastAPI routes (calls service)
```

**Data flow**: `router → service → repo → database`

**Rule**: Never import router in service. Never import service in repo. Keep layers strict.

---

## Conventions to Follow

### model.py

- Extend `SQLModel` with `table=True`
- Always use `UUID` PK with `default_factory=uuid4`
- `created_at` and `updated_at` use `datetime` with `default_factory=lambda: datetime.now(timezone.utc)`
- Add `updated_at` with `sa_column=Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))`
- Reference existing: `modules/users/model.py`

```python
# Pattern
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel

class Tracker(SQLModel, table=True):
    __tablename__ = "trackers"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    name: str = Field(max_length=100)
    currency: str = Field(max_length=10)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)),
    )
```

### schema.py

- Separate `Create`, `Update`, `Response` schemas
- `Update` schemas use `Optional` fields (partial updates)
- `Response` schemas always include `id`, `created_at`
- Reference existing: `modules/users/schema.py`, `modules/auth/schema.py`

### repo.py

- Functions receive `session: Session` as first arg
- Return ORM objects or `None` — no HTTPExceptions here
- Use `select()` from sqlmodel, not raw SQL strings
- Keep queries simple — no aggregation in repo (that goes in service or reports)

```python
# Pattern
from sqlmodel import Session, select
from uuid import UUID
from .model import Tracker

def get_tracker_by_id(session: Session, tracker_id: UUID) -> Tracker | None:
    return session.exec(select(Tracker).where(Tracker.id == tracker_id)).first()

def list_trackers_by_user(session: Session, user_id: UUID) -> list[Tracker]:
    return session.exec(select(Tracker).where(Tracker.user_id == user_id)).all()
```

### service.py

- Functions raise `HTTPException` when something goes wrong
- Calls repo for data access
- Handles business rules (ownership check, default seeding, etc.)
- Gets `session` and current `user` as params

```python
# Ownership check pattern — USE THIS EVERYWHERE
def get_tracker_or_404(session: Session, tracker_id: UUID, user_id: UUID) -> Tracker:
    tracker = tracker_repo.get_tracker_by_id(session, tracker_id)
    if not tracker or tracker.user_id != user_id:
        raise HTTPException(status_code=404, detail="Tracker not found")
    return tracker
```

### router.py

- Use `Annotated[Session, Depends(get_session)]` for DB
- Use `Annotated[User, Depends(get_current_user)]` for auth
- Keep route functions thin — delegate to service
- Reference existing: `modules/users/router.py`, `modules/auth/router.py`

```python
# Pattern
from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from typing import Annotated
from app.core.database import get_session
from modules.users.model import User
from app.core.security import get_current_user

router = APIRouter(prefix="/trackers", tags=["Trackers"])

@router.get("", response_model=list[TrackerResponse])
def list_trackers(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return tracker_service.list_trackers(session, current_user.id)
```

---

## Authorization Rule (CRITICAL)

Every endpoint that accesses tracker-scoped data **must** verify ownership:

```python
# ALWAYS do this before any data operation
tracker = tracker_service.get_tracker_or_404(session, tracker_id, current_user.id)
```

Never return data for a `tracker_id` without checking `tracker.user_id == current_user.id`.

---

## Database Rules

- `tracker_id` is the workspace scope for all data tables
- When you add, remove, or rename a model field, update the matching schema/service/repo code and create a new Alembic migration with `make migrations`
- Indexes are defined in Alembic migrations, not in models
- Migrations live in `alembic/versions/` — always generate with `make migrations`
- Use `make upgrade` to apply
- Never edit existing migration files — create a new one

## Git Rules

- Use Conventional Commits for commit messages: `type(scope): summary`
- Keep the subject short, imperative, and lowercase unless the proper noun needs capitals
- Use a body with bullet points when the change spans multiple files or has important context
- Commit reproducible project files together when they belong to the same change, such as `pyproject.toml` and `uv.lock`
- Do not commit local-only editor or environment files unless the change is intentionally shared
- Prefer focused commits: one logical change per commit

---

## API Conventions

- Base: `/api/v1`
- Tracker-scoped resources: `/trackers/{tracker_id}/expenses` etc.
- Responses use snake_case
- Errors follow this format:

  ```json
  { "detail": "Human readable message" }
  ```

- 404 for missing or unauthorized resources (don't reveal existence)
- 422 for validation errors (Pydantic handles automatically)

---

## Default Categories

When a Tracker is created, seed these 10 categories automatically (in service layer):

```python
DEFAULT_CATEGORIES = [
    {"name": "Uncategorized", "color": "#78716C"},
    {"name": "Groceries",     "color": "#22C55E"},
    {"name": "Transport",     "color": "#3B82F6"},
    {"name": "Dining",        "color": "#F97316"},
    {"name": "Subscriptions", "color": "#8B5CF6"},
    {"name": "Entertainment", "color": "#EC4899"},
    {"name": "Health",        "color": "#14B8A6"},
    {"name": "Shopping",      "color": "#EAB308"},
    {"name": "Utilities",     "color": "#06B6D4"},
    {"name": "Coffee",        "color": "#A855F7"},
]
```

---

## What NOT to Do

- ❌ Don't put SQL aggregations in `repo.py` for reports — that belongs in a `service.py` or separate query builder
- ❌ Don't raise `HTTPException` in `repo.py`
- ❌ Don't use `session.query()` (SQLAlchemy 1.x style) — use `select()` from sqlmodel
- ❌ Don't hardcode user_id in any endpoint — always get from `current_user`
- ❌ Don't forget to register new routers in `app/api/v1/api.py`
- ❌ Don't skip the ownership check for tracker-scoped endpoints

---

## Registering a New Module

After creating all files in `modules/<feature>/`, add the router to `app/api/v1/api.py`:

```python
from modules.trackers.router import router as trackers_router
api_router.include_router(trackers_router)
```

---

## Running the Project

```bash
docker-compose up        # Start PostgreSQL
make run                 # Start API (port 8000, hot reload)
make migrations          # Generate Alembic migration
make upgrade             # Apply migrations
make test                # Run pytest
make lint                # ruff + mypy
```

---

## Implementation Order

Follow this sequence — each phase builds on the previous:

1. **Phase 1**: Trackers → Categories (with default seeding)
2. **Phase 2**: Expenses (depends on trackers + categories)
3. **Phase 3**: Budgets (depends on trackers)
4. **Phase 4**: Dashboard + Reports (aggregation queries)
5. **Phase 5**: Tests + Polish

---

*Keep this file updated as the codebase evolves.*
