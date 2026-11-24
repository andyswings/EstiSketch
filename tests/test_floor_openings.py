import math
import os
import sys
from types import SimpleNamespace

import cairo
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.Dialogs.layers_panel import LayersPanel  # noqa: E402
from EstiSketch.Dialogs.properties_dock import PropertiesDock  # noqa: E402
from EstiSketch.Printing.print_renderer import export_svg  # noqa: E402
from EstiSketch.Printing.print_settings import PrintSettings  # noqa: E402
from EstiSketch.Takeoff.building_takeoff import (  # noqa: E402
    extract_room_areas,
    generate_room_area_report,
)
from EstiSketch.components import FloorOpening, Room, Stair  # noqa: E402
from EstiSketch.geometry.room_holes import (  # noqa: E402
    OPENING_SOURCE_PREFIX,
    is_convex_polygon,
    opening_source_id,
    polygon_area,
    room_ceiling_area_sqft,
    room_floor_area_sqft,
    room_slab_volume_cuft,
    sync_stair_holes,
    triangulate_polygon,
)
from EstiSketch.project_io import open_project, save_project  # noqa: E402


def _make_canvas():
    cfg_dict = config.DEFAULT_SETTINGS.copy()
    cfg = SimpleNamespace(**cfg_dict)
    canvas = CanvasArea(cfg)
    canvas.set_size_request(800, 600)
    return canvas


def _add_rect_room(canvas, x0, y0, x1, y1, layer_id=None, is_slab=False):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    room = Room(
        pts,
        layer_id=layer_id or canvas.active_layer_id,
        identifier=f"room_{len(canvas.rooms) + 1}",
    )
    room.is_slab = is_slab
    room.slab_thickness = 4.0
    canvas.rooms.append(room)
    return room


def test_floor_opening_model_and_labels():
    op = FloorOpening([(0, 0), (48, 0), (48, 48), (0, 48)])
    assert op.identifier.startswith("opening-")
    assert op.display_label == "OPEN TO BELOW"
    assert op.ceiling_only is False
    assert op.show_cross is True
    assert op.show_label is True
    assert opening_source_id(op) == f"{OPENING_SOURCE_PREFIX}{op.identifier}"

    op.opening_type = "atrium"
    assert op.display_label == "ATRIUM"

    op.opening_type = "elevator"
    assert op.display_label == "ELEVATOR"

    op.label = "GRAND ATRIUM"
    assert op.display_label == "GRAND ATRIUM"

    co = FloorOpening([(0, 0), (24, 0), (24, 24), (0, 24)], ceiling_only=True)
    assert co.display_label == "CEILING OPENING"


def test_triangulate_polygon_convex_and_concave_l_shape():
    rect = [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)]
    assert is_convex_polygon(rect) is True
    assert len(triangulate_polygon(rect)) == 1

    # Concave L-shape: 120x120 outer minus 60x60 top-right corner = 10800 sq in
    l_shape = [(0.0, 0.0), (120.0, 0.0), (120.0, 60.0), (60.0, 60.0), (60.0, 120.0), (0.0, 120.0)]
    assert is_convex_polygon(l_shape) is False
    tris = triangulate_polygon(l_shape)
    assert len(tris) == 4
    assert math.isclose(sum(polygon_area(t) for t in tris), 10800.0, rel_tol=1e-6)


def test_sync_holes_cuts_rooms_takeoff_and_overlap_with_stairs():
    canvas = _make_canvas()
    # 20ft x 10ft room = 200 sq ft (with 4" concrete slab)
    r1 = _add_rect_room(canvas, 0.0, 0.0, 240.0, 120.0, is_slab=True)
    # Second adjacent 10ft x 10ft room = 100 sq ft
    r2 = _add_rect_room(canvas, 240.0, 0.0, 360.0, 120.0)

    # Lightwell spanning boundary (x=216..264 = 4ft wide, y=24..72 = 4ft tall -> 16 sq ft total,
    # splitting 8 sq ft out of r1 and 8 sq ft out of r2)
    op = FloorOpening(
        [(216.0, 24.0), (264.0, 24.0), (264.0, 72.0), (216.0, 72.0)],
        opening_type="lightwell",
        identifier="op_span",
        layer_id=canvas.active_layer_id,
    )
    canvas.floor_openings.append(op)

    changed = sync_stair_holes(canvas)
    assert changed is True
    assert math.isclose(room_floor_area_sqft(r1), 192.0, abs_tol=1e-4)
    assert math.isclose(room_ceiling_area_sqft(r1), 192.0, abs_tol=1e-4)
    assert math.isclose(room_floor_area_sqft(r2), 92.0, abs_tol=1e-4)
    assert math.isclose(room_slab_volume_cuft(r1), 192.0 * (4.0 / 12.0), abs_tol=1e-4)

    # Overlapping stair partially over the same region must NOT double-count deduction
    stair = Stair(
        start_point=(192.0, 48.0),
        direction_angle=0.0,
        width=48.0,  # y = 24..72, x = 192..240 -> 4ft x 4ft inside r1, overlaps 2ft x 4ft with op!
        total_run=48.0,
        end_level_id=canvas.active_level_id,
        identifier="st_1",
    )
    stair.opening_clearance = 0.0
    canvas.stairs.append(stair)
    sync_stair_holes(canvas)
    # Union in r1 covers x=192..240, y=24..72 = 16 sq ft -> net = 184 sq ft
    assert math.isclose(room_floor_area_sqft(r1), 184.0, abs_tol=1e-4)


def test_concave_opening_and_ceiling_only_and_level_isolation():
    canvas = _make_canvas()
    r1 = _add_rect_room(canvas, 0.0, 0.0, 240.0, 240.0, is_slab=True)  # 400 sq ft

    # Level 2 layer & room
    lv2_id = canvas.add_level("Level 2")
    l2_layer_id = canvas.add_layer("Layer L2", level_id=lv2_id)
    r2 = _add_rect_room(canvas, 0.0, 0.0, 120.0, 120.0, layer_id=l2_layer_id)  # 100 sq ft

    # Concave L-shaped opening on Level 2: 72x72 - 36x36 = 3888 sq in = 27 sq ft inside r2
    l_op = FloorOpening(
        [(0.0, 0.0), (72.0, 0.0), (72.0, 36.0), (36.0, 36.0), (36.0, 72.0), (0.0, 72.0)],
        opening_type="atrium",
        identifier="op_l",
        layer_id=l2_layer_id,
    )
    canvas.floor_openings.append(l_op)

    # Ceiling-only shaft on Level 1 (4ft x 6ft = 24 sq ft)
    c_op = FloorOpening(
        [(120.0, 120.0), (168.0, 120.0), (168.0, 192.0), (120.0, 192.0)],
        opening_type="shaft",
        ceiling_only=True,
        identifier="op_ceil",
        layer_id=canvas.active_layer_id,
    )
    canvas.floor_openings.append(c_op)

    sync_stair_holes(canvas)

    # Level 1 room: ceiling deducted by 24 sq ft, floor & slab untouched (still 400 sq ft)
    assert math.isclose(room_floor_area_sqft(r1), 400.0, abs_tol=1e-4)
    assert math.isclose(room_ceiling_area_sqft(r1), 376.0, abs_tol=1e-4)
    assert math.isclose(room_slab_volume_cuft(r1), 400.0 / 3.0, abs_tol=1e-4)

    # Level 2 room cut by Level 2 concave L-shaped atrium only (not affected by Level 1 op)
    assert math.isclose(room_floor_area_sqft(r2), 100.0 - 27.0, abs_tol=1e-4)

    # Takeoff integration check
    areas = extract_room_areas(canvas)
    by_id = {a["id"]: a for a in areas}
    assert math.isclose(by_id[r1.identifier]["floor_area_sqft"], 400.0, abs_tol=1e-4)
    assert math.isclose(by_id[r1.identifier]["ceiling_area_sqft"], 376.0, abs_tol=1e-4)
    assert math.isclose(by_id[r2.identifier]["floor_area_sqft"], 73.0, abs_tol=1e-4)
    report = generate_room_area_report(canvas)
    assert "400.0" in report


def test_interactive_draw_translate_delete_undo_redo():
    canvas = _make_canvas()
    canvas.snap_manager.snap_enabled = False
    _add_rect_room(canvas, 0.0, 0.0, 240.0, 240.0)  # 400 sq ft
    canvas.save_state()

    canvas.set_tool_mode("add_floor_opening")
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)

    def to_dev(mx, my):
        return (mx * canvas.zoom * ppi + canvas.offset_x, my * canvas.zoom * ppi + canvas.offset_y)

    # Draw 4ft x 4ft square (48..96) with double-click on final vertex (GTK sends n_press=1 then 2)
    corners = [(48.0, 48.0), (96.0, 48.0), (96.0, 96.0), (48.0, 96.0)]
    for mx, my in corners:
        dx, dy = to_dev(mx, my)
        canvas.on_click(None, 1, dx, dy)
    # Double click at final point
    dx, dy = to_dev(48.0, 96.0)
    canvas.on_click(None, 2, dx, dy)

    assert len(canvas.floor_openings) == 1
    op = canvas.floor_openings[0]
    assert len(op.points) == 4
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 384.0, abs_tol=1e-4)

    # Translate outside the room -> hole vanishes automatically
    canvas.translate_object("floor_opening", op, 500.0, 0.0)
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 400.0, abs_tol=1e-4)

    # Translate back -> hole returns
    canvas.translate_object("floor_opening", op, -500.0, 0.0)
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 384.0, abs_tol=1e-4)

    # Delete selected -> clears opening & room hole
    canvas.selected_items = [{"type": "floor_opening", "object": op}]
    canvas.delete_selected()
    canvas.save_state()
    assert len(canvas.floor_openings) == 0
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 400.0, abs_tol=1e-4)

    # Undo -> restores opening & cutout on canvas.rooms[0]
    canvas.undo()
    assert len(canvas.floor_openings) == 1
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 384.0, abs_tol=1e-4)

    # Redo -> removes opening again
    canvas.redo()
    assert len(canvas.floor_openings) == 0
    assert math.isclose(room_floor_area_sqft(canvas.rooms[0]), 400.0, abs_tol=1e-4)


def test_draw_scene_ghost_and_svg_export(tmp_path):
    canvas = _make_canvas()
    _add_rect_room(canvas, 0.0, 0.0, 240.0, 240.0)
    op = FloorOpening(
        [(48.0, 48.0), (144.0, 48.0), (144.0, 144.0), (48.0, 144.0)],
        opening_type="atrium",
        label="MAIN ATRIUM",
        layer_id=canvas.active_layer_id,
    )
    canvas.floor_openings.append(op)
    sync_stair_holes(canvas)

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 400)
    cr = cairo.Context(surf)
    canvas.draw_scene(cr, 1.0, 2.0, printing=False)
    canvas.draw_scene(cr, 1.0, 2.0, printing=True)

    # Render with selection overlay and preview
    canvas.selected_items = [{"type": "floor_opening", "object": op}]
    canvas.tool_mode = "add_floor_opening"
    canvas.current_opening_points = [(10.0, 10.0), (50.0, 10.0)]
    canvas.current_opening_preview = (50.0, 50.0)
    canvas.draw_scene(cr, 1.0, 2.0, printing=False)

    svg_path = tmp_path / "floor_opening.svg"
    export_svg(canvas, PrintSettings(), str(svg_path))
    assert svg_path.exists() and svg_path.stat().st_size > 200


def test_xml_save_and_open_roundtrip(tmp_path):
    canvas = _make_canvas()
    _add_rect_room(canvas, 0.0, 0.0, 240.0, 240.0)
    op = FloorOpening(
        [(24.0, 24.0), (96.0, 24.0), (96.0, 96.0), (24.0, 96.0)],
        opening_type="elevator",
        label="ELEV 1",
        ceiling_only=False,
        show_cross=True,
        show_label=True,
        identifier="op_roundtrip",
        layer_id=canvas.active_layer_id,
        custom_name="Service Elevator",
        comment="2-stop shaft",
    )
    canvas.floor_openings.append(op)
    sync_stair_holes(canvas)

    proj_file = tmp_path / "test_opening.estisketch"
    save_project(canvas, 1200, 800, str(proj_file))

    canvas2 = _make_canvas()
    open_project(canvas2, str(proj_file))

    assert len(canvas2.floor_openings) == 1
    loaded = canvas2.floor_openings[0]
    assert loaded.identifier == "op_roundtrip"
    assert loaded.opening_type == "elevator"
    assert loaded.label == "ELEV 1"
    assert loaded.ceiling_only is False
    assert loaded.show_cross is True
    assert loaded.show_label is True
    assert loaded.custom_name == "Service Elevator"
    assert loaded.comment == "2-stop shaft"
    assert len(loaded.points) == 4
    assert len(canvas2.rooms) == 1
    assert math.isclose(room_floor_area_sqft(canvas2.rooms[0]), 400.0 - 36.0, abs_tol=1e-4)


def test_properties_dock_and_layers_panel_integration():
    canvas = _make_canvas()
    room = _add_rect_room(canvas, 0.0, 0.0, 240.0, 240.0)
    op = FloorOpening(
        [(0.0, 0.0), (48.0, 0.0), (48.0, 48.0), (0.0, 48.0)],
        layer_id=canvas.active_layer_id,
    )
    canvas.floor_openings.append(op)
    sync_stair_holes(canvas)

    dock = PropertiesDock(canvas, canvas.config)
    dock.refresh_tabs([{"type": "floor_opening", "object": op}])
    assert dock.tabs["floor_opening"].get_sensitive() is True
    assert dock.tabs["floor_opening"].get_active() is True
    assert dock.stack.get_visible_child_name() == "floor_opening"

    dock.floor_opening_page.ceiling_only_check.set_active(True)
    assert op.ceiling_only is True
    # Floor area restored to 400 sq ft because opening switched to ceiling-only
    assert math.isclose(room_floor_area_sqft(room), 400.0, abs_tol=1e-4)
    assert math.isclose(room_ceiling_area_sqft(room), 384.0, abs_tol=1e-4)

    layers_panel = LayersPanel(canvas)
    # 1 room + 1 floor opening = 2 objects on default layer
    assert layers_panel.layer_count_buttons[canvas.active_layer_id].get_label() == "(2)"
    assert any(opt[1] == "floor_opening" for opt in layers_panel._type_filter_options)
    name = layers_panel._get_object_display_name("floor_opening", op)
    assert "Opening -" in name and "16.0 sq ft" in name
