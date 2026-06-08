# FinTracker Backend — Architecture Documentation

---

## 1. Overview

FinTracker is a personal finance tracking application with a tracker-based architecture. Each tracker is an independent financial workspace (e.g., Bangladesh Tracker in BDT, Europe Tracker in EUR) containing its own expenses, categories, budgets, and reports.

### Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python >=3.11) |
| ORM | SQLModel (SQLAlchemy 2.0 under the hood) |
| Migrations | Alembic |
| Database | PostgreSQL 16 (Neon in production, Docker locally) |
| Auth | JWT (access + refresh tokens) + Argon2 password hashing |
| Validation | Pydantic v2 |
| Rate Limiting | SlowAPI (IP-based) |
| Containerization | Docker + Docker Compose |

### Current State

| Module | Status |
|---|---|
| Auth (register, login, refresh) | ✅ Complete |
| Users (profile) | ✅ Complete |
| Trackers | ❌ Not started |
| Categories | ❌ Not started |
| Expenses | ❌ Not started |
| Budgets | ❌ Not started |
| Dashboard | ❌ Not started |
| Reports | ❌ Not started |

---

## 2. Project Structure

```
backend/
├── alembic/                          # Database migrations
│   ├── versions/
│   │   └── bd81a202b4b3_initial_schema.py
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
│   │   └── security.py               # JWT encode/decode, Argon2 hashing
│   └── middleware/
│       └── rate_limit.py             # SlowAPI rate limiter
│
├── modules/                          # Feature modules (DDD-style)
│   ├── auth/
│   │   ├── router.py                 # POST /register, POST /login
│   │   ├── schema.py                 # RegisterSchema, LoginSchema, TokenResponse
│   │   └── service.py                # register_user, authenticate_user
│   │   (reuses modules/users/model.py and modules/users/repo.py)
│   ├── users/
│   │   ├── model.py                  # User SQLModel (table=True)
│   │   ├── repo.py                   # create_user, get_user_by_email, get_user_by_id
│   │   ├── router.py                 # GET /me
│   │   └── schema.py                 # UserCreate, UserResponse
│   ├── trackers/                     # 🆕 To be created
│   ├── categories/                   # 🆕 To be created
│   ├── expenses/                     # 🆕 To be created
│   ├── budgets/                      # 🆕 To be created
│   ├── dashboard/                    # 🆕 To be created
│   └── reports/                      # 🆕 To be created
│
├── tests/                            # 🆕 To be created
├── docs/                             # Architecture documentation
│   └── ARCHITECTURE.md
│
├── docker-compose.yml                # PostgreSQL 16 + API service
├── Dockerfile                        # Python 3.11-slim
├── Makefile                          # Dev commands
├── pyproject.toml                    # Dependencies
├── .env                              # Environment variables
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
│ email          VARCHAR  │← unique, indexed
│ hashed_password VARCHAR │
│ is_active       BOOLEAN │← default: true
│ updated_at    DATETIME  │← auto (onupdate)
│ created_at    DATETIME  │← indexed, auto
└────────────┬────────────┘
             │ 1:N
             ▼
┌─────────────────────────┐
│     refresh_tokens      │← 🆕 Not yet created
├─────────────────────────┤
│ id              UUID PK │
│ user_id        UUID FK  │→ users.id (CASCADE)
│ token_hash     VARCHAR  │← indexed
│ expires_at    DATETIME  │
│ revoked        BOOLEAN  │← default: false
│ created_at    DATETIME  │
└─────────────────────────┘

┌─────────────────────────┐
│        trackers         │
├─────────────────────────┤
│ id              UUID PK │
│ user_id        UUID FK  │→ users.id (CASCADE)
│ name           VARCHAR  │
│ color          VARCHAR  │
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
└────────────┬────────────┘     │ month          VARCHAR  │← "YYYY-MM"
             │ 1:N              │ created_at    DATETIME  │
             ▼                  │ updated_at    DATETIME  │
┌─────────────────────────┐     └─────────────────────────┘
│        expenses         │
├─────────────────────────┤
│ id              UUID PK │
│ tracker_id     UUID FK  │→ trackers.id (CASCADE)
│ category_id    UUID FK  │→ categories.id (RESTRICT)
│ amount         NUMERIC  │
│ date            DATE    │
│ description   VARCHAR?  │
│ type          VARCHAR   │← "need" | "want"
│ created_at    DATETIME  │
│ updated_at    DATETIME  │
└─────────────────────────┘
```

### Relationships

| Parent | Child | FK Column | On Delete |
|---|---|---|---|
| users | refresh_tokens | `user_id` | CASCADE |
| users | trackers | `user_id` | CASCADE |
| trackers | categories | `tracker_id` | CASCADE |
| trackers | expenses | `tracker_id` | CASCADE |
| trackers | budgets | `tracker_id` | CASCADE |
| categories | expenses | `category_id` | RESTRICT (reassign first) |

### Indexes

| Table | Column(s) | Purpose |
|---|---|---|
| users | `email` | Unique login lookup |
| refresh_tokens | `token_hash` | Token lookup for refresh/validation |
| trackers | `user_id` | List user's trackers |
| categories | `tracker_id` | List tracker's categories |
| expenses | `tracker_id`, `date` | Date-range queries per tracker |
| expenses | `tracker_id`, `category_id` | Category filter queries |
| budgets | `tracker_id`, `month` | Look up budget by month |

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
| POST | `/auth/register` | `{ email, password }` | `{ access_token, refresh_token, token_type }` | No | 3/min |
| POST | `/auth/login` | `{ email, password }` | `{ access_token, refresh_token, token_type }` | No | 5/min |
| POST | `/auth/refresh` | `{ refresh_token }` | `{ access_token, refresh_token }` | Refresh | — | 🆕 Not yet implemented |
| POST | `/auth/sign-out` | `{ refresh_token }` | `{ detail }` | Yes | — | 🆕 Not yet implemented |

### Users

| Method | Path | Body | Response | Auth |
|---|---|---|---|---|
| GET | `/users/me` | — | `{ id, email, is_active }` | Yes |
| PUT | `/users/me` | `{ email? }` | `{ id, email, is_active }` | Yes |
| PUT | `/users/me/password` | `{ current_password, new_password }` | `{ detail }` | Yes |

### Trackers

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers` | — | `[{ id, name, currency }]` | Yes |
| GET | `/trackers/:id` | — | `{ id, name, currency }` | Yes |
| POST | `/trackers` | `{ name, currency }` | `{ id, name, currency }` | Yes |
| PUT | `/trackers/:id` | `{ name?, currency? }` | `{ id, name, currency }` | Yes |
| DELETE | `/trackers/:id` | — | `{ detail }` | Yes |

> On tracker creation, 10 default categories are seeded automatically.

### Categories

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/categories` | — | `[{ id, name, color }]` | Yes |
| POST | `/trackers/:trackerId/categories` | `{ name, color }` | `{ id, name, color }` | Yes |
| PUT | `/trackers/:trackerId/categories/:id` | `{ name?, color? }` | `{ id, name, color }` | Yes |
| DELETE | `/trackers/:trackerId/categories/:id` | `?fallback_category_id=...` | `{ detail }` | Yes |

> Delete requires a `fallback_category_id` to reassign existing expenses before deletion.

### Expenses

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/expenses` | Query params (see below) | `[{ id, amount, category_id, date, description, type }]` | Yes |
| GET | `/trackers/:trackerId/expenses/:id` | — | `{ id, amount, category_id, date, description, type }` | Yes |
| POST | `/trackers/:trackerId/expenses` | `{ amount, category_id, date, description?, type }` | `{ id, ... }` | Yes |
| PUT | `/trackers/:trackerId/expenses/:id` | Partial expense object | `{ id, ... }` | Yes |
| DELETE | `/trackers/:trackerId/expenses/:id` | — | `{ detail }` | Yes |

**GET /expenses Query Parameters:**

| Param | Type | Example | Description |
|---|---|---|---|
| `start_date` | string | `2026-05-01` | Date range start (inclusive) |
| `end_date` | string | `2026-05-31` | Date range end (inclusive) |
| `category_ids` | string | `uuid1,uuid2` | Comma-separated category IDs |
| `type` | string | `need` | Filter by expense type |
| `search` | string | `groceries` | Description text search |
| `sort` | string | `date_desc` | Sort order (`date_asc` or `date_desc`) |

### Budgets

| Method | Path | Body / Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/budgets` | — | `[{ id, name, monthly_limit, savings_target, month }]` | Yes |
| GET | `/trackers/:trackerId/budgets/current` | — | `{ budget, status }` | Yes |
| GET | `/trackers/:trackerId/budgets/:id` | — | `{ id, name, monthly_limit, savings_target, month, status }` | Yes |
| POST | `/trackers/:trackerId/budgets` | `{ name, monthly_limit, savings_target, month }` | `{ id, ... }` | Yes |
| PUT | `/trackers/:trackerId/budgets/:id` | Partial budget object | `{ id, ... }` | Yes |
| DELETE | `/trackers/:trackerId/budgets/:id` | — | `{ detail }` | Yes |

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

| Method | Path | Response | Auth |
|---|---|---|---|
| GET | `/trackers/:trackerId/dashboard` | Dashboard summary object | Yes |

**Dashboard Summary Object:**

```json
{
  "total_balance": 18420.55,
  "month_spend": 1267.42,
  "month_income": 3540.00,
  "recent_expenses": [...],
  "budget_status": { ... },
  "needs_wants_split": {
    "needs": 850.00,
    "wants": 417.42,
    "percentage": { "needs": 67, "wants": 33 }
  }
}
```

### Reports

| Method | Path | Query | Response | Auth |
|---|---|---|---|---|
| GET | `/trackers/:trackerId/reports/analytics` | `start_date`, `end_date` | `{ total, min, max, avg, count }` | Yes |
| GET | `/trackers/:trackerId/reports/category-breakdown` | `start_date`, `end_date` | `[{ category_id, name, color, total, percentage, count }]` | Yes |
| GET | `/trackers/:trackerId/reports/spending` | `period`, `start_date`, `end_date` | `[{ label, total, count }]` | Yes |
| GET | `/trackers/:trackerId/reports/year-comparison` | — | `[{ year, total, avg, count }]` | Yes |

**Report Query Parameters:**

| Param | Type | Values | Description |
|---|---|---|---|
| `period` | string | `weekly`, `monthly`, `yearly` | Grouping granularity |
| `start_date` | string | ISO date | Custom range start |
| `end_date` | string | ISO date | Custom range end |

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
     │                                                   │  Decode JWT
     │                                                   │  Validate user_id exists
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
| Access Token | 30 minutes | `{ sub: user_id, exp }` | Client-side (memory/localStorage) |
| Refresh Token | 7 days | `{ sub: user_id, exp, jti }` | Client-side + hash in DB |

### Refresh Token Rotation

Each refresh request:

1. Validates the incoming refresh token (hash lookup, not revoked, not expired)
2. Revokes the old token
3. Issues a new access + refresh token pair
4. Stores the new refresh token hash in DB

This prevents token reuse attacks.

---

## 6. Business Logic Mapping

How each frontend function maps to backend implementation:

| Frontend Function | Backend Endpoint | SQL / Service Logic |
|---|---|---|
| `filterExpenses()` | `GET /expenses?start_date=&end_date=&category_ids=&type=&search=` | `WHERE date BETWEEN ... AND category_id IN (...) AND type = ... AND description ILIKE ...` |
| `groupByCategory()` | `GET /reports/category-breakdown` | `GROUP BY category_id` with JOIN on categories |
| `groupByMonth()` | `GET /reports/spending?period=monthly` | `DATE_TRUNC('month', date)` + `GROUP BY` |
| `groupByWeek()` | `GET /reports/spending?period=weekly` | `DATE_TRUNC('week', date)` + `GROUP BY` |
| `groupByYear()` | `GET /reports/spending?period=yearly` | `DATE_TRUNC('year', date)` + `GROUP BY` |
| `computeAnalytics()` | `GET /reports/analytics` | `SUM(amount), MIN(amount), MAX(amount), AVG(amount), COUNT(*)` |
| `calculateBudgetStatus()` | `GET /budgets/current` | `SUM(amount)` for budget's month + health rules |
| `calculateNeedsWantsSplit()` | `GET /dashboard` (inline) | `SUM(CASE WHEN type='need' THEN amount END)` |
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

- [ ] Expense model (`modules/expenses/model.py`)
- [ ] Expense schemas with filter params
- [ ] Expense repository with query building
- [ ] Expense service (filtering, sorting)
- [ ] Expense router with all CRUD + filtering endpoints
- [ ] Alembic migration for expenses table

### Phase 3 — Budgets

- [ ] Budget model (`modules/budgets/model.py`)
- [ ] Budget schemas (including BudgetStatus response)
- [ ] Budget repository
- [ ] Budget service (status computation, savings health)
- [ ] Budget router (CRUD + `/current` endpoint)
- [ ] Alembic migration for budgets table

### Phase 4 — Dashboard & Reports

- [ ] Dashboard service (aggregation queries)
- [ ] Dashboard router (`GET /dashboard`)
- [ ] Reports service (analytics, breakdown, spending groups, year comparison)
- [ ] Reports router (4 endpoints)

### Phase 5 — Polish

- [ ] Input validation (Pydantic models for all endpoints)
- [ ] Error handling (consistent error response format)
- [ ] CORS configuration for frontend origin
- [ ] Database seeding script
- [ ] Integration tests (pytest + httpx)
- [ ] API documentation (OpenAPI/Swagger)

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

```env
# Database
DATABASE_URL=postgresql://fastapi:password@localhost:5432/fastapi_db

# JWT
SECRET_KEY=<base64-encoded-secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# App
API_V1_STR=/api/v1
DEBUG=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=text
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

*Last updated: 2026-06-03*
