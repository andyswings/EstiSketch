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
