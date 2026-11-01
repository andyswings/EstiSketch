import io
import math
import os
import tempfile
from unittest.mock import MagicMock

import cairo
import pytest

from EstiSketch.components import BackgroundImage
from EstiSketch.measurement_utils import parse_distance
from EstiSketch.project_io import open_project, save_project
from EstiSketch.Canvas.blueprint import (
    apply_calibration, blueprint_corners, calibrated_scale,
    load_surface_from_bytes, point_in_blueprint)


def _png_bytes(w=40, h=20):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 0, 0)
    cr.paint()
    buf = io.BytesIO()
    surf.write_to_png(buf)
    return buf.getvalue()


def test_calibrated_scale_basic():
    # 100 model inches apart that really are 288 inches -> scale up 2.88x
    assert calibrated_scale((0, 0), (100, 0), 288) == pytest.approx(2.88)
    assert calibrated_scale((0, 0), (30, 40), 100) == pytest.approx(2.0)


def test_calibrated_scale_rejects_bad_input():
    with pytest.raises(ValueError):
        calibrated_scale((5, 5), (5, 5), 10)
    with pytest.raises(ValueError):
        calibrated_scale((0, 0), (10, 0), 0)


def test_apply_calibration_scales_about_first_point():
    bp = BackgroundImage(x=10, y=20, scale_x=1.0, scale_y=1.0,
                         pixel_width=100, pixel_height=50)
    p1, p2 = (50.0, 20.0), (150.0, 20.0)
    factor = apply_calibration(bp, p1, p2, 200.0)
    assert factor == pytest.approx(2.0)
    assert bp.scale_x == pytest.approx(2.0) and bp.scale_y == pytest.approx(2.0)
    # p1 is fixed: origin moves away from it by the factor
    assert bp.x == pytest.approx(50 + (10 - 50) * 2)
    assert bp.y == pytest.approx(20)
    # The two image pixels that were clicked (x=40 and x=140 originally)
    # are now exactly the requested real distance apart in model space.
    new_p1 = bp.x + 40 * bp.scale_x
    new_p2 = bp.x + 140 * bp.scale_x
    assert new_p1 == pytest.approx(p1[0])
    assert new_p2 - new_p1 == pytest.approx(200.0)


def test_rotation_helpers():
    bp = BackgroundImage(x=0, y=0, scale_x=1, scale_y=1, rotation=90,
                         pixel_width=10, pixel_height=4)
    corners = blueprint_corners(bp)
    assert corners[1] == pytest.approx((0, 10), abs=1e-9)
    assert point_in_blueprint(bp, -2, 5)
    assert not point_in_blueprint(bp, 5, 2)


@pytest.mark.parametrize("text,expected", [
    ("24' 0\"", 288.0),
    ("24'", 288.0),
    ("288", 288.0),
    ('288"', 288.0),
    ("7500 mm", 7500 / 25.4),
    ("750cm", 750 / 2.54),
    ("7.5 m", 750 / 2.54),
])
def test_parse_distance(text, expected):
    assert parse_distance(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "   ", "abc", "0", "-5"])
def test_parse_distance_invalid(text):
    with pytest.raises(ValueError):
        parse_distance(text)


def test_load_surface_from_png():
    surf = load_surface_from_bytes(_png_bytes(40, 20))
    assert (surf.get_width(), surf.get_height()) == (40, 20)


def test_load_surface_from_jpeg():
    gi = pytest.importorskip("gi")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        __import__("gi.repository.GLib", fromlist=["Bytes"]).Bytes.new(bytes([255, 0, 0] * 12 * 8)),
        GdkPixbuf.Colorspace.RGB, False, 8, 12, 8, 12 * 3)
    ok, data = pixbuf.save_to_bufferv("jpeg", [], [])
    assert ok
    surf = load_surface_from_bytes(bytes(data))
    assert (surf.get_width(), surf.get_height()) == (12, 8)


def test_project_roundtrip_preserves_blueprint():
    canvas = MagicMock()
    for name in ("wall_sets", "rooms", "doors", "windows", "texts",
                 "dimensions", "polyline_sets", "circles", "arcs", "roofs",
                 "stairs", "levels", "layers", "blueprints"):
        setattr(canvas, name, [])
    canvas.active_level_id = "level-1"
    canvas.active_layer_id = "layer-1"
    canvas._blueprint_surfaces = {}
    data = _png_bytes(16, 8)
    canvas.blueprints.append(BackgroundImage(
        identifier="blueprint-1", name="plan.png", image_path="/x/plan.png",
        x=12.5, y=-3.0, scale_x=2.5, scale_y=2.5, rotation=15.0, opacity=0.35,
        visible=False, locked=False, level_id="level-1", image_data=data))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "p.xml")
        save_project(canvas, 800, 600, path)
        canvas.blueprints.clear()
        canvas.get_blueprint_surface = lambda bp: None
        open_project(canvas, path)

    assert len(canvas.blueprints) == 1
    bp = canvas.blueprints[0]
    assert bp.identifier == "blueprint-1" and bp.name == "plan.png"
    assert (bp.x, bp.y) == (12.5, -3.0)
    assert (bp.scale_x, bp.scale_y, bp.rotation, bp.opacity) == (2.5, 2.5, 15.0, 0.35)
    assert bp.visible is False and bp.locked is False
    assert bp.level_id == "level-1"
    assert bp.image_data == data


def test_image_warp_homography_and_bow():
    from EstiSketch.geometry import image_warp as iw
    import numpy as np

    # Unit quad -> scaled/translated quad
    corners = [(10, 20), (110, 20), (110, 80), (10, 80)]
    offsets = [(0, -5), (0, 0), (0, 0), (0, 0)]  # top edge bowed upwards by 5 px

    # Midpoint of top edge (u=0.5, v=0.0) should be at y = 20 - 5 = 15
    sx, sy = iw.source_point(corners, offsets, 0.5, 0.0)
    assert sx == pytest.approx(60.0)
    assert sy == pytest.approx(15.0)

    # Corners should be unaffected by bow
    sx_tl, sy_tl = iw.source_point(corners, offsets, 0.0, 0.0)
    assert (sx_tl, sy_tl) == pytest.approx((10.0, 20.0))

    # Center (u=0.5, v=0.5) should blend top offset with (1-v)*4*u*(1-u) = 0.5 * 1.0 = 0.5
    sx_c, sy_c = iw.source_point(corners, offsets, 0.5, 0.5)
    assert sx_c == pytest.approx(60.0)
    assert sy_c == pytest.approx(50.0 - 2.5)


def test_straighten_surface_applies_transform():
    from EstiSketch.Canvas.blueprint_straighten import (
        straighten_surface, rgba_to_surface, surface_to_rgba)
    import numpy as np

    # Create an input surface 100x100 filled with distinct quadrants
    arr = np.zeros((100, 100, 4), dtype=np.uint8)
    arr[:, :, 3] = 255  # alpha
    arr[:50, :50, 0] = 255  # top-left red (BGRA -> B=255)
    surf = rgba_to_surface(arr)

    # Perspective quad focusing on top-left quadrant
    corners = [(0, 0), (50, 0), (50, 50), (0, 50)]
    offsets = [(0, 0), (0, 0), (0, 0), (0, 0)]

    new_surf, shrink = straighten_surface(surf, corners, offsets)
    assert new_surf.get_width() == 50
    assert new_surf.get_height() == 50
    out_arr = surface_to_rgba(new_surf)
    # The output should be completely filled with the top-left color
    assert np.all(out_arr[:, :, 0] == 255)
    assert np.all(out_arr[:, :, 3] == 255)
