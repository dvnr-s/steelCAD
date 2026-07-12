"""Quote revisions: revision counter, parent link, accepted_at

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-02

A revision is a duplicate of a locked (sent/accepted/rejected) estimate that
keeps the same human-facing number with revision+1; the source moves to the
terminal 'superseded' status. The 0003 single-column unique on `number` is
replaced by UNIQUE(number, revision).

NOTE: downgrade recreates the single-column unique — it will fail if any
revisions (duplicate numbers) exist; delete or renumber them first.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('estimates', sa.Column(
        'revision', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('estimates', sa.Column(
        'parent_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_estimates_parent_id', 'estimates', 'estimates',
        ['parent_id'], ['id'], ondelete='SET NULL')
    op.add_column('estimates', sa.Column(
        'accepted_at', sa.DateTime(timezone=True), nullable=True))
    # Constraint name from 0003_unique_estimate_number.py. IF EXISTS also covers
    # databases bootstrapped via metadata.create_all (constraint named
    # estimates_number_key, or missing entirely on drifted dev DBs).
    op.execute("ALTER TABLE estimates DROP CONSTRAINT IF EXISTS uq_estimates_number")
    op.execute("ALTER TABLE estimates DROP CONSTRAINT IF EXISTS estimates_number_key")
    op.create_unique_constraint(
        'uq_estimates_number_revision', 'estimates', ['number', 'revision'])


def downgrade() -> None:
    op.drop_constraint('uq_estimates_number_revision', 'estimates', type_='unique')
    op.create_unique_constraint('uq_estimates_number', 'estimates', ['number'])
    op.drop_constraint('fk_estimates_parent_id', 'estimates', type_='foreignkey')
    op.drop_column('estimates', 'accepted_at')
    op.drop_column('estimates', 'parent_id')
    op.drop_column('estimates', 'revision')
