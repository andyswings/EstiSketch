import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.Dialogs.layers_panel import LayersPanel  # noqa: E402
from EstiSketch.components import Wall, Room  # noqa: E402
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    return canvas_area.create_canvas_area(cfg)


def _children(box):
    out = []
    ch = box.get_first_child()
    while ch is not None:
        out.append(ch)
        ch = ch.get_next_sibling()
    return out


def test_layers_have_no_expanders_and_show_live_count_badges():
    c = _make_canvas()
    panel = LayersPanel(c)

    rows = _children(panel.layer_list)
    assert len(rows) == 1
    assert not isinstance(rows[0], Gtk.Expander)
    assert isinstance(rows[0], Gtk.Box)

    l0_id = c.layers[0].id
    assert panel.layer_count_buttons[l0_id].get_label() == "(0)"

    w1 = Wall((0, 0), (120, 0), width=5.5, height=96.0, identifier="w1", layer_id=l0_id)
    r1 = Room([(0, 0), (120, 0), (120, 120), (0, 120)], identifier="r1", layer_id=l0_id)
    c.wall_sets = [[w1]]
    c.rooms = [r1]
    c.emit("content-changed")

    assert panel.layer_count_buttons[l0_id].get_label() == "(2)"


def test_clicking_count_badge_and_layer_filter_in_objects_tab():
    c = _make_canvas()
    l1_id = c.layers[0].id
    l2_id = c.add_layer("Layer 2", level_id=c.active_level_id)

    w1 = Wall((0, 0), (100, 0), width=5.5, height=96.0, identifier="w1", custom_name="Wall L1", layer_id=l1_id)
    w2 = Wall((0, 50), (100, 50), width=5.5, height=96.0, identifier="w2", custom_name="Wall L2", layer_id=l2_id)
    w_un = Wall((0, 100), (100, 100), width=5.5, height=96.0, identifier="w3", custom_name="Wall Unassigned", layer_id="")
    c.wall_sets = [[w1], [w2], [w_un]]

    panel = LayersPanel(c)
    assert panel.layer_count_buttons[l1_id].get_label() == "(1)"
    assert panel.layer_count_buttons[l2_id].get_label() == "(1)"

    # Click Layer 2's count badge -> jumps to Objects tab filtered to Layer 2
    panel.layer_count_buttons[l2_id].emit("clicked")
    assert panel.view_stack.get_visible_child_name() == "objects"
    assert panel.objects_tab_btn.get_active() is True
    # Only the heading + 1 object row for Wall L2
    obj_children = _children(panel.all_objects_box)
    assert len(obj_children) == 2
    assert obj_children[0].get_text() == "Objects (1)"

    # Filter to Unassigned
    unassigned_idx = next(
        i for i, (_, k) in enumerate(panel._layer_filter_options) if k == "__unassigned__"
    )
    panel.obj_layer_dropdown.set_selected(unassigned_idx)
    assert _children(panel.all_objects_box)[0].get_text() == "Objects (1)"

    # Filter back to All Layers
    panel.obj_layer_dropdown.set_selected(0)
    assert _children(panel.all_objects_box)[0].get_text() == "Objects (3)"


def test_split_selected_wall_preserves_layer_finishes_and_sloped_height():
    c = _make_canvas()
    lid = c.layers[0].id
    wall = Wall(
        (0.0, 0.0),
        (120.0, 0.0),
        width=5.5,
        height=96.0,
        height_at_end=144.0,
        exterior_wall=True,
        identifier="w-orig",
        layer_id=lid,
    )
    wall.left_finish = "Tile"
    wall.right_finish = "Stucco"
    wall.left_color = (0.3, 0.5, 0.7)
    wall.right_color = (0.9, 0.9, 0.8)
    wall.left_baseboard = True
    wall.right_baseboard = False
    wall.footer = True
    wall.footer_depth = 12.0

    c.wall_sets = [[wall]]
    c.selected_items = [{"type": "wall", "object": wall}]

    c.split_wall(None)

    assert len(c.wall_sets[0]) == 2
    w1, w2 = c.wall_sets[0]
    for sub in (w1, w2):
        assert sub.layer_id == lid
        assert sub.left_finish == "Tile"
        assert sub.right_finish == "Stucco"
        assert sub.left_color == (0.3, 0.5, 0.7)
        assert sub.right_color == (0.9, 0.9, 0.8)
        assert sub.left_baseboard is True
        assert sub.right_baseboard is False
        assert sub.footer is True
        assert sub.footer_depth == 12.0
    assert w1.height == pytest.approx(96.0)
    assert w1.height_at_end == pytest.approx(120.0)
    assert w2.height == pytest.approx(120.0)
    assert w2.height_at_end == pytest.approx(144.0)


def test_open_project_syncs_layers_panel_count_badges():
    c = _make_canvas()
    panel = LayersPanel(c)
    startup_layer_id = c.layers[0].id

    open_project(c, FIXTURE)
    panel.refresh_level_ui()
    panel.refresh_layers()

    loaded_layer_id = c.layers[0].id
    assert loaded_layer_id != startup_layer_id
    assert loaded_layer_id in panel.layer_count_buttons
    expected_count = len(c.get_objects_by_layer_id(loaded_layer_id))
    assert expected_count > 0
    assert panel.layer_count_buttons[loaded_layer_id].get_label() == f"({expected_count})"
