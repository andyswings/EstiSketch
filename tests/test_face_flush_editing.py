"""Face-flush snapping while editing existing walls (drag body / drag endpoint)."""
from types import SimpleNamespace

import gi
gi.require_version("Gtk", "4.0")
import pytest  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.components import Wall  # noqa: E402


@pytest.fixture
def canvas():
    cfg = SimpleNamespace(**config.load_config())
    c = CanvasArea(cfg)
    c.zoom = 1.0
    c.offset_x = 0.0
    c.offset_y = 0.0
    c.snap_manager.snap_enabled = True
    return c


def _T(canvas):
    return canvas.zoom * getattr(canvas.config, "PIXELS_PER_INCH", 2.0)


def test_body_drag_snaps_abutting_and_sets_guide(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    b = Wall((0, 50), (200, 50), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.dragging_wall = b
    canvas.wall_drag_original_start = b.start
    canvas.wall_drag_original_end = b.end
    canvas.wall_drag_start_model = (0.0, 0.0)
    canvas.drag_start_x = 0.0
    canvas.drag_start_y = 0.0
    canvas.wall_drag_connected_start = []
    canvas.wall_drag_connected_end = []

    T = _T(canvas)
    # Move B up to y=7.0 (centerline); abutting A's +y face needs y=6.25.
    canvas.on_drag_update(None, 0.0, -43.0 * T)

    assert b.start[1] == pytest.approx(6.25)
    assert b.end[1] == pytest.approx(6.25)
    assert canvas.edit_face_guide is not None
    assert canvas.edit_face_guide[2] == "abut"

    # Moving far away clears the guide and applies the raw drag.
    canvas.on_drag_update(None, 0.0, -20.0 * T)
    assert canvas.edit_face_guide is None
    assert b.start[1] == pytest.approx(30.0)


def test_body_drag_ignores_connected_and_self(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    canvas.wall_sets = [[a]]
    canvas.dragging_wall = a
    canvas.wall_drag_original_start = a.start
    canvas.wall_drag_original_end = a.end
    canvas.wall_drag_start_model = (0.0, 0.0)
    canvas.drag_start_x = canvas.drag_start_y = 0.0
    canvas.wall_drag_connected_start = []
    canvas.wall_drag_connected_end = []

    canvas.on_drag_update(None, 0.0, 1.0 * _T(canvas))
    assert canvas.edit_face_guide is None
    assert a.start[1] == pytest.approx(1.0)


def test_endpoint_drag_snaps_flush(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    # B already sits flush-abutting A at its start; drag its end near the same line.
    b = Wall((0, 6.25), (200, 10), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.editing_wall = b
    canvas.editing_handle = "end"
    canvas.connected_endpoints = [(b, "end")]
    canvas.joint_drag_origin = b.end

    T = _T(canvas)
    canvas.on_drag_update(None, 0.0, -3.0 * T)  # end -> (200, 7.0)

    assert b.end[1] == pytest.approx(6.25)
    assert canvas.edit_face_guide is not None
    assert canvas.edit_face_guide[2] == "abut"


def test_endpoint_drag_no_snap_when_snapping_disabled(canvas):
    canvas.snap_manager.snap_enabled = False
    a = Wall((0, 0), (200, 0), 8, 96)
    b = Wall((0, 6.25), (200, 10), 4.5, 96)
    canvas.wall_sets = [[a], [b]]
    canvas.editing_wall = b
    canvas.editing_handle = "end"
    canvas.connected_endpoints = [(b, "end")]
    canvas.joint_drag_origin = b.end

    canvas.on_drag_update(None, 0.0, -3.0 * _T(canvas))
    assert b.end[1] == pytest.approx(7.0)
    assert canvas.edit_face_guide is None


def test_endpoint_drag_snaps_to_wall_centerline(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    # Wall B at x=80 (away from A's midpoint at x=100)
    b = Wall((80, 50), (80, 10), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.editing_wall = b
    canvas.editing_handle = "end"
    canvas.connected_endpoints = [(b, "end")]
    canvas.joint_drag_origin = b.end

    T = _T(canvas)
    # Drag end from (80, 10) down by -8 -> (80, 2.0), near wall A centerline (y=0)
    canvas.on_drag_update(None, 0.0, -8.0 * T)

    assert b.end[0] == pytest.approx(80.0)
    assert b.end[1] == pytest.approx(0.0)
    assert canvas.snap_type == "wall_centerline"


def test_endpoint_drag_snaps_to_wall_endpoint(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    b = Wall((250, 50), (202, 3), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.editing_wall = b
    canvas.editing_handle = "end"
    canvas.connected_endpoints = [(b, "end")]
    canvas.joint_drag_origin = b.end

    T = _T(canvas)
    # Drag end near (200, 0)
    canvas.on_drag_update(None, -1.0 * T, -2.0 * T)

    assert b.end[0] == pytest.approx(200.0)
    assert b.end[1] == pytest.approx(0.0)
    assert canvas.snap_type == "endpoint"


def test_body_drag_snaps_centerline(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    b = Wall((0, 50), (200, 50), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.dragging_wall = b
    canvas.wall_drag_original_start = b.start
    canvas.wall_drag_original_end = b.end
    canvas.wall_drag_start_model = (0.0, 0.0)
    canvas.drag_start_x = 0.0
    canvas.drag_start_y = 0.0
    canvas.wall_drag_connected_start = []
    canvas.wall_drag_connected_end = []

    T = _T(canvas)
    # Move B from y=50 down by -49.8 -> y=0.2, closest to A's centerline at y=0.0
    canvas.on_drag_update(None, 0.0, -49.8 * T)

    assert b.start[1] == pytest.approx(0.0)
    assert b.end[1] == pytest.approx(0.0)
    assert canvas.edit_face_guide is not None
    assert canvas.edit_face_guide[2] == "center"


def test_drag_end_cleans_up_snapping_state(canvas):
    a = Wall((0, 0), (200, 0), 8, 96)
    b = Wall((80, 50), (80, 10), 4.5, 96)
    canvas.wall_sets = [[a], [b]]

    canvas.editing_wall = b
    canvas.editing_handle = "end"
    canvas.connected_endpoints = [(b, "end")]
    canvas.joint_drag_origin = b.end

    T = _T(canvas)
    canvas.on_drag_update(None, 0.0, -8.0 * T)
    assert canvas.snap_type == "wall_centerline"

    canvas.on_drag_end(None, 0.0, -8.0 * T)
    assert canvas.snap_type == "none"
    assert canvas.snap_pos is None
    assert canvas.alignment_candidate is None
    assert canvas.raw_current_end is None
