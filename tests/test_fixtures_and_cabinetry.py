"""Tests for Phase 5 architectural fixtures, cabinetry, countertops, and appliances."""

import math
import os
import sys
from types import SimpleNamespace

import cairo
import gi
import pytest

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from EstiSketch.config import DEFAULT_SETTINGS
from EstiSketch.components import Fixture, Room, Wall
from EstiSketch.fixtures_catalog import (
    COUNTERTOP_MATERIALS,
    FIXTURE_CATALOG,
    FIXTURE_CATEGORIES,
    LAYOUT_PRESETS,
    MOUNT_SURFACES,
    generate_kitchen_or_vanity_layout,
    pack_cabinet_run,
    resolve_fixture_surface,
    snap_fixture_to_walls,
    snap_layout_to_walls,
    snap_point_to_wall_face,
)
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.Canvas.render_fixtures import draw_fixture_preview_icon, draw_fixtures
from EstiSketch.Dialogs.fixture_browser import FixtureBrowserDialog, KitchenLayoutDialog
from EstiSketch.Dialogs.layers_panel import LayersPanel
from EstiSketch.Dialogs.properties_dock import PropertiesDock
from EstiSketch.Printing.print_renderer import PrintSettings, export_svg
from EstiSketch.Takeoff.building_takeoff import (
    extract_fixtures_takeoff,
    generate_fixtures_report,
    get_supplier_quote_items,
)
from EstiSketch.project_io import open_project, save_project


def _make_canvas():
    return CanvasArea(SimpleNamespace(**DEFAULT_SETTINGS))


def _make_room(points, name="Kitchen", floor_pattern="none", is_slab=False, slab_thickness=4.0):
    r = Room(points=points)
    r.name = name
    r.floor_pattern = floor_pattern
    r.is_slab = is_slab
    r.slab_thickness = slab_thickness
    return r


class _DummyGesture:
    def get_current_event(self):
        return SimpleNamespace(get_modifier_state=lambda: Gdk.ModifierType(0))

    def get_current_event_state(self):
        return Gdk.ModifierType(0)

    def set_state(self, _state):
        pass


def _to_device(canvas, mx: float, my: float):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    T = canvas.zoom * ppi
    return (mx * T + canvas.offset_x, my * T + canvas.offset_y)


def test_catalog_and_fixture_dataclass_properties():
    assert len(FIXTURE_CATALOG) == 46
    assert len(FIXTURE_CATEGORIES) >= 9
    for cat_key in ("living_furniture", "bedroom_furniture", "dining_furniture", "office_furniture"):
        assert any(k == cat_key for k, _ in FIXTURE_CATEGORIES)
    assert "quartz" in COUNTERTOP_MATERIALS
    assert "floor" in MOUNT_SURFACES and "slab" in MOUNT_SURFACES

    base = Fixture(symbol_type="base_cabinet", x=100.0, y=50.0)
    assert base.identifier.startswith("fixture-")
    assert not base.is_upper
    assert base.has_countertop is True
    assert pytest.approx(base.total_top_elevation, rel=1e-6) == base.height + base.countertop_thickness
    assert len(base.world_corners()) == 4
    assert base.point_inside(100.0, 50.0)
    assert not base.point_inside(100.0 + 40.0, 50.0)

    upper = Fixture(symbol_type="upper_cabinet", x=100.0, y=50.0)
    assert upper.is_upper
    assert upper.has_countertop is False
    assert pytest.approx(upper.total_top_elevation, rel=1e-6) == upper.elevation + upper.height

    # L-corner notch exclusion: back-left wing vs open front-right quadrant
    l_cab = Fixture(symbol_type="corner_base_cabinet", x=0.0, y=0.0, width=36.0, depth=36.0, rotation=0.0)
    assert l_cab.point_inside(-12.0, -12.0)
    assert not l_cab.point_inside(14.0, 14.0)


def test_surface_resolution_and_wall_snapping():
    canvas = _make_canvas()
    r_floor = _make_room(
        [(0.0, 0.0), (144.0, 0.0), (144.0, 120.0), (0.0, 120.0)],
        name="Kitchen",
        floor_pattern="wood_plank",
        is_slab=False,
    )
    r_slab = _make_room(
        [(200.0, 0.0), (320.0, 0.0), (320.0, 120.0), (200.0, 120.0)],
        name="Garage",
        is_slab=True,
        slab_thickness=6.0,
    )
    canvas.rooms.extend([r_floor, r_slab])

    # Auto mode resolves to floor (0.0") on standard floor and slab (6.0") inside concrete slab room
    f_room = Fixture(symbol_type="refrigerator", x=60.0, y=60.0, mount_surface="auto")
    surf_r, elev_r = resolve_fixture_surface(f_room, canvas.rooms)
    assert surf_r == "floor"
    assert pytest.approx(elev_r) == 0.0

    f_slab = Fixture(symbol_type="water_heater", x=250.0, y=60.0, mount_surface="auto")
    surf_s, elev_s = resolve_fixture_surface(f_slab, canvas.rooms)
    assert surf_s == "slab"
    assert pytest.approx(elev_s) == 6.0

    # Explicit slab mount resolves to slab thickness
    f_forced_slab = Fixture(symbol_type="furnace", x=250.0, y=60.0, mount_surface="slab")
    surf_fs, elev_fs = resolve_fixture_surface(f_forced_slab, canvas.rooms)
    assert surf_fs == "slab"
    assert pytest.approx(elev_fs) == 6.0

    # Straight wall snapping: north wall along y=0, interior at y > 0
    w_straight = Wall(start=(0.0, 0.0), end=(144.0, 0.0), width=4.5, height=96.0)
    sx, sy, _rot, snapped = snap_fixture_to_walls(50.0, 18.0, 24.0, 24.0, [w_straight], snap_dist=20.0)
    assert snapped is w_straight
    assert pytest.approx(sy, abs=0.5) == (w_straight.width / 2.0 + 12.0)

    # Curved wall snapping (90 deg arc centered at (0,0), radius 100)
    w_arc = Wall(start=(100.0, 0.0), end=(0.0, 100.0), width=4.0, height=96.0)
    w_arc.is_curved = True
    w_arc.arc_center = (0.0, 0.0)
    w_arc.arc_radius = 100.0
    w_arc.arc_start_angle = 0.0
    w_arc.arc_end_angle = math.pi / 2.0
    ax, ay, _arot, asnapped = snap_fixture_to_walls(60.0, 60.0, 24.0, 24.0, [w_arc], snap_dist=25.0)
    assert asnapped is w_arc
    assert pytest.approx(math.hypot(ax, ay), abs=2.0) == 100.0 - (w_arc.width / 2.0 + 12.0)


def test_pack_cabinet_run_and_all_nine_layout_presets():
    run_items = pack_cabinet_run(
        start=(0.0, 0.0),
        end=(96.0, 0.0),
        include_uppers=True,
        countertop_material="granite",
        layer_id="layer-1",
    )
    bases = [f for f in run_items if not f.is_upper]
    uppers = [f for f in run_items if f.is_upper]
    assert len(bases) >= 3
    assert len(uppers) == len(bases)
    assert pytest.approx(sum(b.width for b in bases), abs=1.0) == 96.0
    assert all(b.countertop_material == "granite" for b in bases)
    assert len({f.identifier for f in run_items}) == len(run_items)

    assert len(LAYOUT_PRESETS) == 9
    for preset_id, _label in LAYOUT_PRESETS:
        items = generate_kitchen_or_vanity_layout(
            layout_type=preset_id,
            origin=(200.0, 200.0),
            rotation_deg=0.0,
            run_a=120.0,
            run_b=108.0,
            include_uppers=True,
            include_appliances=True,
            countertop_material="quartz",
            layer_id="layer-1",
        )
        assert len(items) >= 1, f"Preset {preset_id} generated no items"
        assert all(isinstance(f, Fixture) for f in items)
        assert len({f.identifier for f in items}) == len(items)


def test_canvas_placement_selection_edit_copy_paste_and_undo():
    canvas = _make_canvas()
    canvas.set_size_request(800, 600)
    canvas.rooms.append(
        _make_room(
            [(0.0, 0.0), (240.0, 0.0), (240.0, 180.0), (0.0, 180.0)],
            name="Kitchen",
            floor_pattern="wood_plank",
        )
    )

    # 1. Single fixture tool click placement
    canvas.tool_mode = "add_fixture"
    canvas.active_fixture_type = "refrigerator"
    canvas.rotate_active_fixture_preview(90.0)
    assert canvas.active_fixture_rotation == 90.0
    dx1, dy1 = _to_device(canvas, 60.0, 60.0)
    canvas._handle_fixture_click(1, dx1, dy1)
    assert len(canvas.fixtures) == 1
    fridge = canvas.fixtures[0]
    assert fridge.symbol_type == "refrigerator"
    assert fridge.rotation == 90.0

    # 2. 2-click Cabinet Run placement
    canvas.tool_mode = "draw_cabinet_run"
    rx1, ry1 = _to_device(canvas, 100.0, 24.0)
    rx2, ry2 = _to_device(canvas, 172.0, 24.0)
    canvas._handle_cabinet_run_click(1, rx1, ry1)
    assert canvas.cabinet_run_start is not None
    canvas._handle_cabinet_run_click(1, rx2, ry2)
    assert canvas.cabinet_run_start is None
    assert len(canvas.fixtures) > 1

    # 3. Kitchen Layout Generator click placement
    before_layout = len(canvas.fixtures)
    canvas.tool_mode = "add_kitchen_layout"
    canvas.pending_layout_config = {
        "layout_type": "vanity_double",
        "run_a": 60.0,
        "run_b": 60.0,
        "include_uppers": True,
        "include_appliances": True,
        "countertop_material": "quartz",
        "rotation_deg": 0.0,
    }
    lx, ly = _to_device(canvas, 180.0, 120.0)
    canvas._handle_kitchen_layout_click(1, lx, ly)
    assert len(canvas.fixtures) > before_layout

    # 4. Selection prioritizes fixture over underlying room
    canvas.tool_mode = "pointer"
    canvas.selected_items.clear()
    fx_d, fy_d = _to_device(canvas, fridge.x, fridge.y)
    canvas.click_start = (fx_d, fy_d)
    canvas._handle_pointer_click(_DummyGesture(), 1, fx_d, fy_d)
    assert any(item["type"] == "fixture" and item["object"] is fridge for item in canvas.selected_items)

    # 5. Translate, copy/paste, delete, undo/redo
    orig_x = fridge.x
    canvas.translate_object("fixture", fridge, 12.0, 0.0)
    assert pytest.approx(fridge.x) == orig_x + 12.0

    canvas.copy_selected()
    canvas.paste()
    assert any(f is not fridge and f.symbol_type == "refrigerator" for f in canvas.fixtures)

    count_before_del = len(canvas.fixtures)
    canvas.selected_items = [{"type": "fixture", "object": fridge}]
    canvas.delete_selected()
    canvas.save_state()
    assert len(canvas.fixtures) == count_before_del - 1

    canvas.undo()
    assert any(f.identifier == fridge.identifier for f in canvas.fixtures)
    canvas.redo()
    assert not any(f.identifier == fridge.identifier for f in canvas.fixtures)


def test_cairo_three_pass_masking_and_svg_export(tmp_path):
    canvas = _make_canvas()
    room = _make_room(
        [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)],
        name="Kitchen",
        floor_pattern="wood_plank",
    )
    canvas.rooms.append(room)
    base = Fixture(symbol_type="base_cabinet", x=100.0, y=100.0, width=36.0, depth=24.0)
    upper = Fixture(symbol_type="upper_cabinet", x=100.0, y=96.0, width=36.0, depth=12.0)
    canvas.fixtures.extend([base, upper])

    # Render directly onto an ARGB32 ImageSurface at 1px == 1in
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
    cr = cairo.Context(surface)
    cr.set_source_rgb(0.35, 0.2, 0.1)  # simulate dark brown floor texture underneath
    cr.paint()

    canvas.zoom = 0.5  # with PIXELS_PER_INCH=2.0 -> zoom_transform=1.0
    draw_fixtures(canvas, cr, 1.0, printing=False)
    surface.flush()

    data = surface.get_data()
    stride = surface.get_stride()
    idx = 100 * stride + 100 * 4
    b, g, r = data[idx], data[idx + 1], data[idx + 2]
    assert r > 180 and g > 180 and b > 170

    # Preview icon helper renders cleanly
    icon_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 40, 40)
    draw_fixture_preview_icon(cairo.Context(icon_surf), "toilet", 40, 40)

    # SVG export succeeds cleanly with fixtures present
    svg_path = tmp_path / "fixtures_export.svg"
    export_svg(canvas, PrintSettings(), str(svg_path))
    assert svg_path.exists() and svg_path.stat().st_size > 100


def test_dialogs_properties_dock_layers_and_xml_roundtrip(tmp_path):
    canvas = _make_canvas()
    f1 = Fixture(
        symbol_type="base_cabinet",
        x=48.0,
        y=36.0,
        width=36.0,
        depth=24.0,
        height=34.5,
        rotation=90.0,
        countertop_material="marble",
        countertop_overhang=1.5,
        has_backsplash=True,
        mount_surface="slab",
        base_elevation=4.0,
        custom_name="Island Base",
    )
    f2 = Fixture(symbol_type="dishwasher", x=84.0, y=36.0)
    canvas.fixtures.extend([f1, f2])

    # Browser & Kitchen Layout Dialog
    win = Gtk.Window()
    picked = []
    browser = FixtureBrowserDialog(win, canvas, on_selected=lambda sym: picked.append(sym))
    browser.search_entry.set_text("dishwasher")
    browser._populate_list()
    browser.selected_symbol = "dishwasher"
    browser._commit_selection(close_after=False)
    assert picked == ["dishwasher"]

    configured = []
    layout_dlg = KitchenLayoutDialog(win, canvas, on_configured=lambda cfg: configured.append(cfg))
    layout_dlg.apply_config()
    assert len(configured) == 1 and "layout_type" in configured[0]

    # PropertiesDock & FixturePropertiesWidget
    dock = PropertiesDock(canvas)
    dock.refresh_tabs([{"type": "fixture", "object": f1}])
    assert dock.stack.get_visible_child_name() == "fixture"
    assert pytest.approx(dock.fixture_page.width_spin.get_value()) == 36.0
    assert pytest.approx(dock.fixture_page.elev_spin.get_value()) == 0.0
    assert "+4.0\"" in dock.fixture_page.surface_status_lbl.get_label()

    # LayersPanel fixture filtering
    panel = LayersPanel(canvas)
    fix_idx = next(i for i, (_, key) in enumerate(panel._type_filter_options) if key == "fixture")
    panel.obj_type_dropdown.set_selected(fix_idx)
    panel.refresh_objects_list()

    # XML round-trip
    project_file = tmp_path / "fixtures_test.xml"
    save_project(canvas, 800, 600, str(project_file))
    canvas2 = _make_canvas()
    open_project(canvas2, str(project_file))
    assert len(canvas2.fixtures) == 2
    r1 = next(f for f in canvas2.fixtures if f.symbol_type == "base_cabinet")
    assert pytest.approx(r1.width) == 36.0
    assert pytest.approx(r1.rotation) == 90.0
    assert r1.countertop_material == "marble"
    assert pytest.approx(r1.countertop_overhang) == 1.5
    assert r1.mount_surface == "slab"
    assert pytest.approx(r1.base_elevation) == 4.0
    assert r1.custom_name == "Island Base"


def test_fixtures_takeoff_and_supplier_quotes():
    canvas = _make_canvas()
    # Two 36" base cabinets with 24" depth + 1" overhang -> 36*(24+1)/144 = 6.25 sq ft each = 12.5 sq ft
    b1 = Fixture(symbol_type="base_cabinet", x=18.0, y=12.0, width=36.0, depth=24.0, countertop_material="quartz", countertop_overhang=1.0)
    b2 = Fixture(symbol_type="base_cabinet", x=54.0, y=12.0, width=36.0, depth=24.0, countertop_material="quartz", countertop_overhang=1.0)
    u1 = Fixture(symbol_type="upper_cabinet", x=18.0, y=6.0, width=36.0, depth=12.0)
    t1 = Fixture(symbol_type="tall_pantry", x=90.0, y=12.0, width=24.0, depth=24.0)
    # L-corner cabinet (36x36 minus 12x12 inner notch = 8.0 sq ft, 4.0 LF)
    c1 = Fixture(symbol_type="corner_base_cabinet", x=150.0, y=18.0, width=36.0, depth=36.0, countertop_material="quartz", countertop_overhang=0.0)
    wc = Fixture(symbol_type="toilet", x=200.0, y=50.0)
    # Furniture items should be excluded from construction takeoff/quotes
    sofa = Fixture(symbol_type="sofa", x=300.0, y=50.0)
    bed = Fixture(symbol_type="bed_queen", x=300.0, y=150.0)
    canvas.fixtures.extend([b1, b2, u1, t1, c1, wc, sofa, bed])

    summary = extract_fixtures_takeoff(canvas)
    assert summary["total_fixtures"] == 6

    # Verify preview icon rendering succeeds for all catalog symbols including furniture
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
    cr = cairo.Context(surf)
    for sym in ("sofa", "bed_king", "dining_table", "desk", "office_chair", "tv_console", "bookshelf"):
        draw_fixture_preview_icon(cr, sym, 64, 64)
    assert pytest.approx(summary["base_cabinet_lf"], rel=1e-3) == 10.0
    assert pytest.approx(summary["upper_cabinet_lf"], rel=1e-3) == 3.0
    assert summary["tall_cabinet_count"] == 1
    assert pytest.approx(summary["countertop_sqft_by_material"]["quartz"], rel=1e-3) == 20.5

    report = generate_fixtures_report(canvas)
    assert "ARCHITECTURAL FIXTURES, CABINETRY & APPLIANCE SCHEDULE" in report
    assert "Quartz" in report

    quotes = get_supplier_quote_items(canvas, {})
    by_desc = {q["description"]: q for q in quotes}
    assert pytest.approx(by_desc["Base Cabinets / Vanities"]["qty"], rel=1e-3) == 10.0
    assert pytest.approx(by_desc["Upper Wall Cabinets"]["qty"], rel=1e-3) == 3.0
    assert by_desc["Tall Pantry Cabinets"]["qty"] == 1
    assert by_desc["Countertop (Quartz)"]["qty"] == 23  # ceil(20.5 * 1.10)
    assert by_desc["Toilet (Water Closet)"]["qty"] == 1


def test_corner_snapping_room_edge_snapping_and_run_face_alignment():
    walls = [
        Wall(start=(0.0, 0.0), end=(160.0, 0.0), width=4.0, height=96.0),
        Wall(start=(160.0, 0.0), end=(160.0, 140.0), width=4.0, height=96.0),
        Wall(start=(160.0, 140.0), end=(0.0, 140.0), width=4.0, height=96.0),
        Wall(start=(0.0, 140.0), end=(0.0, 0.0), width=4.0, height=96.0),
    ]
    # 1. All 4 room inside corners (inner faces at x=2..158, y=2..138 -> center +-18 from corner)
    expected = [
        ((20.0, 20.0), 20.0, 20.0, 0.0),
        ((140.0, 20.0), 140.0, 20.0, 90.0),
        ((140.0, 120.0), 140.0, 120.0, 180.0),
        ((20.0, 120.0), 20.0, 120.0, 270.0),
    ]
    for pt, ex, ey, erot in expected:
        sx, sy, rot, w_hit = snap_fixture_to_walls(
            pt[0], pt[1], 36.0, 36.0, walls, snap_dist=24.0, current_rotation=0.0, symbol_type="corner_base_cabinet"
        )
        assert w_hit is not None
        assert pytest.approx(sx, abs=0.5) == ex
        assert pytest.approx(sy, abs=0.5) == ey
        assert pytest.approx(rot, abs=0.5) == erot

    # 2. Dragging corner cabinet along top wall preserves 90 deg instead of flipping backwards
    sx_s, sy_s, rot_s, _ = snap_fixture_to_walls(
        80.0, 20.0, 36.0, 36.0, walls, snap_dist=24.0, current_rotation=90.0, symbol_type="corner_base_cabinet"
    )
    assert pytest.approx(rot_s, abs=0.5) == 90.0
    assert pytest.approx(sy_s, abs=0.5) == 20.0

    # 3. Regular cabinet flush to both top wall & left perpendicular corner wall
    rx, ry, rrot, rw = snap_fixture_to_walls(
        18.0, 16.0, 24.0, 24.0, walls, snap_dist=24.0, current_rotation=0.0, symbol_type="base_cabinet"
    )
    assert rw is not None
    assert pytest.approx(rx, abs=0.5) == 14.0
    assert pytest.approx(ry, abs=0.5) == 14.0
    assert pytest.approx(rrot, abs=0.5) == 0.0

    # 4. Layout snapping into top-right inside corner & single wall
    (lox, loy), lrot, lsnapped = snap_layout_to_walls("u_shaped", (152.0, 8.0), 0.0, walls, snap_dist=24.0)
    assert lsnapped is True
    assert pytest.approx(lox, abs=0.5) == 158.0
    assert pytest.approx(loy, abs=0.5) == 2.0
    assert pytest.approx(lrot, abs=0.5) == 90.0

    (oox, ooy), orot, osnapped = snap_layout_to_walls("one_wall", (152.0, 60.0), 0.0, walls, snap_dist=24.0)
    assert osnapped is True
    assert pytest.approx(oox, abs=0.5) == 158.0
    assert pytest.approx(orot, abs=0.5) == 90.0

    # 5. Room-edge fallback snapping when no Wall objects exist + cabinet run flush face alignment
    canvas = _make_canvas()
    canvas.rooms.append(_make_room([(0.0, 0.0), (144.0, 0.0), (144.0, 120.0), (0.0, 120.0)]))
    ghost = canvas._build_fixture_preview(60.0, 14.0)
    assert pytest.approx(ghost.y, abs=0.5) == 12.0  # back flush to y=0 room edge
    assert pytest.approx(ghost.rotation, abs=0.5) == 0.0

    # Right-to-left run along top wall still faces +Y into room
    canvas.tool_mode = "draw_cabinet_run"
    dx1, dy1 = _to_device(canvas, 120.0, 4.0)
    dx2, dy2 = _to_device(canvas, 24.0, 4.0)
    canvas._handle_cabinet_run_click(1, dx1, dy1)
    canvas._handle_cabinet_run_click(1, dx2, dy2)
    placed_bases = [f for f in canvas.fixtures if not f.is_upper]
    assert len(placed_bases) >= 2
    assert all(pytest.approx(b.y, abs=0.5) == 12.0 for b in placed_bases)
    assert all(pytest.approx(b.rotation, abs=0.5) == 0.0 for b in placed_bases)


def test_rotation_handle_persistence_multi_drag_and_layout_returns():
    canvas = _make_canvas()
    canvas.set_size_request(800, 600)
    cab = Fixture(symbol_type="corner_base_cabinet", x=100.0, y=100.0, width=36.0, depth=36.0, rotation=0.0)
    cab2 = Fixture(symbol_type="base_cabinet", x=142.0, y=94.0, width=24.0, depth=24.0, rotation=0.0)
    canvas.fixtures.extend([cab, cab2])
    canvas.tool_mode = "pointer"
    canvas.selected_items = [{"type": "fixture", "object": cab}]
    canvas.save_state()

    # 1. Drag rotation handle -> must NOT trigger box select / dragging_fixture & must persist + undo/redo
    h_dev = canvas.get_fixture_rotation_handle_device(cab)
    assert h_dev is not None
    canvas.on_click_pressed(_DummyGesture(), 1, h_dev[0], h_dev[1])
    assert canvas.rotating_fixture is cab
    canvas.on_drag_begin(_DummyGesture(), h_dev[0], h_dev[1])
    assert canvas.dragging_fixture is None and not canvas.box_selecting

    # Drag cursor to the -X side of cab -> front faces -X => rot=90 deg
    left_pt = _to_device(canvas, cab.x - 40.0, cab.y)
    canvas.on_drag_update(_DummyGesture(), left_pt[0] - h_dev[0], left_pt[1] - h_dev[1])
    assert pytest.approx(cab.rotation, abs=0.5) == 90.0
    canvas.on_drag_end(_DummyGesture(), left_pt[0] - h_dev[0], left_pt[1] - h_dev[1])
    assert canvas.rotating_fixture is None
    assert pytest.approx(cab.rotation, abs=0.5) == 90.0

    canvas.undo()
    cab_u = next(f for f in canvas.fixtures if f.identifier == cab.identifier)
    assert pytest.approx(cab_u.rotation, abs=0.5) == 0.0
    canvas.redo()
    cab_r = next(f for f in canvas.fixtures if f.identifier == cab.identifier)
    assert pytest.approx(cab_r.rotation, abs=0.5) == 90.0

    # 2. Multi-fixture drag preserves distinct rotations & moves whole selection
    cab2_r = next(f for f in canvas.fixtures if f.identifier == cab2.identifier)
    canvas.selected_items = [{"type": "fixture", "object": cab_r}, {"type": "fixture", "object": cab2_r}]
    start_d = _to_device(canvas, cab_r.x, cab_r.y)
    canvas.on_drag_begin(_DummyGesture(), start_d[0], start_d[1])
    assert canvas.dragging_fixtures is not None and len(canvas.dragging_fixtures) == 2
    end_d = _to_device(canvas, cab_r.x + 20.0, cab_r.y + 10.0)
    canvas.on_drag_update(_DummyGesture(), end_d[0] - start_d[0], end_d[1] - start_d[1])
    canvas.on_drag_end(_DummyGesture(), end_d[0] - start_d[0], end_d[1] - start_d[1])
    assert pytest.approx(cab_r.x, abs=0.5) == 120.0
    assert pytest.approx(cab2_r.x, abs=0.5) == 162.0
    assert pytest.approx(cab_r.rotation, abs=0.5) == 90.0
    assert pytest.approx(cab2_r.rotation, abs=0.5) == 0.0

    # 3. Properties dock dedicated rotation handler updates rotation without clobbering differing widths
    dock = PropertiesDock(canvas)
    dock.refresh_tabs(canvas.selected_items)
    dock.fixture_page.on_rotate_90_clicked(None)
    assert pytest.approx(cab_r.width) == 36.0
    assert pytest.approx(cab2_r.width) == 24.0
    assert pytest.approx(cab_r.rotation) == 180.0
    assert pytest.approx(cab2_r.rotation) == 180.0

    # 4. Peninsula & G-shaped corner orientations
    pen = generate_kitchen_or_vanity_layout("peninsula", (0.0, 0.0), run_a=120.0, run_b=108.0)
    pen_corners = sorted(f.rotation for f in pen if f.symbol_type == "corner_base_cabinet")
    assert pen_corners == [0.0, 270.0]

    gsh = generate_kitchen_or_vanity_layout("g_shaped", (0.0, 0.0), run_a=120.0, run_b=108.0)
    gsh_corners = sorted(f.rotation for f in gsh if f.symbol_type == "corner_base_cabinet")
    assert gsh_corners == [0.0, 90.0, 180.0]


def test_fixture_browser_keeps_open_and_switches_symbols_live():
    canvas = _make_canvas()
    win = Gtk.Window()
    committed = []
    browser = FixtureBrowserDialog(win, canvas, on_selected=lambda sym: committed.append(sym))
    assert browser.keep_open_check.get_active() is True

    # Selecting another symbol row immediately updates canvas.active_fixture_type for multi-placement
    toilet_row = next(r for r, sym in browser._row_symbols.items() if sym == "toilet")
    browser.listbox.select_row(toilet_row)
    assert browser.selected_symbol == "toilet"
    assert canvas.active_fixture_type == "toilet"
    assert canvas.tool_mode == "add_fixture"

    closed = []
    browser.close = lambda: closed.append(True)

    # Activating / clicking Select & Place with keep_open checked keeps browser open & reusable
    browser._on_row_activated(browser.listbox, toilet_row)
    assert committed == ["toilet"]
    assert closed == []

    fridge_row = next(r for r, sym in browser._row_symbols.items() if sym == "refrigerator")
    browser.listbox.select_row(fridge_row)
    assert canvas.active_fixture_type == "refrigerator"

    # Unchecking Keep open and committing triggers close path
    browser.keep_open_check.set_active(False)
    browser.place_btn.emit("clicked")
    assert committed == ["toilet", "refrigerator"]
    assert closed == [True]

