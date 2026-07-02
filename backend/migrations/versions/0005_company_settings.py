"""Add company_settings singleton table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-25

The seller profile (name, logo, GSTIN, bank details, default terms) used to brand
the quotation PDF. Single row, id=1; seeded with a default name so the PDF always
has a letterhead.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, server_default='SteelCAD'),
        sa.Column('logo_data_url', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(40), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('gstin', sa.String(20), nullable=True),
        sa.Column('bank_details', sa.Text(), nullable=True),
        sa.Column('default_terms', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Seed the singleton row.
    op.execute("INSERT INTO company_settings (id, name) VALUES (1, 'SteelCAD')")


def downgrade() -> None:
    op.drop_table('company_settings')
