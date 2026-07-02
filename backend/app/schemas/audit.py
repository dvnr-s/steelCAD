"""Audit log schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AuditEntry(BaseModel):
    id: UUID
    actor_id: Optional[UUID] = None
    actor_name: str = "System"
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime
