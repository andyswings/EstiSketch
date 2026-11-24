import math
import os
import sys
from types import SimpleNamespace

import cairo
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.Canvas.door_window_renderer import (  # noqa: E402
    draw_doors,
    draw_windows,
    get_point_on_wall,
    get_wall_direction,
)
from EstiSketch.Canvas.wall_room_renderer import draw_walls  # noqa: E402
from EstiSketch.components import Door, Wall, Window  # noqa: E402
from EstiSketch.geometry.arc_wall import (  # noqa: E402
    angle_in_arc,
    arc_arc_intersections,
    arc_opening_cutout,
    arc_wall_face_radii,
    arc_wall_length,
    arc_wall_params,
    arc_wall_point,
    arc_wall_project,
    arc_wall_tangent,
    line_arc_intersections,
    tangent_continuation_snap,
    tangent_points_from_point,
)
from EstiSketch.snapping_manager import SnappingManager  # noqa: E402


def _curved_wall(cx=0.0, cy=0.0, radius=100.0, a0_deg=0.0, a1_deg=90.0, width=6.0):
    a0 = math.radians(a0_deg)
    a1 = math.radians(a1_deg)
    start = (cx + radius * math.cos(a0), cy + radius * math.sin(a0))
    end = (cx + radius * math.cos(a1), cy + radius * math.sin(a1))
    return Wall(
        start,
        end,
        width=width,
        height=96.0,
        is_curved=True,
        arc_center=(cx, cy),
        arc_radius=radius,
    )


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    c = CanvasArea(cfg)
    c.set_size_request(800, 600)
    return c


def test_arc_wall_geometry_ccw_cw_and_wrap():
    # CCW quarter circle 0 -> 90 deg around origin, R=100
    w_ccw = _curved_wall(0, 0, 100.0, 0.0, 90.0, width=8.0)
    params = arc_wall_params(w_ccw)
    assert params is not None
    assert params[4] == pytest.approx(math.pi / 2.0)
    assert arc_wall_length(w_ccw) == pytest.approx(50.0 * math.pi)

    mid = arc_wall_point(w_ccw, 0.5)
    assert mid[0] == pytest.approx(100.0 * math.cos(math.pi / 4.0))
    assert mid[1] == pytest.approx(100.0 * math.sin(math.pi / 4.0))

    # Tangent at ratio 0 (east) for CCW arc points south (+Y in Cairo coords)
    t0 = arc_wall_tangent(w_ccw, 0.0)
    assert t0[0] == pytest.approx(0.0, abs=1e-6)
    assert t0[1] == pytest.approx(1.0, abs=1e-6)

    # Left normal at ratio 0 points inward (-X) for CCW
    r_left, r_right = arc_wall_face_radii(w_ccw)
    assert r_left == pytest.approx(96.0)
    assert r_right == pytest.approx(104.0)

    # CW quarter circle crossing 0/2pi seam: +30 deg -> -60 deg
    w_cw = _curved_wall(0, 0, 100.0, 30.0, -60.0, width=6.0)
    _, _, _, s_ang, span = arc_wall_params(w_cw)
    assert span == pytest.approx(-math.pi / 2.0)
    assert angle_in_arc(math.radians(-15.0), s_ang, span) is True
    assert angle_in_arc(math.radians(90.0), s_ang, span) is False

    # Projection onto CW arc at -15 deg (midpoint -> ratio 0.5)
    ratio, dist, closest = arc_wall_project(w_cw, (110.0 * math.cos(math.radians(-15.0)), 110.0 * math.sin(math.radians(-15.0))))
    assert ratio == pytest.approx(0.5, abs=1e-4)
    assert dist == pytest.approx(10.0, abs=1e-4)
    assert math.hypot(closest[0], closest[1]) == pytest.approx(100.0, abs=1e-4)


def test_snapping_manager_arc_midpoints_edges_intersections_and_tangents():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    sm = SnappingManager(snap_enabled=True, snap_threshold=4.0, config=cfg)

    w_arc = _curved_wall(0.0, 0.0, 100.0, 0.0, 90.0, width=8.0)

    # 1. True arc midpoint (at 45 deg, ~70.71, 70.71) vs chord midpoint (50, 50)
    arc_mid = arc_wall_point(w_arc, 0.5)
    pt, stype = sm.snap_point(arc_mid[0] + 1.5, arc_mid[1] - 1.0, -100.0, 0.0, [w_arc], [])
    assert stype == "midpoint"
    assert pt == pytest.approx(arc_mid, abs=1e-5)

    # Chord midpoint (50, 50) must NOT snap as a midpoint of the curved wall
    _, chord_stype = sm.snap_point(50.0, 50.0, 50.0, 50.0, [w_arc], [])
    assert chord_stype != "midpoint"

    # 2. Concentric outer wall edge (radius = 104 at 60 deg)
    ang60 = math.radians(60.0)
    qx, qy = 105.0 * math.cos(ang60), 105.0 * math.sin(ang60)
    ept, etype = sm.snap_point(qx, qy, 0.0, 200.0, [w_arc], [])
    assert etype == "wall_edge"
    assert math.hypot(ept[0], ept[1]) == pytest.approx(104.0, abs=1e-5)

    # 3. Concentric centerline (radius = 100 at 30 deg)
    ang30 = math.radians(30.0)
    cpt, ctype = sm.snap_point(99.0 * math.cos(ang30), 99.0 * math.sin(ang30), 200.0, 200.0, [w_arc], [])
    assert ctype == "wall_centerline"
    assert math.hypot(cpt[0], cpt[1]) == pytest.approx(100.0, abs=1e-5)

    # 4. External point tangent-to-arc snap + geometric orthogonality (T - C) . (T - base) == 0
    base = (200.0, 0.0)
    tpts = tangent_points_from_point(base, w_arc, include_faces=False)
    assert len(tpts) == 1
    texpected = tpts[0][0]
    tpt, ttype = sm.snap_point(texpected[0] + 1.2, texpected[1] + 0.8, base[0], base[1], [w_arc], [])
    assert ttype == "tangent"
    assert tpt == pytest.approx(texpected, abs=1e-4)
    assert sm.tangent_guide is not None and sm.tangent_guide[2] == "tangent_point"
    dot_ortho = texpected[0] * (texpected[0] - base[0]) + texpected[1] * (texpected[1] - base[1])
    assert abs(dot_ortho) < 1e-6

    # 5. Tangent continuation snap extending off curved wall endpoint (0, 100)
    # At angle=90 deg (end of CCW arc), tangent vector points (-1, 0) (west)
    end_pt = w_arc.end  # (0, 100)
    cont_pt, cont_type = sm.snap_point(-80.0, 101.5, end_pt[0], end_pt[1], [w_arc], [], last_wall=w_arc)
    assert cont_type == "tangent"
    assert cont_pt == pytest.approx((-80.0, 100.0), abs=1e-4)
    assert sm.tangent_guide[2] == "tangent_continue"

    # 6. Perpendicular snap off curved wall endpoint follows radial direction (0, +1 -> 90 deg from tangent (-1, 0))
    perp_pt, perp_type = sm.snap_to_perpendicular(2.0, 180.0, end_pt[0], end_pt[1], last_wall=w_arc)
    assert perp_type == "perpendicular"
    assert perp_pt[0] == pytest.approx(0.0, abs=1e-4)
    assert perp_pt[1] == pytest.approx(100.0 + math.hypot(2.0, 80.0), abs=1e-4)

    # 7. Straight-arc and arc-arc intersections
    w_straight = Wall((20.0, -20.0), (20.0, 150.0), width=6.0, height=96.0)
    inter_la = line_arc_intersections(w_straight.start, w_straight.end, w_arc)
    assert len(inter_la) == 1
    assert inter_la[0][0] == pytest.approx(20.0)
    assert inter_la[0][1] == pytest.approx(math.sqrt(100.0**2 - 20.0**2))

    w_arc2 = _curved_wall(100.0, 0.0, 100.0, 90.0, 180.0)
    inter_aa = arc_arc_intersections(w_arc, w_arc2)
    assert len(inter_aa) == 1
    assert inter_aa[0] == pytest.approx((50.0, math.sqrt(100.0**2 - 50.0**2)), abs=1e-4)
    assert len(sm.find_intersections([w_arc, w_straight, w_arc2])) >= 2


def test_locate_and_drag_door_on_cw_and_ccw_curved_walls():
    c = _make_canvas()
    c.config.PIXELS_PER_INCH = 1.0
    c.zoom = 1.0
    c.offset_x = 0.0
    c.offset_y = 0.0

    # CW arc wall crossing 0 deg: +45 deg to -45 deg at radius 120
    w_cw = _curved_wall(200.0, 200.0, 120.0, 45.0, -45.0, width=6.0)
    w_cw.layer_id = c.active_layer_id
    c.wall_sets.append([w_cw])

    # Midpoint of CW arc is at (200 + 120, 200) = (320, 200)
    res = c._locate_on_wall(320.0, 200.0, opening_width=36.0)
    assert res is not None
    found_wall, ratio = res
    assert found_wall is w_cw
    assert ratio == pytest.approx(0.5, abs=1e-4)

    # Near start should clamp by opening_width / 2 along arc length (not hang past end)
    start_res = c._locate_on_wall(w_cw.start[0], w_cw.start[1], opening_width=36.0)
    expected_min_ratio = (36.0 / 2.0) / arc_wall_length(w_cw)
    assert start_res[1] == pytest.approx(expected_min_ratio, abs=1e-4)

    # Dragging door along CW curved wall updates ratio along arc accurately
    door = Door("single", 36.0, 80.0, "left", "inswing", layer_id=c.active_layer_id)
    door_tuple = (w_cw, door, 0.5)
    c.doors.append(door_tuple)
    c.selected_items = [{"type": "door", "object": door_tuple}]
    c.dragging_door_window = {"type": "door", "object": door_tuple}
    c.drag_start_x = 320.0
    c.drag_start_y = 200.0
    c.drag_offset_x = 0.0
    c.drag_offset_y = 0.0

    # Target -22.5 deg (ratio = 0.75 on 45 -> -45 arc)
    ang_tgt = math.radians(-22.5)
    tx = 200.0 + 120.0 * math.cos(ang_tgt)
    ty = 200.0 + 120.0 * math.sin(ang_tgt)
    c.on_drag_update(None, tx - 320.0, ty - 200.0)
    assert c.doors[0][0] is w_cw
    assert c.doors[0][2] == pytest.approx(0.75, abs=1e-3)


def test_curved_wall_tangent_cutout_and_cairo_render():
    w = _curved_wall(200.0, 200.0, 120.0, 0.0, 90.0, width=8.0)
    w.left_color = (0.2, 0.4, 0.8)
    w.right_color = (0.8, 0.5, 0.2)
    w.left_baseboard = True
    w.right_baseboard = True

    cut = arc_opening_cutout(w, 0.5, 36.0)
    assert cut is not None
    # Exact chord width between jamb end-caps equals opening width
    j0, j1 = cut["jamb_start"], cut["jamb_end"]
    assert math.hypot(j1[0] - j0[0], j1[1] - j0[1]) == pytest.approx(36.0, abs=1e-5)

    # Render curved wall + sliding window (empty center interior, easy pixel check)
    c = _make_canvas()
    c.config.DEFAULT_WALL_WIDTH = 8.0
    w.layer_id = c.active_layer_id
    c.wall_sets.append([w])
    door = Door("double", 48.0, 80.0, "left", "outswing", layer_id=c.active_layer_id)
    win = Window(36.0, 36.0, "fixed", layer_id=c.active_layer_id)
    c.doors.append((w, door, 0.28))
    c.windows.append((w, win, 0.72))

    # Render curved wall + door opening at 1px/in so pixel coords == model coords
    c.zoom = 0.5  # zoom * ppi(2.0) = 1.0 px/in
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 420, 420)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    draw_walls(c, cr)
    draw_doors(c, cr, 2.0)
    draw_windows(c, cr, 2.0)

    # Check pixels inside the curved opening along the arc near both jambs (r=117.5, inner side of wall
    # away from exterior text labels): draw_walls paints them black, then draw_doors annular cutout
    # cleanly erases them back to white (255, 255, 255).
    surf_walls = cairo.ImageSurface(cairo.FORMAT_ARGB32, 420, 420)
    cr_w = cairo.Context(surf_walls)
    cr_w.set_source_rgb(1, 1, 1)
    cr_w.paint()
    draw_walls(c, cr_w)
    buf_w = bytes(surf_walls.get_data())
    stride_w = surf_walls.get_stride()

    buf = bytes(surf.get_data())
    stride = surf.get_stride()
    cut_d = arc_opening_cutout(w, 0.28, 48.0)
    for ang_sample in (cut_d["theta_lo"] + 0.03, cut_d["theta_hi"] - 0.03):
        px = int(round(200.0 + 118.0 * math.cos(ang_sample)))
        py = int(round(200.0 + 118.0 * math.sin(ang_sample)))
        idx_w = py * stride_w + px * 4
        assert buf_w[idx_w : idx_w + 3] != b"\xff\xff\xff", "Expected wall stroke before cutout"
        idx = py * stride + px * 4
        b, g, r, _ = buf[idx : idx + 4]
        assert (r, g, b) == (255, 255, 255), f"Curved wall pixel leaked into opening at ({px}, {py}): {(r, g, b)}"

    # Verify helper delegates match arc_wall module
    assert get_point_on_wall(w, 0.5) == pytest.approx(arc_wall_point(w, 0.5))
    assert get_wall_direction(w, 0.5) == pytest.approx(arc_wall_tangent(w, 0.5))
