"""
User model — accounts with role-based access control.

Roles:
  admin  — full system access, can manage users (any role) and rates
  owner  — business-level access, can manage rates and create/manage sales users
  sales  — day-to-day estimating; sees all data but cannot manage rates or users
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ROLE_ADMIN = "admin"
ROLE_OWNER = "owner"
ROLE_SALES = "sales"
VALID_ROLES = {ROLE_ADMIN, ROLE_OWNER, ROLE_SALES}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ROLE_SALES, server_default=ROLE_SALES
    )
    # Legacy column kept for any tooling that may still reference it.
    # In code, use user.role instead.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Account deletion: the row is kept (created_by FKs on designs/customers/
    # estimates are NOT NULL) but PII is scrubbed via anonymize_user() and
    # deleted_at is set, which blocks login and invalidates outstanding tokens.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
