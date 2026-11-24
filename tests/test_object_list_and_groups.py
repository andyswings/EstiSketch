"""Tests for the All Objects list, object metadata (name/comment/layer/level), and ObjectGroup manipulation."""

import math
import os
import sys
from types import SimpleNamespace

import cairo
import gi
gi.require_version("Gtk", "4.0")

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.Dialogs.layers_panel import LayersPanel
from EstiSketch.components import (
    Arc,
    Circle,
    Dimension,
    DimensionChain,
    Door,
    LeaderCallout,
    ObjectGroup,
    Polyline,
    Room,
    Stair,
    Text,
    Wall,
    Window,
)
from EstiSketch.project_io import open_project, save_project
from EstiSketch.roof_components import Roof, RoofLine


def _make_canvas():
    cfg = SimpleNamespace(
        DEFAULT_ZOOM_LEVEL=1.0,
        PIXELS_PER_INCH=2.0,
        WINDOW_WIDTH=1024,
        WINDOW_HEIGHT=768,
        SNAP_ENABLED=True,
        SNAP_THRESHOLD=10.0,
        UNDO_REDO_LIMIT=50,
        DEFAULT_LEVEL_HEIGHT=96.0,
        SHOW_RULERS=False,
        DEBUG=False,
        LAYER_FOCUS_MODE=False,
    )
    return CanvasArea(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Object Enumeration, Metadata, Layer/Level Moving & Deletion
# ─────────────────────────────────────────────────────────────────────────────


def test_get_all_objects_and_lookup_across_layers():
    canvas = _make_canvas()
    layer0 = canvas.active_layer_id
    lvl2_id = canvas.add_level("Level 2")
    layer2 = canvas.add_layer("Upper Walls", level_id=lvl2_id)

    w1 = Wall((0, 0), (120, 0), 6.0, 96.0, layer_id=layer0, custom_name="North Wall", comment="Load bearing")
    w2 = Wall((0, 0), (0, 100), 4.5, 96.0, layer_id=layer2)
    room = Room([(0, 0), (120, 0), (120, 100), (0, 100)], layer_id=layer0, custom_name="Kitchen", comment="Tile floor")
    door = Door("single", 36.0, 80.0, "left", "inswing", layer_id=layer0, comment="Front entry")
    win = Window(36.0, 48.0, "sliding", layer_id=layer0)
    txt = Text(10, 10, "Note", layer_id=layer0)
    dim = Dimension((0, 0), (120, 0), 12.0, layer_id=layer0)
    chain = DimensionChain(points=[(0, 0), (60, 0), (120, 0)], layer_id=layer0)
    leader = LeaderCallout(tip=(10, 10), elbow=(20, 20), shoulder=(40, 20), text="Beam", layer_id=layer0)
    pl = Polyline((0, 0), (50, 50), layer_id=layer0)
    circ = Circle((50, 50), 20.0, layer_id=layer0)
    arc = Arc((50, 50), 20.0, 0.0, math.pi / 2, layer_id=layer0)
    roof = Roof(layer_id=layer2, roof_type="gable", outline_points=[(0, 0), (100, 0), (100, 100), (0, 100)])
    stair = Stair(layer_id=layer0, start_point=(20, 20))

    canvas.wall_sets.append([w1])
    canvas.wall_sets.append([w2])
    canvas.rooms.append(room)
    canvas.doors.append((w1, door, 0.5))
    canvas.windows.append((w1, win, 0.25))
    canvas.texts.append(txt)
    canvas.dimensions.append(dim)
    canvas.dimension_chains.append(chain)
    canvas.leader_callouts.append(leader)
    canvas.polyline_sets.append([pl])
    canvas.circles.append(circ)
    canvas.arcs.append(arc)
    canvas.roofs.append(roof)
    canvas.stairs.append(stair)

    all_objs = canvas.get_all_objects()
    assert len(all_objs) == 14
    types_present = {t for t, _ in all_objs}
    assert types_present == {
        "wall",
        "room",
        "door",
        "window",
        "text",
        "dimension",
        "dimension_chain",
        "leader_callout",
        "polyline",
        "circle",
        "arc",
        "roof",
        "stair",
    }

    found = canvas.find_object_by_id(w1.identifier)
    assert found == ("wall", w1)
    assert canvas.find_object_by_id("nonexistent") is None


def test_move_object_between_layers_and_levels():
    canvas = _make_canvas()
    layer0 = canvas.active_layer_id
    lvl2_id = canvas.add_level("Second Floor")
    layer_extra = canvas.add_layer("Electrical", level_id=canvas.active_level_id)

    w = Wall((0, 0), (120, 0), 6.0, 96.0, layer_id=layer0)
    stair = Stair(layer_id=layer0, start_point=(10, 10), start_level_id=canvas.active_level_id)
    canvas.wall_sets.append([w])
    canvas.stairs.append(stair)

    # Move to another layer on same level
    assert canvas.move_object_to_layer(w, layer_extra) is True
    assert w.layer_id == layer_extra

    # Move to Level 2 (should auto-create a layer for Level 2 since none exists yet)
    assert canvas.move_object_to_level(w, lvl2_id) is True
    moved_layer = canvas.get_layer_by_id(w.layer_id)
    assert moved_layer is not None
    assert moved_layer.level_id == lvl2_id

    # Move stair to Level 2 -> updates start_level_id as well
    assert canvas.move_object_to_level(stair, lvl2_id) is True
    assert stair.start_level_id == lvl2_id

    # Move to Global ("")
    assert canvas.move_object_to_level(w, "") is True
    global_layer = canvas.get_layer_by_id(w.layer_id)
    assert global_layer is not None
    assert global_layer.level_id == ""


def test_delete_single_object_prunes_selection_and_groups():
    canvas = _make_canvas()
    w1 = Wall((0, 0), (100, 0), 6.0, 96.0, layer_id=canvas.active_layer_id)
    w2 = Wall((100, 0), (100, 100), 6.0, 96.0, layer_id=canvas.active_layer_id)
    canvas.wall_sets.append([w1, w2])
    canvas.selected_items = [
        {"type": "wall", "object": w1},
        {"type": "wall", "object": w2},
    ]
    grp = canvas.group_selected("Walls Group")
    assert grp is not None

    assert canvas.delete_object("wall", w1) is True
    assert w1 not in canvas.wall_sets[0]
    assert grp.member_ids == [w2.identifier]

    assert canvas.delete_object("wall", w2) is True
    assert canvas.wall_sets == []
    assert canvas.groups == []  # Empty group auto-pruned


# ─────────────────────────────────────────────────────────────────────────────
# 2. ObjectGroup Unit Manipulation (Move, Rotate, Lock, Hide, Delete, Undo)
# ─────────────────────────────────────────────────────────────────────────────


def test_group_creation_translation_and_rotation():
    canvas = _make_canvas()
    w = Wall((0.0, 0.0), (100.0, 0.0), 6.0, 96.0, layer_id=canvas.active_layer_id)
    door = Door("single", 36.0, 80.0, "left", "inswing", layer_id=canvas.active_layer_id)
    txt = Text(50.0, 20.0, "Label", layer_id=canvas.active_layer_id, rotation=15.0)
    circ = Circle((100.0, 100.0), 10.0, layer_id=canvas.active_layer_id)
    arc = Arc((0.0, 100.0), 10.0, 0.0, math.pi / 2, layer_id=canvas.active_layer_id)
    stair = Stair(layer_id=canvas.active_layer_id, start_point=(20.0, 40.0), direction_angle=0.0)
    roof = Roof(
        layer_id=canvas.active_layer_id,
        outline_points=[(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)],
        manual_lines=[RoofLine(start=(0.0, 50.0), end=(100.0, 50.0))],
    )

    canvas.wall_sets.append([w])
    canvas.doors.append((w, door, 0.5))
    canvas.texts.append(txt)
    canvas.circles.append(circ)
    canvas.arcs.append(arc)
    canvas.stairs.append(stair)
    canvas.roofs.append(roof)

    # Requires at least 2 objects
    canvas.selected_items = [{"type": "wall", "object": w}]
    assert canvas.group_selected() is None

    # Group all of them
    canvas.selected_items = [
        {"type": "wall", "object": w},
        {"type": "door", "object": (w, door, 0.5)},
        {"type": "text", "object": txt},
        {"type": "circle", "object": circ},
        {"type": "arc", "object": arc},
        {"type": "stair", "object": stair},
        {"type": "roof", "object": roof},
    ]
    grp = canvas.group_selected("Assembly A")
    assert grp is not None
    assert grp.identifier.startswith("group-")
    assert len(grp.member_ids) == 7

    # Translate by (+30, -10)
    assert canvas.translate_group(grp, 30.0, -10.0) is True
    assert w.start == pytest.approx((30.0, -10.0))
    assert w.end == pytest.approx((130.0, -10.0))
    assert (txt.x, txt.y) == pytest.approx((80.0, 10.0))
    assert circ.center == pytest.approx((130.0, 90.0))
    assert arc.center == pytest.approx((30.0, 90.0))
    assert stair.start_point == pytest.approx((50.0, 30.0))
    assert roof.outline_points[0] == pytest.approx((30.0, -10.0))
    assert roof.manual_lines[0].start == pytest.approx((30.0, 40.0))

    # Rotate 4 x 90 degrees around a fixed pivot -> returns to exact same state
    orig_w_start = w.start
    orig_txt_pos = (txt.x, txt.y)
    orig_txt_rot = txt.rotation
    orig_arc_start = arc.start_angle
    orig_stair_dir = stair.direction_angle

    pivot = (50.0, 50.0)
    for _ in range(4):
        assert canvas.rotate_group(grp, 90.0, pivot=pivot, save_undo=False) is True

    assert w.start == pytest.approx(orig_w_start, abs=1e-6)
    assert (txt.x, txt.y) == pytest.approx(orig_txt_pos, abs=1e-6)
    assert txt.rotation == pytest.approx(orig_txt_rot, abs=1e-6)
    assert arc.start_angle == pytest.approx(orig_arc_start + 2 * math.pi, abs=1e-6)
    assert stair.direction_angle == pytest.approx(orig_stair_dir + 2 * math.pi, abs=1e-6)


def test_group_lock_hide_ungroup_delete_and_undo():
    canvas = _make_canvas()
    w1 = Wall((0, 0), (100, 0), 6.0, 96.0, layer_id=canvas.active_layer_id)
    w2 = Wall((100, 0), (100, 100), 6.0, 96.0, layer_id=canvas.active_layer_id)
    canvas.wall_sets.append([w1, w2])
    canvas.save_state()

    canvas.selected_items = [
        {"type": "wall", "object": w1},
        {"type": "wall", "object": w2},
    ]
    grp = canvas.group_selected("Corner")
    assert grp is not None

    # Lock group -> blocks translate, rotate, delete, and deselects
    canvas.set_group_locked(grp, True)
    assert grp.locked is True
    assert w1.locked is True and w2.locked is True
    assert canvas.selected_items == []
    assert canvas.translate_group(grp, 50.0, 50.0) is False
    assert canvas.rotate_group(grp, 90.0) is False
    assert canvas.delete_group(grp) is False
    assert w1.start == (0, 0)

    # Unlock group -> allows manipulation again
    canvas.set_group_locked(grp, False)
    assert canvas.translate_group(grp, 10.0, 20.0) is True
    assert w1.start == (10.0, 20.0)

    # Hide group -> hides all members and makes them non-visible
    canvas.select_group(grp)
    assert len(canvas.selected_items) == 2
    canvas.set_group_visible(grp, False)
    assert grp.visible is False
    assert canvas.is_object_on_visible_layer(w1) is False
    assert canvas.selected_items == []
    canvas.set_group_visible(grp, True)
    assert canvas.is_object_on_visible_layer(w1) is True

    # Delete group -> deletes members + group, undo restores both
    assert canvas.delete_group(grp) is True
    assert canvas.wall_sets == []
    assert canvas.groups == []

    canvas.undo()
    assert len(canvas.groups) == 1
    assert len(canvas.wall_sets) == 1
    assert len(canvas.wall_sets[0]) == 2

    # Ungroup -> keeps objects, removes group
    assert canvas.ungroup(canvas.groups[0]) is True
    assert canvas.groups == []
    assert len(canvas.wall_sets[0]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Project IO Round-Trip (custom_name, comment, visible, locked, Groups)
# ─────────────────────────────────────────────────────────────────────────────


def test_project_io_roundtrip_metadata_and_groups(tmp_path):
    canvas = _make_canvas()
    layer0 = canvas.active_layer_id

    w = Wall((0, 0), (144, 0), 6.0, 96.0, layer_id=layer0, custom_name="Main Beam Wall", comment="2x6 framing")
    w.locked = True
    room = Room([(0, 0), (144, 0), (144, 120), (0, 120)], layer_id=layer0, custom_name="Great Room", comment="Oak floor")
    room.visible = False
    txt = Text(20, 30, "Callout", layer_id=layer0, rotation=45.0, custom_name="Title", comment="Keep centered")
    circ = Circle((60, 60), 18.0, layer_id=layer0, custom_name="Column", comment="Steel post")

    canvas.wall_sets.append([w])
    canvas.rooms.append(room)
    canvas.texts.append(txt)
    canvas.circles.append(circ)

    grp = ObjectGroup(
        name="Living Core",
        custom_name="Living Core",
        comment="Do not shift",
        member_ids=[w.identifier, room.identifier, txt.identifier],
        layer_id=layer0,
        visible=True,
        locked=False,
    )
    canvas.groups.append(grp)

    out_file = tmp_path / "test_meta_groups.esk"
    save_project(canvas, 1024, 768, str(out_file))

    loaded = _make_canvas()
    open_project(loaded, str(out_file))

    lw = loaded.wall_sets[0][0]
    assert lw.custom_name == "Main Beam Wall"
    assert lw.comment == "2x6 framing"
    assert lw.locked is True
    assert lw.visible is True

    lr = loaded.rooms[0]
    assert lr.custom_name == "Great Room"
    assert lr.comment == "Oak floor"
    assert lr.visible is False

    lt = loaded.texts[0]
    assert lt.custom_name == "Title"
    assert lt.comment == "Keep centered"
    assert lt.rotation == pytest.approx(45.0)

    lc = loaded.circles[0]
    assert lc.custom_name == "Column"
    assert lc.comment == "Steel post"

    assert len(loaded.groups) == 1
    lg = loaded.groups[0]
    assert lg.identifier == grp.identifier
    assert lg.custom_name == "Living Core"
    assert lg.comment == "Do not shift"
    assert lg.member_ids == [w.identifier, room.identifier, txt.identifier]
    assert lg.identifier in loaded.existing_ids


# ─────────────────────────────────────────────────────────────────────────────
# 4. LayersPanel Objects View & Group Overlay Rendering
# ─────────────────────────────────────────────────────────────────────────────


def test_layers_panel_objects_view_search_and_filter():
    canvas = _make_canvas()
    w1 = Wall((0, 0), (120, 0), 6.0, 96.0, layer_id=canvas.active_layer_id, custom_name="South Wall", comment="Needs insulation")
    c1 = Circle((50, 50), 12.0, layer_id=canvas.active_layer_id, custom_name="Pier Footing", comment="Concrete")
    canvas.wall_sets.append([w1])
    canvas.circles.append(c1)

    panel = LayersPanel(canvas)
    # Switch to Objects view
    panel.objects_tab_btn.set_active(True)
    assert panel.view_stack.get_visible_child_name() == "objects"

    def count_children(box):
        n = 0
        ch = box.get_first_child()
        while ch is not None:
            n += 1
            ch = ch.get_next_sibling()
        return n

    # Header + 2 object rows = 3 children
    assert count_children(panel.all_objects_box) == 3

    # Search by comment text ("insulation") -> Header + 1 matching row = 2 children
    panel.obj_search_entry.set_text("insulation")
    panel.refresh_objects_list()
    assert count_children(panel.all_objects_box) == 2

    # Clear search, filter by Walls -> Header + 1 wall = 2 children
    panel.obj_search_entry.set_text("")
    panel.obj_type_dropdown.set_selected(1)  # "Walls"
    panel.refresh_objects_list()
    assert count_children(panel.all_objects_box) == 2


def test_draw_group_overlays_renders_cleanly():
    canvas = _make_canvas()
    w1 = Wall((0, 0), (100, 0), 6.0, 96.0, layer_id=canvas.active_layer_id)
    w2 = Wall((100, 0), (100, 100), 6.0, 96.0, layer_id=canvas.active_layer_id)
    canvas.wall_sets.append([w1, w2])
    canvas.selected_items = [
        {"type": "wall", "object": w1},
        {"type": "wall", "object": w2},
    ]
    grp = canvas.group_selected("Render Group")
    assert grp is not None

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 400)
    cr = cairo.Context(surface)
    canvas.draw_group_overlays(cr, 2.0)
