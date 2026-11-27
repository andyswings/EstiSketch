"""Tests for the GTK4 Viewport3DWidget, HUD controls, and .glb export integration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402
import pytest  # noqa: E402

from EstiSketch import config, native_3d  # noqa: E402
from EstiSketch.Canvas import canvas_area  # noqa: E402
from EstiSketch.View3D import Viewport3DWidget  # noqa: E402
from EstiSketch.project_io import open_project  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMPLE_HOUSE_XML = REPO_ROOT / "simple_house.xml"


def _require_gtk_display() -> None:
    if not Gtk.init_check():
        pytest.skip("GTK4 display not available")


def test_viewport_3d_widget_sync_and_controls(tmp_path: Path) -> None:
    _require_gtk_display()
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    canvas = canvas_area.create_canvas_area(cfg)
    open_project(canvas, str(SIMPLE_HOUSE_XML))

    exported: list[str] = []
    widget = Viewport3DWidget(canvas, on_export_glb=lambda: exported.append("clicked"))
    widget.sync_from_canvas()

    if not native_3d.is_native_3d_available():
        assert widget._gl_error is not None  # noqa: SLF001
        return

    session = widget._ensure_session()  # noqa: SLF001
    assert session is not None
    assert session.entity_count() > 0

    session.set_camera_mode("walkthrough")
    session.walk_move(1.0, 0.2, 0.0)
    session.set_camera_mode("orbit")
    session.orbit_drag(15.0, -5.0)
    session.pan_drag(10.0, 10.0)
    session.zoom_scroll(1.0)
    session.set_camera_preset("top")
    session.set_render_style("clay")
    session.set_time_of_day(16.0)
    session.set_dollhouse_level(None)
    session.set_auto_hide_roofs(True)

    out_glb = tmp_path / "viewport_out.glb"
    written = widget.export_glb_to_path(str(out_glb))
    assert written > 20
    assert out_glb.is_file()
