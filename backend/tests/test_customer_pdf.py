"""
Unit tests for the customer-facing summary quotation (frame cards, no
component costs, no BOM). Pure — no DB, no WeasyPrint — mirroring
test_diagram.py, so they run everywhere including Windows hosts.

The internal detailed document (render_estimate_html / estimate_pdf.html) is
covered by test_diagram.py and must stay untouched; these tests only cover
the parallel customer render path.
"""
from datetime import date
from types import SimpleNamespace

from app.services.pdf import render_customer_estimate_html, _spec_summary


def _split_tree():
    """A 5×4 window: shutter with glass infill + a fixed pane."""
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
                        {"id": "a", "isLeaf": True, "x": 0, "y": 0, "width": 2.5, "height": 4,
                         "regionType": "shutter", "paneSpec": {"shutterMaterial": "MS_PIPE", "infillType": "glass", "hasBeading": True}},
                        {"id": "b", "isLeaf": True, "x": 2.5, "y": 0, "width": 2.5, "height": 4, "regionType": "fixed"},
                    ],
                },
            },
        },
    }


def _breakdown():
    """A realistic frozen unit_breakdown — descriptions embed ₹ rates, which
    must never surface on the customer document."""
    return {
        "frame": {"label": "Frame", "description": "Frame 18 RFT (4-sided, void-aware) × ₹120/RFT",
                  "quantity": 18, "unit": "RFT", "rate": 120, "cost": 2160.0},
        "splits": [{"label": "Mullion (vertical)", "description": "Mullion (vertical) 4 RFT × ₹240/RFT (double section)",
                    "quantity": 4, "unit": "RFT", "rate": 240, "cost": 960.0}],
        "regions": [
            {"region_label": "Region 1", "region_type": "shutter", "dimensions": "4ft × 2.5ft",
             "pane_structure": {"label": "Shutter pane (MS Pipe)", "description": "Shutter pane 13 RFT × ₹100/RFT", "cost": 1300.0},
             "pane_structure_2": None, "infill": None,
             "beading": {"label": "Beading", "description": "Beading 13 RFT × ₹40/RFT", "cost": 520.0},
             "grill": None,
             "hardware": [{"label": "Hinge (SS 12G)", "description": "3 × ₹120/pc",
                           "quantity": 3, "unit": "pc", "rate": 120, "cost": 360.0}],
             "subtotal": 2180.0},
            {"region_label": "Region 2", "region_type": "fixed", "dimensions": "4ft × 2.5ft",
             "pane_structure": None, "pane_structure_2": None, "infill": None, "beading": None,
             "grill": {"label": "M.S. Square Grill", "description": "MS Grill 10 sqft × ₹100/sqft", "cost": 1000.0},
             "hardware": [], "subtotal": 1000.0},
        ],
    }


def _fake_estimate():
    frames = [
        SimpleNamespace(
            name="Living Room", outer_width=5, outer_height=4, section_size="5", gauge="18G",
            quantity=2, unit_subtotal=1000.0, line_total=2000.0,
            unit_breakdown=_breakdown(), tree_json=_split_tree(),
        ),
        SimpleNamespace(
            name="Store Vent", outer_width=3, outer_height=2, section_size="5", gauge="18G",
            quantity=1, unit_subtotal=500.0, line_total=500.0,
            unit_breakdown={}, tree_json={},
        ),
    ]
    customer = SimpleNamespace(name="Acme Co", company="Acme", phone="123", email="a@b.com",
                               address="Street", gstin="29ABCDE1234F1Z5")
    return SimpleNamespace(
        number=7, title="Ground floor", notes="Site measured.", terms="50% advance.", status="draft",
        quote_date=date(2026, 6, 25), valid_until=date(2026, 7, 25), created_at=date(2026, 6, 25),
        discount_type="PERCENTAGE", discount_value=5, discount_amount=125.0,
        other_charges=[{"label": "Installation", "amount": 3000}],
        subtotal=2500.0, taxable=5375.0, gst=967.5, gst_pct=18,
        grand_total=6343, advance_pct=50, advance_amount=3172,
        customer=customer, frames=frames,
    )


def _company():
    return SimpleNamespace(
        name="Steel Works Pvt Ltd", logo_data_url=None, address="Plot 9", phone="999",
        email="sales@steel.test", gstin="27AAAAA0000A1Z5", bank_details="HDFC ****1234",
        default_terms="Default terms",
    )


# ─── Spec summary ───────────────────────────────────────────────────

def test_spec_summary_uses_labels_never_rates():
    spec = _spec_summary(_breakdown(), _split_tree())
    assert "shutter" in spec
    assert "fixed pane" in spec
    assert "Shutter pane (MS Pipe)" in spec
    assert "Glass" in spec                      # ₹0 glass infill, pulled from the tree
    assert "Beading" in spec
    assert "M.S. Square Grill" in spec
    assert "3 × Hinge (SS 12G)" in spec
    # Never leak pricing math from item descriptions.
    assert "₹" not in spec
    assert "/RFT" not in spec and "/sqft" not in spec and "/pc" not in spec


def test_spec_summary_tolerates_empty_or_legacy_snapshots():
    assert _spec_summary({}, {}) == ""
    assert _spec_summary(None, None) == ""
    # Pre-region_type snapshots (older frozen estimates) must not crash.
    legacy = {"regions": [{"region_label": "Region 1", "hardware": []}]}
    assert _spec_summary(legacy, {}) == ""


# ─── Customer HTML ──────────────────────────────────────────────────

def test_customer_html_shows_frame_cards_and_totals():
    html = render_customer_estimate_html(_fake_estimate(), _company())
    assert "Steel Works Pvt Ltd" in html         # letterhead
    assert "EST-0007" in html
    assert "Living Room" in html
    assert "<svg" in html                        # per-frame schematic
    assert "2 × ₹1,000.00" in html               # qty × unit price (qty > 1)
    assert "₹2,000.00" in html                   # frame line total
    assert "3 × Hinge (SS 12G)" in html          # spec line reaches the card
    assert "Installation" in html                # other charges line
    assert "Discount (5%)" in html               # "%g"-formatted, no trailing ".0"
    assert "Taxable Amount" in html              # bridge row (charges/discount present)
    assert "GST (18%)" in html
    assert "Grand Total" in html
    assert "Advance payable (50%)" in html
    assert "50% advance." in html                # terms
    assert "HDFC ****1234" in html               # bank details


def test_customer_html_hides_internal_detail():
    html = render_customer_estimate_html(_fake_estimate(), _company())
    assert "Bill of Materials" not in html
    assert "Status" not in html                  # draft/sent is internal workflow
    assert "unit breakdown" not in html
    # No per-component cost math anywhere: rates and their units stay internal.
    assert "/RFT" not in html and "/sqft" not in html and "/pc" not in html
    assert "₹120/RFT" not in html
    assert "Mullion" not in html                 # construction detail lives in the diagram


def test_customer_html_quantity_one_shows_amount_only():
    html = render_customer_estimate_html(_fake_estimate(), _company())
    assert "Store Vent" in html
    assert "1 × ₹" not in html                   # no redundant "1 × price" line
    assert "Qty: 1" not in html
