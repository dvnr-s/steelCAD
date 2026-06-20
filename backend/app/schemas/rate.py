"""
Rate-related Pydantic schemas.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RateResponse(BaseModel):
    """Rate item response."""
    id: UUID
    item_code: str
    rate: float
    unit: str
    label: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class RateUpdate(BaseModel):
    """Request body for updating a rate value (admin only)."""
    rate: float = Field(gt=0)
