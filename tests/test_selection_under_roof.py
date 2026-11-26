"""Headless tests: objects beneath a roof stay selectable; rooms can be selected and moved."""
from __future__ import annotations

from types import SimpleNamespace

import gi

gi.require_version("Gtk", "4.0")

import pytest  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.components import Room  # noqa: E402
from EstiSketch.roof_components import Roof  # noqa: E402


@pytest.fixture
def canvas() -> CanvasArea:
    cfg = SimpleNamespace(**config.load_config())
    area = CanvasArea(cfg)
    area.tool_mode = "pointer"
    return area


def _fake_gesture() -> SimpleNamespace:
    event = SimpleNamespace(get_modifier_state=lambda: 0)
    return SimpleNamespace(
        get_current_event=lambda: event,
        set_state=lambda *_a: None,
    )


def _click_model_point(canvas: CanvasArea, mx: float, my: float) -> None:
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    dev_x, dev_y = canvas.model_to_device(mx, my, ppi)
    canvas._handle_pointer_click(_fake_gesture(), 1, dev_x, dev_y)


def _make_room() -> Room:
    return Room([(0, 0), (200, 0), (200, 200), (0, 200)])


def _make_roof() -> Roof:
    roof = Roof()
    roof.outline_points = [(-20, -20), (220, -20), (220, 220), (-20, 220)]
    roof.solved_lines = []
    roof.manual_lines = []
    return roof


def test_room_selectable_without_roof(canvas: CanvasArea) -> None:
    room = _make_room()
    canvas.rooms.append(room)
    _click_model_point(canvas, 100, 100)
    assert [i["type"] for i in canvas.selected_items] == ["room"]


def test_room_selectable_under_roof(canvas: CanvasArea) -> None:
    room = _make_room()
    canvas.rooms.append(room)
    canvas.roofs.append(_make_roof())
    _click_model_point(canvas, 100, 100)
    assert [i["type"] for i in canvas.selected_items] == ["room"]
    assert canvas.selected_items[0]["object"] is room


def test_roof_selected_where_nothing_beneath(canvas: CanvasArea) -> None:
    canvas.rooms.append(_make_room())
    roof = _make_roof()
    canvas.roofs.append(roof)
    _click_model_point(canvas, 210, 210)
    assert [i["type"] for i in canvas.selected_items] == ["roof"]
    assert canvas.selected_items[0]["object"] is roof


def test_room_can_be_dragged_after_click(canvas: CanvasArea) -> None:
    room = _make_room()
    canvas.rooms.append(room)
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    dev_x, dev_y = canvas.model_to_device(100, 100, ppi)
    gesture = _fake_gesture()
    canvas._handle_pointer_click(gesture, 1, dev_x, dev_y)
    canvas.on_drag_begin(gesture, dev_x, dev_y)
    assert canvas.dragging_room is room
    canvas.on_drag_update(gesture, 40.0, 20.0)
    assert room.points[0] != (0, 0)
