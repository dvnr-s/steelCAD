"""
Estimate-related Pydantic schemas.

Hierarchy: Customer → Estimate → EstimateFrame (one geometry per frame, × qty).
Estimate-level discount/GST/advance apply to the aggregate of frame line totals.
"""
from datetime import datetime, date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

EstimateStatus = Literal["draft", "sent", "accepted", "rejected"]


# ─── Per-unit breakdown sub-schemas (output of the pricing engine) ──

class LineItem(BaseModel):
    label: str
    description: str
    quantity: float
    unit: str
    rate: float
    cost: float


class RegionBreakdown(BaseModel):
    region_id: str
    region_label: str
    region_type: str
    dimensions: str
    pane_structure: Optional[LineItem] = None
    # Second shutter leaf of a double-shuttered region (spec §5.7) — jali side.
    pane_structure_2: Optional[LineItem] = None
    infill: Optional[LineItem] = None
    beading: Optional[LineItem] = None
    grill: Optional[LineItem] = None
    hardware: list[LineItem] = []
    subtotal: float


class UnitBreakdown(BaseModel):
    """Full itemized breakdown for a single unit (one frame)."""
    frame: LineItem
    splits: list[LineItem]
    regions: list[RegionBreakdown]
    subtotal: float


# ─── Stateless price preview (used by the canvas live price) ────────

class PriceRequest(BaseModel):
    tree_json: dict


# ─── Frames ─────────────────────────────────────────────────────────

class FrameInput(BaseModel):
    """Add/replace a frame. Provide either source_design_id (copy from library)
    or tree_json (a one-off design). quantity defaults to 1."""
    name: Optional[str] = None
    quantity: int = Field(default=1, ge=1)
    source_design_id: Optional[UUID] = None
    tree_json: Optional[dict] = None


class FrameUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=1)
    tree_json: Optional[dict] = None


class FrameDetail(BaseModel):
    id: UUID
    name: str
    quantity: int
    outer_width: float
    outer_height: float
    section_size: str
    gauge: str
    tree_json: dict
    unit_subtotal: float
    line_total: float
    unit_breakdown: dict
    source_design_id: Optional[UUID] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ─── Estimates ──────────────────────────────────────────────────────

class OtherCharge(BaseModel):
    """PR-9: a manual estimate-level line item the geometry cannot derive —
    labor/fabrication, transport, installation, and similar."""
    label: str = Field(min_length=1, max_length=80)
    amount: float = Field(ge=0)


class EstimateCreate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    valid_until: Optional[date] = None
    terms: Optional[str] = None
    discount_type: Optional[Literal["PERCENTAGE", "FLAT"]] = None
    discount_value: float = Field(default=0, ge=0)
    # None → the company's default_advance_pct applies.
    advance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    other_charges: list[OtherCharge] = Field(default_factory=list, max_length=20)


class EstimateUpdate(BaseModel):
    """Commercial terms + metadata. Status flows through PATCH /status only."""
    title: Optional[str] = None
    notes: Optional[str] = None
    valid_until: Optional[date] = None
    terms: Optional[str] = None
    discount_type: Optional[Literal["PERCENTAGE", "FLAT"]] = None
    discount_value: Optional[float] = Field(default=None, ge=0)
    advance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    other_charges: Optional[list[OtherCharge]] = Field(default=None, max_length=20)


class EstimateStatusUpdate(BaseModel):
    status: EstimateStatus


class CustomerBrief(BaseModel):
    id: UUID
    name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None

    model_config = {"from_attributes": True}


class EstimateDetail(BaseModel):
    id: UUID
    number: int
    revision: int = 1
    parent_id: Optional[UUID] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    status: str
    quote_date: Optional[date] = None
    valid_until: Optional[date] = None
    terms: Optional[str] = None
    customer: CustomerBrief
    discount_type: Optional[str] = None
    discount_value: float
    advance_pct: float
    gst_pct: float
    # Derived: sent quote past its valid_until date (never stored).
    is_expired: bool = False
    frames: list[FrameDetail]
    subtotal: float
    other_charges: list[OtherCharge] = Field(default_factory=list)
    other_charges_total: float = 0
    discount_amount: float
    taxable: float
    gst: float
    grand_total: int
    advance_amount: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EstimateSummary(BaseModel):
    id: UUID
    number: int
    revision: int = 1
    title: Optional[str] = None
    status: str
    customer_id: UUID
    customer_name: str
    frame_count: int
    grand_total: int
    is_expired: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
