# Abort on first error in every recipe and print the failing command.
# Combined with `set -e` in the shell scripts, this guarantees we never
# silently skip a failed step (e.g. a half-applied migration).
.SHELLFLAGS := -ec

.PHONY: help install dev test clean migrations upgrade downgrade run lint format db-status sync-prod sync-prod-dry push-prod push-prod-dry

help:
	@echo "Spendrift backend — development commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       Install runtime dependencies"
	@echo "  make dev           Install runtime + dev dependencies"
	@echo ""
	@echo "Database:"
	@echo "  make migrations    Create a new Alembic migration (prompts for message)"
	@echo "  make upgrade       Apply all pending migrations (alembic upgrade head)"
	@echo "  make downgrade     Roll back the most recent migration"
	@echo "  make db-status     Print the current Alembic revision"
	@echo ""
	@echo "Development:"
	@echo "  make run           Run dev server (uvicorn + hot reload, port 8000)"
	@echo "  make test          Run pytest with coverage for app/ and modules/"
	@echo "  make lint          ruff + mypy + (optional) shellcheck on scripts/"
	@echo "  make format        ruff format + ruff check --fix"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean         Remove pycache, build artefacts, htmlcov/"
	@echo ""
	@echo "Database sync:"
	@echo "  make sync-prod        Dump prod PG and restore into local Docker DB"
	@echo "                        (requires PROD_URL; append ARGS='--keep-dump --jobs 8')"
	@echo "  make sync-prod-dry    Preview sync-prod commands without running them"
	@echo "  make push-prod        Push new rows from local Docker DB into prod"
	@echo "                        (requires PROD_URL; append ARGS='--dry-run --yes --exclude-tables=foo')"
	@echo "  make push-prod-dry    Preview push-prod without touching prod"

install:
	uv sync --no-dev

dev:
	uv sync

migrations:
	@if ! read -p "Enter migration message: " msg; then \
		echo "Aborted (no input)."; \
		exit 1; \
	fi; \
	if [[ -z "$$msg" ]]; then \
		echo "ERROR: migration message cannot be empty."; \
		exit 1; \
	fi; \
	uv run alembic revision --autogenerate -m "$$msg"

upgrade:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade -1

db-status:
	uv run alembic current

run:
	uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000 --reload

test:
	uv run pytest -v --cov=app --cov=modules --cov-report=html --cov-report=term-missing

lint:
	uv run ruff check app modules tests
	uv run mypy app modules
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/*.sh; \
	else \
		echo "shellcheck not installed — skipping shell script lint (brew install shellcheck)"; \
	fi

format:
	uv run ruff format .
	uv run ruff check . --fix

clean:
	@find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) \
		-not -path './.git/*' \
		-not -path './.venv/*' \
		-not -path './node_modules/*' \
		-exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" \
		-not -path './.git/*' \
		-not -path './.venv/*' \
		-delete 2>/dev/null || true
	rm -rf build dist htmlcov *.egg-info 2>/dev/null || true

# ----------------------------------------------------------------------------
# Database sync: prod -> local Docker
#
# Usage:
#   make sync-prod PROD_URL='postgres://user:pass@host:5432/db'
#   make sync-prod PROD_URL='postgres://user:pass@host:5432/db' ARGS='--keep-dump'
#   make sync-prod-dry PROD_URL='postgres://user:pass@host:5432/db'
#
# Local DB settings are read from .env (POSTGRES_DB/USER/PASSWORD).
# The dump is written to /tmp and deleted after restore unless --keep-dump.
# ----------------------------------------------------------------------------
sync-prod:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-prod PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	PROD_URL='$(PROD_URL)' ./scripts/sync-prod.sh $(ARGS)

sync-prod-dry:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-prod-dry PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	PROD_URL='$(PROD_URL)' ./scripts/sync-prod.sh --dry-run $(ARGS)

# ----------------------------------------------------------------------------
# Database sync: local Docker -> prod (new rows only)
#
# Usage:
#   make push-prod PROD_URL='postgres://user:pass@host:5432/db'
#   make push-prod PROD_URL='postgres://user:pass@host:5432/db' ARGS='--dry-run --yes'
#   make push-prod PROD_URL='postgres://user:pass@host:5432/db' ARGS='--exclude-tables=expenses'
#   make push-prod-dry PROD_URL='postgres://user:pass@host:5432/db'
#
# Safety: Backs up prod before changes. Uses ON CONFLICT DO NOTHING.
# Only NEW rows are inserted — existing prod data is never modified or deleted.
# ----------------------------------------------------------------------------
push-prod:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make push-prod PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	PROD_URL='$(PROD_URL)' ./scripts/push-to-prod.sh $(ARGS)

push-prod-dry:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make push-prod-dry PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	PROD_URL='$(PROD_URL)' ./scripts/push-to-prod.sh --dry-run $(ARGS)