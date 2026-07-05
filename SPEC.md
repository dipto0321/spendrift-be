# SPEC

## §G GOAL
multi-tracker personal finance API ! track expenses/budgets/categories per user, per-currency workspace ("Tracker").

## §C CONSTRAINTS
- stack ! FastAPI + SQLModel + Alembic + PostgreSQL 18 (prod) + Pydantic v2 + JWT(PyJWT) + Argon2(pwdlib) + SlowAPI + Docker
- SQLite in-memory only for tests (`tests/conftest.py`), ⊥ prod fallback. `DATABASE_URL` no default, ! set.
- module layout ! `modules/<feature>/{model,schema,repo,service,router}.py`
- layer rule: router→service→repo→db. router ⊥ import service's repo directly; service ⊥ imported by repo; repo ⊥ raise HTTPException; repo ⊥ import service
- API base `/api/v1`. tracker-scoped routes nested `/trackers/{tracker_id}/...`
- storage backend hardcoded S3-compatible impl (`app/core/storage/s3.py`) behind `StorageBackend` Protocol (`app/core/storage/base.py`), swappable only in tests via stub

## §I INTERFACES
env (required): `SECRET_KEY`(≥32 chars), `DATABASE_URL`, `STORAGE_ENDPOINT_URL`, `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY`, `STORAGE_BUCKET_NAME`

env (optional, defaults): `ALGORITHM`=HS256, `ACCESS_TOKEN_EXPIRE_MINUTES`=30, `REFRESH_TOKEN_EXPIRE_DAYS`=7, `API_V1_STR`=/api/v1, `DEBUG`=False, `ALLOW_REGISTRATION`=True, `CORS_ORIGINS`=http://localhost:3000, `STORAGE_PRESIGN_EXPIRY`=86400, `STORAGE_ENV`=dev, `LOG_LEVEL`=INFO, `LOG_FORMAT`=json

- api.auth (prefix `/auth`):
  - POST /register → 201, issue token pair; 403 if !ALLOW_REGISTRATION; 400 dup email
  - POST /login → token pair; 401 bad creds; 403 inactive
  - POST /refresh → rotate refresh (one-time use); 401 invalid/reused/expired
  - POST /sign-out → 204 always (anti-enum)
  - rate limit (SlowAPI, IP-keyed): register 3/min, login 5/min, refresh 10/min, sign-out unlimited

- api.users (prefix `/users`):
  - GET/PATCH /me
  - PATCH /me/password (! current_password match)
  - POST/DELETE /me/avatar (≤1MB, jpeg|png|webp|gif)

- api.trackers (prefix `/trackers`):
  - GET/POST "" ; GET/PATCH/DELETE /{id}
  - create seeds 10 DEFAULT_CATEGORIES

- api.categories (`/trackers/{tracker_id}/categories`) — CRUD

- api.expenses (`/trackers/{tracker_id}/expenses`) — CRUD + filter (start/end date, category_ids CSV, type, search, sort, limit 1-200 default 50, offset)

- api.budgets (`/trackers/{tracker_id}/budgets`) — CRUD + GET /{id}/status (spent, remaining, savings_progress%, savings_health traffic-light, is_over_budget) + GET /current?month=YYYY-MM (default current month; budget+status merged in one call; 204 if none for month; registered before /{id})

- api.dashboard (`/trackers/{tracker_id}/dashboard`) — GET ?month=YYYY-MM (default current UTC month) → total_spent, expense_count, needs/wants split, top-5 categories, budget snapshot

- api.reports (`/trackers/{tracker_id}/reports`) — GET /summary, /spending?period=weekly|monthly|yearly, /category-breakdown, /needs-vs-wants, /year-comparison

- storage: `StorageBackend` protocol — `upload(file_key,data,content_type)`, `delete(file_key)`, `generate_presigned_url(file_key,expires_in)`. impl = S3-compatible (R2/MinIO/AWS), key prefix `{STORAGE_ENV}/...`. currently wired only to user avatars.

## §V INVARIANTS
V1: ∀ tracker-scoped req → ownership check (`get_tracker_or_404`) before data op; tracker.user_id ≠ current_user.id → 404 (⊥ 403, hide existence)
V2: ∀ auth token → type-checked (access ≠ refresh); wrong type ⊥ accepted
V3: refresh token ! one-time use; reuse of rotated token → 401 (rotation chain via `replaced_by_id`)
V4: password ! hashed via Argon2 only, ⊥ plaintext storage
V5: category name unique ∀ tracker (`UniqueConstraint(tracker_id,name)` + service 400 pre-check)
V6: category delete ⊥ allowed if ∃ expense referencing it → 409
V7: expense.amount > 0 (schema `gt=0`)
V8: expense.category_id ! belong to same tracker as expense, else 400
V9: budget ! ≤1 per (tracker_id, month) → dup → 400
V10: budget.monthly_limit > 0, savings_target ≥ 0
V11: user.email unique across all users → dup → 409 on change, 400 on register
V12: avatar upload ≤1MB, type ∈ {jpeg,png,webp,gif} else 422/413
V13: repo.py ⊥ raise HTTPException (layer boundary)
V14: repo.py ⊥ contain aggregation/analytics SQL (belongs service or reports)
V15: sign-out ! always 204 regardless of token validity (anti-enumeration)
V16: registration ⊥ allowed if `ALLOW_REGISTRATION`=false → 403

## §T TASKS
id|status|task|cites
T1|x|auth module (register/login/refresh/sign-out)|V2,V3,V4,V15,V16,I.auth
T2|x|users module (profile+avatar)|V11,V12,I.users
T3|x|trackers module + default category seed|V1,I.trackers
T4|x|categories module|V5,V6,I.categories
T5|x|expenses module|V7,V8,I.expenses
T6|x|budgets module + status calc|V9,V10,I.budgets
T7|x|dashboard aggregation|I.dashboard
T8|x|reports aggregation|I.reports
T9|.|receipts/attachments upload ? storage protocol only wired to avatars today|I.storage
T10|.|per-route rate limits ? only auth routes limited, rest of API unlimited|I.auth
T11|x|GET /budgets/current shortcut (gh#7)|V9,V10,I.budgets

## §B BUGS
id|date|cause|fix
