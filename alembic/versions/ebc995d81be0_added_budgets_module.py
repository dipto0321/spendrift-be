"""Added budgets module

Revision ID: ebc995d81be0
Revises: adb75b1dc8b0
Create Date: 2026-06-10 04:43:56.704172

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

# revision identifiers, used by Alembic.
revision = 'ebc995d81be0'
down_revision = 'adb75b1dc8b0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('budgets',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tracker_id', sa.Uuid(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('monthly_limit', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('savings_target', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('month', sqlmodel.sql.sqltypes.AutoString(length=7), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['tracker_id'], ['trackers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tracker_id', 'month', name='uq_budgets_tracker_id_month')
    )
    op.create_index('ix_budgets_tracker_id', 'budgets', ['tracker_id'], unique=False)


def downgrade():
    op.drop_index('ix_budgets_tracker_id', table_name='budgets')
    op.drop_table('budgets')
