import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
import cairo  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.Canvas.floor_patterns import FLOOR_PATTERNS  # noqa: E402
from EstiSketch.Canvas.wall_room_renderer import draw_rooms  # noqa: E402
from EstiSketch.Dialogs.properties_dock import RoomPropertiesWidget  # noqa: E402
from EstiSketch.Printing.print_settings import PrintSettings  # noqa: E402
from EstiSketch.Printing import print_renderer as pr  # noqa: E402
from EstiSketch.components import Room, Hole  # noqa: E402
from EstiSketch.project_io import save_project, open_project  # noqa: E402


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    return canvas_area.create_canvas_area(cfg)


def _render_room_bytes(room, width=240, height=240):
    c = _make_canvas()
    c.tool_mode = ""
    c.current_room_points = []
    c.rooms = [room]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    draw_rooms(c, cr, 1.0)
    surf.flush()
    return bytes(surf.get_data())


def _interior_distinct_colors(buf, width=240, x0=30, x1=210, y0=30, y1=210):
    colors = set()
    stride = width * 4
    for y in range(y0, y1, 2):
        row = y * stride
        for x in range(x0, x1, 2):
            off = row + x * 4
            colors.add(buf[off:off + 4])
    return colors


@pytest.mark.parametrize("pattern_id", [pid for pid, _ in FLOOR_PATTERNS if pid != "none"])
def test_all_floor_patterns_render_distinct_texture(pattern_id):
    pts = [(10.0, 10.0), (230.0, 10.0), (230.0, 230.0), (10.0, 230.0)]
    solid = Room(pts, identifier="rm-solid")
    solid_buf = _render_room_bytes(solid)
    assert len(_interior_distinct_colors(solid_buf)) == 1

    patterned = Room(pts, identifier="rm-pat")
    patterned.floor_pattern = pattern_id
    pat_buf = _render_room_bytes(patterned)
    assert len(_interior_distinct_colors(pat_buf)) > 1
    assert pat_buf != solid_buf


def test_pattern_rotation_scale_and_huge_polygon_guard():
    pts = [(10.0, 10.0), (230.0, 10.0), (230.0, 230.0), (10.0, 230.0)]
    r0 = Room(pts, identifier="r0")
    r0.floor_pattern = "wood_plank"
    r0.pattern_rotation = 0.0
    r0.pattern_scale = 1.0

    r45 = Room(pts, identifier="r45")
    r45.floor_pattern = "wood_plank"
    r45.pattern_rotation = 45.0
    r45.pattern_scale = 1.0

    r2x = Room(pts, identifier="r2x")
    r2x.floor_pattern = "wood_plank"
    r2x.pattern_rotation = 0.0
    r2x.pattern_scale = 2.0

    b0 = _render_room_bytes(r0)
    b45 = _render_room_bytes(r45)
    b2x = _render_room_bytes(r2x)
    assert b0 != b45
    assert b0 != b2x

    # Huge polygon stays fast & bounded via step guard
    huge = Room([(0.0, 0.0), (1e6, 0.0), (1e6, 1e6), (0.0, 1e6)], identifier="r-huge")
    huge.floor_pattern = "herringbone"
    huge.pattern_scale = 0.25
    _render_room_bytes(huge, width=120, height=120)


def test_floor_pattern_clipped_outside_hole():
    pts = [(10.0, 10.0), (230.0, 10.0), (230.0, 230.0), (10.0, 230.0)]
    c = _make_canvas()
    c.tool_mode = ""
    c.current_room_points = []
    rm = Room(pts, identifier="rm-hole")
    rm.floor_pattern = "tile_12"
    # Manual hole (non-stair source so sync_stair_holes leaves it untouched)
    rm.holes = [Hole(source_id="manual-1", points=[(80.0, 80.0), (160.0, 80.0), (160.0, 160.0), (80.0, 160.0)])]
    c.rooms = [rm]

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 240, 240)
    cr = cairo.Context(surf)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    draw_rooms(c, cr, 1.0)
    surf.flush()
    buf = bytes(surf.get_data())

    # Hole interior remains solid white (255,255,255,255)
    hole_colors = _interior_distinct_colors(buf, width=240, x0=90, x1=150, y0=90, y1=150)
    assert hole_colors == {b"\xff\xff\xff\xff"}


def test_floor_pattern_svg_export(tmp_path):
    c = _make_canvas()
    rm = Room([(0.0, 0.0), (144.0, 0.0), (144.0, 144.0), (0.0, 144.0)],
              identifier="rm-svg", layer_id=c.active_layer_id)
    rm.floor_pattern = "herringbone"
    rm.pattern_rotation = 30.0
    rm.pattern_scale = 1.25
    c.rooms = [rm]

    s = PrintSettings(paper="Letter (8.5 x 11 in)", print_all_levels=False, level_ids=[c.levels[0].id])
    out = tmp_path / "pattern.svg"
    pr.export_svg(c, s, str(out))
    raw = out.read_bytes()
    root = ET.fromstring(raw)
    assert root.tag.endswith("svg")
    assert b"<path" in raw and len(raw) > 1000


def test_floor_pattern_xml_roundtrip_and_legacy_defaults():
    c = _make_canvas()
    rm = Room([(0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0)],
              identifier="rm-xml", layer_id=c.active_layer_id)
    rm.floor_pattern = "tile_18"
    rm.pattern_rotation = 45.0
    rm.pattern_scale = 1.5
    c.rooms = [rm]

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        path = tf.name
    try:
        save_project(c, 800, 600, path)
        c2 = _make_canvas()
        open_project(c2, path)
        assert len(c2.rooms) == 1
        loaded = c2.rooms[0]
        assert loaded.floor_pattern == "tile_18"
        assert loaded.pattern_rotation == pytest.approx(45.0)
        assert loaded.pattern_scale == pytest.approx(1.5)
    finally:
        if os.path.exists(path):
            os.remove(path)

    # Legacy file without pattern elements
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as tf:
        tf.write(
            '<Project window_width="800" window_height="600">'
            '<Levels/><Layers/><Rooms><Room identifier="r-old">'
            '<Points><Point x="0" y="0"/><Point x="10" y="0"/><Point x="10" y="10"/></Points>'
            '<Height>96</Height><FloorType>hardwood</FloorType>'
            '</Room></Rooms></Project>'
        )
        legacy_path = tf.name
    try:
        c3 = _make_canvas()
        open_project(c3, legacy_path)
        loaded = c3.rooms[0]
        assert loaded.floor_pattern == "none"
        assert loaded.pattern_rotation == pytest.approx(0.0)
        assert loaded.pattern_scale == pytest.approx(1.0)
    finally:
        if os.path.exists(legacy_path):
            os.remove(legacy_path)


def test_room_properties_widget_floor_pattern_controls():
    w = RoomPropertiesWidget()
    w.canvas = SimpleNamespace(save_state=lambda: None, queue_draw=lambda: None)
    rm = Room([(0, 0), (100, 0), (100, 100), (0, 100)], identifier="rm-ui")
    w.set_room(rm)

    assert w.pattern_combo.get_active_id() == "none"
    assert w.pattern_rotation_spin.get_sensitive() is False
    assert w.pattern_scale_spin.get_sensitive() is False

    w.pattern_combo.set_active_id("wood_plank")
    assert rm.floor_pattern == "wood_plank"
    assert w.pattern_rotation_spin.get_sensitive() is True
    assert w.pattern_scale_spin.get_sensitive() is True

    w.pattern_rotation_spin.set_value(30.0)
    w.pattern_scale_spin.set_value(1.75)
    assert rm.pattern_rotation == pytest.approx(30.0)
    assert rm.pattern_scale == pytest.approx(1.75)

    w.pattern_combo.set_active_id("none")
    assert rm.floor_pattern == "none"
    assert w.pattern_rotation_spin.get_sensitive() is False
    assert w.pattern_scale_spin.get_sensitive() is False


def test_offset_tiles_and_carpets_distinct():
    pts = [(10.0, 10.0), (230.0, 10.0), (230.0, 230.0), (10.0, 230.0)]
    bufs = {}
    for pid in ("tile_12", "tile_offset_half", "tile_offset_third", "carpet_stipple", "carpet_weave"):
        rm = Room(pts, identifier=f"rm-{pid}")
        rm.floor_pattern = pid
        bufs[pid] = _render_room_bytes(rm)

    assert len({bufs["tile_12"], bufs["tile_offset_half"], bufs["tile_offset_third"]}) == 3
    assert bufs["carpet_stipple"] != bufs["carpet_weave"]
