"""
Design model — stores the full geometry tree as JSONB.
The tree_json column holds the entire recursive design structure (spec §13).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tree_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    outer_width: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    outer_height: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    section_size: Mapped[str] = mapped_column(String(4), nullable=False)
    gauge: Mapped[str] = mapped_column(String(4), nullable=False)
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
    # Soft-delete: non-null means hidden from all lists/gets but recoverable.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    creator = relationship("User", lazy="joined")
