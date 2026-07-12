"""Add audit_log and rate_history tables

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-25

An append-only activity trail (who changed what) and a global rate-change history
(per-estimate pricing stays frozen in Estimate.rate_snapshot).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('entity_type', sa.String(40), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_log_actor_id', 'audit_log', ['actor_id'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])

    op.create_table(
        'rate_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('item_code', sa.String(50), nullable=False),
        sa.Column('old_rate', sa.Numeric(10, 2), nullable=False),
        sa.Column('new_rate', sa.Numeric(10, 2), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_rate_history_item_code', 'rate_history', ['item_code'])
    op.create_index('ix_rate_history_created_at', 'rate_history', ['created_at'])


def downgrade() -> None:
    op.drop_table('rate_history')
    op.drop_table('audit_log')
