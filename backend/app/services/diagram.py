"""
Server-side schematic SVG of a design tree.

Renders the quotation-PDF diagram for *every* frame (deterministic, dependency-free)
so all frames look identical — it mirrors the editor canvas's static render
(FramePreview.jsx / canvasDraw.jsx): region tints, dimension labels, door-swing
symbol, grill overlays, void hatch and the in-concrete ground band.
"""
from xml.sax.saxutils import escape

# Region tints — match canvasDraw.regionFill/regionStroke (fill is faint, like the editor).
_FILL = {
    "shutter": ("#f59e0b", 0.08), "door": ("#ef4444", 0.08), "fixed": ("#22c55e", 0.06),
    "louver": ("#8b5cf6", 0.08), "open": ("#3b82f6", 0.04),
}
_STROKE = {
    "shutter": "#f59e0b", "door": "#ef4444", "fixed": "#22c55e",
    "louver": "#8b5cf6", "open": "#30363d",
}


def _collect(region, regions, splits):
    """Mirror canvasDraw.collect: gather leaf regions + split descriptors."""
    if region.get("isLeaf"):
        regions.append(region)
        return
    split = region.get("split")
    if not split:
        regions.append(region)
        return
    splits.append({
        "direction": split.get("direction"),
        "position": split.get("position", 0.5),
        "x": region.get("x", 0), "y": region.get("y", 0),
        "w": region["width"], "h": region["height"],
    })
    # A branch can itself carry a grill overlay spanning its children.
    if region.get("overlays"):
        regions.append({**region, "_branchWithGrill": True})
    for child in split.get("children", []):
        _collect(child, regions, splits)


def _fmt_ft(n) -> str:
    """Round drift and drop trailing zeros (matches lib/format.fmtFt)."""
    v = round(float(n) * 100) / 100
    return f"{v:g}"


def tree_to_svg(tree: dict, width: int = 360, height: int = 270) -> str:
    """Render a design tree as a detailed schematic SVG string."""
    frame = tree.get("frame") or {}
    W = frame.get("width") or tree.get("outerWidth") or 1
    H = frame.get("height") or tree.get("outerHeight") or 1
    root = frame.get("rootRegion")

    pad = 28
    # fit, capped at true-size (60 px/ft) and floored (8 px/ft) — matches fitScale.
    scale = max(8.0, min(60.0, (width - 2 * pad) / W, (height - 2 * pad) / H))
    tx = (width - W * scale) / 2
    ty = (height - H * scale) / 2

    def fx(ft):
        return round(tx + ft * scale, 1)

    def fy(ft):
        return round(ty + ft * scale, 1)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
    ]

    # Frame background + outline.
    parts.append(
        f'<rect x="{fx(0)}" y="{fy(0)}" width="{round(W * scale, 1)}" '
        f'height="{round(H * scale, 1)}" fill="#ffffff" stroke="#3b82f6" stroke-width="3"/>'
    )

    # In-concrete ground band for door frames.
    if tree.get("productType") == "door":
        x0, x1, yb = fx(0), fx(W), fy(H)
        parts.append(f'<line x1="{x0}" y1="{yb}" x2="{x1}" y2="{yb}" stroke="#8b7c6c" stroke-width="3"/>')
        gx = x0
        while gx < x1:
            parts.append(
                f'<line x1="{round(gx, 1)}" y1="{yb}" x2="{round(gx + 8, 1)}" y2="{round(yb + 8, 1)}" '
                f'stroke="#8b7c6c" stroke-opacity="0.55" stroke-width="1"/>'
            )
            gx += 12

    if root:
        regions, splits = [], []
        _collect(root, regions, splits)

        for region in regions:
            is_leaf = bool(region.get("isLeaf"))
            rt = region.get("regionType") or "open"
            rx, ry = fx(region.get("x", 0)), fy(region.get("y", 0))
            rw = round(region["width"] * scale, 1)
            rh = round(region["height"] * scale, 1)
            fill_c, fill_o = _FILL.get(rt, _FILL["open"])
            stroke_c = _STROKE.get(rt, _STROKE["open"])

            parts.append(
                f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" fill="{fill_c}" '
                f'fill-opacity="{fill_o}" stroke="{stroke_c}" stroke-width="1"/>'
            )

            # Region-type tag (top-left).
            if is_leaf and rt != "open":
                parts.append(
                    f'<text x="{rx + 4}" y="{ry + 13}" font-size="9" fill="{stroke_c}" '
                    f'fill-opacity="0.75" font-family="monospace">{escape(rt.upper())}</text>'
                )

            # Dimension label (height×width), centered, when the region is big enough.
            if rw > 40 and rh > 24:
                label = f'{_fmt_ft(region["height"])}×{_fmt_ft(region["width"])}'
                parts.append(
                    f'<text x="{round(rx + rw / 2, 1)}" y="{round(ry + rh / 2 + 3, 1)}" '
                    f'font-size="10" fill="#6b7280" font-family="monospace" '
                    f'text-anchor="middle">{escape(label)}</text>'
                )

            # Grill overlay.
            overlays = region.get("overlays") or []
            if overlays:
                parts.extend(_grill_svg(overlays[0].get("material"), rx, ry, rw, rh, region["height"]))

            # Void hatch for intentional open regions.
            if is_leaf and rt == "open":
                parts.extend(_void_hatch_svg(rx, ry, rw, rh))

            # Door swing symbol.
            if is_leaf and rt == "door":
                parts.append(_door_swing_svg(region, rx, ry, rw, rh))

        # Mullion / transom bars on top.
        for s in splits:
            vertical = s["direction"] == "vertical"
            if vertical:
                cx = fx(s["x"] + s["w"] * s["position"])
                p = f'{cx},{fy(s["y"])} {cx},{fy(s["y"] + s["h"])}'
            else:
                cy = fy(s["y"] + s["h"] * s["position"])
                p = f'{fx(s["x"])},{cy} {fx(s["x"] + s["w"])},{cy}'
            parts.append(f'<polyline points="{p}" fill="none" stroke="#6b7280" stroke-width="3"/>')

    parts.append("</svg>")
    return "".join(parts)


def _door_swing_svg(region, x, y, w, h) -> str:
    """Triangle whose apex sits on the hinge edge (matches canvasDraw.DoorSwing)."""
    hinge_left = (region.get("doorHand") or "left") != "right"
    apex_x = x if hinge_left else x + w
    latch_x = x + w if hinge_left else x
    pts = f'{latch_x},{round(y + 4, 1)} {apex_x},{round(y + h / 2, 1)} {latch_x},{round(y + h - 4, 1)}'
    return (
        f'<polyline points="{pts}" fill="none" stroke="#ef4444" '
        f'stroke-opacity="0.55" stroke-width="1.25"/>'
    )


def _void_hatch_svg(x, y, w, h) -> list[str]:
    """Faint diagonal hatch (matches canvasDraw.VoidHatch)."""
    out, step, off = [], 12, 12
    while off < w + h:
        x1, y1, x2, y2 = x + off, y, x, y + off
        if x1 > x + w:
            y1 = y + (x1 - (x + w))
            x1 = x + w
        if y2 > y + h:
            x2 = x + (y2 - (y + h))
            y2 = y + h
        out.append(
            f'<line x1="{round(x1, 1)}" y1="{round(y1, 1)}" x2="{round(x2, 1)}" y2="{round(y2, 1)}" '
            f'stroke="#939ca8" stroke-opacity="0.16" stroke-width="1"/>'
        )
        off += step
    return out


def _grill_svg(material, x, y, w, h, region_h_ft) -> list[str]:
    """Grill pattern (matches canvasDraw.GrillOverlay)."""
    out = []
    if material == "MS_SQUARE":
        step = 8
        i = step
        while i < w:
            out.append(
                f'<line x1="{round(x + i, 1)}" y1="{y}" x2="{round(x + i, 1)}" y2="{round(y + h, 1)}" '
                f'stroke="#f59e0b" stroke-opacity="0.25" stroke-width="0.5"/>'
            )
            i += step
        i = step
        while i < h:
            out.append(
                f'<line x1="{x}" y1="{round(y + i, 1)}" x2="{round(x + w, 1)}" y2="{round(y + i, 1)}" '
                f'stroke="#f59e0b" stroke-opacity="0.25" stroke-width="0.5"/>'
            )
            i += step
        return out

    # Horizontal bars (SS pipe / jali).
    bars = max(1, int(2 * region_h_ft - 2 + 0.5))
    gap = h / (bars + 1)
    for k in range(1, bars + 1):
        ly = round(y + gap * k, 1)
        out.append(
            f'<line x1="{round(x + 2, 1)}" y1="{ly}" x2="{round(x + w - 2, 1)}" y2="{ly}" '
            f'stroke="#93c5fd" stroke-opacity="0.5" stroke-width="1.5"/>'
        )
    return out
