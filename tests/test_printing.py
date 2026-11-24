"""Tests for PDF printing: settings, layout math, and PDF export."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.Printing.print_settings import PrintSettings, PAPER_SIZES, SCALES  # noqa: E402
from EstiSketch.Printing import print_renderer as pr  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def test_settings_roundtrip():
    s = PrintSettings(paper="Arch D (24 x 36 in)", landscape=False, scale_name='1/4" = 1\'-0"')
    s.title_block.project_name = "House"
    s2 = PrintSettings.from_dict(s.to_dict())
    assert s2.paper == s.paper and s2.title_block.project_name == "House"
    assert PrintSettings.from_dict({"paper": "bogus"}).paper in PAPER_SIZES


def test_page_size_orientation():
    s = PrintSettings(paper="Letter (8.5 x 11 in)", landscape=True)
    assert s.page_size() == (792.0, 612.0)
    s.landscape = False
    assert s.page_size() == (612.0, 792.0)


def test_architectural_scale_value():
    # 1/4" = 1'-0" -> 0.25 paper inch per 12 model inches -> 1.5 pt per model inch
    assert SCALES['1/4" = 1\'-0"'] == pytest.approx(1.5)
    assert SCALES["1:50"] == pytest.approx(1.44)


def test_fit_scale_fits_draw_rect():
    s = PrintSettings()
    layout = pr.compute_layout(s)
    bounds = (0, 0, 600.0, 300.0)
    k = pr.compute_scale(s, bounds, layout.draw_rect)
    assert 600 * k <= layout.draw_rect[2] + 1e-6
    assert 300 * k <= layout.draw_rect[3] + 1e-6


def test_title_block_reduces_draw_area():
    s = PrintSettings()
    with_tb = pr.compute_layout(s).draw_rect
    s.title_block.enabled = False
    without = pr.compute_layout(s).draw_rect
    assert with_tb[3] < without[3]


def _load_canvas():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    if not Gtk.init_check():
        pytest.skip("no display available")
    from EstiSketch import config
    from EstiSketch.Canvas import canvas_area
    from EstiSketch.project_io import open_project
    from types import SimpleNamespace
    cfg = SimpleNamespace(**config.load_config()) if hasattr(config, "load_config") else config
    canvas = canvas_area.create_canvas_area(cfg)
    open_project(canvas, FIXTURE)
    return canvas


def test_export_pdf(tmp_path):
    canvas = _load_canvas()
    s = PrintSettings(paper="Arch D (24 x 36 in)")
    s.title_block.project_name = "Test"
    out = tmp_path / "out.pdf"
    pages = pr.export_pdf(canvas, s, str(out))
    assert pages == len(canvas.levels)
    data = out.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 1000


def test_export_svg_single_level(tmp_path):
    import xml.etree.ElementTree as ET

    canvas = _load_canvas()
    s = PrintSettings(
        paper="Arch D (24 x 36 in)",
        scale_name='1/4" = 1\'-0"',
        print_all_levels=False,
        level_ids=[canvas.levels[0].id],
    )
    out = tmp_path / "plan.svg"
    paths = pr.export_svg(canvas, s, str(out))
    assert paths == [str(out)]
    raw = out.read_bytes()
    root = ET.fromstring(raw)
    assert root.tag.endswith("svg")
    assert root.attrib.get("width") == "2592pt"
    assert root.attrib.get("height") == "1728pt"
    text = raw.decode("utf-8")
    assert "<path" in text and len(text) > 1000


def test_export_svg_multi_level(tmp_path):
    import xml.etree.ElementTree as ET
    from EstiSketch.components import Level

    canvas = _load_canvas()
    canvas.levels.append(Level(id="lvl-2", name="Second Floor", elevation=96.0))
    s = PrintSettings(paper="Arch D (24 x 36 in)", print_all_levels=True)
    out = tmp_path / "plan.svg"
    paths = pr.export_svg(canvas, s, str(out))
    assert len(paths) == 2
    assert len(set(paths)) == 2
    for p in paths:
        assert p.endswith(".svg")
        assert os.path.exists(p)
        root = ET.fromstring(open(p, "rb").read())
        assert root.tag.endswith("svg")


def test_export_svg_no_levels_raises(tmp_path):
    canvas = _load_canvas()
    s = PrintSettings()
    with pytest.raises(ValueError):
        pr.export_svg(canvas, s, str(tmp_path / "empty.svg"), levels=[])


def test_print_dialog_has_export_svg_button():
    from EstiSketch.Printing.print_dialog import PrintDialog

    canvas = _load_canvas()
    dlg = PrintDialog(None, canvas, "Test")
    assert dlg.export_svg_btn.get_label() == "Export SVG..."
    dlg.destroy()


def test_print_dialog_dirty_state_only_on_change():
    from EstiSketch.Printing.print_dialog import PrintDialog

    canvas = _load_canvas()
    changes = []
    dlg = PrintDialog(None, canvas, "Test", on_settings_changed=lambda: changes.append(True))
    dlg._on_close()
    assert changes == []
    assert canvas.print_settings is None
    dlg.destroy()

    dlg2 = PrintDialog(None, canvas, "Test", on_settings_changed=lambda: changes.append(True))
    dlg2.border_chk.set_active(not dlg2.border_chk.get_active())
    dlg2._on_close()
    assert changes == [True]
    assert isinstance(canvas.print_settings, dict)
    assert canvas.print_settings["draw_border"] is False
    dlg2.destroy()


def test_title_block_includes_north_arrow_svg(tmp_path):
    import xml.etree.ElementTree as ET

    canvas = _load_canvas()
    for angle in (0.0, 45.0, 180.0, 270.0):
        canvas.north_angle = angle
        s = PrintSettings(paper="Arch D (24 x 36 in)")
        s.title_block.enabled = True
        s.title_block.project_name = "North Test"
        out = tmp_path / f"north_{int(angle)}.svg"
        pr.export_svg(canvas, s, str(out))
        raw = out.read_bytes()
        root = ET.fromstring(raw)
        assert root.tag.endswith("svg")
        assert len(raw) > 1000
