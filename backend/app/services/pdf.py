"""
PDF generation — renders a multi-frame estimate as a professional quotation
PDF using WeasyPrint.
"""
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.diagram import tree_to_svg
from app.services.bom import build_bom
from app.services.units import fmt_ft_in

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _build_env() -> Environment:
    """Jinja env with HTML autoescaping ON.

    User-controlled fields (customer name/address/notes, estimate terms, company
    branding) flow straight into this template and are rendered by WeasyPrint. A
    bare Environment does NOT autoescape, which would let any authenticated user
    inject HTML into the PDF — and via WeasyPrint's URL fetcher, reach file:// or
    remote URLs (local-file read / SSRF). Autoescape neutralizes the markup; the
    fetcher below is the second layer.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["money"] = _fmt
    return env


def _data_only_url_fetcher(url: str):
    """WeasyPrint URL fetcher that permits ONLY inline data: URIs.

    Templates legitimately embed the company logo as a data: URL and nothing
    else. Blocking every other scheme stops a hostile field (e.g. an injected
    `<img src="file:///etc/passwd">` or `src="http://internal/…">`) from turning
    a PDF render into local-file disclosure or a blind SSRF from the API host.
    """
    if not url.lower().startswith("data:"):
        raise ValueError(f"Blocked non-data URL during PDF render: {url[:48]!r}")
    from weasyprint import default_url_fetcher

    return default_url_fetcher(url)


def _fmt(value: float) -> str:
    """Format a number as Indian-grouped currency string (no symbol)."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _fmt_date(value) -> str:
    return value.strftime("%d %b %Y") if value else ""


def render_estimate_html(estimate, company=None) -> str:
    """Render the quotation HTML (factored out so tests can assert on it)."""
    template = _build_env().get_template("estimate_pdf.html")

    customer = estimate.customer
    frames = []
    for f in estimate.frames:
        frames.append({
            "name": f.name,
            "dimensions": f"{fmt_ft_in(f.outer_width)} × {fmt_ft_in(f.outer_height)}",
            "section": f'{f.section_size}" {f.gauge}',
            "quantity": f.quantity,
            "unit_subtotal": float(f.unit_subtotal or 0),
            "line_total": float(f.line_total or 0),
            "breakdown": f.unit_breakdown or {},
            # Every frame uses the deterministic server-side schematic so all
            # frames render identically (captured PNGs were per-frame inconsistent).
            "diagram_svg": tree_to_svg(f.tree_json or {}),
        })

    company = company or type("Co", (), {})()
    return template.render(
        estimate={
            "number": estimate.number,
            "revision": getattr(estimate, "revision", 1) or 1,
            "title": estimate.title or "",
            "notes": estimate.notes or "",
            "terms": estimate.terms or getattr(company, "default_terms", None) or "",
            "status": estimate.status,
            "quote_date": _fmt_date(getattr(estimate, "quote_date", None)) or _fmt_date(estimate.created_at),
            "valid_until": _fmt_date(getattr(estimate, "valid_until", None)),
            "discount_type": estimate.discount_type,
            "discount_value": float(estimate.discount_value or 0),
            "discount_amount": float(estimate.discount_amount or 0),
            "subtotal": float(estimate.subtotal or 0),
            # PR-9 manual charges (labor/transport/installation), shown between
            # the frames subtotal and the discount row.
            "other_charges": [
                {"label": c.get("label", ""), "amount": float(c.get("amount", 0) or 0)}
                for c in (getattr(estimate, "other_charges", None) or [])
            ],
            "taxable": float(estimate.taxable or 0),
            "gst": float(estimate.gst or 0),
            "gst_pct": f"{float(getattr(estimate, 'gst_pct', None) or 18):g}",
            "grand_total": int(estimate.grand_total or 0),
            "advance_pct": float(estimate.advance_pct or 0),
            "advance_amount": int(estimate.advance_amount or 0),
        },
        company={
            "name": getattr(company, "name", None) or "SteelCAD",
            "logo_data_url": getattr(company, "logo_data_url", None),
            "address": getattr(company, "address", None) or "",
            "phone": getattr(company, "phone", None) or "",
            "email": getattr(company, "email", None) or "",
            "gstin": getattr(company, "gstin", None) or "",
            "bank_details": getattr(company, "bank_details", None) or "",
        },
        customer={
            "name": customer.name,
            "company": customer.company or "",
            "phone": customer.phone or "",
            "email": customer.email or "",
            "address": customer.address or "",
            "gstin": customer.gstin or "",
        },
        frames=frames,
        bom=build_bom(frames),
        currency=getattr(company, "currency_symbol", None) or "₹",
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC"),
    )


def generate_estimate_pdf(estimate, company=None) -> bytes:
    """
    Render an Estimate (ORM object, with .customer and .frames loaded) to PDF bytes.
    `company` is the CompanySettings row used for letterhead/branding.
    """
    from weasyprint import HTML
    html_content = render_estimate_html(estimate, company)
    return HTML(string=html_content, url_fetcher=_data_only_url_fetcher).write_pdf()


# ─── Customer-facing quotation (summary PDF) ────────────────────────
#
# A second, deliberately separate render path: per-frame cards (diagram +
# specs + qty × unit price) with no component costs and no BOM. The detailed
# document above is the internal cross-checking copy and must stay untouched,
# so nothing below is shared with it beyond the small formatting helpers.

_REGION_TYPE_LABELS = {
    "shutter": "shutter",
    "fixed": "fixed pane",
    "door": "door",
    "louver": "louver",
}


def _tree_has_glass(tree: dict) -> bool:
    """True if any leaf carries glass — glass infill is ₹0 (no priced line
    item, spec §5.3), so the frozen tree is walked instead of the breakdown.
    A HINGES_ONLY shutter (§5.8) has no glass even when double."""
    def walk(region):
        if not region:
            return False
        ps = region.get("paneSpec") or {}
        if ps.get("shutterMaterial") != "HINGES_ONLY" and (
                ps.get("infillType") == "glass" or ps.get("shutterConfig") == "double"):
            return True
        return any(walk(c) for c in (region.get("split") or {}).get("children", []))
    return walk(((tree or {}).get("frame") or {}).get("rootRegion"))


def _tree_has_customer_shutter(tree: dict) -> bool:
    """True if any leaf is a HINGES_ONLY (customer-supplied) shutter — §5.8. It
    has no priced pane line item, so the frozen tree is walked."""
    def walk(region):
        if not region:
            return False
        ps = region.get("paneSpec") or {}
        if region.get("regionType") == "shutter" and ps.get("shutterMaterial") == "HINGES_ONLY":
            return True
        return any(walk(c) for c in (region.get("split") or {}).get("children", []))
    return walk(((tree or {}).get("frame") or {}).get("rootRegion"))


def _spec_summary(breakdown: dict, tree: dict) -> str:
    """
    One price-free specification line per frame for the customer PDF, e.g.
    "shutter, fixed pane · Shutter pane (MS Pipe), Glass, Beading · 3 × Hinge (SS 12G)".

    Built from the frozen unit_breakdown *labels* only — item descriptions
    embed ₹ rates (e.g. "24 RFT × ₹40/RFT") and must never reach the customer.
    """
    regions = (breakdown or {}).get("regions") or []

    # Composition: counts of occupied leaf regions ("2 shutters, fixed pane").
    type_counts: dict[str, int] = {}
    for r in regions:
        label = _REGION_TYPE_LABELS.get((r.get("region_type") or "").lower())
        if label:
            type_counts[label] = type_counts.get(label, 0) + 1
    composition = [f"{n} {label}s" if n > 1 else label for label, n in type_counts.items()]

    # Materials: pane structure / infill / beading / grill labels, deduped in order.
    materials: list[str] = []

    def add(item):
        if item and item.get("label") and item["label"] not in materials:
            materials.append(item["label"])

    for r in regions:
        add(r.get("pane_structure"))
        add(r.get("pane_structure_2"))
    if _tree_has_customer_shutter(tree):
        materials.append("Shutter by customer (hinges only)")
    if _tree_has_glass(tree):
        materials.append("Glass")
    for r in regions:
        add(r.get("infill"))
        add(r.get("beading"))
        add(r.get("grill"))

    # Hardware with quantities aggregated across regions: "4 × Hinge (SS 12G)".
    hw_counts: dict[str, float] = {}
    for r in regions:
        for hw in r.get("hardware") or []:
            if hw.get("label"):
                hw_counts[hw["label"]] = hw_counts.get(hw["label"], 0) + (hw.get("quantity") or 0)
    hardware = [f"{int(q)} × {label}" if q else label for label, q in hw_counts.items()]

    return "  ·  ".join(", ".join(g) for g in (composition, materials, hardware) if g)


def render_customer_estimate_html(estimate, company=None) -> str:
    """Render the customer-facing quotation HTML (factored out for tests)."""
    template = _build_env().get_template("estimate_customer_pdf.html")

    customer = estimate.customer
    frames = []
    for f in estimate.frames:
        frames.append({
            "name": f.name,
            "dimensions": f"{fmt_ft_in(f.outer_width)} × {fmt_ft_in(f.outer_height)}",
            "section": f'{f.section_size}" {f.gauge}',
            "quantity": f.quantity,
            "unit_subtotal": float(f.unit_subtotal or 0),
            "line_total": float(f.line_total or 0),
            "spec": _spec_summary(f.unit_breakdown, f.tree_json),
            "diagram_svg": tree_to_svg(f.tree_json or {}),
        })

    company = company or type("Co", (), {})()
    return template.render(
        # Same commercial fields as the internal document, minus workflow
        # status (draft/sent is internal) and minus any per-component costs.
        estimate={
            "number": estimate.number,
            "revision": getattr(estimate, "revision", 1) or 1,
            "title": estimate.title or "",
            "notes": estimate.notes or "",
            "terms": estimate.terms or getattr(company, "default_terms", None) or "",
            "quote_date": _fmt_date(getattr(estimate, "quote_date", None)) or _fmt_date(estimate.created_at),
            "valid_until": _fmt_date(getattr(estimate, "valid_until", None)),
            "discount_type": estimate.discount_type,
            # Percentages pre-formatted "%g" style ("5", not "5.0") — customer-facing polish.
            "discount_value": f"{float(estimate.discount_value or 0):g}",
            "discount_amount": float(estimate.discount_amount or 0),
            "subtotal": float(estimate.subtotal or 0),
            "other_charges": [
                {"label": c.get("label", ""), "amount": float(c.get("amount", 0) or 0)}
                for c in (getattr(estimate, "other_charges", None) or [])
            ],
            "taxable": float(estimate.taxable or 0),
            "gst": float(estimate.gst or 0),
            "gst_pct": f"{float(getattr(estimate, 'gst_pct', None) or 18):g}",
            "grand_total": int(estimate.grand_total or 0),
            "advance_pct": f"{float(estimate.advance_pct or 0):g}",
            "advance_amount": int(estimate.advance_amount or 0),
        },
        company={
            "name": getattr(company, "name", None) or "SteelCAD",
            "logo_data_url": getattr(company, "logo_data_url", None),
            "address": getattr(company, "address", None) or "",
            "phone": getattr(company, "phone", None) or "",
            "email": getattr(company, "email", None) or "",
            "gstin": getattr(company, "gstin", None) or "",
            "bank_details": getattr(company, "bank_details", None) or "",
        },
        customer={
            "name": customer.name,
            "company": customer.company or "",
            "phone": customer.phone or "",
            "email": customer.email or "",
            "address": customer.address or "",
            "gstin": customer.gstin or "",
        },
        frames=frames,
        currency=getattr(company, "currency_symbol", None) or "₹",
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC"),
    )


def generate_customer_estimate_pdf(estimate, company=None) -> bytes:
    """Render the customer-facing summary quotation to PDF bytes."""
    from weasyprint import HTML
    return HTML(
        string=render_customer_estimate_html(estimate, company),
        url_fetcher=_data_only_url_fetcher,
    ).write_pdf()
