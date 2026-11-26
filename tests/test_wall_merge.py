"""Headless tests for merging split walls and re-homing their openings."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from EstiSketch.geometry.wall_merge import (
    can_merge_walls,
    merge_walls,
    reassign_openings_after_split,
)


def _wall(start, end, width=6.0, h0=96.0, h1=96.0, curved=False):
    return SimpleNamespace(identifier=f"w{start}{end}", start=start, end=end, width=width,
                           height=h0, height_at_end=h1, is_curved=curved)


def test_can_merge_requirements() -> None:
    a, b = _wall((0, 0), (100, 0)), _wall((100, 0), (300, 0))
    assert can_merge_walls(a, b) and can_merge_walls(b, a)
    assert not can_merge_walls(a, _wall((100, 0), (100, 50)))
    assert not can_merge_walls(a, _wall((100, 0), (300, 0), width=8.0))
    assert not can_merge_walls(a, _wall((150, 0), (300, 0)))
    assert not can_merge_walls(a, _wall((100, 0), (300, 0), curved=True))


def test_merge_preserves_opening_positions() -> None:
    a, b = _wall((0, 0), (100, 0), h1=100.0), _wall((100, 0), (300, 0), h0=100.0, h1=110.0)
    door, window = object(), object()
    doors = [(a, door, 0.5)]      # x = 50
    windows = [(b, window, 0.25)]  # x = 150
    sets = [[a, b]]
    merged = merge_walls(a, b, sets, doors, windows)
    assert merged is a and sets == [[a]]
    assert (a.start, a.end) == ((0, 0), (300, 0))
    assert (a.height, a.height_at_end) == (96.0, 110.0)
    assert doors[0][0] is a and doors[0][2] == pytest.approx(50 / 300)
    assert windows[0][0] is a and windows[0][2] == pytest.approx(150 / 300)


def test_merge_works_when_selected_in_reverse_order() -> None:
    a, b = _wall((0, 0), (100, 0)), _wall((100, 0), (300, 0))
    windows = [(a, object(), 0.5)]
    merge_walls(b, a, [[a, b]], [], windows)
    assert (b.start, b.end) == ((0, 0), (300, 0))
    assert windows[0][0] is b and windows[0][2] == pytest.approx(50 / 300)


def test_merge_rejects_non_collinear() -> None:
    with pytest.raises(ValueError):
        merge_walls(_wall((0, 0), (10, 0)), _wall((10, 0), (10, 10)), [], [], [])


def test_split_reassigns_openings_to_halves() -> None:
    orig = _wall((0, 0), (200, 0))
    w1, w2 = _wall((0, 0), (100, 0)), _wall((100, 0), (200, 0))
    d1, d2 = object(), object()
    doors = [(orig, d1, 0.25), (orig, d2, 0.75)]
    reassign_openings_after_split(orig, w1, w2, doors, [])
    assert doors[0][0] is w1 and doors[0][2] == pytest.approx(0.5)
    assert doors[1][0] is w2 and doors[1][2] == pytest.approx(0.5)
