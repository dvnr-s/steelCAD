"""
Design tree validation service.
Implements invariants (INV-1..INV-10) and validation rules (V-1..V-20)
from design_rules_spec.md §3.3 and §11.
"""
from app.services.grill import ss_grill_auto_bars, ss_grill_bar_count, ss_grill_max_bars


# Server-side sanity bounds — protect pricing/PDF/diagram walkers from
# absurd or hostile trees. Generous vs. real-world steel doors/windows.
MAX_FRAME_WIDTH_FT = 30
MAX_FRAME_HEIGHT_FT = 20
MAX_TREE_DEPTH = 8
MAX_TREE_NODES = 200


def validate_tree_bounds(tree: dict) -> list[str]:
    """
    Max-bounds checks (B-1..B-4). Iterative walk — never recurses, so it is safe
    to run on a tree of untrusted depth BEFORE any recursive validation/pricing.
    Returns a list of error messages. Empty list = within bounds.
    """
    errors: list[str] = []
    frame = tree.get("frame") if isinstance(tree, dict) else None
    frame = frame if isinstance(frame, dict) else {}

    width = frame.get("width") or tree.get("outerWidth") or 0
    height = frame.get("height") or tree.get("outerHeight") or 0
    if isinstance(width, (int, float)) and width > MAX_FRAME_WIDTH_FT:
        errors.append(f"B-1: Frame width ({width}ft) exceeds the {MAX_FRAME_WIDTH_FT}ft maximum")
    if isinstance(height, (int, float)) and height > MAX_FRAME_HEIGHT_FT:
        errors.append(f"B-2: Frame height ({height}ft) exceeds the {MAX_FRAME_HEIGHT_FT}ft maximum")

    root = frame.get("rootRegion")
    if not isinstance(root, dict):
        return errors

    too_deep = False
    too_many = False
    count = 0
    stack: list[tuple[dict, int]] = [(root, 1)]
    while stack:
        region, depth = stack.pop()
        count += 1
        if count > MAX_TREE_NODES:
            too_many = True
            break
        if depth > MAX_TREE_DEPTH:
            too_deep = True
            continue  # don't descend further into an over-deep subtree
        split = region.get("split")
        if isinstance(split, dict):
            for child in split.get("children", []):
                if isinstance(child, dict):
                    stack.append((child, depth + 1))

    if too_many:
        errors.append(f"B-4: Design tree exceeds the {MAX_TREE_NODES}-region maximum")
    if too_deep:
        errors.append(f"B-3: Design tree nesting exceeds the depth-{MAX_TREE_DEPTH} maximum")
    return errors


def validate_design_tree(tree: dict) -> list[str]:
    """
    Validate the entire design tree.
    Returns a list of error messages. Empty list = valid.
    """
    # Bounds first — the walkers below recurse, so refuse oversized/over-deep
    # trees before touching them.
    errors: list[str] = validate_tree_bounds(tree)
    if errors:
        return errors

    # V-1: Frame dimensions >= 1 ft
    frame = tree.get("frame")
    if not frame:
        errors.append("Design must have a frame (INV-1)")
        return errors

    if frame.get("width", 0) < 1:
        errors.append("V-1: Frame width must be ≥ 1 ft")
    if frame.get("height", 0) < 1:
        errors.append("V-1: Frame height must be ≥ 1 ft")

    # INV-2: Frame has exactly one root region
    root = frame.get("rootRegion")
    if not root:
        errors.append("INV-2: Frame must have a root region")
        return errors

    # INV-10: all splits use same section/gauge as design root
    # (enforced structurally — no per-split override fields in schema)

    # Recursively validate regions
    _validate_region(root, errors)

    return errors


def _validate_region(region: dict, errors: list[str]) -> None:
    """Recursively validate a region and its descendants."""
    rid = str(region.get("id", "?"))
    w = region.get("width", 0)
    h = region.get("height", 0)

    # V-2: Minimum region dimensions
    if w < 0.5:
        errors.append(f"V-2: Region {rid} width ({w}ft) < 0.5ft minimum")
    if h < 0.5:
        errors.append(f"V-2: Region {rid} height ({h}ft) < 0.5ft minimum")

    is_leaf = region.get("isLeaf", True)
    split = region.get("split")

    # INV-4: Leaf ↔ split consistency
    if is_leaf and split is not None:
        errors.append(f"INV-4: Region {rid} is marked leaf but has a split")
    if not is_leaf and split is None:
        errors.append(f"INV-4: Region {rid} is marked branch but has no split")

    if is_leaf:
        _validate_leaf(region, errors)
    else:
        _validate_branch(region, errors)

    # Recurse into children
    if split:
        children = split.get("children", [])

        # INV-3: Every split has exactly 2 children
        if len(children) != 2:
            errors.append(
                f"INV-3: Split {split.get('id', '?')} must have exactly 2 children, "
                f"has {len(children)}"
            )

        # INV-8: Split position strictly between 0 and 1
        pos = split.get("position", 0.5)
        if pos <= 0 or pos >= 1:
            errors.append(
                f"INV-8: Split position must be in (0, 1) exclusive, got {pos}"
            )

        # V-3: Split leaves >= 0.5 ft on each side
        direction = split.get("direction", "vertical")
        if direction == "vertical":
            side_a, side_b = w * pos, w * (1 - pos)
        else:
            side_a, side_b = h * pos, h * (1 - pos)

        if side_a < 0.5:
            errors.append(
                f"V-3: Split {split.get('id', '?')} leaves only "
                f"{side_a:.2f}ft on side A (minimum 0.5ft)"
            )
        if side_b < 0.5:
            errors.append(
                f"V-3: Split {split.get('id', '?')} leaves only "
                f"{side_b:.2f}ft on side B (minimum 0.5ft)"
            )

        for child in children:
            _validate_region(child, errors)


def _validate_leaf(region: dict, errors: list[str]) -> None:
    """Validate a leaf region's type, pane spec, and hardware."""
    rid = str(region.get("id", "?"))
    rt = region.get("regionType")
    ps = region.get("paneSpec")
    hardware = region.get("hardware", [])

    # INV-7: Every leaf must have a regionType
    if not rt:
        errors.append(f"INV-7: Leaf region {rid} must have a regionType (default: 'open')")
        return

    # P-5: open/louver have no pane spec
    if rt in ("open", "louver") and ps:
        infill = ps.get("infillType", "none")
        if (infill != "none" or ps.get("hasBeading") or ps.get("shutterMaterial")
                or ps.get("jaliMaterial") or ps.get("jaliBeading")
                or ps.get("shutterConfig", "single") != "single"):
            errors.append(f"P-5: '{rt}' region {rid} should not have pane specification")

    # V-12: shutter regions must have a shutter material (door regions do NOT —
    # a door leaf has no pane, see V-18 / §4A.2). HINGES_ONLY (§5.8) counts.
    if rt == "shutter":
        if not ps or not ps.get("shutterMaterial"):
            errors.append(f"V-12: shutter region {rid} must have a shutter material selected")

    # HINGES_ONLY (§5.8): customer-supplied shutter — we charge hinges only.
    is_hinges_only = rt == "shutter" and (ps or {}).get("shutterMaterial") == "HINGES_ONLY"

    # V-19: double shuttering (§5.7) — shutter regions only. A FABRICATED double
    # needs a jali-side material; the explicit infill is the glass side. A
    # HINGES_ONLY double (§5.8) is exempt — its constraints are V-21. Jali-side
    # fields are meaningless while single.
    is_double_shutter = rt == "shutter" and (ps or {}).get("shutterConfig") == "double"
    if (ps or {}).get("shutterConfig", "single") == "double":
        if rt != "shutter":
            errors.append(f"V-19: double shuttering is only valid on 'shutter' regions, not '{rt}' region {rid}")
        elif not is_hinges_only:
            if not ps.get("jaliMaterial"):
                errors.append(f"V-19: double-shuttered region {rid} must have a jali-side shutter material selected")
            if ps.get("infillType", "none") != "glass":
                errors.append(f"V-19: double-shuttered region {rid} must have glass infill (the jali side is implied)")
    elif ps and (ps.get("jaliMaterial") or ps.get("jaliBeading")):
        errors.append(f"V-19: jali-side pane fields on region {rid} require double shuttering")

    # V-21: a HINGES_ONLY shutter (§5.8) is customer-supplied — no infill, no
    # beading, no jali-side material. Only hinges are ours (P-17).
    if is_hinges_only:
        if ps.get("infillType", "none") != "none":
            errors.append(f"V-21: HINGES_ONLY (customer-supplied) shutter {rid} must have infillType 'none'")
        if ps.get("hasBeading") or ps.get("jaliBeading"):
            errors.append(f"V-21: HINGES_ONLY (customer-supplied) shutter {rid} cannot have beading")
        if ps.get("jaliMaterial"):
            errors.append(f"V-21: HINGES_ONLY (customer-supplied) shutter {rid} cannot have a jali-side material")

    # V-18: door regions carry hardware only — no pane (shutter material / infill /
    # beading) and no grill overlay (§4A.2)
    if rt == "door":
        if ps and (ps.get("shutterMaterial") or ps.get("infillType", "none") != "none" or ps.get("hasBeading")):
            errors.append(f"V-18: door region {rid} has no pane (no shutter material, infill, or beading)")
        if region.get("overlays"):
            errors.append(f"V-18: door region {rid} cannot have a grill")

    # V-5: shutter/door must have at least one hinge; a double shutter is hinged
    # per shutter leaf (HW-9) — front (glass side) AND back (jali side)
    if rt in ("shutter", "door"):
        has_hinge = any(hw.get("hardwareType") == "hinge" for hw in hardware)
        if not has_hinge:
            errors.append(f"V-5: {rt} region {rid} must have at least one hinge")
        elif is_double_shutter:
            front = any(hw.get("hardwareType") == "hinge" and hw.get("side", "front") != "back" for hw in hardware)
            back = any(hw.get("hardwareType") == "hinge" and hw.get("side") == "back" for hw in hardware)
            if not (front and back):
                errors.append(f"V-5: double-shuttered region {rid} must have at least one hinge on each side (HW-9)")

    # V-14: Lock only on door regions
    for hw in hardware:
        if hw.get("hardwareType") == "lock" and rt != "door":
            errors.append(
                f"V-14: Lock cannot be applied to '{rt}' region {rid}. "
                f"Only 'door' regions."
            )

    # V-16: Back-side hardware requires a double-rebate door (§4A.6) or a
    # double-shuttered region (§5.7 — the back side is the jali shutter)
    has_back_hw = any(hw.get("side") == "back" for hw in hardware)
    if has_back_hw and not (rt == "door" and region.get("rebate") == "double") and not is_double_shutter:
        errors.append(
            f"V-16: Back-side hardware on region {rid} requires a double-rebate "
            f"door or a double-shuttered region."
        )

    # V-17: doorHand / rebate are meaningful only on door regions
    if rt != "door":
        if region.get("doorHand"):
            errors.append(f"V-17: doorHand is only valid on 'door' regions, not '{rt}' region {rid}")
        if region.get("rebate", "single") != "single":
            errors.append(f"V-17: rebate is only valid on 'door' regions, not '{rt}' region {rid}")

    # V-13: Beading requires infill
    if ps and ps.get("hasBeading"):
        if ps.get("infillType", "none") == "none":
            errors.append(f"V-13: Beading on region {rid} requires infill (glass or jali)")

    # V-9: Grill overlays must have valid material
    for overlay in region.get("overlays", []):
        if not overlay.get("material"):
            errors.append(f"V-9: Grill on region {rid} must have a valid material")

    # V-20: manual bar adjustment bounds (§6.2A)
    _validate_grill_bar_adjust(region, errors)


def _validate_grill_bar_adjust(region: dict, errors: list[str]) -> None:
    """
    V-20 (§6.2A): `barAdjust` must be a whole number, is valid only on SS
    grills, and when non-zero the effective bar count must stay within
    1 … floor(height × 6) (one bar per 2" of height). Rejected, never clamped —
    the billed count must always equal what the user sees.
    """
    rid = str(region.get("id", "?"))
    h = region.get("height", 0)
    for overlay in region.get("overlays", []):
        raw = (overlay.get("config") or {}).get("barAdjust")
        if raw in (None, 0):
            continue
        if isinstance(raw, bool) or not isinstance(raw, int):
            errors.append(f"V-20: Grill bar adjustment on region {rid} must be a whole number")
            continue
        if overlay.get("material") == "MS_SQUARE":
            errors.append(f"V-20: Bar adjustment is not valid on MS grill (region {rid})")
            continue
        bars = ss_grill_bar_count(h, raw)
        max_bars = ss_grill_max_bars(h)
        if bars < 1 or bars > max_bars:
            errors.append(
                f"V-20: Grill bar count on region {rid} must be between 1 and {max_bars} "
                f"(auto {ss_grill_auto_bars(h)} {raw:+d} = {bars})"
            )


def _validate_branch(region: dict, errors: list[str]) -> None:
    """Validate a branch region — must not have leaf-only properties."""
    rid = str(region.get("id", "?"))

    # INV-6: Branch regionType must be null
    if region.get("regionType"):
        errors.append(f"INV-6: Branch region {rid} must not have a regionType")

    # INV-6: Branch paneSpec must be null/empty
    ps = region.get("paneSpec")
    if ps:
        if (ps.get("infillType", "none") != "none"
                or ps.get("hasBeading")
                or ps.get("shutterMaterial")
                or ps.get("jaliMaterial")
                or ps.get("jaliBeading")
                or ps.get("shutterConfig", "single") != "single"):
            errors.append(f"INV-6: Branch region {rid} must not have pane specification")

    # INV-6: Branch hardware must be empty
    if region.get("hardware"):
        errors.append(f"INV-6: Branch region {rid} must not have hardware")

    # INV-5 / V-6: Branch regions may ONLY have SS grill overlays (not MS)
    for overlay in region.get("overlays", []):
        if overlay.get("material") == "MS_SQUARE":
            errors.append(f"V-6: MS grill cannot be applied to branch region {rid}")

    # V-20: manual bar adjustment bounds (§6.2A) — SS continuity grills too
    _validate_grill_bar_adjust(region, errors)
