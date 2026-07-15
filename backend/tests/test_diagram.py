"""
Unit tests for the per-frame diagram + branded quotation HTML.

These are pure (no DB, no WeasyPrint) so they run everywhere, exercising the SVG
fallback renderer and the Jinja branding template directly.
"""
from datetime import date
from types import SimpleNamespace

from app.services.diagram import tree_to_svg
from app.services.bom import build_bom
from app.services.pdf import render_estimate_html


def _split_tree():
    """A 5×4 window split vertically into a shutter + a fixed pane."""
    return {
        "outerWidth": 5, "outerHeight": 4, "sectionSize": "5", "gauge": "18G",
        "productType": "window",
        "frame": {
            "width": 5, "height": 4,
            "rootRegion": {
                "id": "root", "isLeaf": False, "x": 0, "y": 0, "width": 5, "height": 4,
                "split": {
                    "direction": "vertical", "position": 0.5,
                    "children": [
                        {"id": "a", "isLeaf": True, "x": 0, "y": 0, "width": 2.5, "height": 4, "regionType": "shutter"},
                        {"id": "b", "isLeaf": True, "x": 2.5, "y": 0, "width": 2.5, "height": 4, "regionType": "fixed"},
                    ],
                },
            },
        },
    }


def test_tree_to_svg_draws_regions_and_mullion():
    svg = tree_to_svg(_split_tree())
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "SHUTTER" in svg and "FIXED" in svg
    assert '<polyline' in svg and 'stroke="#6b7280"' in svg   # the mullion
    assert svg.count("<rect") >= 3  # two leaves + the outer frame outline


def test_tree_to_svg_handles_single_leaf():
    tree = {
        "frame": {"width": 3, "height": 3, "rootRegion": {
            "id": "r", "isLeaf": True, "x": 0, "y": 0, "width": 3, "height": 3, "regionType": "open"}}
    }
    svg = tree_to_svg(tree)
    assert svg.startswith("<svg")
    assert 'stroke="#6b7280"' not in svg     # no mullion (no splits)


def _fake_estimate():
    frame = SimpleNamespace(
        name="Living Room", outer_width=5, outer_height=4, section_size="5", gauge="18G",
        quantity=2, unit_subtotal=1000.0, line_total=2000.0,
        unit_breakdown={"frame": {"label": "Frame", "description": "x", "cost": 500}, "splits": [], "regions": []},
        tree_json=_split_tree(),
    )
    customer = SimpleNamespace(name="Acme Co", company="Acme", phone="123", email="a@b.com",
                               address="Street", gstin="29ABCDE1234F1Z5")
    return SimpleNamespace(
        number=7, title="Ground floor", notes="", terms="50% advance.", status="sent",
        quote_date=date(2026, 6, 25), valid_until=date(2026, 7, 25), created_at=date(2026, 6, 25),
        discount_type=None, discount_value=0, discount_amount=0,
        subtotal=2000.0, taxable=2000.0, gst=360.0, grand_total=2360, advance_pct=50, advance_amount=1180,
        customer=customer, frames=[frame],
    )


def test_build_bom_aggregates_across_frames_and_quantity():
    breakdown = {
        "frame": {"label": "Frame", "quantity": 18, "unit": "RFT", "cost": 100.0},
        "splits": [{"label": "Mullion (vertical)", "quantity": 4, "unit": "RFT", "cost": 50.0}],
        "regions": [],
    }
    frames = [
        {"breakdown": breakdown, "quantity": 2},
        {"breakdown": breakdown, "quantity": 1},
    ]
    bom = build_bom(frames)
    by_label = {r["label"]: r for r in bom}
    # Frame: 18 RFT × (2 + 1) frames = 54 RFT; cost 100 × 3 = 300.
    assert by_label["Frame"]["quantity"] == 54
    assert by_label["Frame"]["cost"] == 300.0
    assert by_label["Mullion (vertical)"]["quantity"] == 12


def test_render_estimate_html_includes_branding_and_fallback_diagram():
    company = SimpleNamespace(
        name="Steel Works Pvt Ltd", logo_data_url=None, address="Plot 9", phone="999",
        email="sales@steel.test", gstin="27AAAAA0000A1Z5", bank_details="HDFC ****1234",
        default_terms="Default terms",
    )
    html = render_estimate_html(_fake_estimate(), company)
    assert "Steel Works Pvt Ltd" in html       # seller letterhead
    assert "27AAAAA0000A1Z5" in html            # seller GSTIN
    assert "HDFC ****1234" in html              # bank details
    assert "50% advance." in html               # estimate terms
    assert "Valid until" in html
    assert "<svg" in html                        # per-frame schematic diagram embedded
    assert "EST-0007" in html
    assert "Bill of Materials" in html           # BOM section rendered


# ─── SS grill bars: drawn = billed, same pitch in every region (§6.2) ──

import re


def _ss_grill(bar_adjust=None):
    overlay = {"id": "g1", "type": "overlay", "overlayType": "grill", "material": "SS_PIPE_ROUND"}
    if bar_adjust is not None:
        overlay["config"] = {"barAdjust": bar_adjust}
    return overlay


def _grilled_two_row_tree(bar_adjust=None):
    """5×10 frame split horizontally: 2.5ft grilled region above a 7.5ft grilled region."""
    return {
        "outerWidth": 5, "outerHeight": 10, "sectionSize": "5", "gauge": "18G",
        "frame": {
            "width": 5, "height": 10,
            "rootRegion": {
                "id": "root", "isLeaf": False, "x": 0, "y": 0, "width": 5, "height": 10,
                "split": {
                    "direction": "horizontal", "position": 0.25,
                    "children": [
                        {"id": "top", "isLeaf": True, "x": 0, "y": 0, "width": 5, "height": 2.5,
                         "regionType": "fixed", "overlays": [_ss_grill()]},
                        {"id": "bottom", "isLeaf": True, "x": 0, "y": 2.5, "width": 5, "height": 7.5,
                         "regionType": "fixed", "overlays": [_ss_grill(bar_adjust)]},
                    ],
                },
            },
        },
    }


def _grill_bar_ys(svg):
    """y1 of every SS grill bar line, in document order."""
    return [float(m) for m in re.findall(r'y1="([\d.]+)"[^/]*stroke="#93c5fd"', svg)]


def test_grill_bars_drawn_equal_billed():
    svg = tree_to_svg(_grilled_two_row_tree())
    ys = _grill_bar_ys(svg)
    assert len(ys) == 3 + 13   # 2.5ft → 3 bars, 7.5ft → 13 bars


def test_grill_bars_evenly_spaced_within_each_region():
    """§6.2 rendering rule: bars fill each region with equal gaps, edge to edge."""
    svg = tree_to_svg(_grilled_two_row_tree())
    ys = _grill_bar_ys(svg)
    for bars in (ys[:3], ys[3:]):
        gaps = [b - a for a, b in zip(bars, bars[1:])]
        # uniform spacing within the region (0.1px coordinate rounding)
        assert max(gaps) - min(gaps) <= 0.25


def test_grill_bar_adjust_changes_drawn_count():
    svg = tree_to_svg(_grilled_two_row_tree(bar_adjust=2))
    ys = _grill_bar_ys(svg)
    assert len(ys) == 3 + 15   # bottom region draws its adjusted (billed) count


def test_no_decorative_bars_on_too_short_region():
    tree = {
        "frame": {"width": 4, "height": 1, "rootRegion": {
            "id": "r", "isLeaf": True, "x": 0, "y": 0, "width": 4, "height": 1,
            "regionType": "fixed", "overlays": [_ss_grill()]}},
    }
    assert "#93c5fd" not in tree_to_svg(tree)
