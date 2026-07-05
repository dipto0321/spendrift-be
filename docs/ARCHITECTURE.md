# Spendrift Backend — Architecture Documentation

---

## 1. Overview

Spendrift is a personal finance tracking application with a tracker-based architecture. Each tracker is an independent financial workspace (e.g., Bangladesh Tracker in BDT, Europe Tracker in EUR) containing its own expenses, categories, budgets, and reports.

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python >=3.11) |
| ORM | SQLModel (SQLAlchemy 2.0 under the hood) |
| Migrations | Alembic |
| Database | PostgreSQL 18 |
| Auth | JWT (access + refresh tokens) + Argon2 password hashing |
| Validation | Pydantic v2 |
| Rate Limiting | SlowAPI (IP-based) |
| Containerization | Docker + Docker Compose |

### Current State

| Module | Status |
|---|---|
| Auth (register, login, refresh) | ✅ Complete |
| Users (profile) | ✅ Complete |
| Trackers | ✅ Complete |
| Categories | ✅ Complete |
| Expenses | ✅ Complete |
| Budgets | ✅ Complete |
| Dashboard | ✅ Complete |
| Reports | ✅ Complete |

---

## 2. Project Structure

```
backend/
├── alembic/                          # Database migrations (11 revisions)
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
│
├── app/                              # Core application
│   ├── main.py                       # FastAPI app factory, middleware, health probes
│   ├── api/
│   │   └── v1/
│   │       └── api.py                # v1 router aggregation
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings (env vars)
│   │   ├── database.py               # SQLModel engine + session factory
│   │   ├── logging_config.py         # Structured logging (JSON/Text)
│   │   ├── security.py               # JWT encode/decode, Argon2 hashing, get_current_user
│   │   └── storage/                  # S3-compatible object storage (avatars)
│   │       ├── base.py               # StorageBackend Protocol
│   │       └── s3.py                 # S3StorageBackend (R2/MinIO/AWS)
│   └── middleware/
│       └── rate_limit.py             # SlowAPI rate limiter (auth routes only)
│
├── modules/                          # Feature modules (one folder per domain)
│   ├── auth/                         # register, login, refresh, sign-out
│   ├── refresh_tokens/               # hashed refresh token storage + rotation chain
│   ├── users/                        # profile, password, avatar upload
│   ├── trackers/                     # workspace CRUD + default category seeding
│   ├── categories/                   # per-tracker category CRUD
│   ├── expenses/                     # per-tracker expense CRUD + filtering
│   ├── budgets/                      # per-tracker monthly budgets + status calc
│   ├── dashboard/                    # per-tracker month summary (aggregation only)
│   └── reports/                      # summary/spending/breakdown/year-comparison (aggregation only)
│
├── tests/                            # Pytest suite (SQLite in-memory), one file per module
├── docs/
│   ├── ARCHITECTURE.md
│   └── screenshots/
│
├── docker-compose.yml                # PostgreSQL 18 + API service
├── Dockerfile                        # Python 3.14-slim
├── Makefile                          # Dev commands
├── pyproject.toml                    # Dependencies (requires-python >=3.11)
├── .env.example                      # Template for local .env
└── README.md
```

---

## 3. Database Schema

### ER Diagram

```
┌─────────────────────────┐
│         users           │
├─────────────────────────┤
│ id              UUID PK │
│ name           VARCHAR  │← indexed
│ email          VARCHAR  │← unique, indexed
│ hashed_password VARCHAR │
│ is_active       BOOLEAN │← default: true
│ avatar_file_key TEXT?   │← R2/S3 key, null if no avatar (never exposed raw)
│ updated_at    DATETIME  │← auto (onupdate)
│ created_at    DATETIME  │← indexed, auto
└────────────┬────────────┘
             │ 1:N
             ├───────────────────────────────┐
             ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│     refresh_tokens      │     │      user_avatars       │
├─────────────────────────┤     ├─────────────────────────┤
│ id              UUID PK │     │ id              UUID PK │
│ user_id        UUID FK  │→    │ user_id        UUID FK  │→ users.id (CASCADE)
│ token_hash     VARCHAR  │← idx│ file_key       VARCHAR  │
│ expires_at    DATETIME  │     │ content_type   VARCHAR  │
│ revoked        BOOLEAN  │← default: false │ size_bytes  INT │
│ replaced_by_id UUID?    │← self-FK, rotation chain
│ created_at    DATETIME  │     │ created_at    DATETIME  │
└─────────────────────────┘     └─────────────────────────┘
             (audit trail of uploaded avatar files, for storage cleanup)

┌─────────────────────────┐
│        trackers         │
├─────────────────────────┤
│ id              UUID PK │
│ user_id        UUID FK  │→ users.id
│ name           VARCHAR  │
│ currency       VARCHAR  │
│ updated_at    DATETIME  │
│ created_at    DATETIME  │
└────────────┬────────────┘
             │ 1:N
             ├───────────────────────────────┐
             ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│       categories        │     │        budgets          │
├─────────────────────────┤     ├─────────────────────────┤
│ id              UUID PK │     │ id              UUID PK │
│ tracker_id     UUID FK  │→    │ tracker_id     UUID FK  │→ trackers.id
│ name           VARCHAR  │     │ name           VARCHAR  │
│ color          VARCHAR  │     │ monthly_limit   NUMERIC │
│ created_at    DATETIME  │     │ savings_target  NUMERIC │
│ UNIQUE(tracker_id,name) │     │ month          VARCHAR  │← "YYYY-MM"
└────────────┬────────────┘     │ created_at    DATETIME  │
             │ 1:N              │ updated_at    DATETIME  │
             ▼                  │ UNIQUE(tracker_id,month) │
┌─────────────────────────┐     └─────────────────────────┘
│        expenses         │
├─────────────────────────┤
│ id              UUID PK │
│ tracker_id     UUID FK  │→ trackers.id (CASCADE)
│ category_id    UUID FK  │→ categories.id (RESTRICT)
│ amount         NUMERIC(12,2) │
│ date            DATE    │
│ description   VARCHAR(255)? │
│ type          VARCHAR(10)│← "need" | "want"
│ created_at    DATETIME  │
│ updated_at    DATETIME  │
└─────────────────────────┘
```

### Relationships

| Parent | Child | FK Column | On Delete |
|---|---|---|---|
| users | refresh_tokens | `user_id` | CASCADE |
| users | user_avatars | `user_id` | CASCADE |
| users | trackers | `user_id` | (no cascade set) |
| trackers | categories | `tracker_id` | CASCADE |
| trackers | expenses | `tracker_id` | CASCADE |
| trackers | budgets | `tracker_id` | CASCADE |
| categories | expenses | `category_id` | RESTRICT (blocked at service layer with 409 before it can surface as a DB error) |

### Indexes

| Table | Column(s) | Purpose |
|---|---|---|
| users | `email` | Unique login lookup |
| users | `name`, `created_at` | Lookup / ordering |
| refresh_tokens | `token_hash` | Token lookup for refresh/validation |
| user_avatars | `user_id` | List a user's avatar history |
| categories | `tracker_id` + `UNIQUE(tracker_id, name)` | List + enforce unique category names per tracker |
| expenses | `tracker_id`, `date` | Date-range queries per tracker |
| expenses | `tracker_id`, `category_id` | Category filter queries |
| budgets | `UNIQUE(tracker_id, month)` | One budget per tracker per month |

### Multi-Tenancy Pattern

Every data table (except `users` and `refresh_tokens`) includes a `tracker_id`. The active tracker acts as a **workspace scope**. All API queries are filtered by `tracker_id`, ensuring data isolation between trackers.

```
user ──→ tracker ──→ { expenses, categories, budgets }
```

The API validates that the requested `tracker_id` belongs to the authenticated user before any data operation.

### Model Change Rule

When a model field is added, removed, or renamed, update the matching schema, service, and repo code, then create a new Alembic migration with `make migrations`. Do not edit existing migration files.

### Git Rules

Use Conventional Commits for repository changes: `type(scope): summary`. Keep the subject short and imperative, and add a body with bullet points when the change spans multiple files or needs extra context. Commit reproducible files together when they belong to the same change, such as `pyproject.toml` and `uv.lock`, and avoid committing local-only editor or environment files unless the change is meant to be shared.

---

## 4. API Endpoints

### Base URL

```
http://localhost:8000/api/v1
```

### Auth

| Method | Path | Body | Response | Auth | Rate Limit |
|---|---|---|---|---|---|
| POST | `/auth/register` | `{ name, email, password }` | `{ access_token, refresh_token, token_type }` (201) | No | 3/min |
| POST | `/auth/login` | `{ email, password }` | `{ access_token, refresh_token, token_type }` | No | 5/min |
| POST | `/auth/refresh` | `{ refresh_token }` | `{ access_token, refresh_token, token_type }` | Refresh token | 10/min |
| POST | `/auth/sign-out` | `{ refresh_token }` | — (204, always, anti-enumeration) | No | unlimited |

`ALLOW_REGISTRATION=false` disables `/auth/register` (403) without touching other routes — a kill switch for deployments where sign-ups should be closed.

### Users

| Method | Path | Body | Response | Auth |
|---|---|---|---|---|
| GET | `/users/me` | — | `{ id, name, email, is_active, avatar_url, created_at, updated_at }` | Yes |
| PATCH | `/users/me` | `{ name, email }` | Same as above | Yes |
| PATCH | `/users/me/password` | `{ current_password, new_password }` | Same as above | Yes |
| POST | `/users/me/avatar` | multipart file upload | Same as above | Yes |
| DELETE | `/users/me/avatar` | — | Same as above | Yes |

Avatar uploads are capped at 1MB, restricted to `jpeg`/`png`/`webp`/`gif`, and stored in S3-compatible object storage (`app/core/storage/`). `avatar_url` is always a presigned URL or `null` — the raw storage key is never returned to clients.

### Trackers

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers` | — | `[{ id, name, currency, created_at, updated_at }]` | Yes |
| GET | `/trackers/:id` | — | `{ id, name, currency, created_at, updated_at }` | Yes |
| POST | `/trackers` | `{ name, currency }` | Same as above (201) | Yes |
| PATCH | `/trackers/:id` | `{ name?, currency? }` | Same as above | Yes |
| DELETE | `/trackers/:id` | — | — (204) | Yes |

> On tracker creation, 10 default categories are seeded automatically.

### Categories

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/categories` | — | `[{ id, tracker_id, name, color }]` | Yes |
| POST | `/trackers/:trackerId/categories` | `{ name, color }` | Same as above (201) | Yes |
| GET | `/trackers/:trackerId/categories/:id` | — | Same as above | Yes |
| PATCH | `/trackers/:trackerId/categories/:id` | `{ name?, color? }` | Same as above | Yes |
| DELETE | `/trackers/:trackerId/categories/:id` | — | — (204) | Yes |

> Category names are unique per tracker (400 on duplicate). Delete returns **409** if any expense still references the category — the caller must reassign or delete those expenses first (no automatic reassignment).

### Expenses

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/expenses` | Query params (see below) | `[{ id, tracker_id, category_id, amount, date, description, type }]` | Yes |
| POST | `/trackers/:trackerId/expenses` | `{ amount, category_id, date, description?, type }` | Same as above (201) | Yes |
| GET | `/trackers/:trackerId/expenses/:id` | — | Same as above | Yes |
| PATCH | `/trackers/:trackerId/expenses/:id` | Partial expense object | Same as above | Yes |
| DELETE | `/trackers/:trackerId/expenses/:id` | — | — (204) | Yes |

**GET /expenses Query Parameters:**

| Param | Type | Example | Description |
|---|---|---|---|
| `start_date` | date | `2026-05-01` | Date range start (inclusive) |
| `end_date` | date | `2026-05-31` | Date range end (inclusive) |
| `category_ids` | string | `uuid1,uuid2` | Comma-separated category IDs |
| `type` | string | `need` | Filter by expense type (`need`/`want`) |
| `search` | string | `groceries` | Description text search |
| `sort` | string | `date_desc` | `date_asc` or `date_desc` (default `date_desc`) |
| `limit` | int | `50` | 1-200, default 50 |
| `offset` | int | `0` | Pagination offset, default 0 |

`amount` must be `> 0`; `category_id` must belong to the same tracker as the expense (else 400).

### Budgets

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/budgets` | `?month=YYYY-MM` (optional filter) | `[{ id, tracker_id, name, monthly_limit, savings_target, month, created_at, updated_at }]` | Yes |
| POST | `/trackers/:trackerId/budgets` | `{ name, monthly_limit, savings_target, month }` | Same as above (201) | Yes |
| GET | `/trackers/:trackerId/budgets/:id` | — | Same as above | Yes |
| GET | `/trackers/:trackerId/budgets/:id/status` | — | Budget status object (below) | Yes |
| GET | `/trackers/:trackerId/budgets/current` | `?month=YYYY-MM` (default: current UTC month) | Budget + status merged (below), or 204 if none for that month | Yes |
| PATCH | `/trackers/:trackerId/budgets/:id` | Partial budget object | Same as budget response | Yes |
| DELETE | `/trackers/:trackerId/budgets/:id` | — | — (204) | Yes |

One budget per `(tracker_id, month)` — duplicate `month` on create returns 400. `monthly_limit > 0`, `savings_target >= 0`.

`/current` combines the list-then-status waterfall (list budgets, find the one for the month, fetch its status) into one call. It's registered before `/:id` so the literal `current` segment isn't matched as a budget UUID.

**Budget Status Object (computed server-side):**

```json
{
  "spent": 1267.42,
  "remaining": 1232.58,
  "savings_progress": 85,
  "savings_health": "green",
  "is_over_budget": false
}
```

**Savings Health Rules:**

| Condition | Health |
|---|---|
| `spent > monthly_limit` | `red` (Over Budget) |
| `remaining >= savings_target` | `green` (On Track) |
| `spent < 80% of limit` | `green` (On Track) |
| `spent < 95% of limit` | `yellow` (Caution) |
| Otherwise | `red` (Over Budget) |

### Dashboard

| Method | Path | Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/dashboard` | `?month=YYYY-MM` (default: current UTC month) | Dashboard summary object | Yes |

**Dashboard Summary Object** (aggregation only, no `model.py` — matches `modules/dashboard/schema.py::DashboardResponse`):

```json
{
  "month": "2026-07",
  "total_spent": 1267.42,
  "expense_count": 34,
  "needs_wants": {
    "needs_total": 850.00,
    "wants_total": 417.42,
    "needs_percentage": 67,
    "wants_percentage": 33
  },
  "top_categories": [
    { "category_id": "...", "name": "Groceries", "color": "#22C55E", "total": 320.10, "percentage": 25 }
  ],
  "budget": {
    "budget_id": "...", "name": "July", "monthly_limit": 2000.00, "savings_target": 500.00,
    "spent": 1267.42, "remaining": 732.58, "savings_progress": 85,
    "savings_health": "green", "is_over_budget": false
  }
}
```

`budget` is `null` if no budget exists for the requested month. `top_categories` returns at most 5 entries, largest spend first.

### Reports

All under `/trackers/:trackerId/reports` (also aggregation only, no `model.py`):

| Method | Path | Query | Response |
|---|---|---|---|
| GET | `/summary` | `start_date`, `end_date` | `{ total, min, max, avg, count }` |
| GET | `/spending` | `period` (`weekly`\|`monthly`\|`yearly`, default `monthly`), `start_date`, `end_date` | `[{ label, total, count }]` |
| GET | `/category-breakdown` | `start_date`, `end_date` | `[{ category_id, category_name, category_color, total, percentage, count }]` (largest first) |
| GET | `/needs-vs-wants` | `start_date`, `end_date` | `{ needs_total, wants_total, needs_percentage, wants_percentage }` |
| GET | `/year-comparison` | — | `[{ year, total, avg, count }]` (avg = total/12, ascending by year) |

All endpoints require auth (Yes). `end_date < start_date` → 400. `label` in `/spending` is the ISO Monday date for `weekly`, `YYYY-MM` for `monthly`, `YYYY` for `yearly`. Per-day totals are aggregated in SQL, then bucketed in Python so the same code runs against Postgres and SQLite (tests).

---

## 5. Authentication Flow

```
┌──────────┐                                      ┌──────────┐
│  Client  │                                      │  Server  │
└────┬─────┘                                      └────┬─────┘
     │                                                  │
      │  POST /auth/login                                  │
      │  { email, password }                              │
     │ ──────────────────────────────────────────────►   │
     │                                                   │  Verify credentials
     │                                                   │  Generate access_token (30min)
     │                                                   │  Generate refresh_token (7 days)
     │                                                   │  Store refresh_token hash in DB
     │  ◄──────────────────────────────────────────────  │
     │  { access_token, refresh_token, token_type }      │
     │                                                   │
     │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
     │                                                   │
     │  GET /trackers                                    │
     │  Authorization: Bearer <access_token>             │
     │ ──────────────────────────────────────────────►   │
     │                                                   │  Decode JWT, check type="access"
     │                                                   │  Look up user by email (sub claim)
     │                                                   │  Execute query
     │  ◄──────────────────────────────────────────────  │
     │  { data: [...] }                                  │
     │                                                   │
     │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─    │
     │                                                   │
     │  (access_token expires)                           │
     │                                                   │
     │  POST /auth/refresh                               │
     │  { refresh_token }                                │
     │ ──────────────────────────────────────────────►   │
     │                                                   │  Verify token hash in DB
     │                                                   │  Check not revoked
     │                                                   │  Check not expired
     │                                                   │  Revoke old refresh_token
     │                                                   │  Generate new token pair
     │                                                   │  Store new refresh_token
     │  ◄──────────────────────────────────────────────  │
     │  { access_token, refresh_token }                  │
```

### Token Specifications

| Token | Expiry | Payload | Storage |
|---|---|---|---|
| Access Token | 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`) | `{ sub: email, exp, type: "access" }` | Client-side (memory/localStorage) |
| Refresh Token | 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`) | `{ sub: email, exp, type: "refresh", jti }` | Client-side + SHA-256 hash in DB |

Note: `sub` carries the user's **email**, not their id — `get_current_user` looks the user up by email on every request. `type` is checked on decode so an access token can never be used where a refresh token is expected, or vice versa.

### Refresh Token Rotation

Each refresh request:

1. Validates the incoming refresh token (hash lookup, not revoked, not expired)
2. Revokes the old token and links it to its replacement (`replaced_by_id`)
3. Issues a new access + refresh token pair
4. Stores the new refresh token hash in DB

Reusing an already-rotated (revoked) refresh token returns 401 — this prevents token reuse attacks. `POST /auth/sign-out` revokes a refresh token directly and always returns 204, even for an invalid/unknown token, so the endpoint can't be used to probe which tokens exist.

---

## 6. Business Logic Mapping

How each frontend function maps to backend implementation:

| Frontend Function | Backend Endpoint | SQL / Service Logic |
|---|---|---|
| `filterExpenses()` | `GET /expenses?start_date=&end_date=&category_ids=&type=&search=&sort=&limit=&offset=` | `WHERE date BETWEEN ... AND category_id IN (...) AND type = ... AND description ILIKE ...` |
| `groupByCategory()` | `GET /reports/category-breakdown` | `GROUP BY category_id` with JOIN on categories |
| `groupByMonth()` | `GET /reports/spending?period=monthly` | `DATE_TRUNC('month', date)` + `GROUP BY` |
| `groupByWeek()` | `GET /reports/spending?period=weekly` | `DATE_TRUNC('week', date)` + `GROUP BY` |
| `groupByYear()` | `GET /reports/spending?period=yearly` | `DATE_TRUNC('year', date)` + `GROUP BY` |
| `computeAnalytics()` | `GET /reports/summary` | `SUM(amount), MIN(amount), MAX(amount), AVG(amount), COUNT(*)` |
| `calculateBudgetStatus()` | `GET /budgets/:id/status` | `SUM(amount)` for budget's month + health rules |
| `calculateNeedsWantsSplit()` | `GET /reports/needs-vs-wants` or inline in `GET /dashboard` | `SUM(CASE WHEN type='need' THEN amount END)` |
| `multiYearComparison()` | `GET /reports/year-comparison` | `EXTRACT(YEAR FROM date)` + `GROUP BY` + per-year avg |
| `computeCategoryBreakdown()` | `GET /reports/category-breakdown` | `GROUP BY category_id` + percentage calculation |

---

## 7. Default Categories

Seeded automatically when a new tracker is created:

| Name | Color |
|---|---|
| Uncategorized | `#78716C` |
| Groceries | `#22C55E` |
| Transport | `#3B82F6` |
| Dining | `#F97316` |
| Subscriptions | `#8B5CF6` |
| Entertainment | `#EC4899` |
| Health | `#14B8A6` |
| Shopping | `#EAB308` |
| Utilities | `#06B6D4` |
| Coffee | `#A855F7` |

---

## 8. Implementation Phases

### Phase 0 — Foundation (Complete)

- [x] FastAPI app scaffold with health probes
- [x] SQLModel + PostgreSQL setup with Docker
- [x] Alembic migrations configured
- [x] User model + auth (register, login)
- [x] JWT access + refresh tokens
- [x] Argon2 password hashing
- [x] Rate limiting (SlowAPI)
- [x] Structured logging

### Phase 1 — Trackers & Categories

- [x] Tracker model (`modules/trackers/model.py`)
- [x] Tracker schemas (`modules/trackers/schema.py`)
- [x] Tracker repository (`modules/trackers/repo.py`)
- [x] Tracker service (`modules/trackers/service.py`)
- [x] Tracker router (`modules/trackers/router.py`)
- [x] Category model (`modules/categories/model.py`)
- [x] Category schemas, repo, service, router
- [x] Default category seeding on tracker creation
- [x] Alembic migration for trackers + categories tables

### Phase 2 — Expenses

- [x] Expense model (`modules/expenses/model.py`)
- [x] Expense schemas with filter params
- [x] Expense repository with query building
- [x] Expense service (filtering, sorting)
- [x] Expense router with all CRUD + filtering endpoints
- [x] Alembic migration for expenses table

### Phase 3 — Budgets

- [x] Budget model (`modules/budgets/model.py`)
- [x] Budget schemas (including BudgetStatus response)
- [x] Budget repository
- [x] Budget service (status computation, savings health)
- [x] Budget router (CRUD + `/status` endpoint)
- [x] Alembic migration for budgets table

### Phase 4 — Dashboard & Reports

- [x] Dashboard service (aggregation queries)
- [x] Dashboard router (`GET /dashboard`)
- [x] Reports service (summary, category breakdown, spending over time, needs-vs-wants, year comparison)
- [x] Reports router (5 endpoints)

### Phase 5 — Polish

- [x] Input validation (Pydantic models for all endpoints)
- [x] Error handling (consistent error response format)
- [x] CORS configuration for frontend origin
- [x] Database seeding script
- [x] Integration tests (pytest + httpx)

---

## 9. Key Design Decisions

| Decision | Rationale |
|---|---|
| **SQLModel (not pure SQLAlchemy)** | Matches existing codebase. SQLModel combines SQLAlchemy + Pydantic in one model definition. |
| **`modules/` pattern (not `app/models/`)** | Matches existing structure. Each feature is a self-contained module with model, schema, repo, service, router. |
| **Tracker-scoped URLs** | `/trackers/:id/expenses` makes authorization implicit — middleware validates ownership before any data operation. |
| **Server-side computation** | Budget status, analytics, and reports are computed in SQL, not fetched raw and processed in Python. More efficient, leverages DB indexes. |
| **Argon2 hashing** | Already in place. More secure than bcrypt for password hashing. |
| **Refresh token rotation** | Each refresh issues new tokens and revokes the old pair. Prevents token reuse attacks. |
| **Hard delete with CASCADE** | Simple approach for personal use. No soft delete unless audit trail is needed later. |
| **Default categories per tracker** | New trackers start with 10 pre-defined categories. Users can add/edit/delete as needed. |
| **RESTful, not GraphQL** | Sufficient for current needs. GraphQL can be added later if the API surface grows complex. |

---

## 10. Frontend Integration Strategy

The frontend already follows a **repository pattern** with interfaces defined in the domain layer. Switching from mocks to real API calls requires only changing the `data/repository.ts` implementations.

### Current (Mock)

```typescript
// src/features/expenses/data/repository.ts
export const expenseRepository: ExpenseRepository = {
  getAll: async (filter) => {
    // In-memory array filtering
    return filterExpenses(expenses, filter);
  },
  create: async (input) => {
    const expense = { ...input, id: crypto.randomUUID() };
    expenses.push(expense);
    return expense;
  },
};
```

### After Backend Integration

```typescript
// src/features/expenses/data/repository.ts
const API_URL = import.meta.env.VITE_API_URL;

export const expenseRepository: ExpenseRepository = {
  getAll: async (filter) => {
    const params = buildSearchParams(filter);
    const res = await fetch(`${API_URL}/trackers/${trackerId}/expenses?${params}`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` },
    });
    return res.json();
  },
  create: async (input) => {
    const res = await fetch(`${API_URL}/trackers/${trackerId}/expenses`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAccessToken()}`,
      },
      body: JSON.stringify(input),
    });
    return res.json();
  },
};
```

### What Stays the Same

- Repository interfaces (`ExpenseRepository`, `CategoryRepository`, etc.)
- TanStack Query hooks and cache invalidation
- Query keys (`["expenses"]`, `["budgets"]`, etc.)
- Component layer — no changes needed

### What Changes

- Only `data/repository.ts` files in each feature
- Add an auth token manager (interceptor for 401 → refresh flow)
- Environment variable for API URL

---

## 11. Environment Variables

See `.env.example` at repo root for the full, current template. Loaded via `app/core/config.py` (`pydantic-settings`); unknown `.env` keys (e.g. Docker Compose's `POSTGRES_*`) are ignored rather than rejected.

```env
# Security (required)
SECRET_KEY=<random string, >= 32 chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database (required)
DATABASE_URL=postgresql://fastapi:password@localhost:5432/fastapi_db

# App
API_V1_STR=/api/v1
DEBUG=false
ALLOW_REGISTRATION=true          # kill switch for public sign-up

# CORS (comma-separated, no wildcard support since credentials are allowed)
CORS_ORIGINS=http://localhost:3000

# Storage (required) — S3-compatible: Cloudflare R2, MinIO, AWS S3, etc.
STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
STORAGE_ACCESS_KEY_ID=<key>
STORAGE_SECRET_ACCESS_KEY=<secret>
STORAGE_BUCKET_NAME=<bucket>
STORAGE_PRESIGN_EXPIRY=86400     # seconds
STORAGE_ENV=dev                  # key prefix, e.g. "dev/avatars/..."

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 12. Development Commands

```bash
# Install dependencies
make install          # Production
make dev              # With dev tools

# Database
make migrations       # Generate new migration
make upgrade          # Apply pending migrations
make downgrade        # Rollback last migration

# Run
make run              # Dev server (port 8000, hot reload)

# Docker
docker-compose up     # PostgreSQL + API

# Test & Lint
make test             # pytest with coverage
make lint             # ruff + mypy
make format           # black + ruff fix
```

---

*Last updated: 2026-07-05*
