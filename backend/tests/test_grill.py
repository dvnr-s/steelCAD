"""
SS grill bar math (services/grill.py) — pure unit tests, no DB required.

This module is the backend mirror of frontend/src/lib/grill.js; these tests pin
the shared behavior (spec §6.2 / §6.2A): whole-bar counts, the manual delta,
and even distribution of the billed bars across the region height.
"""
import pytest

from app.services.grill import (
    grill_bar_adjust,
    ss_grill_auto_bars,
    ss_grill_bar_count,
    ss_grill_bar_offsets,
    ss_grill_max_bars,
)


@pytest.mark.parametrize("height,expected", [
    (1.0, 0),     # too short to earn a bar
    (0.5, 0),     # never negative
    (1.25, 1),    # 0.5 rounds half-up to 1
    (2.5, 3),
    (2.95, 4),    # 3.9 → 4 (whole bars)
    (2.25, 3),    # 2.5 rounds half-up to 3 (matches JS Math.round)
    (5.0, 8),     # spec §6.2 example 1
    (7.5, 13),
])
def test_auto_bar_count(height, expected):
    assert ss_grill_auto_bars(height) == expected


def test_bar_count_applies_delta_and_floors_at_zero():
    assert ss_grill_bar_count(5.0, 2) == 10
    assert ss_grill_bar_count(5.0, -3) == 5
    assert ss_grill_bar_count(5.0, -20) == 0   # clamped, validation rejects earlier


def test_max_bars_is_one_per_two_inches():
    assert ss_grill_max_bars(5.0) == 30
    assert ss_grill_max_bars(2.5) == 15


def test_bar_adjust_reads_overlay_config():
    assert grill_bar_adjust({"config": {"barAdjust": 2}}) == 2
    assert grill_bar_adjust({"config": {}}) == 0
    assert grill_bar_adjust({}) == 0
    assert grill_bar_adjust({"config": {"barAdjust": "junk"}}) == 0


def test_offsets_spread_bars_evenly_across_the_region():
    """§6.2 rendering rule: gap = h / (bars + 1), bars fill the whole height."""
    assert ss_grill_bar_offsets(2.5) == pytest.approx([0.625, 1.25, 1.875])
    tall = ss_grill_bar_offsets(7.5)   # 13 bars
    assert len(tall) == 13
    gap = 7.5 / 14
    assert tall[0] == pytest.approx(gap)          # same gap above the first bar…
    assert tall[-1] == pytest.approx(7.5 - gap)   # …and below the last
    for a, b in zip(tall, tall[1:]):
        assert b - a == pytest.approx(gap)        # equal spacing throughout


def test_offsets_single_bar_is_centered():
    assert ss_grill_bar_offsets(1.25) == [0.625]


def test_offsets_empty_when_no_bars():
    assert ss_grill_bar_offsets(1.0) == []


def test_offsets_respace_automatically_for_adjusted_counts():
    """A manual delta just re-spaces the even distribution — no fixed margins."""
    offsets = ss_grill_bar_offsets(7.5, 2)   # 13 auto + 2 = 15 bars
    assert len(offsets) == 15
    gap = 7.5 / 16
    assert offsets[0] == pytest.approx(gap)
    assert offsets[-1] == pytest.approx(7.5 - gap)
