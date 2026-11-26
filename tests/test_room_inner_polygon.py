from types import SimpleNamespace

import pytest

from EstiSketch import config
from EstiSketch.Canvas import canvas_area
from EstiSketch.Canvas.canvas_geometry import CanvasGeometryMixin as G
from EstiSketch.components import Wall
from EstiSketch.geometry.room_loop import find_enclosed_room_inner_polygon


def area(p):
    return abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                   for i in range(len(p)))) / 2


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    c = canvas_area.create_canvas_area(cfg)
    c.zoom = 1.0
    c.offset_x = 0.0
    c.offset_y = 0.0
    return c


def _double_click_room(canvas, model_x: float, model_y: float) -> None:
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    dev_x = model_x * canvas.zoom * ppi + canvas.offset_x
    dev_y = model_y * canvas.zoom * ppi + canvas.offset_y
    canvas._handle_room_click(1, dev_x, dev_y)
    canvas._handle_room_click(2, dev_x, dev_y)


def test_inset_square_both_orientations():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    for poly in (sq, sq[::-1]):
        out = G._inset_polygon(poly, [4.0] * 4)
        assert abs(area(out) - 92 * 92) < 1e-6
        assert all(4 - 1e-6 <= x <= 96 + 1e-6 and 4 - 1e-6 <= y <= 96 + 1e-6 for x, y in out)


def test_inset_mixed_thickness():
    sq = [(0, 0), (100, 0), (100, 100), (0, 100)]
    out = G._inset_polygon(sq, [8, 2, 2, 2])
    xs = sorted(p[0] for p in out)
    ys = sorted(p[1] for p in out)
    assert (xs[0], xs[-1], ys[0], ys[-1]) == (2, 98, 8, 98)


def test_inset_skips_duplicate_consecutive_vertices():
    sq = [(0, 0), (100, 0), (100, 0), (100, 100), (0, 100)]
    out = G._inset_polygon(sq, [4.0, 4.0, 4.0, 4.0, 4.0])
    assert abs(area(out) - 92 * 92) < 1e-6


def _wall(start, end, width=6.0, wall_id="w", layer_id=""):
    return Wall(start, end, width=width, height=96.0, identifier=wall_id, layer_id=layer_id)


def test_double_click_single_and_multi_wall_set_creates_inner_room():
    c = _make_canvas()
    lid = c.active_layer_id
    w1 = _wall((0.0, 0.0), (120.0, 0.0), 6.0, "w1", lid)
    w2 = _wall((120.0, 0.0), (120.0, 120.0), 6.0, "w2", lid)
    w3 = _wall((0.0, 120.0), (120.0, 120.0), 6.0, "w3r", lid)
    w4 = _wall((0.0, 120.0), (0.0, 0.0), 6.0, "w4", lid)
    # Four separate wall sets + reversed edge direction
    c.wall_sets = [[w1], [w2], [w4], [w3]]

    _double_click_room(c, 60.0, 60.0)
    assert len(c.rooms) == 1
    xs = [p[0] for p in c.rooms[0].points]
    ys = [p[1] for p in c.rooms[0].points]
    assert min(xs) == pytest.approx(3.0)
    assert max(xs) == pytest.approx(117.0)
    assert min(ys) == pytest.approx(3.0)
    assert max(ys) == pytest.approx(117.0)


def test_double_click_subdivided_room_picks_smallest_face_with_mixed_widths():
    # Outer loop 200x100 with 6" walls, divided at x=100 by a 4" partition wall
    walls = [
        _wall((0.0, 0.0), (200.0, 0.0), 6.0, "n"),
        _wall((200.0, 0.0), (200.0, 100.0), 6.0, "e"),
        _wall((200.0, 100.0), (0.0, 100.0), 6.0, "s"),
        _wall((0.0, 100.0), (0.0, 0.0), 6.0, "w"),
        _wall((100.0, 0.0), (100.0, 100.0), 4.0, "part"),
    ]
    inner_left = find_enclosed_room_inner_polygon(walls, (50.0, 50.0))
    assert inner_left is not None
    xs = [p[0] for p in inner_left]
    ys = [p[1] for p in inner_left]
    assert min(xs) == pytest.approx(3.0)
    assert max(xs) == pytest.approx(98.0)  # 100 - 4/2 interior face
    assert min(ys) == pytest.approx(3.0)
    assert max(ys) == pytest.approx(97.0)


def test_double_click_hidden_layer_ignored_and_manual_finalize_not_duplicated():
    c = _make_canvas()
    lid = c.active_layer_id
    w1 = _wall((0.0, 0.0), (200.0, 0.0), 6.0, "w1", lid)
    w2 = _wall((200.0, 0.0), (200.0, 200.0), 6.0, "w2", lid)
    w3 = _wall((200.0, 200.0), (0.0, 200.0), 6.0, "w3", lid)
    w4 = _wall((0.0, 200.0), (0.0, 0.0), 6.0, "w4", lid)
    c.wall_sets = [[w1, w2, w3, w4]]

    # Manual 3-point room finalized by double-click inside closed walls must create ONE room
    c.current_room_points = [(20.0, 20.0), (80.0, 20.0), (80.0, 80.0)]
    ppi = getattr(c.config, "PIXELS_PER_INCH", 2.0)
    c._handle_room_click(2, 50.0 * ppi, 50.0 * ppi)
    assert len(c.rooms) == 1
    assert c.rooms[0].points == [(20.0, 20.0), (80.0, 20.0), (80.0, 80.0)]

    # Hidden layer walls are ignored
    c.rooms = []
    c.get_layer_by_id(lid).visible = False
    _double_click_room(c, 100.0, 100.0)
    assert len(c.rooms) == 0
