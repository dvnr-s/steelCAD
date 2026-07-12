"""Drop estimate_frames.preview_image

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-26

The captured-canvas PNG is no longer used: the quotation PDF now renders every
frame with the deterministic server-side SVG schematic (app.services.diagram),
so all frames look identical. The column and its data are removed.
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('estimate_frames', 'preview_image')


def downgrade() -> None:
    op.add_column('estimate_frames', sa.Column('preview_image', sa.Text(), nullable=True))
