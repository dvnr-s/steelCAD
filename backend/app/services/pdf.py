"""
PDF generation service — renders estimate breakdown as a professional PDF using WeasyPrint.
"""
import io
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def generate_estimate_pdf(
    design_name: str,
    design_dims: str,
    section_info: str,
    breakdown: dict,
    rate_snapshot: dict,
    version_number: int,
    created_at: datetime,
) -> bytes:
    """
    Render the estimate breakdown as a styled PDF.

    Returns raw PDF bytes.
    """
    # Import WeasyPrint here so the module can be imported even if WeasyPrint is not installed
    # (useful for tests that don't need PDF functionality)
    from weasyprint import HTML

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("estimate_pdf.html")

    html_content = template.render(
        design_name=design_name,
        design_dims=design_dims,
        section_info=section_info,
        breakdown=breakdown,
        rate_snapshot=rate_snapshot,
        version_number=version_number,
        created_at=(
            created_at.strftime("%d %b %Y, %I:%M %p")
            if created_at
            else ""
        ),
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC"),
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes
