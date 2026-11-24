import math
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
import cairo  # noqa: E402
from gi.repository import Gdk  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.Canvas.wall_room_renderer import draw_walls  # noqa: E402
from EstiSketch.Dialogs.properties_dock import WallPropertiesWidget  # noqa: E402
from EstiSketch.Takeoff.building_takeoff import (  # noqa: E402
    extract_wall_finishes,
    generate_wall_finish_report,
    get_supplier_quote_items,
)
from EstiSketch.components import Wall, Room, Door, Window  # noqa: E402
from EstiSketch.project_io import save_project, open_project  # noqa: E402


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    return canvas_area.create_canvas_area(cfg)


def test_wall_per_side_defaults():
    w = Wall((0, 0), (120, 0), width=5.5, height=96.0)
    assert w.left_finish == "Drywall"
    assert w.right_finish == "Drywall"
    assert w.left_color is None
    assert w.right_color is None
    assert w.left_baseboard is False
    assert w.right_baseboard is False


def test_wall_per_side_xml_roundtrip_and_legacy():
    c = _make_canvas()
    w = Wall((0, 0), (120, 0), width=5.5, height=96.0, identifier="w-side-1", layer_id=c.active_layer_id)
    w.left_finish = "Vinyl Siding"
    w.right_finish = "Tile"
    w.left_color = (0.2, 0.4, 0.8)
    w.right_color = None
    w.left_baseboard = False
    w.right_baseboard = True
    c.wall_sets = [[w]]

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        path = tf.name
    try:
        save_project(c, 800, 600, path)
        c2 = _make_canvas()
        open_project(c2, path)
        loaded = c2.wall_sets[0][0]
        assert loaded.left_finish == "Vinyl Siding"
        assert loaded.right_finish == "Tile"
        assert loaded.left_color is not None
        assert loaded.left_color[0] == pytest.approx(0.2, abs=0.01)
        assert loaded.left_color[1] == pytest.approx(0.4, abs=0.01)
        assert loaded.left_color[2] == pytest.approx(0.8, abs=0.01)
        assert loaded.right_color is None
        assert loaded.left_baseboard is False
        assert loaded.right_baseboard is True
    finally:
        if os.path.exists(path):
            os.remove(path)

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as tf:
        tf.write(
            '<Project window_width="800" window_height="600"><Levels/><Layers/>'
            '<WallSets><WallSet><Wall identifier="w-old">'
            '<Start x="0" y="0"/><End x="120" y="0"/><Width>5.5</Width><Height>96</Height>'
            '</Wall></WallSet></WallSets></Project>'
        )
        legacy_path = tf.name
    try:
        c3 = _make_canvas()
        open_project(c3, legacy_path)
        old_w = c3.wall_sets[0][0]
        assert old_w.left_finish == "Drywall"
        assert old_w.right_finish == "Drywall"
        assert old_w.left_color is None
        assert old_w.right_color is None
        assert old_w.left_baseboard is False
        assert old_w.right_baseboard is False
    finally:
        if os.path.exists(legacy_path):
            os.remove(legacy_path)


def test_extract_wall_finishes_areas_baseboards_and_quote():
    c = _make_canvas()
    # 10' x 10' room polygon (clockwise in screen coords: left normal points inside!)
    # Wait: for (0,0)->(120,0), left normal (-dy, dx) = (0, +120) -> inside (0..120, 0..120)
    # So Left is interior, Right is exterior.
    w = Wall((0.0, 0.0), (120.0, 0.0), width=5.5, height=96.0, identifier="w-ext", layer_id=c.active_layer_id)
    w.left_finish = "Painted Drywall"
    w.right_finish = "Hardie Lap Siding"
    w.left_baseboard = True
    w.right_baseboard = False

    # Partition wall completely inside the room: both faces are interior, one has "None" finish
    p = Wall((60.0, 10.0), (60.0, 110.0), width=4.5, height=96.0, identifier="w-int", layer_id=c.active_layer_id)
    p.left_finish = "Drywall"
    p.right_finish = "None"
    p.left_baseboard = True
    p.right_baseboard = True

    c.wall_sets = [[w], [p]]
    c.rooms = [Room([(0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0)], identifier="r1")]

    # Door (36" x 80") and Window (48" x 36") on w
    door = Door("single", 36.0, 80.0, "left", "in", identifier="d1")
    win = Window(48.0, 36.0, "sliding", identifier="win1")
    c.doors = [(w, door, 0.25)]
    c.windows = [(w, win, 0.75)]

    res = extract_wall_finishes(c)
    # w: interior centerline 10' * 8' = 80 sf; exterior extended by 5.5" corner = (10 + 5.5/12) * 8
    # openings = (36*80 + 48*36)/144 = 20 + 12 = 32 sf
    # p: 100" = 8.3333' * 8' = 66.6667 sf; right side is "None" so skipped
    w_int_net = 80.0 - 32.0
    w_ext_net = (10.0 + 5.5 / 12.0) * 8.0 - 32.0
    p_net = (100.0 / 12.0) * 8.0
    assert res["exterior_surface_sqft"] == pytest.approx(w_ext_net)
    assert res["interior_surface_sqft"] == pytest.approx(w_int_net + p_net)
    assert res["exterior_by_finish"]["Hardie Lap Siding"] == pytest.approx(w_ext_net)
    assert res["interior_by_finish"]["Painted Drywall"] == pytest.approx(w_int_net)
    assert res["interior_by_finish"]["Drywall"] == pytest.approx(p_net)
    assert "None" not in res["interior_by_finish"]

    # Baseboard: w has left_baseboard only -> 10' - 3' door = 7' (window NOT deducted)
    # p has both sides -> 2 * (100/12) ft
    expected_bb = (10.0 - 3.0) + 2.0 * (100.0 / 12.0)
    assert res["baseboard_linear_ft"] == pytest.approx(expected_bb)

    report = generate_wall_finish_report(c)
    assert "PER-SIDE WALL FINISHES & BASEBOARDS REPORT" in report
    assert "Hardie Lap Siding" in report
    assert "Painted Drywall" in report

    items = get_supplier_quote_items(c, SimpleNamespace(**config.DEFAULT_SETTINGS))
    descs = {it["description"]: it for it in items}
    assert descs["Interior Wall Finish (Painted Drywall)"]["qty"] == math.ceil(w_int_net * 1.10 - 1e-9)
    assert descs["Exterior Wall Finish (Hardie Lap Siding)"]["qty"] == math.ceil(w_ext_net * 1.10 - 1e-9)
    assert descs["Baseboard Molding (16' Sticks)"]["qty"] == math.ceil((expected_bb * 1.10) / 16.0 - 1e-9)


def test_wall_properties_widget_per_side_controls():
    w_ui = WallPropertiesWidget()
    w_ui.canvas = SimpleNamespace(
        queue_draw=lambda: None,
        recalculate_roofs_for_wall=lambda wid: None,
        save_state=lambda: None,
    )
    wall = Wall((0, 0), (120, 0), width=5.5, height=96.0, identifier="w-ui")
    w_ui.set_wall(wall)

    w_ui.left_finish_combo.set_active(3)  # "Tile"
    w_ui.right_finish_combo.set_active(6)  # "Vinyl Siding"
    assert wall.left_finish == "Tile"
    assert wall.right_finish == "Vinyl Siding"

    rgba = Gdk.RGBA()
    rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.8, 0.2, 0.1, 1.0
    w_ui.left_color_btn.set_rgba(rgba)
    w_ui.on_left_color_changed(w_ui.left_color_btn)
    assert wall.left_color == pytest.approx((0.8, 0.2, 0.1))

    w_ui.left_baseboard_check.set_active(True)
    assert wall.left_baseboard is True
    assert wall.right_baseboard is False

    w_ui.on_swap_wall_sides(None)
    assert wall.left_finish == "Vinyl Siding"
    assert wall.right_finish == "Tile"
    assert wall.left_color is None
    assert wall.right_color == pytest.approx((0.8, 0.2, 0.1))
    assert wall.left_baseboard is False
    assert wall.right_baseboard is True

    w_ui.on_clear_right_color(None)
    assert wall.right_color is None


def test_draw_walls_renders_per_side_accents():
    def _render(wall):
        c = _make_canvas()
        c.wall_sets = [[wall]]
        c.walls = []
        c.current_wall = None
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
        cr = cairo.Context(surf)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        draw_walls(c, cr)
        surf.flush()
        return bytes(surf.get_data())

    plain = Wall((20.0, 50.0), (180.0, 50.0), width=8.0, height=96.0, identifier="w-plain")
    styled = Wall((20.0, 50.0), (180.0, 50.0), width=8.0, height=96.0, identifier="w-styled")
    styled.left_color = (0.9, 0.2, 0.2)
    styled.right_baseboard = True

    assert _render(plain) != _render(styled)
