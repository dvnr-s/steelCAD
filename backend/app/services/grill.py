"""
SS grill bar math — the single source of truth for how many bars a grilled
region carries and where they sit (spec §6.2 / §6.2A).

Mirrors frontend/src/lib/grill.js exactly: pricing, validation and the PDF
diagram all read the same numbers, so the bars drawn are always the bars billed.
"""
import math


def _round_half_up(x: float) -> int:
    """Round-half-up — matches JS Math.round for positive values."""
    return math.floor(x + 0.5)


def ss_grill_auto_bars(height_ft: float) -> int:
    """Auto bar count from the spec formula: max(0, round((2 × h) − 2))."""
    return max(0, _round_half_up(2 * height_ft - 2))


def ss_grill_bar_count(height_ft: float, bar_adjust: int = 0) -> int:
    """Effective (billed = drawn) count: auto + manual delta (§6.2A)."""
    return max(0, ss_grill_auto_bars(height_ft) + (bar_adjust or 0))


def ss_grill_max_bars(height_ft: float) -> int:
    """Most bars a region can hold at the 2-inch pitch limit (V-20)."""
    return math.floor(height_ft * 6)


def grill_bar_adjust(overlay: dict) -> int:
    """The barAdjust delta stored on a grill overlay node (0 when unset)."""
    config = overlay.get("config") or {}
    try:
        return int(config.get("barAdjust") or 0)
    except (TypeError, ValueError):
        return 0


def ss_grill_bar_offsets(height_ft: float, bar_adjust: int = 0) -> list[float]:
    """
    Y offsets (feet from the region top) where bars are drawn (spec §6.2
    rendering rule): the billed bars distributed evenly across the region's
    full height — gap = h / (bars + 1) — so the pattern always fills the
    region with equal spacing, whatever the count.
    """
    bars = ss_grill_bar_count(height_ft, bar_adjust)
    if bars <= 0:
        return []
    gap = height_ft / (bars + 1)
    return [gap * (i + 1) for i in range(bars)]
