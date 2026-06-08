"""
Alembic configuration for database migrations.
"""

from logging.config import fileConfig
from pathlib import Path
import sys

# Ensure project root is importable so `app` and `modules` resolve in Alembic
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import engine_from_config
from sqlalchemy import pool

import alembic.context as context
from app.core.config import settings
from sqlmodel import SQLModel

# Import all models to make them available to Alembic
from modules.users.model import User  # noqa
from modules.trackers.model import Tracker  # noqa
from modules.categories.model import Category  # noqa
from modules.refresh_tokens.model import RefreshToken  # noqa

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set SQLAlchemy URL from settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set the target metadata
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
