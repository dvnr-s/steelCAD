"""Add role column to users; backfill admins

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-25

Adds the `role` column (admin|owner|sales) that replaces the is_admin boolean
for access control. Existing admins (is_admin=true) are backfilled to role='admin';
all others default to 'sales'. The is_admin column is kept for legacy tooling.
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add role column — nullable first so the UPDATE can run before NOT NULL
    op.add_column('users', sa.Column('role', sa.String(20), nullable=True))

    # Backfill: existing admins → 'admin', everyone else → 'sales'
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = true")
    op.execute("UPDATE users SET role = 'sales' WHERE is_admin = false OR is_admin IS NULL")

    # Now enforce NOT NULL + server default
    op.alter_column('users', 'role', nullable=False, server_default='sales')


def downgrade() -> None:
    op.drop_column('users', 'role')
