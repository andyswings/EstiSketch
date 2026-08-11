from types import SimpleNamespace
import gi
gi.require_version("Gtk", "4.0")
import pytest
from EstiSketch.components import Room
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch import config

@pytest.fixture
def canvas():
    cfg = SimpleNamespace(**config.load_config())
    return CanvasArea(cfg)

def test_room_deletion(canvas):
    room = Room([(0, 0), (100, 0), (100, 100), (0, 100)])
    room.name = "Test Room"
    canvas.rooms.append(room)
    assert len(canvas.rooms) == 1

    # Select whole room
    canvas.selected_items = [{"type": "room", "object": room}]

    # Delete selected
    canvas.delete_selected()

    # Room should be removed from canvas.rooms
    assert len(canvas.rooms) == 0
    assert len(canvas.selected_items) == 0

def test_room_vertex_deletion(canvas):
    room = Room([(0, 0), (100, 0), (100, 100), (0, 100)])
    room.name = "Test Room"
    canvas.rooms.append(room)
    assert len(canvas.rooms) == 1

    # Select single vertex (index 2)
    canvas.selected_items = [{"type": "vertex", "object": (room, 2)}]

    # Delete selected vertex
    canvas.delete_selected()

    # Room should remain with 3 points
    assert len(canvas.rooms) == 1
    assert len(room.points) == 3

    # Select another vertex, reducing points to 2 (<3)
    canvas.selected_items = [{"type": "vertex", "object": (room, 0)}]
    canvas.delete_selected()

    # Room with < 3 points should be removed automatically
    assert len(canvas.rooms) == 0

def test_handle_polyline_click_hints(canvas):
    # Verify _handle_polyline_click does not raise UnboundLocalError for TOOL_HINTS
    canvas.tool_mode = "add_polyline"
    canvas._handle_polyline_click(1, 10.0, 10.0)
    assert canvas.drawing_polyline is True
    canvas._handle_polyline_click(1, 50.0, 50.0)
    assert len(canvas.polylines) == 1
    canvas._handle_polyline_click(2, 50.0, 50.0)
    assert canvas.drawing_polyline is False
