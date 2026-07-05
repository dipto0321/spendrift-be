"""add category_budgets table

Revision ID: bd89125ec348
Revises: a1b2c3d4e5f6
Create Date: 2026-07-05 13:00:40.323335

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision = 'bd89125ec348'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None

# NOTE: autogenerate also picked up pre-existing drift unrelated to this
# change (nullable created_at columns on several tables, a missing
# ix_budgets_tracker_id index) caused by alembic/env.py previously not
# importing the Budget model. That drift is intentionally left out of this
# migration — see the category_budgets module PR discussion — and should be
# addressed in its own migration if/when it's actually a problem.


def upgrade():
    op.create_table('category_budgets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('budget_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('allocated_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['budget_id'], ['budgets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('budget_id', 'category_id', name='uq_category_budgets_budget_id_category_id')
    )


def downgrade():
    op.drop_table('category_budgets')
