"""Initial schema — all tables

Revision ID: 0001
Revises:
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # ── customers ────────────────────────────────────────────────────
    op.create_table(
        'customers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('company', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(40), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('gstin', sa.String(20), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── designs ──────────────────────────────────────────────────────
    op.create_table(
        'designs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tree_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('outer_width', sa.Numeric(6, 2), nullable=False),
        sa.Column('outer_height', sa.Numeric(6, 2), nullable=False),
        sa.Column('section_size', sa.String(4), nullable=False),
        sa.Column('gauge', sa.String(4), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── rates ─────────────────────────────────────────────────────────
    op.create_table(
        'rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('item_code', sa.String(50), nullable=False),
        sa.Column('rate', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rates_item_code', 'rates', ['item_code'], unique=True)

    # ── estimates ─────────────────────────────────────────────────────
    op.create_table(
        'estimates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='draft', nullable=False),
        sa.Column('discount_type', sa.String(20), nullable=True),
        sa.Column('discount_value', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('advance_pct', sa.Numeric(5, 2), server_default='50', nullable=False),
        sa.Column('rate_snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('subtotal', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('discount_amount', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('taxable', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('gst', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('grand_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('advance_amount', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_estimates_customer_id', 'estimates', ['customer_id'])

    # ── estimate_frames ───────────────────────────────────────────────
    op.create_table(
        'estimate_frames',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('estimate_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_design_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('tree_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('outer_width', sa.Numeric(6, 2), nullable=False),
        sa.Column('outer_height', sa.Numeric(6, 2), nullable=False),
        sa.Column('section_size', sa.String(4), nullable=False),
        sa.Column('gauge', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('unit_breakdown', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('unit_subtotal', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('line_total', sa.Numeric(12, 2), server_default='0', nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['estimate_id'], ['estimates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_design_id'], ['designs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_estimate_frames_estimate_id', 'estimate_frames', ['estimate_id'])


def downgrade() -> None:
    op.drop_table('estimate_frames')
    op.drop_table('estimates')
    op.drop_index('ix_rates_item_code', table_name='rates')
    op.drop_table('rates')
    op.drop_table('designs')
    op.drop_table('customers')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
