"""
PDF generation — renders a multi-frame estimate as a professional quotation
PDF using WeasyPrint.
"""
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _fmt(value: float) -> str:
    """Format a number as Indian-grouped currency string (no symbol)."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def generate_estimate_pdf(estimate) -> bytes:
    """
    Render an Estimate (ORM object, with .customer and .frames loaded) to PDF bytes.
    """
    from weasyprint import HTML

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.filters["money"] = _fmt
    template = env.get_template("estimate_pdf.html")

    customer = estimate.customer
    frames = [
        {
            "name": f.name,
            "dimensions": f"{float(f.outer_width)}ft × {float(f.outer_height)}ft",
            "section": f'{f.section_size}" {f.gauge}',
            "quantity": f.quantity,
            "unit_subtotal": float(f.unit_subtotal or 0),
            "line_total": float(f.line_total or 0),
            "breakdown": f.unit_breakdown or {},
        }
        for f in estimate.frames
    ]

    html_content = template.render(
        estimate={
            "number": estimate.number,
            "title": estimate.title or "",
            "notes": estimate.notes or "",
            "status": estimate.status,
            "discount_type": estimate.discount_type,
            "discount_value": float(estimate.discount_value or 0),
            "discount_amount": float(estimate.discount_amount or 0),
            "subtotal": float(estimate.subtotal or 0),
            "taxable": float(estimate.taxable or 0),
            "gst": float(estimate.gst or 0),
            "grand_total": int(estimate.grand_total or 0),
            "advance_pct": float(estimate.advance_pct or 0),
            "advance_amount": int(estimate.advance_amount or 0),
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
        created_at=estimate.created_at.strftime("%d %b %Y") if estimate.created_at else "",
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC"),
    )

    return HTML(string=html_content).write_pdf()
