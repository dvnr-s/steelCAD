"""Estimate other charges (labor / transport / installation line items)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-13

PR-9: estimates gain `other_charges` — a JSONB list of {label, amount} manual
line items for costs the geometry cannot derive (labor, transport,
installation). Charges join the frames subtotal before discount, so discount
and GST apply to the combined amount. Pre-existing estimates simply have no
charges ([]), leaving their totals untouched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('estimates', sa.Column(
        'other_charges', postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column('estimates', 'other_charges')
