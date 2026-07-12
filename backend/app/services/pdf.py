"""
PDF generation — renders a multi-frame estimate as a professional quotation
PDF using WeasyPrint.
"""
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.services.diagram import tree_to_svg
from app.services.bom import build_bom

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


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
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["money"] = _fmt
    template = env.get_template("estimate_pdf.html")

    customer = estimate.customer
    frames = []
    for f in estimate.frames:
        frames.append({
            "name": f.name,
            "dimensions": f"{float(f.outer_width)}ft × {float(f.outer_height)}ft",
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
    return HTML(string=html_content).write_pdf()
