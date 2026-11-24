import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.Dialogs.properties_dock import PropertiesDock  # noqa: E402
from EstiSketch.components import Wall  # noqa: E402


EXPECTED_TABS = [
    "wall",
    "room",
    "text",
    "dimension",
    "dimension_chain",
    "leader",
    "window",
    "door",
    "circle",
    "arc",
    "polyline",
    "roof",
    "stair",
]


def _make_dock(split=1045):
    cfg_dict = config.DEFAULT_SETTINGS.copy()
    cfg_dict["LAYERS_PROPERTIES_SPLIT"] = split
    cfg = SimpleNamespace(**cfg_dict)
    canvas = CanvasArea(cfg)
    dock = PropertiesDock(canvas, cfg)
    return dock, canvas


def test_properties_dock_tabs_visible_and_clamped_with_large_split():
    dock, _ = _make_dock(split=1045)

    assert list(dock.tabs.keys()) == EXPECTED_TABS
    for name, btn in dock.tabs.items():
        assert btn.get_visible(), f"Tab button '{name}' should be visible"
        assert btn.get_ancestor(Gtk.ScrolledWindow) is dock.tab_scroll

    assert isinstance(dock.tab_scroll, Gtk.ScrolledWindow)
    assert dock.tab_bar.get_ancestor(Gtk.ScrolledWindow) is dock.tab_scroll
    assert dock.content_paned.get_position() <= 450
    assert dock.icon_bar_spacer.get_size_request().height <= 360

    min_h, _ = dock.measure(Gtk.Orientation.VERTICAL, -1)[:2]
    assert min_h < 650, f"PropertiesDock min height inflated to {min_h}px"

    icon_bar_min_w, _ = dock.icon_bar.measure(Gtk.Orientation.HORIZONTAL, -1)[:2]
    assert icon_bar_min_w <= 60, f"icon_bar min width too wide: {icon_bar_min_w}px"

    dock._sync_tab_spacer(2000)
    assert dock.icon_bar_spacer.get_size_request().height <= 360


def test_properties_dock_refresh_tabs_enables_and_switches_wall_tab():
    dock, _ = _make_dock(split=1045)
    wall = Wall(start=(0, 0), end=(120, 0), width=5.5, height=96.0, identifier="w-test-1")

    dock.refresh_tabs([{"type": "wall", "object": wall}])

    assert dock.tabs["wall"].get_sensitive() is True
    assert dock.tabs["wall"].get_active() is True
    assert dock.stack.get_visible_child_name() == "wall"

    dock.refresh_tabs([])
    assert dock.tabs["wall"].get_sensitive() is False
    assert dock.stack.get_visible_child_name() == "empty"
