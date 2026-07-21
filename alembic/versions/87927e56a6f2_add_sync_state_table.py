"""add sync_state table

Revision ID: 87927e56a6f2
Revises: 525e6b3665ec
Create Date: 2026-07-19 20:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "87927e56a6f2"
down_revision = "525e6b3665ec"
branch_labels = None
depends_on = None


def upgrade():
    # Used by scripts/sync_db.py to track the high-watermark for each
    # bidirectional sync. One row per synced table; last_synced_at is the
    # cursor used by the next run. NOT a SQLModel — autogenerate will skip it.
    op.create_table(
        "sync_state",
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("'epoch'::timestamptz"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("table_name"),
    )


def downgrade():
    op.drop_table("sync_state")
