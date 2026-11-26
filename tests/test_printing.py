"""Tests for PDF printing: settings, layout math, and PDF export."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.Printing.print_settings import (  # noqa: E402
    LINE_WEIGHT_CATEGORIES,
    LINE_WEIGHT_PRESETS,
    LineWeights,
    PAPER_SIZES,
    PrintSettings,
    SCALES,
    resolve_stroke_width,
)
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


def test_line_weights_presets_clamping_and_resolve():
    lw = LineWeights()
    assert lw.preset == "Standard AIA"
    assert lw.width_pt("openings") == pytest.approx(0.75)

    lw.apply_preset("Bold (Presentation)")
    assert lw.global_multiplier == pytest.approx(1.40)
    assert lw.width_pt("openings") == pytest.approx(0.95 * 1.40)

    clamped = LineWeights.from_dict({"global_multiplier": 99.0, "openings": -3.0})
    assert clamped.global_multiplier == pytest.approx(5.0)
    assert clamped.openings == pytest.approx(0.05)

    class _Dummy:
        _print_line_weights = None

    dummy = _Dummy()
    # Interactive mode preserves pixel-based scaling
    assert resolve_stroke_width(dummy, "openings", 1.0, 2.0) == pytest.approx(0.5)
    # Active print mode converts configured pt weight by print scale
    dummy._print_line_weights = lw
    assert resolve_stroke_width(dummy, "openings", 1.0, 2.0) == pytest.approx((0.95 * 1.40) / 2.0)


def test_print_settings_backwards_compat_and_roundtrip():
    legacy = PrintSettings.from_dict({"paper": "Letter (8.5 x 11 in)"})
    assert legacy.line_weights.preset == "Standard AIA"
    assert legacy.tile_enabled is False
    assert legacy.tile_overlap_in == pytest.approx(0.5)

    custom = PrintSettings(
        paper="Arch D (24 x 36 in)",
        scale_name='1/4" = 1\'-0"',
        tile_enabled=True,
        tile_overlap_in=0.75,
        tile_registration_marks=False,
        tile_page_numbers=False,
    )
    custom.line_weights.apply_preset("Fine (Small Scale)")
    custom.line_weights.openings = 0.42
    custom.line_weights.preset = "Custom"
    restored = PrintSettings.from_dict(custom.to_dict())
    assert restored.tile_enabled is True
    assert restored.tile_overlap_in == pytest.approx(0.75)
    assert restored.tile_registration_marks is False
    assert restored.tile_page_numbers is False
    assert restored.line_weights.preset == "Custom"
    assert restored.line_weights.openings == pytest.approx(0.42)


def test_line_weights_affect_svg_output(tmp_path):
    import re

    canvas = _load_canvas()
    fine = PrintSettings(paper="Arch D (24 x 36 in)", scale_name='1/4" = 1\'-0"')
    fine.line_weights.apply_preset("Fine (Small Scale)")
    bold = PrintSettings(paper="Arch D (24 x 36 in)", scale_name='1/4" = 1\'-0"')
    bold.line_weights.apply_preset("Bold (Presentation)")

    p_fine = tmp_path / "fine.svg"
    p_bold = tmp_path / "bold.svg"
    pr.export_svg(canvas, fine, str(p_fine))
    pr.export_svg(canvas, bold, str(p_bold))

    assert p_fine.read_text("utf-8") != p_bold.read_text("utf-8")
    fine_sw = [float(x) for x in re.findall(r'stroke-width="([0-9.]+)"', p_fine.read_text("utf-8"))]
    bold_sw = [float(x) for x in re.findall(r'stroke-width="([0-9.]+)"', p_bold.read_text("utf-8"))]
    assert fine_sw and bold_sw
    assert min(bold_sw) > min(fine_sw) or sum(bold_sw) > sum(fine_sw)


def test_compute_tile_grid_overlap_and_fit_behavior():
    # Single sheet when drawing fits
    single = pr.compute_tile_grid((0.0, 0.0, 100.0, 80.0), 1.0, (36.0, 36.0, 500.0, 400.0), 36.0)
    assert len(single) == 1
    assert single[0].rows == 1 and single[0].cols == 1

    # Oversized drawing splits into multi-row/col grid with exact overlap continuity
    tiles = pr.compute_tile_grid((0.0, 0.0, 200.0, 150.0), 2.0, (0.0, 0.0, 200.0, 180.0), 36.0)
    # Content = 400x300 pt; draw_rect = 200x180 pt; step = 164x144 pt -> 3 cols x 2 rows
    assert len(tiles) == 6
    assert tiles[0].rows == 2 and tiles[0].cols == 3
    t00, t01 = tiles[0], tiles[1]
    t10 = tiles[3]
    scale = 2.0
    right_edge_00 = t00.origin_model_x + 200.0 / scale
    left_edge_01 = t01.origin_model_x
    assert (right_edge_00 - left_edge_01) * scale == pytest.approx(36.0)
    bottom_edge_00 = t00.origin_model_y + 180.0 / scale
    top_edge_10 = t10.origin_model_y
    assert (bottom_edge_00 - top_edge_10) * scale == pytest.approx(36.0)


def test_tiling_pdf_svg_and_overview(tmp_path):
    import cairo
    import xml.etree.ElementTree as ET

    canvas = _load_canvas()
    # Fit to page never tiles even if tile_enabled=True
    fit_s = PrintSettings(paper="Letter (8.5 x 11 in)", scale_name="Fit to page", tile_enabled=True)
    assert len(pr.resolve_sheets(canvas, fit_s)) == len(canvas.levels)

    # Large scale on small paper triggers multi-page tiling
    tiled_s = PrintSettings(
        paper="Letter (8.5 x 11 in)",
        scale_name='1" = 1\'-0"',
        tile_enabled=True,
        tile_overlap_in=0.5,
        print_all_levels=False,
        level_ids=[canvas.levels[0].id],
    )
    sheets = pr.resolve_sheets(canvas, tiled_s)
    assert len(sheets) > 1
    assert all(sh.tile is not None for sh in sheets)

    pdf_out = tmp_path / "tiled.pdf"
    assert pr.export_pdf(canvas, tiled_s, str(pdf_out)) == len(sheets)
    assert pdf_out.read_bytes().startswith(b"%PDF")

    svg_paths = pr.export_svg(canvas, tiled_s, str(tmp_path / "tiled.svg"))
    assert len(svg_paths) == len(sheets)
    assert any("_R1C1" in p for p in svg_paths)
    for p in svg_paths:
        root = ET.fromstring(open(p, "rb").read())
        assert root.tag.endswith("svg")

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 600, 400)
    cr = cairo.Context(surf)
    bounds = pr.content_bounds(canvas, canvas.levels[0].id)
    rects = pr.render_tile_overview(cr, canvas, tiled_s, canvas.levels[0], bounds, sheets[0].tile, 600.0, 400.0)
    assert len(rects) == len(sheets)


def test_gtk_printer_paper_sizes_and_operation():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    if not Gtk.init_check():
        pytest.skip("no display available")
    from EstiSketch.Printing import gtk_printer

    for paper_name, (expected_w, expected_h) in PAPER_SIZES.items():
        ps = gtk_printer.paper_size_for_name(paper_name)
        assert ps.get_width(Gtk.Unit.POINTS) == pytest.approx(expected_w, abs=1.5)
        assert ps.get_height(Gtk.Unit.POINTS) == pytest.approx(expected_h, abs=1.5)

        setup = gtk_printer.build_page_setup(PrintSettings(paper=paper_name, landscape=True))
        w, h = gtk_printer.page_size_from_setup(setup)
        assert w == pytest.approx(expected_h, abs=1.5)
        assert h == pytest.approx(expected_w, abs=1.5)
        assert setup.get_top_margin(Gtk.Unit.POINTS) == pytest.approx(0.0)

    canvas = _load_canvas()
    op, state = gtk_printer.prepare_print_operation(
        canvas,
        PrintSettings(paper="Arch D (24 x 36 in)"),
        job_name="UnitTest",
    )
    assert isinstance(op, Gtk.PrintOperation)
    assert len(state.levels) == len(canvas.levels)


def test_print_dialog_line_weights_tiling_and_print_button():
    from EstiSketch.Printing.print_dialog import PrintDialog

    canvas = _load_canvas()
    changes = []
    dlg = PrintDialog(None, canvas, "Test", on_settings_changed=lambda: changes.append(True))
    assert dlg.print_btn.get_label() == "Print..."
    assert len(dlg.lw_spins) == len(LINE_WEIGHT_CATEGORIES)
    assert dlg.tile_chk.get_sensitive() is False  # Fit to page active initially

    # Select fixed scale and enable tiling -> dirty state triggers on close
    scale_names = list(SCALES.keys())
    dlg.scale_dd.set_selected(scale_names.index('1" = 1\'-0"'))
    assert dlg.tile_chk.get_sensitive() is True
    dlg.tile_chk.set_active(True)
    assert dlg.tile_overview_btn.get_sensitive() is True

    # Adjust a line weight preset
    preset_names = list(LINE_WEIGHT_PRESETS.keys()) + ["Custom"]
    dlg.lw_preset_dd.set_selected(preset_names.index("Bold (Presentation)"))
    assert dlg.lw_mult_spin.get_value() == pytest.approx(1.40)

    dlg._on_close()
    assert changes == [True]
    assert isinstance(canvas.print_settings, dict)
    assert canvas.print_settings["tile_enabled"] is True
    assert canvas.print_settings["line_weights"]["global_multiplier"] == pytest.approx(1.40)
    dlg.destroy()
