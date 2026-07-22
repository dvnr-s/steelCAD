"""Add users.password_changed_at for token (session) invalidation.

Every JWT embeds this instant as its `pwd` claim; auth rejects a token whose
claim predates the column's current value. Changing or resetting a password
bumps it, which immediately invalidates all previously issued access/refresh
tokens. Existing rows are backfilled to created_at.
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'password_changed_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Seed the watermark from account creation for pre-existing users.
    op.execute("UPDATE users SET password_changed_at = created_at")


def downgrade() -> None:
    op.drop_column('users', 'password_changed_at')
