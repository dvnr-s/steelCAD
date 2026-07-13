"""
Bill of materials — aggregate the per-frame pricing line items of an estimate into
a consolidated materials summary (section RFT, shutter material, glass/jali area,
grills, hardware counts). Pure grouping of existing pricing output; no new math.
"""
from collections import OrderedDict


def _iter_line_items(breakdown: dict):
    """Yield every priced line item (label, quantity, unit, cost) in a unit breakdown."""
    if not breakdown:
        return
    frame = breakdown.get("frame")
    if frame:
        yield frame
    for s in breakdown.get("splits", []):
        yield s
    for r in breakdown.get("regions", []):
        for key in ("pane_structure", "pane_structure_2", "infill", "beading", "grill"):
            if r.get(key):
                yield r[key]
        for hw in r.get("hardware", []):
            yield hw


def build_bom(frames: list[dict]) -> list[dict]:
    """
    Aggregate line items across all frames (× each frame's quantity) into rows
    keyed by (label, unit), summing quantity and cost.

    `frames` is the list rendered by pdf.render_estimate_html — each has
    `breakdown` and `quantity`.
    """
    rows: "OrderedDict[tuple, dict]" = OrderedDict()
    for f in frames:
        qty = f.get("quantity", 1) or 1
        for item in _iter_line_items(f.get("breakdown") or {}):
            key = (item.get("label", ""), item.get("unit", ""))
            row = rows.get(key)
            if row is None:
                row = {"label": key[0], "unit": key[1], "quantity": 0.0, "cost": 0.0}
                rows[key] = row
            row["quantity"] += (item.get("quantity", 0) or 0) * qty
            row["cost"] += (item.get("cost", 0) or 0) * qty

    out = []
    for row in rows.values():
        out.append({
            "label": row["label"],
            "unit": row["unit"],
            "quantity": round(row["quantity"], 2),
            "cost": round(row["cost"], 2),
        })
    return out
