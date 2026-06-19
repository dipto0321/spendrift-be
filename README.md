# Spendrift — Personal Finance Backend

> A multi-tracker personal finance API built with FastAPI, SQLModel, and PostgreSQL.

**Author**: Dipto Karmakar  
**License**: [AGPL-3.0](LICENSE) — free to study, not free to commercialize

---

## What is Spendrift?

Spendrift is a personal finance backend where each user can manage multiple **Trackers** (e.g. a "Bangladesh Tracker" in BDT, a "Europe Tracker" in EUR). Every tracker is an independent workspace with its own expenses, categories, and budgets.

## Stack

- **FastAPI** — async REST API
- **SQLModel + Alembic** — ORM and migrations
- **PostgreSQL 18** — primary database
- **Pydantic v2** — request/response validation
- **Argon2 + JWT** — authentication
- **SlowAPI** — rate limiting
- **Docker** — local development

## Features

| Module     | Status      |
|------------|-------------|
| Auth       | Complete    |
| Users      | Complete    |
| Trackers   | Complete    |
| Categories | Complete    |
| Expenses   | Complete    |
| Budgets    | Complete    |
| Dashboard  | Complete    |
| Reports    | Complete    |

## Getting Started

### Prerequisites

- Docker (for PostgreSQL)
- Python 3.12+
- `uv` package manager

### Setup

```bash
# 1. Start PostgreSQL
docker-compose up -d

# 2. Install dependencies
pip install -e ".[postgres]"

# 3. Copy and configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL and SECRET_KEY

# 4. Apply migrations
make upgrade

# 5. Start the API
make run
```

API runs at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/docs`

## Key Commands

```bash
make run          # Start API with hot reload (port 8000)
make migrations   # Generate Alembic migration
make upgrade      # Apply pending migrations
make test         # Run test suite
make lint         # ruff + mypy
```

## API Overview

Base path: `/api/v1`

| Group      | Endpoints                                      |
|------------|------------------------------------------------|
| Auth       | `POST /auth/register`, `POST /auth/login`      |
| Users      | `GET /users/me`, `PATCH /users/me`             |
| Trackers   | `CRUD /trackers`                               |
| Categories | `CRUD /trackers/{id}/categories`               |
| Expenses   | `CRUD /trackers/{id}/expenses`                 |
| Budgets    | `CRUD /trackers/{id}/budgets`                  |
| Dashboard  | `GET /trackers/{id}/dashboard`                 |
| Reports    | `GET /trackers/{id}/reports`                   |

## Project Structure

```text
backend/
├── app/
│   ├── main.py           # FastAPI app entry point
│   ├── api/v1/           # Router registration
│   └── core/             # Config, DB session, security
├── modules/
│   ├── auth/             # JWT auth
│   ├── users/            # User profile
│   ├── trackers/         # Tracker workspaces
│   ├── categories/       # Expense categories
│   ├── expenses/         # Expense records
│   ├── budgets/          # Budget limits
│   ├── dashboard/        # Summary aggregations
│   └── reports/          # Detailed reports
├── alembic/              # Database migrations
├── tests/                # Pytest suite
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

## License

Copyright (c) 2026 Dipto Karmakar

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.  
See the [LICENSE](LICENSE) file for full terms.

**In plain English:**

- You may study and use this code for personal/educational purposes
- If you modify and distribute it, you must open-source your version under AGPL-3.0
- You may **not** use this in a commercial product or SaaS without written permission from the author
- You **must** credit the original author (Dipto Karmakar) in any derivative work

For commercial licensing inquiries: [diptokmk47@gmail.com](mailto:diptokmk47@gmail.com)
