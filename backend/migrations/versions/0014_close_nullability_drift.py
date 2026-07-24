"""Close NOT NULL drift between the ORM models and the migrated schema.

Two columns were added as nullable and never tightened, so the schema built by
`create_all` (dev) and the schema built by the migrations (production) disagreed:

  - `estimates.quote_date`        — added nullable in 0004, backfilled, left nullable
  - `company_settings.updated_at` — created nullable in 0005

Both are declared non-optional on the models (`Mapped[date]` / `Mapped[datetime]`
with Python-side defaults), so dev enforced NOT NULL while production did not.
`alembic revision --autogenerate` against a migrated database reported exactly
these two ALTERs — this migration is that diff, applied.

No application path can currently write a NULL here (the ORM always supplies a
default), so the backfills below are belt-and-braces for any row created by hand
or by an older tool before the constraint existed.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill before tightening — a single NULL would abort the ALTER.
    op.execute(
        "UPDATE estimates SET quote_date = created_at::date WHERE quote_date IS NULL"
    )
    op.alter_column(
        'estimates', 'quote_date',
        existing_type=sa.Date(),
        nullable=False,
    )

    op.execute(
        "UPDATE company_settings SET updated_at = now() WHERE updated_at IS NULL"
    )
    op.alter_column(
        'company_settings', 'updated_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'company_settings', 'updated_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        'estimates', 'quote_date',
        existing_type=sa.Date(),
        nullable=True,
    )
