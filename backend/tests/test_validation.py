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
