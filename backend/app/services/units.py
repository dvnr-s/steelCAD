"""
Dimension display units — feet-and-inches formatting.

Mirrors frontend lib/format.js `fmtFtIn` exactly so dimensions read the same
on the canvas, the estimate builder, and the PDFs: 5.5 → 5'6", 5 → 5',
0.75 → 9". Geometry is grid-aligned to 0.25 ft so inches are always whole;
rounding to the nearest inch also absorbs float drift.
"""


def fmt_ft_in(value: float) -> str:
    """Format decimal feet as a feet-and-inches string (5.5 → 5'6\")."""
    total_in = round(float(value) * 12)
    ft, inch = divmod(total_in, 12)
    if ft == 0 and inch != 0:
        return f'{inch}"'
    return f"{ft}'" if inch == 0 else f"{ft}'{inch}\""
