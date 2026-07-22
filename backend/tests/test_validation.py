"""
Tree bounds validation — pure unit tests, no DB required.
"""
from uuid import uuid4

from app.services.validation import (
    validate_tree_bounds, validate_design_tree,
    MAX_FRAME_WIDTH_FT, MAX_FRAME_HEIGHT_FT, MAX_TREE_DEPTH, MAX_TREE_NODES,
)


def _leaf(width=4.0, height=3.0):
    return {
        "id": str(uuid4()), "type": "region", "x": 0, "y": 0,
        "width": width, "height": height,
        "isLeaf": True, "regionType": "fixed",
    }


def _branch(children, width=4.0, height=3.0):
    return {
        "id": str(uuid4()), "type": "region", "x": 0, "y": 0,
        "width": width, "height": height, "isLeaf": False,
        "split": {
            "id": str(uuid4()), "type": "split",
            "direction": "vertical", "position": 0.5,
            "children": children,
        },
    }


def _tree(root, width=4.0, height=3.0):
    return {
        "id": str(uuid4()), "type": "design", "name": "T",
        "productType": "window",
        "outerWidth": width, "outerHeight": height,
        "sectionSize": "5", "gauge": "18G",
        "frame": {
            "id": str(uuid4()), "type": "frame",
            "width": width, "height": height, "rootRegion": root,
        },
    }


def _chain(depth):
    """A degenerate chain of splits `depth` regions deep."""
    node = _leaf()
    for _ in range(depth - 1):
        node = _branch([node, _leaf()])
    return node


def _full(depth):
    """A full binary region tree of the given depth (2^depth - 1 regions)."""
    if depth == 1:
        return _leaf()
    return _branch([_full(depth - 1), _full(depth - 1)])


def test_valid_tree_within_bounds():
    assert validate_tree_bounds(_tree(_leaf())) == []


def test_width_exceeds_max():
    errors = validate_tree_bounds(_tree(_leaf(), width=MAX_FRAME_WIDTH_FT + 1))
    assert any("B-1" in e for e in errors)


def test_height_exceeds_max():
    errors = validate_tree_bounds(_tree(_leaf(), height=MAX_FRAME_HEIGHT_FT + 1))
    assert any("B-2" in e for e in errors)


def test_width_at_max_is_allowed():
    assert validate_tree_bounds(_tree(_leaf(), width=MAX_FRAME_WIDTH_FT)) == []


def test_depth_exceeds_max():
    errors = validate_tree_bounds(_tree(_chain(MAX_TREE_DEPTH + 1)))
    assert any("B-3" in e for e in errors)


def test_depth_at_max_is_allowed():
    assert validate_tree_bounds(_tree(_chain(MAX_TREE_DEPTH))) == []


def test_node_count_exceeds_max():
    # A full depth-8 tree has 255 regions > MAX_TREE_NODES (200) at legal depth.
    assert 2 ** MAX_TREE_DEPTH - 1 > MAX_TREE_NODES
    errors = validate_tree_bounds(_tree(_full(MAX_TREE_DEPTH)))
    assert any("B-4" in e for e in errors)


def test_bounds_survive_malformed_tree():
    # Must not raise on junk — it runs before schema-shaped guarantees exist.
    assert validate_tree_bounds({}) == []
    assert validate_tree_bounds({"frame": None}) == []
    assert validate_tree_bounds({"frame": {"rootRegion": None}}) == []


def test_design_validation_short_circuits_on_bounds():
    """validate_design_tree must refuse oversized trees before recursing."""
    errors = validate_design_tree(_tree(_chain(MAX_TREE_DEPTH + 5)))
    assert errors and all(e.startswith("B-") for e in errors)


# ─── Double shuttering (V-19 / V-5 / V-16, spec §5.7) ──────────────

def _hinge(side="front"):
    return {
        "id": str(uuid4()), "type": "hardware", "hardwareType": "hinge",
        "variant": "SS_12G", "quantity": 2, "autoComputed": True, "side": side,
    }


def _double_shutter_leaf(**overrides):
    leaf = _leaf()
    leaf.update({
        "regionType": "shutter",
        "paneSpec": {
            "shutterConfig": "double",
            "shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": False,
            "jaliMaterial": "MS_PIPE", "jaliBeading": False,
        },
        "hardware": [_hinge("front"), _hinge("back")],
    })
    leaf.update(overrides)
    return leaf


def test_valid_double_shutter_passes():
    assert validate_design_tree(_tree(_double_shutter_leaf())) == []


def test_double_shutter_requires_jali_material():
    leaf = _double_shutter_leaf()
    leaf["paneSpec"]["jaliMaterial"] = None
    errors = validate_design_tree(_tree(leaf))
    assert any("V-19" in e and "jali-side" in e for e in errors)


def test_double_shutter_requires_glass_infill():
    leaf = _double_shutter_leaf()
    leaf["paneSpec"]["infillType"] = "jali"
    errors = validate_design_tree(_tree(leaf))
    assert any("V-19" in e and "glass infill" in e for e in errors)


def test_double_shutter_only_on_shutter_regions():
    leaf = _double_shutter_leaf(regionType="fixed", hardware=[])
    errors = validate_design_tree(_tree(leaf))
    assert any("V-19" in e and "'fixed'" in e for e in errors)


def test_jali_fields_rejected_on_single_shutter():
    leaf = _double_shutter_leaf(hardware=[_hinge("front")])
    leaf["paneSpec"]["shutterConfig"] = "single"
    errors = validate_design_tree(_tree(leaf))
    assert any("V-19" in e and "require double shuttering" in e for e in errors)


def test_double_shutter_needs_hinges_on_both_sides():
    leaf = _double_shutter_leaf(hardware=[_hinge("front")])
    errors = validate_design_tree(_tree(leaf))
    assert any("V-5" in e and "each side" in e for e in errors)


def test_back_hinge_allowed_on_double_shutter_but_not_single():
    # Double shutter: back-side hinge is the jali shutter's — valid (V-16).
    assert validate_design_tree(_tree(_double_shutter_leaf())) == []
    # Single shutter: no back side exists.
    leaf = _double_shutter_leaf()
    leaf["paneSpec"] = {"shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": False}
    errors = validate_design_tree(_tree(leaf))
    assert any("V-16" in e for e in errors)


# ─── V-21: customer-supplied shutter (HINGES_ONLY, spec §5.8) ──────

def _hinges_only_leaf(config="single", **pane_overrides):
    leaf = _leaf()
    pane = {"shutterMaterial": "HINGES_ONLY", "infillType": "none", "hasBeading": False}
    if config == "double":
        pane["shutterConfig"] = "double"
        hardware = [_hinge("front"), _hinge("back")]
    else:
        hardware = [_hinge("front")]
    pane.update(pane_overrides)
    leaf.update({"regionType": "shutter", "paneSpec": pane, "hardware": hardware})
    return leaf


def test_hinges_only_single_passes():
    assert validate_design_tree(_tree(_hinges_only_leaf())) == []


def test_hinges_only_double_passes():
    # Exempt from V-19's jali-material / glass-infill requirement (§5.8); still
    # needs a hinge on each side (V-5 / HW-9).
    assert validate_design_tree(_tree(_hinges_only_leaf("double"))) == []


def test_hinges_only_double_needs_back_hinge():
    leaf = _hinges_only_leaf("double")
    leaf["hardware"] = [_hinge("front")]
    errors = validate_design_tree(_tree(leaf))
    assert any("V-5" in e and "each side" in e for e in errors)


def test_hinges_only_rejects_infill():
    errors = validate_design_tree(_tree(_hinges_only_leaf(infillType="glass")))
    assert any("V-21" in e and "infillType" in e for e in errors)


def test_hinges_only_rejects_beading():
    errors = validate_design_tree(_tree(_hinges_only_leaf(hasBeading=True)))
    assert any("V-21" in e and "beading" in e for e in errors)


def test_hinges_only_rejects_jali_material():
    errors = validate_design_tree(_tree(_hinges_only_leaf("double", jaliMaterial="MS_PIPE")))
    assert any("V-21" in e and "jali-side material" in e for e in errors)


# ─── V-20: manual grill bar adjustment bounds (§6.2A) ──────────────

def _ss_grill(bar_adjust=None, material="SS_PIPE_ROUND"):
    overlay = {"id": str(uuid4()), "type": "overlay", "overlayType": "grill", "material": material}
    if bar_adjust is not None:
        overlay["config"] = {"barAdjust": bar_adjust}
    return overlay


def test_bar_adjust_within_bounds_is_valid():
    # 4×3 fixed leaf: auto = 4 bars, +2 = 6, max = 18 → fine.
    leaf = _leaf()
    leaf["overlays"] = [_ss_grill(2)]
    assert validate_design_tree(_tree(leaf)) == []


def test_bar_adjust_cannot_zero_out_the_grill():
    # auto 4 − 4 = 0 bars → below the 1-bar minimum.
    leaf = _leaf()
    leaf["overlays"] = [_ss_grill(-4)]
    errors = validate_design_tree(_tree(leaf))
    assert any("V-20" in e for e in errors)


def test_bar_adjust_capped_at_two_inch_pitch():
    # max = floor(3 × 6) = 18; auto 4 + 15 = 19 → too dense.
    leaf = _leaf()
    leaf["overlays"] = [_ss_grill(15)]
    errors = validate_design_tree(_tree(leaf))
    assert any("V-20" in e for e in errors)


def test_bar_adjust_must_be_whole_number():
    leaf = _leaf()
    leaf["overlays"] = [_ss_grill(2.5)]
    errors = validate_design_tree(_tree(leaf))
    assert any("V-20" in e and "whole number" in e for e in errors)


def test_bar_adjust_invalid_on_ms_grill():
    leaf = _leaf()
    leaf["overlays"] = [_ss_grill(2, material="MS_SQUARE")]
    errors = validate_design_tree(_tree(leaf))
    assert any("V-20" in e and "MS grill" in e for e in errors)


def test_bar_adjust_checked_on_branch_continuity_grill():
    branch = _branch([_leaf(width=2.0), _leaf(width=2.0)])
    branch["overlays"] = [_ss_grill(-4)]
    errors = validate_design_tree(_tree(branch))
    assert any("V-20" in e for e in errors)


# ─── V-22: stored geometry must match the tree that derives it (§12.2) ──

def _vsplit_tree(pos=0.5, fw=4.0, fh=3.0):
    """A frame with one vertical split whose children are laid out honestly:
    widths fw×pos / fw×(1−pos) at full height — matching editorStore relayout."""
    left = _leaf(width=fw * pos, height=fh)
    right = _leaf(width=fw * (1 - pos), height=fh)
    branch = _branch([left, right], width=fw, height=fh)
    branch["split"]["position"] = pos
    return _tree(branch, width=fw, height=fh)


def _hsplit_tree(pos=0.5, fw=4.0, fh=3.0):
    """A frame with one horizontal split: heights fh×pos / fh×(1−pos) at full width."""
    top = _leaf(width=fw, height=fh * pos)
    bottom = _leaf(width=fw, height=fh * (1 - pos))
    branch = _branch([top, bottom], width=fw, height=fh)
    branch["split"].update({"direction": "horizontal", "position": pos})
    return _tree(branch, width=fw, height=fh)


def test_consistent_vertical_split_passes():
    assert validate_design_tree(_vsplit_tree(pos=0.6)) == []


def test_consistent_horizontal_split_passes():
    assert validate_design_tree(_hsplit_tree(pos=0.4)) == []


def test_child_width_inconsistent_with_split_is_rejected():
    # The headline case: a 5ft-wide child relabelled as 1ft would misprice.
    tree = _vsplit_tree(pos=0.5)          # honest children are 2.0ft wide
    tree["frame"]["rootRegion"]["split"]["children"][0]["width"] = 1.0
    errors = validate_design_tree(tree)
    assert any("V-22" in e for e in errors)


def test_child_height_inconsistent_with_horizontal_split_is_rejected():
    tree = _hsplit_tree(pos=0.5)          # honest children are 1.5ft tall
    tree["frame"]["rootRegion"]["split"]["children"][1]["height"] = 0.9
    errors = validate_design_tree(tree)
    assert any("V-22" in e for e in errors)


def test_root_region_must_match_frame():
    tree = _tree(_leaf(width=4.0, height=3.0), width=4.0, height=3.0)
    tree["frame"]["rootRegion"]["width"] = 2.0   # root no longer spans the frame
    errors = validate_design_tree(tree)
    assert any("V-22" in e and "Root region" in e for e in errors)


def test_geometry_within_tolerance_passes():
    # Float drift below the 1e-3 tolerance must not be flagged (honest,
    # frontend-cleaned geometry lands here).
    tree = _vsplit_tree(pos=0.5)                  # children 2.0ft wide
    tree["frame"]["rootRegion"]["split"]["children"][0]["width"] = 2.0004
    assert validate_design_tree(tree) == []


# ─── V-23: sectionSize / gauge must be present (pricing derives from them) ──

def test_missing_section_size_rejected():
    tree = _tree(_leaf())
    del tree["sectionSize"]
    errors = validate_design_tree(tree)
    assert any("V-23" in e and "sectionSize" in e for e in errors)


def test_missing_gauge_rejected():
    tree = _tree(_leaf())
    del tree["gauge"]
    errors = validate_design_tree(tree)
    assert any("V-23" in e and "gauge" in e for e in errors)
