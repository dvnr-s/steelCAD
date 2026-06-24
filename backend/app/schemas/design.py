"""
Design tree Pydantic schemas — recursive models matching spec §13 serialization format.

The tree is: Design → Frame → rootRegion → (leaf | Split → [Region, Region])
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Pane, Overlay, Hardware sub-schemas ────────────────────────────

class PaneSpec(BaseModel):
    """Layered pane specification (spec §5)."""
    shutterMaterial: Optional[Literal["MS_PIPE", "GP_SHEET"]] = None
    infillType: Literal["none", "glass", "jali"] = "none"
    hasBeading: bool = False


class GrillOverlay(BaseModel):
    """Grill overlay on a region (spec §6). The ONLY overlay type."""
    id: UUID
    type: Literal["overlay"] = "overlay"
    overlayType: Literal["grill"] = "grill"
    material: Literal["MS_SQUARE", "SS_PIPE_ROUND", "SS_PIPE_SQUARE"]


class Hardware(BaseModel):
    """Hardware attachment on a leaf region (spec §7).

    `side` distinguishes front- vs back-side hardware on a door (spec §4A.6).
    `back` is only valid on a double-rebate door region (validated server-side).
    """
    id: UUID
    type: Literal["hardware"] = "hardware"
    hardwareType: Literal["hinge", "lock"]
    variant: str
    quantity: int = Field(ge=1)
    autoComputed: bool = True
    side: Literal["front", "back"] = "front"


# ─── Tree node schemas (recursive) ─────────────────────────────────

class Region(BaseModel):
    """
    A bounded rectangular area. Can be leaf (terminal) or branch (has split).
    Leaf regions have regionType, paneSpec, hardware.
    Branch regions can only have SS grill overlays.
    """
    id: UUID
    type: Literal["region"] = "region"
    x: float = 0
    y: float = 0
    width: float = Field(ge=0.5)
    height: float = Field(ge=0.5)
    isLeaf: bool
    regionType: Optional[Literal["open", "fixed", "shutter", "door", "louver"]] = None
    paneSpec: Optional[PaneSpec] = None
    overlays: list[GrillOverlay] = []
    hardware: list[Hardware] = []
    split: Optional[Split] = None
    # Door-region-only labelling (spec §4A). Cosmetic hand + rebate selector.
    doorHand: Optional[Literal["left", "right"]] = None
    rebate: Literal["single", "double"] = "single"


class Split(BaseModel):
    """
    Structural divider — binary split producing exactly 2 child regions.
    Position is a ratio (0..1 exclusive) within the parent region.
    """
    id: UUID
    type: Literal["split"] = "split"
    direction: Literal["horizontal", "vertical"]
    position: float = Field(gt=0, lt=1)
    children: list[Region] = Field(min_length=2, max_length=2)


# Rebuild forward references for recursive models
Region.model_rebuild()
Split.model_rebuild()


class Frame(BaseModel):
    """Outer boundary of the design. Always at (0,0)."""
    id: UUID
    type: Literal["frame"] = "frame"
    width: float = Field(ge=1)
    height: float = Field(ge=1)
    rootRegion: Region


class DesignTree(BaseModel):
    """
    Full design tree — the serialized JSON structure (spec §13).
    This is the canonical in-memory representation of a steel window/door design.
    """
    id: UUID
    type: Literal["design"] = "design"
    name: str
    productType: Literal["window", "door"] = "window"
    outerWidth: float = Field(ge=1)
    outerHeight: float = Field(ge=1)
    sectionSize: Literal["5", "6", "10"]
    gauge: Literal["18G", "16G"]
    frame: Frame


# ─── API request/response schemas ──────────────────────────────────

class DesignCreate(BaseModel):
    """Request body for creating a new design."""
    name: str
    description: Optional[str] = None
    productType: Literal["window", "door"] = "window"
    outerWidth: float = Field(ge=1)
    outerHeight: float = Field(ge=1)
    sectionSize: Literal["5", "6", "10"] = "5"
    gauge: Literal["18G", "16G"] = "18G"
    tree_json: DesignTree


class DesignUpdate(BaseModel):
    """Request body for updating an existing design."""
    name: Optional[str] = None
    description: Optional[str] = None
    tree_json: Optional[DesignTree] = None


class DesignResponse(BaseModel):
    """Full design response with tree JSON and metadata."""
    id: UUID
    name: str
    description: Optional[str]
    tree_json: dict
    outer_width: float
    outer_height: float
    section_size: str
    gauge: str
    created_by: UUID
    created_by_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DesignListItem(BaseModel):
    """Compact design summary for dashboard list view."""
    id: UUID
    name: str
    description: Optional[str]
    product_type: str = "window"
    outer_width: float
    outer_height: float
    section_size: str
    gauge: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
