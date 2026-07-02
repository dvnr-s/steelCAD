"""
Company settings — a single-row table holding the seller's identity used to
brand the quotation PDF (letterhead, GSTIN, bank details, default terms).

Singleton: there is always exactly one row, id=1. In a future multi-tenant move
this becomes one row per organization.
"""
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="SteelCAD")
    logo_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # data:image/png;base64,...
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
