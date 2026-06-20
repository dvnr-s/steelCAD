"""
Estimate-related Pydantic schemas — request, breakdown line items, response.
"""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Request ────────────────────────────────────────────────────────

class EstimateRequest(BaseModel):
    """Parameters for generating an estimate from a saved design."""
    discount_type: Optional[Literal["PERCENTAGE", "FLAT"]] = None
    discount_value: float = Field(default=0, ge=0)
    advance_pct: float = Field(default=50, ge=0, le=100)


# ─── Breakdown sub-schemas ──────────────────────────────────────────

class LineItem(BaseModel):
    """A single priced line in the estimate breakdown."""
    label: str
    description: str
    quantity: float
    unit: str
    rate: float
    cost: float


class RegionBreakdown(BaseModel):
    """Cost breakdown for one region."""
    region_id: str
    region_label: str
    region_type: str
    dimensions: str
    pane_structure: Optional[LineItem] = None
    infill: Optional[LineItem] = None
    beading: Optional[LineItem] = None
    grill: Optional[LineItem] = None
    hardware: list[LineItem] = []
    subtotal: float


class EstimateBreakdown(BaseModel):
    """Full itemized estimate breakdown."""
    frame: LineItem
    splits: list[LineItem]
    regions: list[RegionBreakdown]
    subtotal: float
    discount_type: Optional[str] = None
    discount_value: float = 0
    discount_amount: float = 0
    taxable: float
    gst: float
    grand_total: int
    advance_pct: float
    advance_amount: float


# ─── Response ───────────────────────────────────────────────────────

class EstimateResponse(BaseModel):
    """Full estimate with breakdown and rate snapshot."""
    id: UUID
    design_id: UUID
    version_number: int
    breakdown: EstimateBreakdown
    rate_snapshot: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class EstimateListItem(BaseModel):
    """Compact estimate summary for list view."""
    id: UUID
    version_number: int
    grand_total: int
    created_at: datetime

    model_config = {"from_attributes": True}
