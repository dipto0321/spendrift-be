"""add user_avatars table and rename avatar_url to avatar_file_key

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rename users.avatar_url → users.avatar_file_key.
    # Existing base64 data URLs are cleared — they are incompatible with the
    # new file-key semantics (presigned URL generation would fail on them).
    op.alter_column("users", "avatar_url", new_column_name="avatar_file_key")
    op.execute("UPDATE users SET avatar_file_key = NULL")

    op.create_table(
        "user_avatars",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_avatars_user_id", "user_avatars", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_avatars_user_id", table_name="user_avatars")
    op.drop_table("user_avatars")
    op.alter_column("users", "avatar_file_key", new_column_name="avatar_url")
