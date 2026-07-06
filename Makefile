ENV_FILE := .env
PYTHON := python3

.PHONY: help install dev test clean migrations run lint format sync-prod sync-prod-dry

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
	@echo "Database sync:"
	@echo "  make sync-prod        Dump prod PG and restore into local Docker DB"
	@echo "                       (requires PROD_URL; append ARGS='--keep-dump --jobs 8')"
	@echo "  make sync-prod-dry    Preview sync-prod commands without running them"

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
	@PROD_URL='$(PROD_URL)' ./scripts/sync-prod.sh $(ARGS)

sync-prod-dry:
	@if [ -z "$(PROD_URL)" ]; then \
		echo "ERROR: PROD_URL is required."; \
		echo "  make sync-prod-dry PROD_URL='postgres://user:pass@host:5432/db'"; \
		exit 1; \
	fi
	@PROD_URL='$(PROD_URL)' ./scripts/sync-prod.sh --dry-run $(ARGS)
