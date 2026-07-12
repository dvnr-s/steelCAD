"""Configurable commercial terms: GST %, default advance %, currency symbol

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-02

company_settings gains the shop-wide commercial defaults; estimates gains a
per-estimate gst_pct snapshot (same reproducibility philosophy as
rate_snapshot: a settings change must never silently reprice an existing
estimate).
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('company_settings', sa.Column(
        'gst_pct', sa.Numeric(5, 2), nullable=False, server_default='18'))
    op.add_column('company_settings', sa.Column(
        'default_advance_pct', sa.Numeric(5, 2), nullable=False, server_default='50'))
    op.add_column('company_settings', sa.Column(
        'currency_symbol', sa.String(8), nullable=False, server_default='₹'))
    # Pre-existing estimates were all priced at 18% GST.
    op.add_column('estimates', sa.Column(
        'gst_pct', sa.Numeric(5, 2), nullable=False, server_default='18'))


def downgrade() -> None:
    op.drop_column('estimates', 'gst_pct')
    op.drop_column('company_settings', 'currency_symbol')
    op.drop_column('company_settings', 'default_advance_pct')
    op.drop_column('company_settings', 'gst_pct')
