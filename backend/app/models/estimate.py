"""
Estimate models.

An Estimate belongs to a Customer and groups multiple frames (doors/windows).
Each EstimateFrame carries its own geometry tree (a copy, so editing it never
mutates a library design) plus a quantity. Estimate-level discount, GST, and
advance are applied to the aggregate of all frame line totals.
"""
import uuid
from datetime import datetime, date, timezone

from sqlalchemy import String, Integer, Numeric, Text, DateTime, Date, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Estimate(Base):
    __tablename__ = "estimates"
    __table_args__ = (
        # Revisions share the source's number: EST-0007 rev 1, rev 2, ...
        UniqueConstraint("number", "revision", name="uq_estimates_number_revision"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # human-friendly EST-#### sequence
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | accepted | rejected | superseded
    # Revision chain: a revise copies a locked quote as number/revision+1 and
    # marks the source 'superseded' (terminal — immutable, kept for history).
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estimates.id", ondelete="SET NULL"), nullable=True
    )
    # Set when the quote moves to accepted (dashboard revenue-by-month).
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Quote metadata
    quote_date: Mapped[date] = mapped_column(
        Date, default=lambda: datetime.now(timezone.utc).date()
    )
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Estimate-level commercial terms
    discount_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discount_value: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    advance_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=50)
    # GST % snapshot taken from company settings at creation — a settings change
    # never silently reprices an existing estimate (same idea as rate_snapshot).
    gst_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=18)

    # Snapshot of rates used at last recompute (reproducibility)
    rate_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Aggregate totals (recomputed whenever frames/terms change)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    taxable: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    gst: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    grand_total: Mapped[int] = mapped_column(Integer, default=0)
    advance_amount: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    # Soft-delete: non-null means hidden from lists/gets but recoverable.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    customer = relationship("Customer", back_populates="estimates", lazy="joined")
    frames = relationship(
        "EstimateFrame", back_populates="estimate", lazy="selectin",
        cascade="all, delete-orphan", order_by="EstimateFrame.sort_order",
    )


class EstimateFrame(Base):
    __tablename__ = "estimate_frames"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("estimates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Provenance if added from the reusable design library (nulled if that design is deleted).
    source_design_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("designs.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tree_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outer_width: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    outer_height: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    section_size: Mapped[str] = mapped_column(String(4), nullable=False)
    gauge: Mapped[str] = mapped_column(String(4), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    unit_subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    estimate = relationship("Estimate", back_populates="frames")
