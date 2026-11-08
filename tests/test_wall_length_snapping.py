"""Tests for wall length increment snapping (0.25") and near-whole-foot auto-fix / prompt."""
import math
from types import SimpleNamespace

import gi
gi.require_version("Gtk", "4.0")
import pytest  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.components import Wall  # noqa: E402
from EstiSketch.measurement_utils import MeasurementConverter  # noqa: E402


@pytest.fixture
def canvas(monkeypatch):
    cfg = SimpleNamespace(**config.load_config())
    cfg.WALL_LENGTH_SNAP_INCREMENT = 0.25
    cfg.WALL_NEAR_FOOT_TOLERANCE = 0.5
    cfg.WALL_NEAR_FOOT_BEHAVIOR = "auto"
    c = CanvasArea(cfg)
    c.zoom = 1.0
    c.offset_x = 0.0
    c.offset_y = 0.0
    c.snap_manager.snap_enabled = True
    c.set_tool_mode("draw_walls")
    return c


def _dev(canvas, model_x, model_y):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    return canvas.model_to_device(model_x, model_y, ppi)


def test_wall_draws_in_quarter_inch_increments(canvas):
    """Drawing a wall quantizes length to 0.25\" increments."""
    # Start wall at (0, 0)
    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))
    assert canvas.drawing_wall is True

    # Move to 126.31" (10' 6.31") -> should quantize to 126.25" (10' 6.25")
    canvas.on_motion(None, *_dev(canvas, 126.31, 0.4))
    assert canvas.current_wall.end[0] == pytest.approx(126.25)
    assert canvas.current_wall.end[1] == pytest.approx(0.0)

    # Click at 126.38" -> should quantize to 126.50" (10' 6.5")
    canvas._handle_wall_click(1, *_dev(canvas, 126.38, 0.2))
    assert len(canvas.walls) == 1
    placed = canvas.walls[0]
    length = math.hypot(placed.end[0] - placed.start[0], placed.end[1] - placed.start[1])
    assert length == pytest.approx(126.50)
    assert placed.end[1] == pytest.approx(0.0)


def test_angled_wall_length_quantized_to_quarter_inch(canvas):
    """45-degree wall has its hypotenuse length quantized to 0.25\" increments."""
    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))

    raw_len = 100.33  # not near a whole foot (8' 4.33")
    rad = math.radians(45.0)
    mx = raw_len * math.cos(rad)
    my = raw_len * math.sin(rad)

    canvas._handle_wall_click(1, *_dev(canvas, mx, my))
    assert len(canvas.walls) == 1
    placed = canvas.walls[0]
    length = math.hypot(placed.end[0] - placed.start[0], placed.end[1] - placed.start[1])
    assert length == pytest.approx(100.25)
    angle_deg = math.degrees(math.atan2(placed.end[1], placed.end[0]))
    assert angle_deg == pytest.approx(45.0)


def test_near_foot_auto_fixes_39ft_11_95in_to_40ft(canvas):
    """In 'auto' mode, a wall drawn at 39' 11.95\" (479.95\") or 39' 11.75\" (479.75\") snaps to 40' 0\" (480.0\")."""
    canvas.config.WALL_NEAR_FOOT_BEHAVIOR = "auto"
    canvas.config.WALL_NEAR_FOOT_TOLERANCE = 0.5

    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))

    # Motion at 39' 11.72" (479.72") -> within 0.5" of 480.0", auto-snaps preview to 480.0"
    canvas.on_motion(None, *_dev(canvas, 479.72, 0.5))
    assert canvas.current_wall.end == pytest.approx((480.0, 0.0))

    # Click at 39' 11.95" (479.95") -> places wall at exact 480.0" (40' 0")
    canvas._handle_wall_click(1, *_dev(canvas, 479.95, 0.2))
    assert len(canvas.walls) == 1
    placed = canvas.walls[0]
    assert placed.end == pytest.approx((480.0, 0.0))
    assert canvas.current_wall.start == pytest.approx((480.0, 0.0))


def test_near_foot_prompt_mode_prompts_and_adjusts_wall(canvas, monkeypatch):
    """In 'prompt' mode, drawing at 39' 11.75\" prompts to snap to 40' 0\" and adjusts the wall on confirmation."""
    canvas.config.WALL_NEAR_FOOT_BEHAVIOR = "prompt"
    canvas.config.WALL_NEAR_FOOT_TOLERANCE = 0.5

    captured_dialogs = []

    class DummyDialog:
        def __init__(self, drawn_str, target_str):
            self.drawn_str = drawn_str
            self.target_str = target_str
            self._cb = None

        def connect(self, sig, cb):
            if sig == "response":
                self._cb = cb

        def present(self):
            captured_dialogs.append(self)

        def destroy(self):
            pass

    monkeypatch.setattr(
        "EstiSketch.Canvas.events_wall.create_near_foot_confirm_dialog",
        lambda parent, drawn_str, target_str: DummyDialog(drawn_str, target_str),
    )

    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))
    # Click at 479.74" -> quantizes to 479.75" (39' 11.75") and triggers prompt for 480.0" (40' 0")
    canvas._handle_wall_click(1, *_dev(canvas, 479.74, 0.0))

    assert len(canvas.walls) == 1
    placed = canvas.walls[0]
    assert placed.end == pytest.approx((479.75, 0.0))
    assert len(captured_dialogs) == 1
    dlg = captured_dialogs[0]
    assert "39' 11.75\"" in dlg.drawn_str
    assert "40' 0.0\"" in dlg.target_str

    # Simulate user clicking "Snap to 40' 0.0"" (Gtk.ResponseType.OK)
    from gi.repository import Gtk
    dlg._cb(dlg, Gtk.ResponseType.OK)

    assert placed.end == pytest.approx((480.0, 0.0))
    assert canvas.current_wall.start == pytest.approx((480.0, 0.0))


def test_near_foot_off_mode_keeps_quarter_inch_step(canvas):
    """In 'off' mode, 39' 11.75\" stays at 479.75\" without auto-snapping to 480.0\"."""
    canvas.config.WALL_NEAR_FOOT_BEHAVIOR = "off"
    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))
    canvas._handle_wall_click(1, *_dev(canvas, 479.74, 0.0))

    assert len(canvas.walls) == 1
    assert canvas.walls[0].end == pytest.approx((479.75, 0.0))


def test_continuing_wall_does_not_snap_to_previous_wall_edge_offset(canvas):
    """Drawing a second wall collinear with the first should stay at y=0, not jump to y=±width/2."""
    canvas._handle_wall_click(1, *_dev(canvas, 0.0, 0.0))
    canvas._handle_wall_click(1, *_dev(canvas, 120.0, 0.0))
    assert canvas.walls[0].end == pytest.approx((120.0, 0.0))

    # Move slightly off-axis (y=2.0, which is near the 5.5" wall's top face at y=2.75)
    canvas.on_motion(None, *_dev(canvas, 240.0, 2.0))
    assert canvas.current_wall.end == pytest.approx((240.0, 0.0))


def test_snap_selected_walls_to_nearest_foot_action(canvas):
    """Right-click action snaps selected wall and connected wall endpoints to nearest whole foot."""
    w1 = Wall((0.0, 0.0), (479.95, 0.0), 5.5, 96.0, identifier="wall-1")
    w2 = Wall((479.95, 0.0), (479.95, 240.0), 5.5, 96.0, identifier="wall-2")
    canvas.wall_sets = [[w1, w2]]
    canvas.selected_items = [{"type": "wall", "object": w1}]

    count = canvas.snap_selected_walls_to_nearest_foot()
    assert count == 1
    assert w1.end == pytest.approx((480.0, 0.0))
    assert w2.start == pytest.approx((480.0, 0.0))


def test_format_measurement_rollover():
    """Lengths like 479.999\" format as 40' 0.0\" rather than 39' 12.0\"."""
    assert MeasurementConverter.format_measurement(479.999, use_fraction=False) == "40' 0.0\""
    assert MeasurementConverter.format_measurement(479.999, use_fraction=True) == "40' 0\""


def test_parallel_wall_endpoint_snapping_in_active_chain(canvas):
    """Drawing a 3rd wall in a rectangular chain snaps parallel to the 1st wall's start endpoint."""
    # Wall 1: (0.1, 0) -> (203.6, 0) (snaps to 203.5" length -> end at (203.6, 0))
    canvas._handle_wall_click(1, *_dev(canvas, 0.1, 0.0))
    canvas._handle_wall_click(1, *_dev(canvas, 203.6, 0.0))
    # Wall 2: (203.6, 0) -> (203.6, 150.0)
    canvas._handle_wall_click(1, *_dev(canvas, 203.6, 150.0))
    assert len(canvas.walls) == 2

    # Move left for Wall 3 near x=0.1 (e.g. cursor at x=5.5, y=154.0 — within 10" alignment tolerance)
    canvas.on_motion(None, *_dev(canvas, 5.5, 154.0))
    assert canvas.current_wall.end == pytest.approx((0.1, 150.0))
    assert canvas.snap_type == "alignment"
    assert canvas.alignment_candidate == pytest.approx((0.1, 0.0))

    # Clicking places Wall 3 aligned with Wall 1's start x=0.1 (not re-quantized away or snapped to near-foot)
    canvas._handle_wall_click(1, *_dev(canvas, 5.5, 154.0))
    assert len(canvas.walls) == 3
    assert canvas.walls[2].end == pytest.approx((0.1, 150.0))


def test_parallel_wall_endpoint_snapping_to_existing_wall_set(canvas):
    """Drawing a new wall parallel to an existing wall in wall_sets snaps to its endpoint alignment."""
    existing = Wall((10.0, 20.0), (195.37, 20.0), 5.5, 96.0, identifier="wall-existing")
    canvas.wall_sets = [[existing]]

    # Start a new wall below at (10.0, 120.0)
    canvas._handle_wall_click(1, *_dev(canvas, 10.0, 120.0))

    # Move near x=195.37 (within 10" tolerance, e.g. x=191.0, y=123.0)
    canvas.on_motion(None, *_dev(canvas, 191.0, 123.0))
    assert canvas.current_wall.end == pytest.approx((195.37, 120.0))
    assert canvas.snap_type == "alignment"
    assert canvas.alignment_candidate == pytest.approx((195.37, 20.0))


