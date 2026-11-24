import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
import cairo  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.Dialogs.layers_panel import LayersPanel  # noqa: E402
from EstiSketch.components import Wall, Level, Layer  # noqa: E402
from EstiSketch.project_io import save_project, open_project  # noqa: E402


def _make_three_level_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    c = canvas_area.create_canvas_area(cfg)
    l1 = c.levels[0]
    l1.name = "Level 1"
    l1.elevation = 0.0
    l2_id = c.add_level("Level 2")
    l3_id = c.add_level("Level 3")

    la1 = c.layers[0]
    la1.level_id = l1.id
    la2_id = c.add_layer("Layer L2", level_id=l2_id)
    la3_id = c.add_layer("Layer L3", level_id=l3_id)
    return c, (l1.id, l2_id, l3_id), (la1.id, la2_id, la3_id)


def test_resolve_ghost_level_id_and_remove_level():
    c, (l1, l2, l3), _ = _make_three_level_canvas()
    c.set_active_level(l2)

    assert c.resolve_ghost_level_id() is None

    c.set_ghost_level("below")
    assert c.resolve_ghost_level_id() == l1

    c.set_ghost_level("above")
    assert c.resolve_ghost_level_id() == l3

    c.set_active_level(l1)
    c.set_ghost_level("below")
    assert c.resolve_ghost_level_id() is None

    c.set_active_level(l3)
    c.set_ghost_level("above")
    assert c.resolve_ghost_level_id() is None

    c.set_ghost_level(l1)
    assert c.resolve_ghost_level_id() == l1

    # Self-ghosting resolves to None
    c.set_ghost_level(l3)
    assert c.resolve_ghost_level_id() is None

    # Show all levels suppresses ghosting
    c.set_ghost_level(l1)
    c.show_all_levels = True
    assert c.resolve_ghost_level_id() is None
    c.show_all_levels = False
    assert c.resolve_ghost_level_id() == l1

    # Removing the ghosted level clears ghost_level_id
    c.remove_level(l1)
    assert c.ghost_level_id is None


def test_ghost_render_muted_and_excluded_from_printing():
    c, (l1, l2, _), (la1, la2, _) = _make_three_level_canvas()
    w1 = Wall((20.0, 40.0), (180.0, 40.0), width=6.0, height=96.0, layer_id=la1, identifier="w-l1")
    w2 = Wall((20.0, 120.0), (180.0, 120.0), width=6.0, height=96.0, layer_id=la2, identifier="w-l2")
    c.wall_sets = [[w1], [w2]]

    c.set_active_level(l2)
    assert c.is_object_on_visible_layer(w1) is False
    assert c.is_object_on_visible_layer(w2) is True

    def _render(printing=False):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 220, 180)
        cr = cairo.Context(surf)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        c.draw_scene(cr, 1.0, 1.0, printing=printing)
        surf.flush()
        return surf

    def _pixel_rgb(surf, x, y):
        stride = surf.get_stride()
        data = surf.get_data()
        off = y * stride + x * 4
        # ARGB32 on little-endian is BGRA
        b, g, r, _ = data[off], data[off + 1], data[off + 2], data[off + 3]
        return (r, g, b)

    # With ghost off: L1 wall area (100, 40) is white; L2 wall (100, 120) is drawn
    c.set_ghost_level(None)
    s_off = _render(printing=False)
    assert _pixel_rgb(s_off, 100, 40) == (255, 255, 255)
    assert _pixel_rgb(s_off, 100, 120) != (255, 255, 255)

    # With ghost = "below": L1 wall appears muted (lighter than active L2 wall),
    # and outside render pass L1 wall remains non-selectable/invisible
    c.set_ghost_level("below")
    c.set_ghost_opacity(0.25)
    s_on = _render(printing=False)
    ghost_px = _pixel_rgb(s_on, 100, 40)
    active_px = _pixel_rgb(s_on, 100, 120)
    assert ghost_px != (255, 255, 255)
    assert sum(ghost_px) > sum(active_px)
    assert c.is_object_on_visible_layer(w1) is False

    # Printing mode omits the ghost trace
    s_print = _render(printing=True)
    assert _pixel_rgb(s_print, 100, 40) == (255, 255, 255)
    assert _pixel_rgb(s_print, 100, 120) != (255, 255, 255)


def test_ghost_xml_roundtrip_and_legacy_defaults():
    c, (l1, l2, _), _ = _make_three_level_canvas()
    c.set_active_level(l2)
    c.set_ghost_level("below")
    c.set_ghost_opacity(0.40)

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
        path = tf.name
    try:
        save_project(c, 800, 600, path)
        cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
        c2 = canvas_area.create_canvas_area(cfg)
        open_project(c2, path)
        assert c2.ghost_level_id == "below"
        assert c2.ghost_opacity == pytest.approx(0.40)
    finally:
        if os.path.exists(path):
            os.remove(path)

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as tf:
        tf.write('<Project window_width="800" window_height="600"><Levels/><Layers/></Project>')
        legacy_path = tf.name
    try:
        open_project(c, legacy_path)
        assert c.ghost_level_id is None
        assert c.ghost_opacity == pytest.approx(0.25)
    finally:
        if os.path.exists(legacy_path):
            os.remove(legacy_path)


def test_layers_panel_ghost_controls_sync():
    c, (l1, l2, _), _ = _make_three_level_canvas()
    c.set_active_level(l2)
    panel = LayersPanel(c)

    # Options: Off, Below (N-1), Above (N+1), Level 1, Level 2, Level 3
    assert panel.ghost_level_dropdown.get_selected() == 0
    assert panel.ghost_opacity_scale.get_sensitive() is False

    # Select "Below (N-1)" (index 1)
    panel.ghost_level_dropdown.set_selected(1)
    assert c.ghost_level_id == "below"
    assert panel.ghost_opacity_scale.get_sensitive() is True

    panel.ghost_opacity_scale.set_value(0.50)
    assert c.ghost_opacity == pytest.approx(0.50)

    # Toggling Show All disables ghost controls
    panel.show_all_btn.set_active(True)
    assert panel.ghost_level_dropdown.get_sensitive() is False
    assert panel.ghost_opacity_scale.get_sensitive() is False

    panel.show_all_btn.set_active(False)
    assert panel.ghost_level_dropdown.get_sensitive() is True
    assert panel.ghost_opacity_scale.get_sensitive() is True
