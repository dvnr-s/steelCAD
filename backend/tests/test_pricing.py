"""
Pricing engine unit tests.

Tests the core business logic against the examples in design_rules_spec.md.
These tests run WITHOUT a database — the pricing engine is pure Python.
"""
import uuid
import pytest
from app.services.pricing import price_design, _round2, _round_rupee, DEFAULT_RATES


# ─── Build a rate dict from DEFAULT_RATES ──────────────────────────
RATES = {r["item_code"]: r["rate"] for r in DEFAULT_RATES}


def _uuid() -> str:
    """Generate a UUID string for test fixtures."""
    return str(uuid.uuid4())


# ─── Helpers to build tree fixtures ────────────────────────────────

def _leaf_region(
    width: float,
    height: float,
    region_type: str = "open",
    pane_spec: dict | None = None,
    overlays: list | None = None,
    hardware: list | None = None,
    x: float = 0,
    y: float = 0,
) -> dict:
    return {
        "id": _uuid(),
        "type": "region",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "isLeaf": True,
        "regionType": region_type,
        "paneSpec": pane_spec,
        "overlays": overlays or [],
        "hardware": hardware or [],
        "split": None,
    }


def _design_tree(
    width: float,
    height: float,
    root_region: dict,
    section_size: str = "5",
    gauge: str = "18G",
) -> dict:
    return {
        "id": _uuid(),
        "type": "design",
        "name": "Test Design",
        "outerWidth": width,
        "outerHeight": height,
        "sectionSize": section_size,
        "gauge": gauge,
        "frame": {
            "id": _uuid(),
            "type": "frame",
            "width": width,
            "height": height,
            "rootRegion": root_region,
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Test: Rounding helpers
# ═══════════════════════════════════════════════════════════════════

def test_round2():
    assert _round2(1.005) == 1.01  # banker's rounding edge case
    assert _round2(1.234) == 1.23
    assert _round2(1.235) == 1.24
    assert _round2(100.0) == 100.0


def test_round_rupee():
    assert _round_rupee(1234.4) == 1234
    assert _round_rupee(1234.5) == 1235
    assert _round_rupee(1234.6) == 1235


# ═══════════════════════════════════════════════════════════════════
# Test: Simple frame-only design (no splits, open region)
# ═══════════════════════════════════════════════════════════════════

def test_frame_only_open_region():
    """A 5ft × 4ft frame with one open region. Only frame cost."""
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES)

    # Frame: 2×(5+4) = 18 RFT × ₹120 = ₹2,160
    assert result["frame"]["quantity"] == 18.0
    assert result["frame"]["rate"] == 120.0
    assert result["frame"]["cost"] == 2160.0

    # No splits, no region costs
    assert result["splits"] == []
    assert result["subtotal"] == 2160.0

    # GST: 2160 × 0.18 = 388.80
    assert result["gst"] == 388.80
    # Grand total: 2160 + 388.80 = 2548.80 → ₹2549
    assert result["grand_total"] == 2549


# ═══════════════════════════════════════════════════════════════════
# Test: Spec §13 example — 5ft × 4ft window with vertical split
# ═══════════════════════════════════════════════════════════════════

def test_spec_example_5x4_split():
    """
    Matches the example from design_rules_spec.md §13:
    5ft × 4ft window, vertical split at 60%.
    Left: fixed, glass + beading + MS grill.
    Right: shutter (MS pipe), glass + beading, 2 hinges.
    """
    left_region = _leaf_region(
        width=3.0, height=4.0,
        region_type="fixed",
        pane_spec={"shutterMaterial": None, "infillType": "glass", "hasBeading": True},
        overlays=[{
            "id": _uuid(),
            "type": "overlay",
            "overlayType": "grill",
            "material": "MS_SQUARE",
        }],
    )
    right_region = _leaf_region(
        width=2.0, height=4.0, x=3.0,
        region_type="shutter",
        pane_spec={"shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": True},
        hardware=[{
            "id": _uuid(),
            "type": "hardware",
            "hardwareType": "hinge",
            "variant": "SS_12G",
            "quantity": 2,
            "autoComputed": True,
        }],
    )

    root = {
        "id": _uuid(),
        "type": "region",
        "x": 0, "y": 0,
        "width": 5.0, "height": 4.0,
        "isLeaf": False,
        "regionType": None,
        "paneSpec": None,
        "overlays": [],
        "hardware": [],
        "split": {
            "id": _uuid(),
            "type": "split",
            "direction": "vertical",
            "position": 0.6,
            "children": [left_region, right_region],
        },
    }

    tree = _design_tree(5.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    # Frame: 2×(5+4) = 18 RFT × 120 = ₹2,160
    assert result["frame"]["cost"] == 2160.0

    # One vertical split (mullion): length = 4ft × 120 = ₹480
    assert len(result["splits"]) == 1
    assert result["splits"][0]["quantity"] == 4.0
    assert result["splits"][0]["cost"] == 480.0

    # Left panel (fixed, glass + beading + MS grill):
    left = result["regions"][0]
    assert left["region_type"] == "fixed"
    # No pane structure for fixed (P-4)
    assert left["pane_structure"] is None
    # Beading: 2×(3+4)×40 = ₹560
    assert left["beading"]["cost"] == 560.0
    # MS grill: 3×4×100 = ₹1,200
    assert left["grill"]["cost"] == 1200.0
    # Left subtotal: 560 + 1200 = ₹1,760
    assert left["subtotal"] == 1760.0

    # Right panel (shutter, MS pipe, glass + beading, 2 hinges):
    right = result["regions"][1]
    assert right["region_type"] == "shutter"
    # Pane structure: 2×(2+4)×100 = ₹1,200
    assert right["pane_structure"]["cost"] == 1200.0
    # Beading: 2×(2+4)×40 = ₹480
    assert right["beading"]["cost"] == 480.0
    # Hinges: 2×120 = ₹240
    assert right["hardware"][0]["cost"] == 240.0
    # Right subtotal: 1200 + 480 + 240 = ₹1,920
    assert right["subtotal"] == 1920.0

    # Total: frame(2160) + split(480) + left(1760) + right(1920) = ₹6,320
    assert result["subtotal"] == 6320.0


# ═══════════════════════════════════════════════════════════════════
# Test: SS grill bar-count formula
# ═══════════════════════════════════════════════════════════════════

def test_ss_grill_bar_count():
    """
    Spec §6.2 example 1: 5ft × 4ft region with SS Pipe Round grill.
    bars = (2×5) − 2 = 8
    RFT = 8 × 4 = 32
    cost = 32 × 90 = ₹2,880
    """
    root = _leaf_region(
        width=4.0, height=5.0,
        region_type="open",
        overlays=[{
            "id": _uuid(),
            "type": "overlay",
            "overlayType": "grill",
            "material": "SS_PIPE_ROUND",
        }],
    )
    tree = _design_tree(4.0, 5.0, root, "5", "18G")
    result = price_design(tree, RATES)

    grill = result["regions"][0]["grill"]
    assert grill is not None
    assert grill["quantity"] == 32.0  # 8 bars × 4ft
    assert grill["rate"] == 90.0
    assert grill["cost"] == 2880.0


# ═══════════════════════════════════════════════════════════════════
# Test: SS grill continuity on branch region
# ═══════════════════════════════════════════════════════════════════

def test_ss_grill_continuity():
    """
    Spec §13 note: 3ft × 4ft branch region with SS grill.
    bars = (2×4)−2 = 6, RFT = 6×3 = 18.
    Internal splits are irrelevant — grill uses enclosing region dims.
    """
    child_a = _leaf_region(2.0, 4.0, "open")
    child_b = _leaf_region(1.0, 4.0, "open", x=2.0)

    branch = {
        "id": _uuid(),
        "type": "region",
        "x": 0, "y": 0,
        "width": 3.0, "height": 4.0,
        "isLeaf": False,
        "regionType": None,
        "paneSpec": None,
        "overlays": [{
            "id": _uuid(),
            "type": "overlay",
            "overlayType": "grill",
            "material": "SS_PIPE_ROUND",
        }],
        "hardware": [],
        "split": {
            "id": _uuid(),
            "type": "split",
            "direction": "vertical",
            "position": 0.67,
            "children": [child_a, child_b],
        },
    }

    tree = _design_tree(3.0, 4.0, branch, "5", "18G")
    result = price_design(tree, RATES)

    # The branch region should have grill cost
    branch_bd = [r for r in result["regions"] if r["region_type"] == "branch"]
    assert len(branch_bd) == 1
    grill = branch_bd[0]["grill"]
    assert grill is not None
    assert grill["quantity"] == 18.0  # 6 bars × 3ft
    assert grill["cost"] == 1620.0   # 18 × 90


# ═══════════════════════════════════════════════════════════════════
# Test: Door region with GP sheet, hinges, lock
# ═══════════════════════════════════════════════════════════════════

def test_door_with_lock():
    """
    Spec §13 example: 7ft × 3ft door, GP Sheet.
    Pane: 2×(7+3)×250 = ₹5,000
    Hinges (door, ≤7ft → 3): 3×120 = ₹360
    Lock: 1×100 = ₹100
    """
    root = _leaf_region(
        width=3.0, height=7.0,
        region_type="door",
        pane_spec={"shutterMaterial": "GP_SHEET", "infillType": "none", "hasBeading": False},
        hardware=[
            {
                "id": _uuid(), "type": "hardware",
                "hardwareType": "hinge", "variant": "SS_12G",
                "quantity": 3, "autoComputed": True,
            },
            {
                "id": _uuid(), "type": "hardware",
                "hardwareType": "lock", "variant": "standard",
                "quantity": 1, "autoComputed": False,
            },
        ],
    )
    tree = _design_tree(3.0, 7.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    # Pane structure: 2×(3+7)×250 = ₹5,000
    assert region["pane_structure"]["cost"] == 5000.0
    # Hinges: 3×120 = ₹360
    assert region["hardware"][0]["cost"] == 360.0
    # Lock: 1×100 = ₹100
    assert region["hardware"][1]["cost"] == 100.0
    assert region["subtotal"] == 5460.0


# ═══════════════════════════════════════════════════════════════════
# Test: Jali infill + beading
# ═══════════════════════════════════════════════════════════════════

def test_jali_with_beading():
    """
    Spec §5.5 example: shutter 3×4ft MS_PIPE, jali, beading.
    Pane: 2×(3+4)×100 = ₹1,400
    Jali: 3×4×110 = ₹1,320
    Beading: 2×(3+4)×40 = ₹560
    Total: ₹3,280
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={"shutterMaterial": "MS_PIPE", "infillType": "jali", "hasBeading": True},
        hardware=[{
            "id": _uuid(), "type": "hardware",
            "hardwareType": "hinge", "variant": "SS_12G",
            "quantity": 2, "autoComputed": True,
        }],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"]["cost"] == 1400.0
    assert region["infill"]["cost"] == 1320.0
    assert region["beading"]["cost"] == 560.0
    # Region subtotal: 1400+1320+560+240(hinges) = ₹3,520
    assert region["subtotal"] == 3520.0


# ═══════════════════════════════════════════════════════════════════
# Test: Discount — percentage
# ═══════════════════════════════════════════════════════════════════

def test_percentage_discount():
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, discount_type="PERCENTAGE", discount_value=10)

    assert result["subtotal"] == 2160.0
    assert result["discount_amount"] == 216.0   # 10% of 2160
    assert result["taxable"] == 1944.0           # 2160 - 216
    assert result["gst"] == 349.92               # 1944 × 0.18
    assert result["grand_total"] == 2294         # round(1944 + 349.92)


# ═══════════════════════════════════════════════════════════════════
# Test: Discount — flat
# ═══════════════════════════════════════════════════════════════════

def test_flat_discount():
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, discount_type="FLAT", discount_value=500)

    assert result["subtotal"] == 2160.0
    assert result["discount_amount"] == 500.0
    assert result["taxable"] == 1660.0
    assert result["gst"] == 298.80
    assert result["grand_total"] == 1959


# ═══════════════════════════════════════════════════════════════════
# Test: Different section sizes and gauges
# ═══════════════════════════════════════════════════════════════════

def test_section_6_16g():
    """6\" 16G section at ₹210/RFT."""
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "6", "16G")

    result = price_design(tree, RATES)

    # Frame: 18 RFT × ₹210 = ₹3,780
    assert result["frame"]["rate"] == 210.0
    assert result["frame"]["cost"] == 3780.0


def test_section_10_18g():
    """10\" 18G section at ₹230/RFT."""
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "10", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["rate"] == 230.0
    assert result["frame"]["cost"] == 4140.0  # 18 × 230


# ═══════════════════════════════════════════════════════════════════
# Test: Advance calculation
# ═══════════════════════════════════════════════════════════════════

def test_advance_percentage():
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, advance_pct=60)

    assert result["advance_pct"] == 60.0
    # Grand total: 2549 → 60% = 1529.4 → ₹1529
    assert result["advance_amount"] == 1529
