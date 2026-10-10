import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.Canvas.winder_geometry import l_stair_layout  # noqa: E402
from EstiSketch.components import Stair  # noqa: E402


def test_layout_no_winders_matches_legacy():
    lay = l_stair_layout(14, 0, 11.0, 36.0, 36.0, 0)
    assert lay["steps_before"] == 7 and lay["steps_after"] == 7
    assert lay["run_before"] == pytest.approx(6 * 11.0)
    assert lay["run_after"] == pytest.approx(6 * 11.0)
    assert lay["landing_depth"] == 36.0


def test_layout_with_winders_steps_add_up():
    lay = l_stair_layout(14, 0, 11.0, 48.0, 36.0, 3)
    assert lay["winder_count"] == 3
    assert lay["steps_before"] + lay["steps_after"] + 3 == 14
    assert lay["landing_depth"] == 36.0  # winder square equals stair width
    assert lay["run_before"] == pytest.approx(lay["steps_before"] * 11.0)


def test_layout_clamps_winders():
    lay = l_stair_layout(4, 0, 11.0, 36.0, 36.0, 5)
    assert lay["winder_count"] == 2
    assert lay["steps_before"] + lay["steps_after"] == 2


def _roundtrip(stair):
    from EstiSketch.project_io import open_project, save_project
    canvas = MagicMock()
    for name in ("wall_sets", "rooms", "doors", "windows", "texts", "dimensions",
                 "polyline_sets", "circles", "arcs", "roofs", "stairs",
                 "levels", "layers"):
        setattr(canvas, name, [])
    canvas.stairs = [stair]
    canvas.active_level_id = "level-1"
    canvas.active_layer_id = "layer-1"
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        path = f.name
    try:
        save_project(canvas, 800, 600, path)
        canvas.stairs = []
        open_project(canvas, path)
        return canvas.stairs
    finally:
        os.remove(path)


def test_winder_roundtrip():
    s = Stair(identifier="s1", stair_type="L-shaped")
    s.winder_count = 3
    s.turn_direction = "right"
    s.steps_before_landing = 5
    s.landing_depth = 42.0
    out = _roundtrip(s)
    assert len(out) == 1
    assert out[0].winder_count == 3
    assert out[0].turn_direction == "right"
    assert out[0].steps_before_landing == 5
    assert out[0].landing_depth == 42.0


@pytest.mark.parametrize("turn", ["left", "right"])
def test_render_smoke(turn):
    pytest.importorskip("cairo")
    import cairo
    from EstiSketch.Canvas.render_stair import CanvasStairRendererMixin

    class Fake(CanvasStairRendererMixin):
        selected_items = []

    for n in (0, 2, 3, 5):
        s = Stair(identifier="s", stair_type="L-shaped")
        s.winder_count = n
        s.turn_direction = turn
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 400)
        cr = cairo.Context(surf)
        cr.translate(50, 200)
        Fake()._draw_l_shaped_stair(cr, s, 1.0, 1.0)
