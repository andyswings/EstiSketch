"""Headless tests for File > New canvas reset."""
from __future__ import annotations

from types import SimpleNamespace

from EstiSketch.Canvas.project_reset import (
    CONTENT_LIST_ATTRS,
    reset_canvas_content,
)
from EstiSketch.components import Layer, Level


def _dirty_canvas() -> SimpleNamespace:
    canvas = SimpleNamespace()
    for name in CONTENT_LIST_ATTRS:
        setattr(canvas, name, ["stale"])
    canvas.current_wall = object()
    canvas.drawing_wall = True
    canvas.ghost_level_id = "level-x"
    canvas.north_angle = 45.0
    canvas.print_settings = {"scale": 1}
    canvas.takeoff_state = {"assumptions": {"a": 1}}
    canvas.cut_lower_ceiling_under_stairs = True
    canvas._blueprint_surfaces = {"bp": object()}
    canvas.levels = [Level(id="l1"), Level(id="l2")]
    canvas.layers = [Layer(id="a"), Layer(id="b")]
    canvas.active_level_id = "l2"
    canvas.active_layer_id = "b"
    canvas.existing_ids = ["a", "b"]
    return canvas


def test_reset_clears_all_object_lists_in_place() -> None:
    canvas = _dirty_canvas()
    rooms = canvas.rooms
    reset_canvas_content(canvas)
    for name in CONTENT_LIST_ATTRS:
        assert getattr(canvas, name) == [], name
    assert rooms is canvas.rooms
    assert canvas._blueprint_surfaces == {}


def test_reset_restores_defaults_and_transient_state() -> None:
    canvas = _dirty_canvas()
    reset_canvas_content(canvas)
    assert canvas.current_wall is None
    assert canvas.drawing_wall is False
    assert canvas.ghost_level_id is None
    assert canvas.north_angle == 0.0
    assert canvas.print_settings is None
    assert canvas.cut_lower_ceiling_under_stairs is False
    assert canvas.takeoff_state["assumptions"] == {}
    assert len(canvas.levels) == 1 and len(canvas.layers) == 1
    assert canvas.active_level_id == canvas.levels[0].id
    assert canvas.active_layer_id == canvas.layers[0].id
    assert canvas.layers[0].level_id == canvas.levels[0].id
    assert set(canvas.existing_ids) == {canvas.levels[0].id, canvas.layers[0].id}
