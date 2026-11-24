import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.Canvas.winder_geometry import (  # noqa: E402
    winder_treads, polygon_area, MAX_WINDERS)


@pytest.mark.parametrize("n", range(1, MAX_WINDERS + 1))
@pytest.mark.parametrize("turn", ["left", "right"])
def test_wedges_tile_square(n, turn):
    w = 36.0
    polys = winder_treads(w, n, turn)
    assert len(polys) == n
    assert sum(polygon_area(p) for p in polys) == pytest.approx(w * w)
    for p in polys:
        for u, v in p:
            assert -1e-9 <= u <= w + 1e-9
            assert -1e-9 <= v <= w + 1e-9


def test_zero_winders():
    assert winder_treads(36.0, 0) == []


def test_left_pivot_and_right_mirror():
    left = winder_treads(36.0, 3, "left")
    right = winder_treads(36.0, 3, "right")
    assert all(p[0] == (0.0, 0.0) for p in left)
    assert all(p[0] == (0.0, 36.0) for p in right)


def test_three_winders_equal_angles():
    # 3 winders -> 30 degrees each around the pivot
    polys = winder_treads(36.0, 3, "left")
    angles = []
    for p in polys:
        a1 = math.atan2(p[1][1], p[1][0])
        a2 = math.atan2(p[-1][1], p[-1][0])
        angles.append(abs(a1 - a2))
    assert all(a == pytest.approx(math.pi / 6) for a in angles)


def test_first_winder_touches_entry_edge():
    polys = winder_treads(36.0, 3, "left")
    # entry edge is u=0; the first wedge has its 2nd vertex at (0, width)
    assert polys[0][1][0] == pytest.approx(0.0, abs=1e-9)
    assert polys[0][1][1] == pytest.approx(36.0)
