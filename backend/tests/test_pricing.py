"""
Pricing engine unit tests.

Tests the core business logic against the examples in design_rules_spec.md.
These tests run WITHOUT a database — the pricing engine is pure Python.
"""
import uuid
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
    """
    A 5ft × 4ft frame whose only leaf is 'open' — a fully void frame.
    Void-aware: no edge is backed by an occupied leaf → 0 RFT, ₹0 frame cost.
    """
    root = _leaf_region(5.0, 4.0, "open")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["quantity"] == 0.0
    assert result["frame"]["cost"] == 0.0
    assert result["splits"] == []
    assert result["subtotal"] == 0.0


def test_frame_only_fixed_region():
    """A 5ft × 4ft frame with one fixed region. Frame = full perimeter (void-aware, all occupied)."""
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES)

    # Frame: void-aware 4-sided, full region → 2×(5+4) = 18 RFT × ₹120 = ₹2,160
    assert result["frame"]["quantity"] == 18.0
    assert result["frame"]["rate"] == 120.0
    assert result["frame"]["cost"] == 2160.0
    assert result["splits"] == []
    assert result["subtotal"] == 2160.0
    assert result["gst"] == 388.80
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

    # One vertical split (mullion): partition member = double section.
    # length 4ft × (₹120 × 2) = ₹960
    assert len(result["splits"]) == 1
    assert result["splits"][0]["quantity"] == 4.0
    assert result["splits"][0]["rate"] == 240.0
    assert result["splits"][0]["cost"] == 960.0

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

    # Total: frame(2160) + split(960) + left(1760) + right(1920) = ₹6,800
    assert result["subtotal"] == 6800.0


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
# Test: SS grill whole-bar rounding + manual bar adjustment (§6.2 / §6.2A)
# ═══════════════════════════════════════════════════════════════════

def _ss_overlay(bar_adjust: int | None = None) -> dict:
    overlay = {"id": _uuid(), "type": "overlay", "overlayType": "grill", "material": "SS_PIPE_ROUND"}
    if bar_adjust is not None:
        overlay["config"] = {"barAdjust": bar_adjust}
    return overlay


def test_ss_grill_bars_are_whole_numbers():
    """
    §6.2: bars are physical objects — max(0, round(2h − 2)), never fractional.
    h = 2.95 → 2×2.95 − 2 = 3.9 → 4 bars; RFT = 4 × 4 = 16; cost = 16 × 90.
    """
    root = _leaf_region(width=4.0, height=2.95, region_type="fixed", overlays=[_ss_overlay()])
    tree = _design_tree(4.0, 2.95, root)
    grill = price_design(tree, RATES)["regions"][0]["grill"]
    assert grill["bars"] == 4
    assert grill["quantity"] == 16.0
    assert grill["cost"] == 1440.0


def test_ss_grill_zero_bars_when_too_short():
    """h ≤ 1 ft → auto count 0 → nothing billed (and nothing drawn)."""
    root = _leaf_region(width=4.0, height=1.0, region_type="fixed", overlays=[_ss_overlay()])
    tree = _design_tree(4.0, 1.0, root)
    grill = price_design(tree, RATES)["regions"][0]["grill"]
    assert grill["bars"] == 0
    assert grill["quantity"] == 0.0
    assert grill["cost"] == 0.0


def test_ss_grill_manual_bar_adjust_up():
    """§6.2A: 5ft-tall region, barAdjust +2 → 8 auto + 2 = 10 bars, billed as shown."""
    root = _leaf_region(width=4.0, height=5.0, region_type="fixed", overlays=[_ss_overlay(2)])
    tree = _design_tree(4.0, 5.0, root)
    grill = price_design(tree, RATES)["regions"][0]["grill"]
    assert grill["bars"] == 10
    assert grill["bar_adjust"] == 2
    assert grill["quantity"] == 40.0   # 10 bars × 4ft
    assert grill["cost"] == 3600.0     # 40 × 90
    assert "(auto 8 +2)" in grill["description"]


def test_ss_grill_manual_bar_adjust_down():
    """§6.2A: barAdjust −3 → 8 auto − 3 = 5 bars."""
    root = _leaf_region(width=4.0, height=5.0, region_type="fixed", overlays=[_ss_overlay(-3)])
    tree = _design_tree(4.0, 5.0, root)
    grill = price_design(tree, RATES)["regions"][0]["grill"]
    assert grill["bars"] == 5
    assert grill["quantity"] == 20.0
    assert grill["cost"] == 1800.0
    assert "(auto 8 -3)" in grill["description"]


def test_ss_grill_unadjusted_description_has_no_auto_note():
    root = _leaf_region(width=4.0, height=5.0, region_type="fixed", overlays=[_ss_overlay()])
    tree = _design_tree(4.0, 5.0, root)
    grill = price_design(tree, RATES)["regions"][0]["grill"]
    assert grill["bar_adjust"] == 0
    assert "auto" not in grill["description"]
    assert grill["description"].startswith("8 bars ×")


# ═══════════════════════════════════════════════════════════════════
# Test: Door region with GP sheet, hinges, lock
# ═══════════════════════════════════════════════════════════════════

def test_door_region_is_hardware_only():
    """
    §4A.2: a door region has NO pane — only hardware.
    7ft × 3ft door: no pane structure.
    Hinges (door, ≤7ft → 3): 3×120 = ₹360
    Lock: 1×100 = ₹100  → region subtotal ₹460
    """
    root = _leaf_region(
        width=3.0, height=7.0,
        region_type="door",
        pane_spec=None,
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
    # No pane structure for a door region
    assert region["pane_structure"] is None
    # Hinges: 3×120 = ₹360
    assert region["hardware"][0]["cost"] == 360.0
    # Lock: 1×100 = ₹100
    assert region["hardware"][1]["cost"] == 100.0
    assert region["subtotal"] == 460.0


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
# Test: Double shuttering (§5.7) — glass + jali leaves on one opening
# ═══════════════════════════════════════════════════════════════════

def _hinge(quantity=2, side="front"):
    return {
        "id": _uuid(), "type": "hardware",
        "hardwareType": "hinge", "variant": "SS_12G",
        "quantity": quantity, "autoComputed": True, "side": side,
    }


def test_double_shutter_spec_example():
    """
    Spec §5.7 worked example: shutter 3×4ft, double —
    glass side MS_PIPE with beading, jali side MS_PIPE, 2+2 hinges.
    Glass pane: 2×(3+4)×100 = ₹1,400
    Jali pane:  2×(3+4)×100 = ₹1,400
    Jali mesh:  3×4×110     = ₹1,320
    Beading:    2×(3+4)×40  = ₹560 (glass side only)
    Hinges:     4×120       = ₹480
    Subtotal: ₹5,160
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={
            "shutterConfig": "double",
            "shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": True,
            "jaliMaterial": "MS_PIPE", "jaliBeading": False,
        },
        hardware=[_hinge(side="front"), _hinge(side="back")],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"]["cost"] == 1400.0
    assert "glass side" in region["pane_structure"]["label"]
    assert region["pane_structure_2"]["cost"] == 1400.0
    assert "jali side" in region["pane_structure_2"]["label"]
    assert region["infill"]["cost"] == 1320.0     # jali side always carries mesh (P-15)
    assert region["beading"]["cost"] == 560.0     # one beaded side
    assert region["subtotal"] == 5160.0


def test_double_shutter_mixed_materials_both_beaded():
    """
    Sides price independently (P-14/P-16): glass side GP_SHEET, jali side MS_PIPE,
    beading on both sides = a 2×perimeter beading run.
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={
            "shutterConfig": "double",
            "shutterMaterial": "GP_SHEET", "infillType": "glass", "hasBeading": True,
            "jaliMaterial": "MS_PIPE", "jaliBeading": True,
        },
        hardware=[_hinge(side="front"), _hinge(side="back")],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"]["cost"] == 3500.0    # 14 RFT × ₹250
    assert region["pane_structure_2"]["cost"] == 1400.0  # 14 RFT × ₹100
    assert region["beading"]["quantity"] == 28.0         # 2 × 2×(3+4)
    assert region["beading"]["cost"] == 1120.0
    assert region["infill"]["cost"] == 1320.0
    assert region["subtotal"] == 3500 + 1400 + 1320 + 1120 + 480


def test_single_shutter_unaffected_by_double_fields():
    """
    Back-compat: a paneSpec without shutterConfig prices exactly as before —
    no second pane, no implied jali mesh, plain 'Shutter pane' label.
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={"shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": False},
        hardware=[_hinge()],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"]["label"] == "Shutter pane (MS Pipe)"
    assert region["pane_structure_2"] is None
    assert region["infill"] is None
    assert region["subtotal"] == 1400.0 + 240.0


# ═══════════════════════════════════════════════════════════════════
# Test: Customer-supplied shutter (§5.8) — HINGES_ONLY, hinges are the only cost
# ═══════════════════════════════════════════════════════════════════

def test_hinges_only_single():
    """
    §5.8 worked example: shutter 3×4ft HINGES_ONLY, single, 2 hinges.
    Customer supplies the shutter — no pane / infill / beading. Only the hinges
    are ours: 2 × 120 = ₹240.
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={"shutterMaterial": "HINGES_ONLY", "infillType": "none", "hasBeading": False},
        hardware=[_hinge(quantity=2)],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"] is None
    assert region["pane_structure_2"] is None
    assert region["infill"] is None
    assert region["beading"] is None
    assert sum(hw["cost"] for hw in region["hardware"]) == 240.0
    assert region["subtotal"] == 240.0


def test_hinges_only_double():
    """
    §5.8: a HINGES_ONLY double is customer-supplied on both faces — hinges on both
    sides (front + back), still no pane / infill / beading. 2+2 hinges = ₹480.
    """
    root = _leaf_region(
        width=3.0, height=4.0,
        region_type="shutter",
        pane_spec={
            "shutterConfig": "double",
            "shutterMaterial": "HINGES_ONLY", "infillType": "none", "hasBeading": False,
        },
        hardware=[_hinge(side="front"), _hinge(side="back")],
    )
    tree = _design_tree(3.0, 4.0, root, "5", "18G")
    result = price_design(tree, RATES)

    region = result["regions"][0]
    assert region["pane_structure"] is None
    assert region["pane_structure_2"] is None   # no jali-side pane despite double
    assert region["infill"] is None             # no implied jali mesh
    assert region["beading"] is None
    assert region["subtotal"] == 480.0


# ═══════════════════════════════════════════════════════════════════
# Test: Discount — percentage
# ═══════════════════════════════════════════════════════════════════

def test_percentage_discount():
    root = _leaf_region(5.0, 4.0, "fixed")
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
    root = _leaf_region(5.0, 4.0, "fixed")
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
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "6", "16G")

    result = price_design(tree, RATES)

    # Frame: 18 RFT × ₹210 = ₹3,780
    assert result["frame"]["rate"] == 210.0
    assert result["frame"]["cost"] == 3780.0


def test_section_10_18g():
    """10\" 18G section at ₹230/RFT."""
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "10", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["rate"] == 230.0
    assert result["frame"]["cost"] == 4140.0  # 18 × 230


# ═══════════════════════════════════════════════════════════════════
# Test: Advance calculation
# ═══════════════════════════════════════════════════════════════════

def test_advance_percentage():
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, advance_pct=60)

    assert result["advance_pct"] == 60.0
    # Grand total: 2549 → 60% = 1529.4 → ₹1529
    assert result["advance_amount"] == 1529


# ═══════════════════════════════════════════════════════════════════
# Test: Configurable GST percentage
# ═══════════════════════════════════════════════════════════════════

def test_gst_pct_12():
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, gst_pct=12)

    assert result["subtotal"] == 2160.0
    assert result["gst"] == 259.2                # 2160 × 0.12
    assert result["grand_total"] == 2419         # round(2160 + 259.2)


def test_gst_pct_defaults_to_18():
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    assert price_design(tree, RATES)["gst"] == price_design(tree, RATES, gst_pct=18)["gst"]


def test_gst_pct_zero():
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_design(tree, RATES, gst_pct=0)
    assert result["gst"] == 0.0
    assert result["grand_total"] == 2160


# ═══════════════════════════════════════════════════════════════════
# Test: Standalone Door product (spec §4A)
# ═══════════════════════════════════════════════════════════════════

def _door_tree(width, height, root_region, section_size="5", gauge="18G"):
    """A design tree with productType 'door'."""
    tree = _design_tree(width, height, root_region, section_size, gauge)
    tree["productType"] = "door"
    return tree


def _branch(width, height, x, y, direction, position, child_a, child_b):
    """A branch region with a split into two children (for composite fixtures)."""
    return {
        "id": _uuid(), "type": "region", "x": x, "y": y,
        "width": width, "height": height, "isLeaf": False, "regionType": None,
        "paneSpec": None, "overlays": [], "hardware": [],
        "split": {
            "id": _uuid(), "type": "split", "direction": direction,
            "position": position, "children": [child_a, child_b],
        },
    }


def test_door_product_frame_is_three_sided():
    """
    §4A.1: a plain door product's outer frame excludes the base run.
    3ft × 7ft door frame = 2×7 + 3 = 17 RFT × ₹120 = ₹2,040
    (a window would be 2×(3+7) = 20 RFT × ₹120 = ₹2,400).
    """
    root = _leaf_region(3.0, 7.0, "door")
    tree = _door_tree(3.0, 7.0, root, "5", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["quantity"] == 17.0
    assert result["frame"]["cost"] == 2040.0
    assert "base in concrete" in result["frame"]["label"].lower()


# ─── Door + window composites (§4A.3) ──────────────────────────────

def test_composite_door_with_partial_side_window():
    """
    Reference sketch: door 4×7 (left) + top-aligned window 3×5 (right), with a
    2ft empty void below the window.
    Frame (single, base excluded): left 7 + top 7 + window-right 5 = 19 RFT.
    Mullions: door|column 7×2 = 14, window sill 3×1 = 3.
    Total steel = 36 RFT × ₹120 = ₹4,320.
    """
    door = _leaf_region(4.0, 7.0, "door", x=0, y=0)
    window = _leaf_region(3.0, 5.0, "fixed", pane_spec=None, x=4.0, y=0)
    void = _leaf_region(3.0, 2.0, "open", x=4.0, y=5.0)
    right_col = _branch(3.0, 7.0, 4.0, 0, "horizontal", 5.0 / 7.0, window, void)
    root = _branch(7.0, 7.0, 0, 0, "vertical", 4.0 / 7.0, door, right_col)
    tree = _door_tree(7.0, 7.0, root, "5", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["quantity"] == 19.0
    assert result["frame"]["cost"] == 2280.0     # 19 × 120

    splits = result["splits"]
    assert len(splits) == 2
    # vertical door|column — double section
    assert splits[0]["quantity"] == 7.0 and splits[0]["rate"] == 240.0 and splits[0]["cost"] == 1680.0
    # window sill (bordering the void) — single section
    assert splits[1]["quantity"] == 3.0 and splits[1]["rate"] == 120.0 and splits[1]["cost"] == 360.0

    # 36 RFT × 120 = 4,320 (door + fixed window carry no extra region cost here)
    assert result["subtotal"] == 4320.0


def test_composite_door_with_middle_window():
    """
    Door 4×7 + a 3×3 window centred on the right (2ft void above AND below).
    Frame: left 7 + top 4 + window-right 3 = 14 RFT.
    Mullions: door|column 7×2 = 14, head 3×1, sill 3×1.
    Total = 34 RFT × ₹120 = ₹4,080.
    """
    door = _leaf_region(4.0, 7.0, "door", x=0, y=0)
    void_top = _leaf_region(3.0, 2.0, "open", x=4.0, y=0)
    window = _leaf_region(3.0, 3.0, "fixed", pane_spec=None, x=4.0, y=2.0)
    void_bot = _leaf_region(3.0, 2.0, "open", x=4.0, y=5.0)
    rest = _branch(3.0, 5.0, 4.0, 2.0, "horizontal", 3.0 / 5.0, window, void_bot)
    right_col = _branch(3.0, 7.0, 4.0, 0, "horizontal", 2.0 / 7.0, void_top, rest)
    root = _branch(7.0, 7.0, 0, 0, "vertical", 4.0 / 7.0, door, right_col)
    tree = _door_tree(7.0, 7.0, root, "5", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["quantity"] == 14.0
    assert result["frame"]["cost"] == 1680.0

    splits = result["splits"]
    assert len(splits) == 3
    assert splits[0]["rate"] == 240.0 and splits[0]["cost"] == 1680.0   # door|column double
    assert splits[1]["rate"] == 120.0 and splits[1]["cost"] == 360.0    # head, single
    assert splits[2]["rate"] == 120.0 and splits[2]["cost"] == 360.0    # sill, single

    assert result["subtotal"] == 4080.0   # 34 × 120


def test_composite_door_with_fanlight():
    """
    Door 4×7 with a 4×2 fanlight on top (total 4×9).
    Frame: left 9 + top 4 + right 9 = 22 RFT.
    Mullion: door|fanlight transom 4×2 = 8.
    Total = 30 RFT × ₹120 = ₹3,600.
    """
    fanlight = _leaf_region(4.0, 2.0, "fixed", pane_spec=None, x=0, y=0)
    door = _leaf_region(4.0, 7.0, "door", x=0, y=2.0)
    root = _branch(4.0, 9.0, 0, 0, "horizontal", 2.0 / 9.0, fanlight, door)
    tree = _door_tree(4.0, 9.0, root, "5", "18G")

    result = price_design(tree, RATES)

    assert result["frame"]["quantity"] == 22.0
    assert result["frame"]["cost"] == 2640.0

    splits = result["splits"]
    assert len(splits) == 1
    assert splits[0]["quantity"] == 4.0 and splits[0]["rate"] == 240.0 and splits[0]["cost"] == 960.0

    assert result["subtotal"] == 3600.0   # 30 × 120


def test_door_leaf_not_priced_separately():
    """
    §4A.2: a `door` leaf is not priced separately and has no pane. In a door
    product the chowkhat frame carries the steel; the door region adds only
    its hardware.
    Frame: 2×7 + 3 = 17 RFT × 120 = ₹2,040. Door region: hinges 3×120 = ₹360.
    """
    root = _leaf_region(
        3.0, 7.0, "door",
        pane_spec=None,
        hardware=[{
            "id": _uuid(), "type": "hardware", "hardwareType": "hinge",
            "variant": "SS_12G", "quantity": 3, "autoComputed": True, "side": "front",
        }],
    )
    tree = _door_tree(3.0, 7.0, root, "5", "18G")

    result = price_design(tree, RATES)
    region = result["regions"][0]
    assert region["pane_structure"] is None
    assert region["subtotal"] == 360.0           # hardware only
    assert result["frame"]["cost"] == 2040.0     # 3-sided chowkhat carries the steel
    assert result["subtotal"] == 2400.0          # 2040 frame + 360 hinges


def test_door_with_side_window_shared_mullion():
    """
    §4A.3: door + side window. The shared mullion is billed once by the window
    convention (2× section). The door leaf excludes its base; the side window
    (a shutter) keeps full-perimeter window pricing.
    """
    door = _leaf_region(
        3.0, 7.0, "door",
        pane_spec=None,
        hardware=[{
            "id": _uuid(), "type": "hardware", "hardwareType": "hinge",
            "variant": "SS_12G", "quantity": 3, "autoComputed": True, "side": "front",
        }],
    )
    window = _leaf_region(
        3.0, 7.0, "shutter", x=3.0,
        pane_spec={"shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": False},
        hardware=[{
            "id": _uuid(), "type": "hardware", "hardwareType": "hinge",
            "variant": "SS_12G", "quantity": 3, "autoComputed": True, "side": "front",
        }],
    )
    root = {
        "id": _uuid(), "type": "region", "x": 0, "y": 0,
        "width": 6.0, "height": 7.0, "isLeaf": False, "regionType": None,
        "paneSpec": None, "overlays": [], "hardware": [],
        "split": {
            "id": _uuid(), "type": "split", "direction": "vertical",
            "position": 0.5, "children": [door, window],
        },
    }
    tree = _door_tree(6.0, 7.0, root, "5", "18G")

    result = price_design(tree, RATES)

    # Frame (door product, 3-sided): 2×7 + 6 = 20 RFT × 120 = ₹2,400
    assert result["frame"]["cost"] == 2400.0
    assert "base in concrete" in result["frame"]["label"].lower()
    # One mullion, billed once: length 7 × (120×2) = ₹1,680
    assert len(result["splits"]) == 1
    assert result["splits"][0]["cost"] == 1680.0
    # Door region has no pane — hardware only: hinges 3×120 = ₹360
    door_bd = result["regions"][0]
    assert door_bd["pane_structure"] is None
    assert door_bd["subtotal"] == 360.0
    # Side window keeps full perimeter (window rules): 2×(3+7)×100 = 2,000 + hinges 360 = 2,360
    win_bd = result["regions"][1]
    assert win_bd["pane_structure"]["cost"] == 2000.0
    assert win_bd["subtotal"] == 2360.0
    # Total: 2400 frame + 1680 mullion + 360 door + 2360 window = ₹6,800
    assert result["subtotal"] == 6800.0


def test_rebate_is_price_neutral_and_back_side_hardware_adds():
    """
    §4A.5/§4A.6: single vs double rebate produce the SAME frame price.
    Double rebate only permits back-side hardware, which is priced as normal.
    """
    def door_root(rebate, extra_hw):
        return _leaf_region(
            3.0, 7.0, "door",
            pane_spec=None,
            hardware=[
                {"id": _uuid(), "type": "hardware", "hardwareType": "hinge",
                 "variant": "SS_12G", "quantity": 3, "autoComputed": True, "side": "front"},
                *extra_hw,
            ],
        ) | {"rebate": rebate}

    single = price_design(_door_tree(3.0, 7.0, door_root("single", [])), RATES)
    double = price_design(_door_tree(3.0, 7.0, door_root("double", [
        {"id": _uuid(), "type": "hardware", "hardwareType": "hinge",
         "variant": "SS_12G", "quantity": 3, "autoComputed": True, "side": "back"},
        {"id": _uuid(), "type": "hardware", "hardwareType": "lock",
         "variant": "standard", "quantity": 1, "autoComputed": False, "side": "back"},
    ])), RATES)

    # Frame price is identical regardless of rebate.
    assert single["frame"]["cost"] == double["frame"]["cost"] == 2040.0
    # Back-side hinges (3×120=360) + lock (100) = ₹460 added.
    assert double["subtotal"] - single["subtotal"] == 460.0
    # Back-side line items are labelled.
    labels = [hw["label"] for hw in double["regions"][0]["hardware"]]
    assert any("back side" in lbl for lbl in labels)


def test_window_product_unchanged_without_product_type():
    """Regression: a tree with no productType still prices as a window (void-aware 4-sided)."""
    root = _leaf_region(3.0, 7.0, "fixed")
    tree = _design_tree(3.0, 7.0, root, "5", "18G")  # no productType key
    assert "productType" not in tree

    result = price_design(tree, RATES)
    # Full occupied region → void-aware 4-sided = full perimeter: 2×(3+7) = 20 RFT × 120 = ₹2,400
    assert result["frame"]["quantity"] == 20.0
    assert result["frame"]["cost"] == 2400.0
    assert result["frame"]["label"] == "Frame"


# ═══════════════════════════════════════════════════════════════════
# Test: Window product with an open void region (matches door behaviour)
# ═══════════════════════════════════════════════════════════════════

def _void_aware_layout():
    """
    Shared 6×9 composite used by the void-aware tests:
      top strip:  FIXED  6×2  (x=0, y=0)
      left:       DOOR   3.5×7 (x=0, y=2)
      top-right:  FIXED  2.5×3 (x=3.5, y=2)
      bot-right:  OPEN   2.5×4 (x=3.5, y=5)
    """
    top   = _leaf_region(6.0, 2.0, "fixed", x=0,   y=0)
    door  = _leaf_region(3.5, 7.0, "door",  x=0,   y=2,
                         hardware=[{"id": _uuid(), "type": "hardware",
                                    "hardwareType": "hinge", "variant": "SS_12G",
                                    "quantity": 3, "autoComputed": True, "side": "front"}])
    fixed = _leaf_region(2.5, 3.0, "fixed", x=3.5, y=2)
    void  = _leaf_region(2.5, 4.0, "open",  x=3.5, y=5)

    right_col = _branch(2.5, 7.0, 3.5, 2.0, "horizontal", 3.0 / 7.0, fixed, void)
    bottom_row = _branch(6.0, 7.0, 0.0, 2.0, "vertical",   3.5 / 6.0, door,  right_col)
    return _branch(6.0, 9.0, 0.0, 0.0, "horizontal", 2.0 / 9.0, top, bottom_row)


def test_window_frame_is_void_aware():
    """
    A window product with an open void region — mirrors the door composite test.

    Void-aware frame edges (door regions carry no bottom sill — they open to the floor):
      left:   FIXED(h=2) + DOOR(h=7)                       = 9
      top:    FIXED(w=6)                                    = 6
      right:  FIXED(h=2, full-width) + FIXED(h=3, 2.5×3)  = 5
      bottom: DOOR is sill-exempt → 0
      Total = 20 RFT × ₹175 = ₹3,500

    The 2.5ft transom between FIXED and OPEN is single (borders void).
    """
    root = _void_aware_layout()
    tree = _design_tree(6.0, 9.0, root, "6", "18G")  # window product (no productType)

    result = price_design(tree, RATES)

    # Frame: void-aware, door bottom sill-exempt = 20 RFT × ₹175 = ₹3,500
    assert result["frame"]["quantity"] == 20.0
    assert result["frame"]["cost"] == 3500.0

    # The 2.5ft transom (FIXED vs OPEN) must be single, not double.
    single_transoms = [s for s in result["splits"] if not s["double"]]
    assert len(single_transoms) == 1
    assert single_transoms[0]["quantity"] == 2.5
    assert single_transoms[0]["rate"] == 175.0   # single = 1× section rate


def test_window_and_door_frames_match_for_same_layout():
    """
    The same composite priced as a window vs a door must now produce an identical
    frame and identical subtotal — a door region in a window carries no bottom sill,
    so the two products no longer diverge (the original ambiguity is gone).
    """
    window = price_design(_design_tree(6.0, 9.0, _void_aware_layout(), "6", "18G"), RATES)
    door = price_design(_door_tree(6.0, 9.0, _void_aware_layout(), "6", "18G"), RATES)

    assert window["frame"]["quantity"] == door["frame"]["quantity"] == 20.0
    assert window["subtotal"] == door["subtotal"]


# ═══════════════════════════════════════════════════════════════════
# Test: Other charges (PR-9 — labor / transport / installation)
# ═══════════════════════════════════════════════════════════════════

from app.services.pricing import _apply_commercial_terms, price_estimate, sum_other_charges


def test_other_charges_spec_example():
    """Spec §9.4 worked example: frames ₹10,000 + transport ₹1,500 +
    installation ₹2,000, 10% discount, GST 18%, advance 50%."""
    terms = _apply_commercial_terms(
        10000.0, "PERCENTAGE", 10, 50, gst_pct=18,
        other_charges=[
            {"label": "Transport", "amount": 1500},
            {"label": "Installation", "amount": 2000},
        ],
    )

    assert terms["other_charges_total"] == 3500.0
    assert terms["discount_amount"] == 1350.0   # 10% of 13,500 gross
    assert terms["taxable"] == 12150.0
    assert terms["gst"] == 2187.0
    assert terms["grand_total"] == 14337
    assert terms["advance_amount"] == 7169      # 7168.50 → HALF_UP


def test_price_estimate_with_other_charges():
    """Charges join the aggregate after the frames subtotal; the frames
    subtotal itself stays materials-only."""
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")

    result = price_estimate(
        [{"name": "W1", "quantity": 1, "tree": tree}],
        RATES,
        other_charges=[{"label": "Transport", "amount": 500}],
    )

    assert result["subtotal"] == 2160.0                  # frames only
    assert result["other_charges_total"] == 500.0
    assert result["other_charges"] == [{"label": "Transport", "amount": 500}]
    assert result["taxable"] == 2660.0                   # gross, no discount
    assert result["gst"] == 478.8                        # 2660 × 0.18
    assert result["grand_total"] == 3139                 # round(3138.8)


def test_other_charges_absent_is_neutral():
    """No charges (None or []) must leave every total exactly as before."""
    root = _leaf_region(5.0, 4.0, "fixed")
    tree = _design_tree(5.0, 4.0, root, "5", "18G")
    frames = [{"name": "W1", "quantity": 2, "tree": tree}]

    base = price_estimate(frames, RATES)
    empty = price_estimate(frames, RATES, other_charges=[])

    assert base["other_charges_total"] == 0.0
    for key in ("subtotal", "discount_amount", "taxable", "gst", "grand_total", "advance_amount"):
        assert base[key] == empty[key]


def test_flat_discount_caps_at_gross_including_charges():
    """A FLAT discount larger than frames+charges is capped at the gross."""
    terms = _apply_commercial_terms(
        100.0, "FLAT", 500, 50,
        other_charges=[{"label": "Labor", "amount": 50}],
    )

    assert terms["discount_amount"] == 150.0   # capped at 100 + 50
    assert terms["taxable"] == 0.0
    assert terms["grand_total"] == 0


def test_sum_other_charges_tolerates_missing_amounts():
    assert sum_other_charges(None) == 0.0
    assert sum_other_charges([]) == 0.0
    assert sum_other_charges([{"label": "x"}, {"label": "y", "amount": None}]) == 0.0
    assert sum_other_charges([{"label": "a", "amount": 10.555}, {"amount": 4}]) == 14.56
