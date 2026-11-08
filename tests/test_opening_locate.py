import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("gi")

from EstiSketch.Canvas.events_tools import CanvasToolsMixin  # noqa: E402
from EstiSketch.Canvas.events_helpers import *  # noqa: E402,F401,F403
import EstiSketch.Canvas.events_helpers as eh  # noqa: E402


def _helpers_cls():
    for v in vars(eh).values():
        if isinstance(v, type) and hasattr(v, "distance_point_to_segment"):
            return v
    pytest.skip("helpers mixin not found")


class Harness(CanvasToolsMixin):
    pass


def _make(walls):
    H = type("H", (CanvasToolsMixin, _helpers_cls()), {})
    h = H.__new__(H)
    h.config = SimpleNamespace(PIXELS_PER_INCH=1.0, DEFAULT_DOOR_TYPE="single",
                               DEFAULT_WINDOW_TYPE="sliding")
    h.zoom = 1.0
    h.offset_x = 0.0
    h.offset_y = 0.0
    h.active_layer_id = "L1"
    h.wall_sets = [walls]
    return h


def _wall(a, b):
    return SimpleNamespace(start=a, end=b, is_curved=False, arc_center=None,
                           arc_radius=None, width=6.0)


def test_locate_midpoint():
    h = _make([_wall((0, 0), (200, 0))])
    wall, ratio = h._locate_on_wall(100, 2)
    assert ratio == pytest.approx(0.5)


def test_locate_none_when_far():
    h = _make([_wall((0, 0), (200, 0))])
    assert h._locate_on_wall(100, 80) is None


def test_ratio_clamped_for_opening_width():
    h = _make([_wall((0, 0), (200, 0))])
    _, ratio = h._locate_on_wall(1, 0, opening_width=36.0)
    assert ratio == pytest.approx(18.0 / 200.0)
    _, ratio = h._locate_on_wall(199, 0, opening_width=36.0)
    assert ratio == pytest.approx(1.0 - 18.0 / 200.0)


def test_default_builders_match_dims():
    h = _make([])
    d = h._build_default_door(identifier="ghost")
    assert d.width == h._default_door_dims()[0]
    assert h._build_default_window().width == 48.0


def test_configured_door_and_window_sizes():
    h = _make([])
    h.config.DEFAULT_DOOR_WIDTH = 42.0
    h.config.DEFAULT_DOOR_HEIGHT = 84.0
    h.config.DEFAULT_WINDOW_WIDTH = 60.0
    h.config.DEFAULT_WINDOW_HEIGHT = 48.0

    door = h._build_default_door(identifier="d1")
    assert (door.width, door.height) == (42.0, 84.0)

    win = h._build_default_window(identifier="w1")
    assert (win.width, win.height) == (60.0, 48.0)


def test_all_tools_have_hints():
    from EstiSketch.Resources.tool_hints import TOOL_HINTS
    all_tools = [
        "pointer", "panning", "draw_walls", "draw_rooms",
        "add_doors", "add_windows", "add_stair", "add_polyline",
        "add_dimension", "add_dimension_chain", "add_leader",
        "add_text", "add_circle", "add_arc", "design_roof", "add_roof_line",
    ]
    for tool in all_tools:
        assert tool in TOOL_HINTS and TOOL_HINTS[tool], f"Missing hint for {tool}"
    assert "add_stair_active" in TOOL_HINTS


def test_wall_custom_heights():
    from EstiSketch.components import Wall
    from EstiSketch.Dialogs.properties_dock import WallPropertiesWidget

    widget = WallPropertiesWidget()
    widget.canvas = SimpleNamespace(queue_draw=lambda: None, recalculate_roofs_for_wall=lambda wid: None)

    # 1. Rectangular wall with custom height (102" = 8.5')
    w = Wall((0, 0), (120, 0), 5.5, 102.0, identifier="wall-1")
    widget.set_wall(w)
    assert widget.height_combo.get_active_text() == "Custom"
    assert widget.custom_height_row.get_visible() is True
    assert widget.custom_height_spin.get_value() == pytest.approx(102.0)

    # Adjust custom height via spin button -> updates both start & end on rectangular wall
    widget.custom_height_spin.set_value(110.0)
    assert w.height == pytest.approx(110.0)
    assert w.height_at_end == pytest.approx(110.0)

    # 2. Sloped wall with custom end height
    widget.sloped_check.set_active(True)
    widget.height_end_combo.set_active(len(widget.available_heights))  # "Custom"
    assert widget.custom_height_end_row.get_visible() is True
    widget.custom_height_end_spin.set_value(135.5)
    assert w.height == pytest.approx(110.0)
    assert w.height_at_end == pytest.approx(135.5)
    assert w.is_sloped is True


def test_copy_paste_multiple_windows_and_objects():
    from EstiSketch.Canvas.canvas_area import CanvasArea
    from EstiSketch.components import Wall, Window, Door
    from EstiSketch.config import DEFAULT_SETTINGS

    cfg = SimpleNamespace(**DEFAULT_SETTINGS)
    canvas = CanvasArea(cfg)

    w = Wall((0, 0), (240, 0), 5.5, 96.0, identifier="w1", layer_id=canvas.active_layer_id)
    canvas.wall_sets.append([w])
    win1 = Window(36.0, 36.0, "sliding", identifier="win1", layer_id=canvas.active_layer_id)
    win2 = Window(36.0, 36.0, "sliding", identifier="win2", layer_id=canvas.active_layer_id)
    door1 = Door("single", 36.0, 80.0, "left", "inswing", identifier="d1", layer_id=canvas.active_layer_id)

    t1 = (w, win1, 0.25)
    t2 = (w, win2, 0.55)
    td = (w, door1, 0.80)
    canvas.windows.extend([t1, t2])
    canvas.doors.append(td)

    canvas.selected_items = [
        {"type": "window", "object": t1},
        {"type": "window", "object": t2},
        {"type": "door", "object": td},
    ]
    canvas.copy_selected()
    canvas.paste()

    assert len(canvas.windows) == 4
    assert len(canvas.doors) == 2
    # Pasted windows must reference the live wall `w`, have unique IDs, and not collide in ratio
    pasted_wins = canvas.windows[2:]
    assert pasted_wins[0][0] is w
    assert pasted_wins[1][0] is w
    assert pasted_wins[0][1].identifier != pasted_wins[1][1].identifier
    assert pasted_wins[0][2] != pytest.approx(pasted_wins[1][2])


def test_level_layer_visibility_and_deselection():
    from EstiSketch.Canvas.canvas_area import CanvasArea
    from EstiSketch.components import Wall
    from EstiSketch.config import DEFAULT_SETTINGS

    cfg = SimpleNamespace(**DEFAULT_SETTINGS)
    canvas = CanvasArea(cfg)
    level1_id = canvas.active_level_id
    layer1_id = canvas.active_layer_id

    # Add a wall on Level 1's layer and select it
    w1 = Wall((0, 0), (120, 0), 5.5, 96.0, identifier="w-lvl1", layer_id=layer1_id)
    canvas.wall_sets.append([w1])
    canvas.selected_items = [{"type": "wall", "object": w1}]

    # Add a Global layer and a wall on it
    global_layer_id = canvas.add_layer("Global Layer", level_id="")
    w_global = Wall((0, 50), (120, 50), 5.5, 96.0, identifier="w-global", layer_id=global_layer_id)
    canvas.wall_sets.append([w_global])
    canvas.selected_items.append({"type": "wall", "object": w_global})

    # Create Level 2 and switch to it
    level2_id = canvas.add_level("Level 2")
    layer2_id = canvas.add_layer("Level 2 Layer", level_id=level2_id)
    canvas.set_active_level(level2_id)

    # Level 1 wall should be hidden and automatically deselected; Global wall remains visible and selected
    assert canvas.is_object_on_visible_layer(w1) is False
    assert canvas.is_object_on_visible_layer(w_global) is True
    assert [item["object"] for item in canvas.selected_items] == [w_global]

    # Layer on Level 1 cannot be set active while Level 2 is active (unless show_all_levels is True)
    assert canvas.set_active_layer(layer1_id) is False
    assert canvas.set_active_layer(global_layer_id) is True
    assert canvas.set_active_layer(layer2_id) is True


