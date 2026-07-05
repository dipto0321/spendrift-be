"""add user_preferences table

Revision ID: 525e6b3665ec
Revises: bd89125ec348
Create Date: 2026-07-06 04:34:34.333157

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision = '525e6b3665ec'
down_revision = 'bd89125ec348'
branch_labels = None
depends_on = None

# NOTE: autogenerate also picked up pre-existing drift unrelated to this
# change (nullable created_at/expires_at columns across several tables, a
# missing ix_budgets_tracker_id index) — same drift already called out in
# bd89125ec348. Left out of this migration; address separately if needed.


def upgrade():
    op.create_table('user_preferences',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('budget_alerts_enabled', sa.Boolean(), nullable=False),
    sa.Column('weekly_summary_enabled', sa.Boolean(), nullable=False),
    sa.Column('round_amounts_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )


def downgrade():
    op.drop_table('user_preferences')
