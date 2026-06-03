"""migrate_users_to_proper_types

Revision ID: 18ba05361672
Revises: bd81a202b4b3
Create Date: 2026-06-03 23:17:04.837983

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel  # noqa: F401


# revision identifiers, used by Alembic.
revision = '18ba05361672'
down_revision = 'bd81a202b4b3'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the index on created_at before altering the column
    op.drop_index("ix_users_created_at", table_name="users")

    # Convert id from VARCHAR to UUID
    op.alter_column(
        "users",
        "id",
        existing_type=sa.String(),
        type_=postgresql.UUID(),
        postgresql_using="id::uuid",
    )

    # Convert created_at from VARCHAR to TIMESTAMP (UTC-aware)
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.String(),
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at::timestamp with time zone",
    )

    # Add updated_at column
    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Recreate the index on created_at
    op.create_index("ix_users_created_at", "users", ["created_at"])


def downgrade():
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_column("users", "updated_at")

    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.String(),
        postgresql_using="created_at::text",
    )

    op.alter_column(
        "users",
        "id",
        existing_type=postgresql.UUID(),
        type_=sa.String(),
        postgresql_using="id::text",
    )

    op.create_index("ix_users_created_at", "users", ["created_at"])
