ENV_FILE := .env
PYTHON := python3

.PHONY: help install dev test clean migrations run lint format

help:
	@echo "FastAPI Scaffold with Auth - Development Commands"
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

install:
	$(PYTHON) -m pip install -e ".[postgres]"

dev:
	$(PYTHON) -m pip install -e ".[dev,postgres]"

migrations:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

upgrade:
	alembic upgrade head

downgrade:
	alembic downgrade -1

run:
	fastapi dev app/main.py --host 0.0.0.0 --port 8000 --reload

test:
	pytest -v --cov=. --cov-report=html

lint:
	ruff check . --show-source || true
	mypy app modules

format:
	black .
	ruff check . --fix

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info

db-init:
	alembic current
