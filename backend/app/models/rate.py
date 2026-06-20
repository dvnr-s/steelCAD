"""
Rate model — material rate lookup table.
Seeded from spec §9.2 defaults. Only admins can update rates.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Rate(Base):
    __tablename__ = "rates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
