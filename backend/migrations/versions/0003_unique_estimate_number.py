"""Add UNIQUE constraint on estimates.number

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-25

Estimate numbers are a human-friendly EST-#### sequence allocated as max(number)+1.
Without a UNIQUE constraint, two concurrent creates could pick the same number.
This adds the constraint that the application's retry loop relies on.

NOTE: if a pre-existing database already contains duplicate `number` values, this
migration will fail — deduplicate them first (renumber the collisions) before upgrading.
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint('uq_estimates_number', 'estimates', ['number'])


def downgrade() -> None:
    op.drop_constraint('uq_estimates_number', 'estimates', type_='unique')
