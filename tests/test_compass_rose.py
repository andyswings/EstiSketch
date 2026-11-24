import os
import sys
import math
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
import cairo  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.Canvas.compass import draw_north_arrow  # noqa: E402
from EstiSketch.project_io import save_project, open_project  # noqa: E402


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    c = canvas_area.create_canvas_area(cfg)
    c.get_width = lambda: 800
    c.get_height = lambda: 600
    return c


def test_north_angle_default_and_clear():
    c = _make_canvas()
    assert c.north_angle == 0.0
    c.north_angle = 123.0
    c.clear()
    assert c.north_angle == 0.0


def test_north_angle_xml_roundtrip():
    c = _make_canvas()
    c.north_angle = 135.0
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        path = tf.name
    try:
        save_project(c, 800, 600, path)
        c2 = _make_canvas()
        open_project(c2, path)
        assert c2.north_angle == pytest.approx(135.0)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_north_angle_missing_attr_defaults_to_zero():
    c = _make_canvas()
    c.north_angle = 90.0
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as tf:
        tf.write('<Project window_width="800" window_height="600"><Levels/><Layers/></Project>')
        path = tf.name
    try:
        open_project(c, path)
        assert c.north_angle == 0.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_compass_drag_rotation_undo_redo_and_double_click_reset():
    c = _make_canvas()
    c.save_state()  # initial state at 0°

    cx, cy, _ = c._compass_geometry(800, 600)
    # Single press on compass, then drag to right (+X from center -> 90°)
    c.on_click_pressed(None, 1, cx, cy)
    c.on_drag_begin(SimpleNamespace(set_state=lambda s: None), cx, cy)
    assert c.dragging_compass is True

    for target_x, target_y, expected in [
        (cx, cy - 40, 0.0),
        (cx + 40, cy, 90.0),
        (cx, cy + 40, 180.0),
        (cx - 40, cy, 270.0),
    ]:
        c.on_drag_update(None, target_x - cx, target_y - cy)
        assert c.north_angle == pytest.approx(expected)

    c.on_drag_end(None, -40, 0)
    assert c.dragging_compass is False
    assert c.north_angle == pytest.approx(270.0)

    c.undo()
    assert c.north_angle == pytest.approx(0.0)
    c.redo()
    assert c.north_angle == pytest.approx(270.0)

    # Double-click on compass resets to 0°
    c.on_click_pressed(None, 2, cx, cy)
    assert c.north_angle == pytest.approx(0.0)


def test_draw_north_arrow_and_compass_rose_render_pixels():
    c = _make_canvas()
    c.north_angle = 45.0
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    c.draw_compass_rose(cr, 800, 600)
    surf.flush()
    buf = bytes(surf.get_data())
    # White pixel is 255,255,255,255; verify non-white pixels were drawn
    assert any(b != 255 for b in buf)

    surf2 = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
    cr2 = cairo.Context(surf2)
    draw_north_arrow(cr2, 50, 50, 30, 315.0, show_degree_label=True, highlight=True)
    surf2.flush()
    assert any(b != 0 for b in bytes(surf2.get_data()))
