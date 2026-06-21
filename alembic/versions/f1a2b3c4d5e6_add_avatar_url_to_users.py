"""add avatar_url to users

Revision ID: f1a2b3c4d5e6
Revises: ebc995d81be0
Create Date: 2026-06-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = 'e65289d0e673'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('avatar_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'avatar_url')
