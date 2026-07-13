"""
SteelCAD Pricing Engine
========================

Pure Python module — NO database access, NO side effects.
Takes the design tree JSON + rate lookup dict → returns full itemized breakdown.

Implements the traversal algorithm from design_rules_spec.md §9.

Key design decisions:
  - All monetary values kept to 2 decimal places (PR-1, PR-2).
  - Grand total rounded to nearest rupee (PR-3).
  - GST = 18% on post-discount amount (PR-4).
  - MS grill = area-based pricing (§6.1).
  - SS grill = bar-count pricing (§6.2), supports continuity on branch regions.
  - Structural pane cost only on shutter/door regions, NOT fixed (§5.2, P-4).
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


# Type alias for rate dictionary
RateDict = dict[str, float]

# Interior partition members (mullions/transoms) are double sections — two lengths
# of the profile run back-to-back to divide the unit — so they cost 2× the section
# rate per RFT versus the single-run outer frame.
MULLION_RATE_MULTIPLIER = 2


# ─── Rounding helpers ──────────────────────────────────────────────

def _round2(value: float) -> float:
    """Round to 2 decimal places (PR-1, PR-2)."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _round_rupee(value: float) -> int:
    """Round to nearest rupee (PR-3)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fmt_ft(value: float) -> str:
    """Feet value for display: 2-decimal round, trailing zeros dropped (4.0 → '4')."""
    return f"{round(float(value), 2):g}"


# ─── Rate lookup ───────────────────────────────────────────────────

def _lookup_rate(key: str, rates: RateDict) -> float:
    """Lookup a rate by item code. Raises ValueError if not found."""
    if key not in rates:
        raise ValueError(f"Unknown rate key: {key}")
    return rates[key]


def _section_rate(section_size: str, gauge: str, rates: RateDict) -> float:
    """Resolve frame/split section rate from size + gauge."""
    return _lookup_rate(f"SECTION_{section_size}_{gauge}", rates)


# ─── Occupancy helpers (§4A composites) ───────────────────────────

_EPS = 1e-6


def _subtree_has_occupied(region: dict) -> bool:
    """
    True if the subtree contains any non-open (occupied) leaf.
    `open` regions are empty voids — no steel, no cost (§4).
    """
    if region.get("isLeaf", True) or not region.get("split"):
        return region.get("regionType") not in (None, "open")
    return any(_subtree_has_occupied(c) for c in region["split"].get("children", []))


def _iter_leaves(region: dict):
    """Yield every leaf region in the subtree (depth-first)."""
    if region.get("isLeaf", True) or not region.get("split"):
        yield region
        return
    for child in region["split"]["children"]:
        yield from _iter_leaves(child)


# ─── Frame cost (§9.1 step 1) ─────────────────────────────────────

def _door_frame_rft(frame: dict) -> float:
    """
    Void-aware door frame (§4A): the three non-base outer sides (left, top, right)
    of the bounding box, counting only the extent backed by a non-open region.
    The bottom sits in the concrete (excluded); empty voids that reach an outer
    edge carry no steel. Reduces to 2×H + W for a plain door (no voids).
    """
    W = frame["width"]
    left = top = right = 0.0
    for leaf in _iter_leaves(frame["rootRegion"]):
        if leaf.get("regionType") in (None, "open"):
            continue  # empty void — no steel
        x, y = leaf.get("x", 0), leaf.get("y", 0)
        w, h = leaf["width"], leaf["height"]
        if abs(x) < _EPS:                 # touches left edge
            left += h
        if abs(y) < _EPS:                 # touches top edge
            top += w
        if abs((x + w) - W) < _EPS:       # touches right edge
            right += h
        # bottom (y + h ≈ H) is the base — in the concrete, excluded
    return _round2(left + top + right)


def _window_frame_rft(frame: dict) -> float:
    """
    Void-aware window frame: all four outer sides, counting only the extent backed
    by a non-open region.  Empty voids that reach an outer edge carry no steel —
    same logic as _door_frame_rft, but the bottom sill is included (not in concrete)
    EXCEPT beneath a `door` region: a door opens to the floor and has no sill, so a
    door leaf touching the bottom edge carries no sill steel (its left/top/right
    chowkhat sides are unaffected). Reduces to 2×(W+H) when every leaf is occupied
    and none is a door.
    """
    W, H = frame["width"], frame["height"]
    left = top = right = bottom = 0.0
    for leaf in _iter_leaves(frame["rootRegion"]):
        if leaf.get("regionType") in (None, "open"):
            continue  # empty void — no steel
        x, y = leaf.get("x", 0), leaf.get("y", 0)
        w, h = leaf["width"], leaf["height"]
        if abs(x) < _EPS:                 # touches left edge
            left += h
        if abs(y) < _EPS:                 # touches top edge
            top += w
        if abs((x + w) - W) < _EPS:       # touches right edge
            right += h
        if abs((y + h) - H) < _EPS and leaf.get("regionType") != "door":
            bottom += w                   # bottom sill — a door opens to the floor (no sill)
    return _round2(left + top + right + bottom)


def _compute_frame_cost(frame: dict, rate: float, product_type: str = "window") -> dict:
    """
    Frame cost = running feet × section rate.

    Window (default): full perimeter, 2 × (w + h).
    Door (§4A.1): the base sits in the concrete, so the frame is 3-sided. For a
    plain door this is 2 × height + width; for a door + window composite it is the
    void-aware outer boundary (see `_door_frame_rft`).
    """
    if product_type == "door":
        rf = _door_frame_rft(frame)
        label = "Door frame (base in concrete)"
        description = f"Door frame {rf} RFT (3-sided, void-aware) × ₹{rate}/RFT"
    else:
        rf = _window_frame_rft(frame)
        label = "Frame"
        description = f"Frame {rf} RFT (4-sided, void-aware) × ₹{rate}/RFT"
    cost = _round2(rf * rate)
    return {
        "label": label,
        "description": description,
        "quantity": rf,
        "unit": "RFT",
        "rate": rate,
        "cost": cost,
    }


# ─── Split costs (§9.1 step 2) ────────────────────────────────────

def _collect_splits(region: dict, product_type: str = "window") -> list[dict]:
    """
    Recursively collect all splits in the tree.
    Each split's length = parent region's height (vertical) or width (horizontal).

    A split where both sides contain at least one occupied (non-open) leaf is a
    double section (mullion/transom); a split that borders an empty void on either
    side is a single section regardless of product type.
    """
    splits = []
    split = region.get("split")
    if split is None:
        return splits

    direction = split["direction"]
    children = split.get("children", [])
    if direction == "vertical":
        length = region["height"]
        label = "Mullion (vertical)"
    else:
        length = region["width"]
        label = "Transom (horizontal)"

    double = all(_subtree_has_occupied(c) for c in children)

    splits.append({
        "split_id": split.get("id", ""),
        "direction": direction,
        "length": _round2(length),
        "label": label,
        "double": double,
    })

    for child in children:
        splits.extend(_collect_splits(child, product_type))

    return splits


def _compute_split_costs(splits: list[dict], rate: float) -> list[dict]:
    """
    Convert collected splits into priced line items.

    Double sections (mullions/transoms between two occupied regions) cost 2× the
    section rate per RFT (MULLION_RATE_MULTIPLIER). A single member bordering an
    empty void (door composites, §4A) costs 1× — it is just one section.
    """
    items = []
    for s in splits:
        length = s["length"]
        if s.get("double", True):
            eff_rate = _round2(rate * MULLION_RATE_MULTIPLIER)
            note = "double section"
        else:
            eff_rate = _round2(rate)
            note = "single section (borders open space)"
        cost = _round2(length * eff_rate)
        items.append({
            "label": s["label"],
            "description": f"{s['label']} {length} RFT × ₹{eff_rate}/RFT ({note})",
            "quantity": length,
            "unit": "RFT",
            "rate": eff_rate,
            "cost": cost,
            "double": s.get("double", True),
        })
    return items


# ─── Pane structure cost (§5.2, §5.7) ──────────────────────────────

def _is_double_shutter(region: dict) -> bool:
    """True for a shutter region double-shuttered per §5.7 (glass + jali leaves)."""
    ps = region.get("paneSpec") or {}
    return region.get("regionType") == "shutter" and ps.get("shutterConfig") == "double"


def _pane_item(mat: str, rf: float, rates: RateDict, label: str) -> dict:
    """One structural pane line item: rf × shutter material rate."""
    rate = _lookup_rate(f"SHUTTER_{mat}", rates)
    cost = _round2(rf * rate)
    mat_label = "MS Pipe" if mat == "MS_PIPE" else "GP Sheet"
    return {
        "label": f"{label} ({mat_label})",
        "description": f"{label} {rf} RFT × ₹{rate}/RFT",
        "quantity": rf,
        "unit": "RFT",
        "rate": rate,
        "cost": cost,
    }


def _compute_pane_structure(region: dict, rates: RateDict) -> Optional[dict]:
    """
    Structural pane cost — `shutter` regions only.
    pane_RF = 2 × (width + height), cost = pane_RF × shutter_material_rate.
    On a double shutter (§5.7) this is the GLASS-side leaf.

    `door` regions have NO structural pane (§4A.2): a door leaf is not priced
    separately — the chowkhat frame's 3-sided running feet (§4A.1) carries the
    door's steel. `fixed`/`open`/`louver` have no pane either (P-4/P-5).
    """
    rt = region.get("regionType")
    if rt != "shutter":
        return None

    ps = region.get("paneSpec")
    if not ps:
        return None

    mat = ps.get("shutterMaterial")
    if not mat:
        return None

    w, h = region["width"], region["height"]
    rf = _round2(2 * (w + h))
    label = "Shutter pane — glass side" if _is_double_shutter(region) else "Shutter pane"
    return _pane_item(mat, rf, rates, label)


def _compute_jali_pane_structure(region: dict, rates: RateDict) -> Optional[dict]:
    """
    Jali-side structural pane of a double shutter (§5.7) — a second, fully-priced
    leaf: pane_RF × jali-side material rate (P-14).
    """
    if not _is_double_shutter(region):
        return None

    mat = (region.get("paneSpec") or {}).get("jaliMaterial")
    if not mat:
        return None

    w, h = region["width"], region["height"]
    rf = _round2(2 * (w + h))
    return _pane_item(mat, rf, rates, "Shutter pane — jali side")


# ─── Infill cost (§5.3) ───────────────────────────────────────────

def _compute_infill(region: dict, rates: RateDict) -> Optional[dict]:
    """
    Infill cost: glass = ₹0 (no line item needed), jali = area-based.
    Jali cost is ADDITIONAL to pane structure cost — never replaces it (P-7).
    The jali side of a double shutter always carries mesh (§5.7 / P-15).
    """
    ps = region.get("paneSpec")
    if not ps:
        return None

    if ps.get("infillType") != "jali" and not _is_double_shutter(region):
        return None  # glass = ₹0, no line item

    w, h = region["width"], region["height"]
    area = _round2(w * h)
    rate = _lookup_rate("JALI_WIRE_MESH", rates)
    cost = _round2(area * rate)

    return {
        "label": "Jali wire mesh",
        "description": f"Jali {area} sqft × ₹{rate}/sqft",
        "quantity": area,
        "unit": "sqft",
        "rate": rate,
        "cost": cost,
    }


# ─── Beading cost (§5.4) ──────────────────────────────────────────

def _compute_beading(region: dict, rates: RateDict) -> Optional[dict]:
    """
    Beading cost = perimeter × beading rate, one 2×(w+h) run per beaded side.
    Applies to BOTH glass and jali panes (P-8). Requires infill (P-9, V-13).
    A double shutter (§5.7) beads each side independently (P-16): `hasBeading`
    is the glass side, `jaliBeading` the jali side.
    """
    ps = region.get("paneSpec")
    if not ps:
        return None

    if _is_double_shutter(region):
        sides = int(bool(ps.get("hasBeading"))) + int(bool(ps.get("jaliBeading")))
    else:
        sides = 1 if ps.get("hasBeading") and ps.get("infillType", "none") != "none" else 0

    if sides == 0:
        return None

    w, h = region["width"], region["height"]
    rf = _round2(sides * 2 * (w + h))
    rate = _lookup_rate("GLASS_BEADING", rates)
    cost = _round2(rf * rate)
    note = " (both sides)" if sides == 2 else ""

    return {
        "label": "Beading",
        "description": f"Beading {rf} RFT × ₹{rate}/RFT{note}",
        "quantity": rf,
        "unit": "RFT",
        "rate": rate,
        "cost": cost,
    }


# ─── Grill cost (§6) ──────────────────────────────────────────────

def _compute_grill(overlay: dict, region: dict, rates: RateDict) -> Optional[dict]:
    """
    Grill pricing — MS and SS are completely different models (§6 rule 11).

    MS grill (§6.1): area-based = width × height × rate/sqft (leaf only).
    SS grill (§6.2): bar-count = ((2 × height) − 2) × width × rate/RFT.
        Uses the attached region's full dimensions (continuity model).
    """
    material = overlay.get("material")
    if not material:
        return None

    w, h = region["width"], region["height"]

    if material == "MS_SQUARE":
        area = _round2(w * h)
        rate = _lookup_rate("GRILL_MS_SQUARE", rates)
        cost = _round2(area * rate)
        return {
            "label": "M.S. Square Grill",
            "description": f"MS Grill {area} sqft × ₹{rate}/sqft",
            "quantity": area,
            "unit": "sqft",
            "rate": rate,
            "cost": cost,
        }
    else:
        # SS grill: bar-count formula
        bars = _round2((2 * h) - 2)
        total_rft = _round2(bars * w)
        rate = _lookup_rate(f"GRILL_{material}", rates)
        cost = _round2(total_rft * rate)

        mat_label = "SS Pipe Round" if material == "SS_PIPE_ROUND" else "SS Pipe Square"
        return {
            "label": f"{mat_label} Grill",
            "description": f"{int(bars)} bars × {w}ft = {total_rft} RFT × ₹{rate}/RFT",
            "quantity": total_rft,
            "unit": "RFT",
            "rate": rate,
            "cost": cost,
        }


# ─── Hardware costs (§7) ──────────────────────────────────────────

def _compute_hardware(region: dict, rates: RateDict) -> list[dict]:
    """
    Hardware pricing: per piece × quantity.
    Hinges on shutter + door regions; locks on door regions only (V-14).
    """
    items = []
    for hw in region.get("hardware", []):
        hw_type = hw.get("hardwareType")
        variant = hw.get("variant", "")
        qty = hw.get("quantity", 0)
        # Back-side hardware on a double-rebate door (§4A.6). Cosmetic suffix only —
        # priced identically to front-side hardware.
        side_suffix = " — back side" if hw.get("side") == "back" else ""

        if hw_type == "hinge":
            rate = _lookup_rate(f"HINGE_{variant}", rates)
            cost = _round2(qty * rate)
            items.append({
                "label": f"Hinge ({variant.replace('_', ' ')}){side_suffix}",
                "description": f"{qty} × ₹{rate}/pc",
                "quantity": qty,
                "unit": "pc",
                "rate": rate,
                "cost": cost,
            })
        elif hw_type == "lock":
            rate = _lookup_rate("LOCK_PROVISION", rates)
            cost = _round2(qty * rate)
            items.append({
                "label": f"Lock provision{side_suffix}",
                "description": f"{qty} × ₹{rate}/pc",
                "quantity": qty,
                "unit": "pc",
                "rate": rate,
                "cost": cost,
            })

    return items


# ─── Region breakdown (§9.1 step 3) ───────────────────────────────

def _walk_regions(region: dict, rates: RateDict, counter: list[int]) -> list[dict]:
    """
    Depth-first traversal of all regions.
    Returns a list of RegionBreakdown dicts.

    For leaf regions: computes pane, infill, beading, hardware costs.
    For all regions: computes grill overlay costs (SS grill can be on branch).
    `door` regions carry hardware only — no pane, infill, beading, or grill (§4A.2).
    """
    results = []
    is_leaf = region.get("isLeaf", True)
    rt = region.get("regionType", "open")
    w, h = region["width"], region["height"]

    region_bd = {
        "region_id": str(region.get("id", "")),
        "region_label": "",
        "region_type": rt or "branch",
        "dimensions": f"{_fmt_ft(h)}ft × {_fmt_ft(w)}ft",
        "pane_structure": None,
        "pane_structure_2": None,
        "infill": None,
        "beading": None,
        "grill": None,
        "hardware": [],
        "subtotal": 0.0,
    }

    sub = 0.0

    # 3a. Leaf-only costs: pane spec + hardware
    if is_leaf:
        counter[0] += 1
        region_bd["region_label"] = f"Region {counter[0]}"

        pane = _compute_pane_structure(region, rates)
        if pane:
            region_bd["pane_structure"] = pane
            sub += pane["cost"]

        pane2 = _compute_jali_pane_structure(region, rates)
        if pane2:
            region_bd["pane_structure_2"] = pane2
            sub += pane2["cost"]

        infill = _compute_infill(region, rates)
        if infill:
            region_bd["infill"] = infill
            sub += infill["cost"]

        beading = _compute_beading(region, rates)
        if beading:
            region_bd["beading"] = beading
            sub += beading["cost"]

        hw_items = _compute_hardware(region, rates)
        region_bd["hardware"] = hw_items
        for hw in hw_items:
            sub += hw["cost"]

    # 3b. Grill overlay costs (leaf OR branch — SS grill continuity model).
    #     `door` regions never carry grill (§4A.2), so skip them defensively.
    if rt != "door":
        for overlay in region.get("overlays", []):
            grill = _compute_grill(overlay, region, rates)
            if grill:
                region_bd["grill"] = grill
                sub += grill["cost"]

    region_bd["subtotal"] = _round2(sub)

    # Include if it has costs or is a leaf
    if is_leaf or sub > 0:
        results.append(region_bd)

    # Recurse into children
    if not is_leaf and region.get("split"):
        for child in region["split"].get("children", []):
            results.extend(_walk_regions(child, rates, counter))

    return results


# ─── Main pricing function (§9.1) ─────────────────────────────────

def price_design(
    tree: dict,
    rates: RateDict,
    discount_type: Optional[str] = None,
    discount_value: float = 0,
    advance_pct: float = 50,
    gst_pct: float = 18.0,
) -> dict:
    """
    Main pricing entry point. Performs full tree traversal per spec §9.1.

    Args:
        tree: Full design tree JSON (DesignTree schema).
        rates: Dict mapping item_code → rate value.
        discount_type: "PERCENTAGE" | "FLAT" | None.
        discount_value: Discount amount (percent or flat ₹).
        advance_pct: Advance percentage (default 50%).
        gst_pct: GST percentage on the post-discount amount (default 18%).

    Returns:
        EstimateBreakdown dict with all line items, totals, GST.
    """
    section_size = tree["sectionSize"]
    gauge = tree["gauge"]
    sec_rate = _section_rate(section_size, gauge, rates)
    # "window" (default) or "door" — selects the 3-sided concrete-base rules (§4A).
    product_type = tree.get("productType", "window")

    frame = tree["frame"]
    root_region = frame["rootRegion"]

    # 1. Frame cost
    frame_item = _compute_frame_cost(frame, sec_rate, product_type)

    # 2. Collect and price all splits
    raw_splits = _collect_splits(root_region, product_type)
    split_items = _compute_split_costs(raw_splits, sec_rate)

    # 3. Walk all regions (depth-first)
    counter = [0]  # mutable counter for region numbering
    region_breakdowns = _walk_regions(root_region, rates, counter)

    # 4. Aggregate subtotal
    subtotal = frame_item["cost"]
    for s in split_items:
        subtotal += s["cost"]
    for r in region_breakdowns:
        subtotal += r["subtotal"]
    subtotal = _round2(subtotal)

    # 5. Discount (PR-5)
    discount_amount = 0.0
    if discount_type == "PERCENTAGE" and discount_value > 0:
        discount_amount = _round2(subtotal * discount_value / 100)
    elif discount_type == "FLAT" and discount_value > 0:
        discount_amount = _round2(min(discount_value, subtotal))

    # 6. Taxable, GST, total
    taxable = _round2(subtotal - discount_amount)
    gst = _round2(taxable * gst_pct / 100)      # PR-4 (default 18%)
    grand_total = _round_rupee(taxable + gst)   # PR-3: nearest rupee
    advance_amount = _round_rupee(grand_total * advance_pct / 100)

    return {
        "frame": frame_item,
        "splits": split_items,
        "regions": region_breakdowns,
        "subtotal": subtotal,
        "discount_type": discount_type,
        "discount_value": _round2(discount_value),
        "discount_amount": discount_amount,
        "taxable": taxable,
        "gst": gst,
        "grand_total": grand_total,
        "advance_pct": _round2(advance_pct),
        "advance_amount": advance_amount,
    }


# ─── Estimate aggregation (multi-frame) ───────────────────────────

def sum_other_charges(other_charges: Optional[list]) -> float:
    """Total of the PR-9 manual charge line items ({label, amount} dicts)."""
    return _round2(sum(
        float(c.get("amount", 0) or 0) for c in (other_charges or [])
    ))


def _apply_commercial_terms(
    subtotal: float,
    discount_type: Optional[str],
    discount_value: float,
    advance_pct: float,
    gst_pct: float = 18.0,
    other_charges: Optional[list] = None,
) -> dict:
    """Apply other charges (PR-9) → discount → GST → grand total → advance.

    Charges join the subtotal before discount, so discount and GST apply to
    the combined amount (composite supply)."""
    other_charges_total = sum_other_charges(other_charges)
    gross = _round2(subtotal + other_charges_total)

    discount_amount = 0.0
    if discount_type == "PERCENTAGE" and discount_value > 0:
        discount_amount = _round2(gross * discount_value / 100)
    elif discount_type == "FLAT" and discount_value > 0:
        discount_amount = _round2(min(discount_value, gross))

    taxable = _round2(gross - discount_amount)
    gst = _round2(taxable * gst_pct / 100)
    grand_total = _round_rupee(taxable + gst)
    advance_amount = _round_rupee(grand_total * advance_pct / 100)
    return {
        "other_charges_total": other_charges_total,
        "discount_amount": discount_amount,
        "taxable": taxable,
        "gst": gst,
        "grand_total": grand_total,
        "advance_amount": advance_amount,
    }


def price_estimate(
    frames: list[dict],
    rates: RateDict,
    discount_type: Optional[str] = None,
    discount_value: float = 0,
    advance_pct: float = 50,
    gst_pct: float = 18.0,
    other_charges: Optional[list] = None,
) -> dict:
    """
    Price a multi-frame estimate.

    Each frame is priced as a single unit (its own full breakdown, with no
    per-frame discount/GST), then multiplied by its quantity. Estimate-level
    other charges (PR-9), discount, GST, and advance are applied once to the
    aggregate.

    Args:
        frames: list of {name, quantity, tree} dicts.
        rates: item_code → rate.
        other_charges: optional list of {label, amount} manual line items.
    """
    frame_lines = []
    subtotal = 0.0
    for f in frames:
        tree = f["tree"]
        qty = int(f.get("quantity", 1) or 1)
        unit = price_design(tree, rates, discount_type=None, discount_value=0, advance_pct=0)
        unit_subtotal = unit["subtotal"]
        line_total = _round2(unit_subtotal * qty)
        subtotal += line_total
        frame_lines.append({
            "name": f.get("name", "Frame"),
            "dimensions": f"{tree['frame']['width']}ft × {tree['frame']['height']}ft",
            "section": f"{tree.get('sectionSize', '')}\" {tree.get('gauge', '')}".strip(),
            "quantity": qty,
            "unit_subtotal": unit_subtotal,
            "line_total": line_total,
            "breakdown": unit,
        })

    subtotal = _round2(subtotal)
    terms = _apply_commercial_terms(
        subtotal, discount_type, discount_value, advance_pct, gst_pct,
        other_charges=other_charges,
    )

    return {
        "frames": frame_lines,
        "subtotal": subtotal,
        "other_charges": list(other_charges or []),
        "discount_type": discount_type,
        "discount_value": _round2(discount_value),
        "advance_pct": _round2(advance_pct),
        **terms,
    }


# ─── Default rates from spec §9.2 ─────────────────────────────────

DEFAULT_RATES = [
    {"item_code": "SECTION_5_18G",     "rate": 120, "unit": "per RFT",   "label": "Section 5\" 18G"},
    {"item_code": "SECTION_5_16G",     "rate": 155, "unit": "per RFT",   "label": "Section 5\" 16G"},
    {"item_code": "SECTION_6_18G",     "rate": 175, "unit": "per RFT",   "label": "Section 6\" 18G"},
    {"item_code": "SECTION_6_16G",     "rate": 210, "unit": "per RFT",   "label": "Section 6\" 16G"},
    {"item_code": "SECTION_10_18G",    "rate": 230, "unit": "per RFT",   "label": "Section 10\" 18G"},
    {"item_code": "SECTION_10_16G",    "rate": 270, "unit": "per RFT",   "label": "Section 10\" 16G"},
    {"item_code": "SHUTTER_MS_PIPE",   "rate": 100, "unit": "per RFT",   "label": "Shutter MS Pipe"},
    {"item_code": "SHUTTER_GP_SHEET",  "rate": 250, "unit": "per RFT",   "label": "Shutter GP Sheet"},
    {"item_code": "HINGE_SS_12G",      "rate": 120, "unit": "per piece", "label": "Hinge SS 12G"},
    {"item_code": "HINGE_SS_10G",      "rate": 260, "unit": "per piece", "label": "Hinge SS 10G"},
    {"item_code": "GRILL_MS_SQUARE",   "rate": 100, "unit": "per sqft",  "label": "Grill MS Square"},
    {"item_code": "GRILL_SS_PIPE_ROUND",  "rate": 90,  "unit": "per RFT",   "label": "Grill SS Pipe Round"},
    {"item_code": "GRILL_SS_PIPE_SQUARE", "rate": 110, "unit": "per RFT",   "label": "Grill SS Pipe Square"},
    {"item_code": "GLASS_BEADING",     "rate": 40,  "unit": "per RFT",   "label": "Glass Beading"},
    {"item_code": "JALI_WIRE_MESH",    "rate": 110, "unit": "per sqft",  "label": "Jali Wire Mesh"},
    {"item_code": "LOCK_PROVISION",    "rate": 100, "unit": "per piece", "label": "Lock Provision"},
]
