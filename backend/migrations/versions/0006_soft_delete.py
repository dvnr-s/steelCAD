"""Add soft-delete (deleted_at) to designs, customers, estimates

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-25

Deletes become recoverable: handlers set `deleted_at` instead of removing rows, and
every list/get query filters `deleted_at IS NULL`. A restore endpoint clears it.
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None

_TABLES = ('designs', 'customers', 'estimates')


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
        op.create_index(f'ix_{table}_deleted_at', table, ['deleted_at'])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f'ix_{table}_deleted_at', table_name=table)
        op.drop_column(table, 'deleted_at')
