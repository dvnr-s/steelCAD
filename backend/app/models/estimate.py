"""
EstimateVersion model — immutable pricing snapshots.
Each estimate version captures the rate snapshot + full breakdown at generation time.
Old estimates NEVER change when rates are updated (PR-7).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EstimateVersion(Base):
    __tablename__ = "estimate_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    design_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("designs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rate_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    breakdown_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    discount_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discount_value: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    taxable: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    gst: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    grand_total: Mapped[int] = mapped_column(Integer, nullable=False)
    advance_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=50)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationship
    design = relationship("Design", back_populates="estimates")
