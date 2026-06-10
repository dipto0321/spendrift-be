"""Timezone-aware datetime columns

Revision ID: e65289d0e673
Revises: ebc995d81be0
Create Date: 2026-06-10 13:26:30.413444

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e65289d0e673'
down_revision = 'ebc995d81be0'
branch_labels = None
depends_on = None

# (table, column, nullable) pairs converted from naive TIMESTAMP to
# TIMESTAMPTZ. Stored values were written as UTC, so the USING clause
# interprets them explicitly as UTC rather than the server timezone.
COLUMNS = [
    ("users", "created_at", False),
    ("users", "updated_at", True),
    ("refresh_tokens", "expires_at", False),
    ("refresh_tokens", "created_at", False),
    ("trackers", "created_at", False),
    ("categories", "created_at", False),
    ("expenses", "created_at", False),
    ("budgets", "created_at", False),
]


def upgrade():
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade():
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
