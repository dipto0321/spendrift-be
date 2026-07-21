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

env (optional, defaults): `GEMINI_API_KEY`=None (AI endpoints 503 until set), `GEMINI_MODEL`=gemini-flash-latest (rolling alias; pinned versions get retired for new keys), `GEMINI_TIMEOUT_SECONDS`=30, `ALGORITHM`=HS256, `ACCESS_TOKEN_EXPIRE_MINUTES`=30, `REFRESH_TOKEN_EXPIRE_DAYS`=7, `API_V1_STR`=/api/v1, `DEBUG`=False, `ALLOW_REGISTRATION`=True, `CORS_ORIGINS`=http://localhost:3000, `STORAGE_PRESIGN_EXPIRY`=86400, `STORAGE_ENV`=dev, `LOG_LEVEL`=INFO, `LOG_FORMAT`=json

- api.auth (prefix `/auth`):
  - POST /register → 201, issue token pair; 403 if !ALLOW_REGISTRATION; 400 dup email
  - POST /login → token pair; 401 bad creds; 403 inactive
  - POST /refresh → rotate refresh (one-time use); 401 invalid/reused/expired
  - POST /sign-out → 204 always (anti-enum)
  - rate limit (SlowAPI, IP-keyed): register 3/min, login 5/min, refresh 10/min (own decorator, ⊥ stacked w/ default), sign-out @limiter.exempt (unlimited)

- global default rate limit: DEFAULT_RATE_LIMIT=60/min per IP (`app/middleware/rate_limit.py`), auto-applied by SlowAPIMiddleware to ∀ route ⊥ own `@limiter.limit(...)` decorator

- api.users (prefix `/users`):
  - GET/PATCH /me
  - PATCH /me/password (! current_password match)
  - POST/DELETE /me/avatar (≤1MB, jpeg|png|webp|gif)

- api.preferences (prefix `/preferences`, NOT tracker-scoped, 1 row/user):
  - GET "" → lazily creates default row (budget_alerts_enabled=true, weekly_summary_enabled=true, round_amounts_enabled=false) if none exists yet
  - PUT "" → partial update, any subset of the 3 booleans
  - budget_alerts_enabled gates FE call to /budget-alerts, not enforced server-side

- api.ai (`/trackers/{tracker_id}/ai`, stateless — no model/repo):
  - POST /parse-expenses {text ≤4000, default_date} → {expenses[{amount, description, category_id|null, type, date}]} — candidate rows only, ⊥ persistence
  - categories loaded server-side from tracker (DB = source of truth ∴ new/renamed categories auto-fresh, ⊥ client ships list, ⊥ LLM context cache needed); ownership via get_tracker_or_404 (V1)
  - Gemini structured-output via `app/core/llm` (Protocol + `get_llm` dependency, mirrors storage pattern); model returns category NAME → service maps name→id (case-insens) ∴ hallucinated category ⊥ map to real UUID
  - errors: no GEMINI_API_KEY → 503; provider fail/non-list payload → 502; 0 salvageable rows → 422
  - rate limit 10/min/IP (own decorator, protects free-tier quota)

- api.trackers (prefix `/trackers`):
  - GET/POST "" ; GET/PATCH/DELETE /{id}
  - create seeds 10 DEFAULT_CATEGORIES

- api.categories (`/trackers/{tracker_id}/categories`) — CRUD

- api.expenses (`/trackers/{tracker_id}/expenses`) — CRUD + filter (start/end date, category_ids CSV, type, search, sort, limit 1-200 default 50, offset). list resp ! set `X-Total-Count` header = total matches (filters applied, limit/offset ignored); CORS `expose_headers` ! include it or browser JS can't read it

- api.budgets (`/trackers/{tracker_id}/budgets`) — CRUD + GET /{id}/status (spent, remaining, savings_progress%, savings_health traffic-light, is_over_budget) + GET /current?month=YYYY-MM (default current month; budget+status merged in one call; 204 if none for month; registered before /{id})

- api.category_budgets (`/trackers/{tracker_id}/budgets/{budget_id}/category-allocations`) — GET list, PUT full-replace `[{category_id,allocated_amount}]`. resp adds actual_amount+percentage_used computed for budget's month (percentage_used ⊥ capped @100)

- api.budget_alerts (`/trackers/{tracker_id}/budget-alerts`) — GET ?month=YYYY-MM (default current UTC month) → `[{category_id,category_name,spent,limit,percentage,level}]`. level ∈ {ok,warning,exceeded} from fixed thresholds (80%/100%). reuses category_budgets allocations + same actual-spend aggregation, ⊥ new table. [] if no budget for month or no allocations set

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
V17: category_budget ! ≤1 per (budget_id, category_id) → dup in PUT payload → 400
V18: category_budget.allocated_amount > 0
V19: category_budget.category_id ! belong to same tracker as budget, else 400
V20: category delete ⊥ allowed if ∃ category_budget referencing it → 409 (mirrors V6)
V21: alembic/env.py ! import every SQLModel table module so target_metadata is complete; missing import → autogenerate proposes DROPPING the unlisted table
V22: user_preferences ! ≤1 row per user_id (UNIQUE constraint); GET lazily creates default row instead of 404
V23: budget alert level thresholds fixed constants (WARNING_THRESHOLD=80, EXCEEDED_THRESHOLD=100), ⊥ magic numbers scattered in code
V24: ∀ route ⊥ own rate-limit decorator → global default (60/min/IP) applies via SlowAPIMiddleware; sign-out excluded via @limiter.exempt, register/login/refresh excluded via their own decorator (⊥ stacked)
V25: LLM output = untrusted input: ∀ parsed row coerced field-by-field (bad type→need, bad date→default_date, amount ⊥ >0 or no description → row dropped); ⊥ raw LLM json passed to client
V26: /ai/parse-expenses ⊥ write DB — persistence only via normal /expenses endpoints after user review (FE V18 mirror)
V27: GEMINI_MODEL ! rolling alias (gemini-flash-latest) ⊥ pinned version — Google retires pinned models for new API keys (see B2)

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
T9|.|receipts/attachments upload ? storage protocol only wired to avatars today (gh#13)|I.storage
T10|x|global default rate limit (60/min/IP) extended to all routes (gh#14)|V24,I.auth
T11|x|GET /budgets/current shortcut (gh#7)|V9,V10,I.budgets
T12|x|X-Total-Count header on expenses list (gh#6)|I.expenses
T13|x|category_budgets module: per-category allocation (gh#5)|V17,V18,V19,V20,I.category_budgets
T14|x|preferences module: user_preferences table + GET/PUT (gh#16)|V22,I.preferences
T15|x|budget_alerts module: per-category threshold status (gh#17)|V23,I.budget_alerts
T16|x|ai module: POST /ai/parse-expenses smart-paste parsing (Gemini via app/core/llm)|V25,V26,I.ai

## §B BUGS
id|date|cause|fix
B1|2026-07-05|alembic/env.py missed importing Budget model ∴ target_metadata ⊥ know budgets table exists ∴ autogenerate would propose DROP TABLE budgets|added missing import (+ CategoryBudget). §V21
B2|2026-07-19|default GEMINI_MODEL pinned gemini-2.5-flash; Google retired it for new API keys → generateContent 404 → FE saw 502 on first real smart-paste|switched default/.env/.env.example to gemini-flash-latest rolling alias. §V27
B3|2026-07-19|scripts/push-to-prod.sh: `psql ... -v ON_ERROR_STOP=0 | tail -20` silently swallowed failed INSERTs, and `2>/dev/null || echo "0"` coerced query errors to "0 rows" — both hid data-loss conditions|swapped to `ON_ERROR_STOP=1` with full psql log + tail; errors now surface loudly. Added schema pre-check (information_schema.columns), timezone-safe timestamps via `AT TIME ZONE 'UTC'`, `PGPASSWORD` env var (no password in argv), `--yes` / `--exclude-tables` flags, refresh_tokens+alembic_version default-excluded, and a `cleanup_tmp` EXIT trap. See `docs/SCRIPTS_REVIEW.md` for full audit.
B4|2026-07-19|Makefile: `db-init` target ran `alembic current` (only reports revision); misleadingly named and not in `.PHONY`|renamed to `db-status`, added to `.PHONY`. Also added `.SHELLFLAGS := -ec` for strict-mode recipes, scoped `make test` coverage to `app/ modules/` (matches `pyproject.toml`), removed unused `ENV_FILE`/`PYTHON` vars, expanded `clean` to remove `htmlcov/`, added optional `shellcheck scripts/*.sh` to `make lint`.
B5|2026-07-19|scripts/sync-prod.sh: regex-based `PROD_URL` parsing broke on URL-encoded passwords and IPv6 hosts; `--jobs` accepted non-numeric values; no `pg_restore`/`psql` preflight; `LOCAL_URL` embedded password in argv|replaced URL parsing with `python3 -c urllib.parse`, validated `--jobs` as integer, added preflight checks, switched all DB connections to `PGPASSWORD` env var, added explicit `pg_restore` failure path that points at the preserved dump. See `docs/SCRIPTS_REVIEW.md`.
