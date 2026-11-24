"""Phase 1 (SH3D parity): face-flush snapping and mixed-thickness wall joins."""
import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.geometry.wall_joins import (  # noqa: E402
    face_flush_offsets, wall_join_polygon)
from EstiSketch.snapping_manager import SnappingManager  # noqa: E402


def wall(start, end, width):
    return SimpleNamespace(start=start, end=end, width=width, is_curved=False)


# ── face_flush_offsets ──────────────────────────────────────────────────────

def test_offsets_equal_width_abut_and_center():
    offs = face_flush_offsets(6, 6)
    assert sorted(o for o, _, _ in offs) == [-6.0, 0.0, 6.0]
    assert {k for _, _, k in offs} == {"abut", "center"}


def test_offsets_different_width():
    offs = {(round(o, 3), k) for o, _, k in face_flush_offsets(8, 4.5)}
    assert offs == {(1.75, "flush"), (-1.75, "flush"),
                    (6.25, "abut"), (-6.25, "abut"),
                    (0.0, "center")}


# ── wall_join_polygon ───────────────────────────────────────────────────────

def test_join_polygon_right_angle_outer_corner():
    # a runs +x, b runs +y (left turn in y-up). Outer corner is at +x/-y.
    poly = wall_join_polygon((-100, 0), (0, 0), 8, (0, 0), (0, 100), 4)
    assert poly[0] == (0, 0)
    assert poly[1] == pytest.approx((0, -4))
    assert poly[2] == pytest.approx((2, -4))
    assert poly[3] == pytest.approx((2, 0))


def test_join_polygon_right_turn_mirrors():
    poly = wall_join_polygon((-100, 0), (0, 0), 8, (0, 0), (0, -100), 4)
    assert poly[2] == pytest.approx((2, 4))


def test_join_polygon_collinear_and_degenerate():
    assert wall_join_polygon((0, 0), (10, 0), 8, (10, 0), (20, 0), 4) is None
    assert wall_join_polygon((0, 0), (0, 0), 8, (0, 0), (0, 5), 4) is None


def test_join_polygon_miter_limit():
    # Near-reversal produces a huge miter; it should be rejected.
    ang = math.radians(2)
    end = (100 * math.cos(math.pi - ang), 100 * math.sin(math.pi - ang))
    assert wall_join_polygon((-100, 0), (0, 0), 8, (0, 0), end, 4) is None


# ── SnappingManager.snap_to_face_flush ──────────────────────────────────────

def test_snap_flush_same_side_for_thinner_wall():
    sm = SnappingManager(snap_threshold=4)
    ext = wall((0, 0), (200, 0), 8)  # faces at y = +/-4
    # Thin 4.5" wall continuing along the wall: centerline y=1.75 gives a flush face at y=4.
    pt, kind = sm.snap_to_face_flush(250, 2.5, 100, 2.5, [ext], 4.5)
    assert kind == "face_flush"
    assert pt[1] == pytest.approx(1.75)
    assert pt[0] == pytest.approx(250)


def test_snap_abut_alongside():
    sm = SnappingManager(snap_threshold=4)
    ext = wall((0, 0), (200, 0), 8)
    pt, kind = sm.snap_to_face_flush(120, 8, 20, 8, [ext], 4.5)
    assert kind == "face_flush"
    assert pt[1] == pytest.approx(6.25)


def test_snap_ignores_non_parallel_walls():
    sm = SnappingManager(snap_threshold=4)
    ext = wall((0, 0), (200, 0), 8)
    # New wall running vertically must not snap to an offset of a horizontal wall.
    _, kind = sm.snap_to_face_flush(100, 7, 100, -60, [ext], 4.5)
    assert kind == "none"


def test_snap_point_reports_guide_and_prefers_face():
    sm = SnappingManager(snap_threshold=4)
    ext = wall((0, 0), (200, 0), 8)
    pt, kind = sm.snap_point(120, 6.8, 20, 6.8, [ext], [],
                             new_wall_width=4.5)
    assert kind == "face_flush"
    assert pt[1] == pytest.approx(6.25)
    g0, g1, gk = sm.face_flush_guide
    assert gk == "abut"
    assert g0[1] == pytest.approx(4) and g1[1] == pytest.approx(4)

    sm.snap_point(500, 500, 20, 500, [ext], [], new_wall_width=4.5)
    assert sm.face_flush_guide is None
