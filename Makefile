ENV_FILE := .env
PYTHON := python3

.PHONY: help install dev test clean migrations run lint format sync-db sync-db-dry sync-db-status sync-db-reset sync-db-test-up sync-db-test-down sync-db-test-sync sync-db-test-drop

help:
	@echo "Expense tracker app - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install dependencies"
	@echo "  make dev          Install dev dependencies"
	@echo ""
	@echo "Database:"
	@echo "  make migrations   Create new migration"
	@echo "  make upgrade      Run migrations (upgrade to head)"
	@echo "  make downgrade    Rollback last migration"
	@echo ""
	@echo "Development:"
	@echo "  make run          Run dev server"
	@echo "  make test         Run test suite"
	@echo "  make lint         Run linters (ruff, mypy)"
	@echo "  make format       Format code (black, ruff)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean        Remove pycache and build files"
	@echo ""
	@echo "Database sync (bidirectional, incremental, rollback-safe):"
	@echo "  make sync-db          Sync local Docker DB <-> prod (requires PROD_URL)"
	@echo "  make sync-db-dry      Preview sync-db without writing"
	@echo "  make sync-db-status   Print per-table sync watermarks on both sides"
	@echo "  make sync-db-reset    Reset watermarks to epoch (next run scans fully)"
	@echo "                        Append ARGS='--keep-dump --jobs 8 --verbose'"
	@echo ""
	@echo "Sync test harness (isolated 'prod' on port 5433, never touches real DB):"
	@echo "  make sync-db-test-up     Start a throwaway test Postgres on port 5433"
	@echo "  make sync-db-test-sync   Run sync-db-dry against the test container"
	@echo "  make sync-db-test-drop   Stop and remove the test container"

install:
	uv sync --no-dev

dev:
	uv sync

migrations:
	@read -p "Enter migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

upgrade:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade -1

run:
	uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v --cov=. --cov-report=html

lint:
	uv run ruff check app modules tests
	uv run mypy app modules

format:
	uv run ruff format .
	uv run ruff check . --fix

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info

db-init:
	uv run alembic current

# ----------------------------------------------------------------------------
# Bidirectional DB sync: local Docker <-> prod
#
# Usage:
#   make sync-db        PROD_URL='postgres://user:pass@host:5432/db'
#   make sync-db-dry    PROD_URL='postgres://user:pass@host:5432/db'
#   make sync-db-status
#   make sync-db-reset  PROD_URL='postgres://user:pass@host:5432/db'
#
# Local settings come from .env (POSTGRES_DB/USER/PASSWORD).
# Both DBs are dumped to /tmp before any mutation; restored on failure.
# Append ARGS='--keep-dump --jobs 8 --verbose' to tune.
# ----------------------------------------------------------------------------
sync-db:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-db PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	@PROD_URL='$(PROD_URL)' ./scripts/sync-db.sh $(ARGS)

sync-db-dry:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-db-dry PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	@PROD_URL='$(PROD_URL)' ./scripts/sync-db.sh --dry-run $(ARGS)

sync-db-status:
	@PROD_URL='$(PROD_URL)' ./scripts/sync-db.sh --status $(ARGS)

sync-db-reset:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-db-reset PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	@PROD_URL='$(PROD_URL)' ./scripts/sync-db.sh --reset-watermark $(ARGS)

# ----------------------------------------------------------------------------
# Sync test harness
#
# Spins up an isolated Postgres 18 container on 127.0.0.1:5433 that acts as
# 'prod' for sync testing. Different port, different DB name, different
# container — your real local DB on 5432 is never touched.
# ----------------------------------------------------------------------------
TEST_CONTAINER := fintrack-test-prod
TEST_PORT      := 5433
TEST_USER      := fastapi
TEST_PASSWORD  := password
TEST_DB        := fintrack_test
# Note: TEST_URL uses `postgresql://` (psycopg2 dialect) so alembic accepts it
# directly. The sync script itself accepts both `postgres://` and `postgresql://`.
TEST_URL       := postgresql://$(TEST_USER):$(TEST_PASSWORD)@localhost:$(TEST_PORT)/$(TEST_DB)

sync-db-test-up:
	@if docker ps --format '{{.Names}}' | grep -qx "$(TEST_CONTAINER)"; then \
		echo "$(TEST_CONTAINER) already running on port $(TEST_PORT)"; \
		echo "If migrations are missing, run:"; \
		echo "  DATABASE_URL='$(TEST_URL)' uv run alembic upgrade head"; \
	else \
		echo "==> Starting isolated test Postgres on 127.0.0.1:$(TEST_PORT)"; \
		docker run -d --name $(TEST_CONTAINER) \
		  -e POSTGRES_USER=$(TEST_USER) \
		  -e POSTGRES_PASSWORD=$(TEST_PASSWORD) \
		  -e POSTGRES_DB=$(TEST_DB) \
		  -p 127.0.0.1:$(TEST_PORT):5432 \
		  postgres:18-alpine; \
		echo "==> Waiting for Postgres to be ready..."; \
		for i in 1 2 3 4 5 6 7 8 9 10; do \
		  if docker exec $(TEST_CONTAINER) pg_isready -U $(TEST_USER) -d $(TEST_DB) >/dev/null 2>&1; then \
		    echo "    ready."; break; \
		  fi; \
		  sleep 1; \
		done; \
		echo "==> Applying migrations to test DB"; \
		DATABASE_URL='$(TEST_URL)' uv run alembic upgrade head; \
		echo ""; \
		echo "Test 'prod' is ready at $(TEST_URL)"; \
		echo "Run 'make sync-db-test-sync' to dry-run, or:"; \
		echo "  PROD_URL='$(TEST_URL)' make sync-db"; \
	fi

sync-db-test-sync:
	@PROD_URL='$(TEST_URL)' ./scripts/sync-db.sh --dry-run --verbose $(ARGS)

sync-db-test-drop:
	@if docker ps -a --format '{{.Names}}' | grep -qx "$(TEST_CONTAINER)"; then \
		echo "==> Stopping and removing $(TEST_CONTAINER)"; \
		docker stop $(TEST_CONTAINER) >/dev/null; \
		docker rm $(TEST_CONTAINER) >/dev/null; \
		echo "==> Cleaning up any leftover sync dumps"; \
		rm -f /tmp/fintrack-sync-*.dump; \
		rm -rf /tmp/fintrack-sync-*.dump.dir; \
		echo "Done."; \
	else \
		echo "$(TEST_CONTAINER) is not running."; \
	fi
