"""Add users.deleted_at for anonymized account deletion.

Deleting a user no longer removes the row (designs/customers/estimates carry a
NOT NULL created_by FK to users.id). Instead PII is scrubbed in place and
deleted_at is set; auth rejects tokens for deleted users.
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_users_deleted_at', 'users', ['deleted_at'])


def downgrade() -> None:
    op.drop_index('ix_users_deleted_at', table_name='users')
    op.drop_column('users', 'deleted_at')
