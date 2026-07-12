"""Add quote metadata + frame preview image

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-25

Adds quote-level metadata to estimates (quote_date, valid_until, terms) and a
captured-render column to estimate_frames (preview_image, a PNG data-URL embedded
in the quotation PDF; null falls back to a server-side SVG schematic).
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('estimates', sa.Column('quote_date', sa.Date(), nullable=True))
    op.add_column('estimates', sa.Column('valid_until', sa.Date(), nullable=True))
    op.add_column('estimates', sa.Column('terms', sa.Text(), nullable=True))
    # Backfill quote_date for existing rows so the column reads cleanly.
    op.execute("UPDATE estimates SET quote_date = created_at::date WHERE quote_date IS NULL")

    op.add_column('estimate_frames', sa.Column('preview_image', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('estimate_frames', 'preview_image')
    op.drop_column('estimates', 'terms')
    op.drop_column('estimates', 'valid_until')
    op.drop_column('estimates', 'quote_date')
