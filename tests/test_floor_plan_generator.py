"""Headless tests for the multi-style, multi-option floor plan generator and layout dialog."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cairo
import gi
import pytest

gi.require_version("Gtk", "4.0")

from EstiSketch import config, native_3d  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.Dialogs.floor_plan_generator_dialog import (  # noqa: E402
    FloorPlanGeneratorDialog,
    _draw_plan_preview,
)
from EstiSketch.Dialogs.layout_checks_dialog import LayoutChecksDialog  # noqa: E402
from EstiSketch.floor_plan_generator import (  # noqa: E402
    HOME_STYLES,
    MAX_OPTIONS_PER_STYLE,
    MAX_STYLES,
    MAX_TOTAL_PLANS,
    FloorPlanRequest,
    generate_floor_plans,
    populate_canvas_from_plan,
)
from EstiSketch.geometry.design_checks import validate_project_layout  # noqa: E402
from EstiSketch.project_io import open_project, save_project  # noqa: E402
from EstiSketch.scene_ir import build_scene_ir_from_canvas  # noqa: E402


def test_request_caps_and_normalization() -> None:
    req = FloorPlanRequest(
        bedrooms=9,
        bathrooms=2.7,
        levels=5,
        garage_cars=6,
        min_sqft=2400,
        max_sqft=1800,
        styles=tuple(HOME_STYLES.keys()),
        options_per_style=9,
    )
    norm = req.normalized()
    assert norm.bedrooms == 5
    assert norm.bathrooms == 2.5
    assert norm.levels == 2
    assert norm.garage_cars == 3
    assert norm.min_sqft == 2400 and norm.max_sqft == 2400
    assert len(norm.styles) == MAX_STYLES
    assert norm.options_per_style == MAX_OPTIONS_PER_STYLE

    plans = generate_floor_plans(req)
    assert len(plans) <= MAX_TOTAL_PLANS
    assert len({p.style_key for p in plans}) == MAX_STYLES

    empty_styles = FloorPlanRequest(styles=()).normalized()
    assert empty_styles.styles == ("craftsman",)


@pytest.mark.parametrize("style_key", list(HOME_STYLES.keys()))
def test_all_styles_generate_valid_architecture(style_key: str) -> None:
    spec = HOME_STYLES[style_key]
    req = FloorPlanRequest(
        bedrooms=3,
        bathrooms=2.0,
        levels=1,
        garage_cars=2,
        min_sqft=1500,
        max_sqft=2100,
        include_office=True,
        include_dining=True,
        include_laundry=True,
        styles=(style_key,),
        options_per_style=4,
    )
    plans = generate_floor_plans(req)
    assert len(plans) == 4
    assert len({p.variant_name for p in plans}) == 4

    for plan in plans:
        assert plan.layout_violations == [], f"{style_key} v{plan.option_index}: {plan.layout_violations}"
        canvas = plan.canvas
        assert len(canvas.roofs) >= 1  # type: ignore[attr-defined]
        roof = canvas.roofs[0]  # type: ignore[attr-defined]
        assert roof.roof_type == spec.roof_type
        assert roof.pitch_rise == spec.roof_pitch_rise
        assert roof.material == spec.roof_material
        ext_walls = [
            w
            for ws in canvas.wall_sets  # type: ignore[attr-defined]
            for w in ws
            if w.exterior_wall
        ]
        assert ext_walls
        assert all(w.height == spec.main_wall_height_in for w in ext_walls)
        assert all(w.exterior_finish == spec.exterior_finish for w in ext_walls)


@pytest.mark.parametrize(
    "bedrooms,bathrooms,levels,garage_cars",
    [
        (1, 1.0, 1, 0),
        (2, 1.5, 1, 1),
        (4, 2.5, 1, 2),
        (5, 3.0, 1, 3),
        (2, 2.0, 2, 1),
        (3, 2.5, 2, 2),
        (4, 3.0, 2, 2),
        (5, 3.5, 2, 3),
    ],
)
def test_program_matrix_produces_violation_free_plans(
    bedrooms: int, bathrooms: float, levels: int, garage_cars: int
) -> None:
    req = FloorPlanRequest(
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        levels=levels,
        garage_cars=garage_cars,
        min_sqft=1300 if levels == 1 else 1800,
        max_sqft=2800 if levels == 1 else 3400,
        include_office=bedrooms >= 3,
        include_dining=True,
        include_laundry=True,
        styles=("craftsman", "modern"),
        options_per_style=2,
    )
    plans = generate_floor_plans(req)
    assert len(plans) == 4
    for plan in plans:
        assert plan.layout_violations == [], plan.layout_violations
        canvas = plan.canvas
        assert len(canvas.levels) == levels  # type: ignore[attr-defined]
        garage_rooms = [
            r for r in canvas.rooms if getattr(r, "room_type", "") == "garage"  # type: ignore[attr-defined]
        ]
        assert len(garage_rooms) == (1 if garage_cars > 0 else 0)
        if levels == 2:
            assert len(canvas.stairs) == 1  # type: ignore[attr-defined]
            lvl2_id = canvas.levels[1].id  # type: ignore[attr-defined]
            layer_to_lvl = {l.id: l.level_id for l in canvas.layers}  # type: ignore[attr-defined]
            lvl2_holes = [
                h
                for r in canvas.rooms  # type: ignore[attr-defined]
                if layer_to_lvl.get(r.layer_id, "") == lvl2_id
                for h in r.holes
            ]
            assert len(lvl2_holes) >= 1


def test_populate_canvas_roundtrip_preview_scene_ir_and_layout_dialog(tmp_path: Path) -> None:
    req = FloorPlanRequest(
        bedrooms=3,
        bathrooms=2.5,
        levels=2,
        garage_cars=2,
        min_sqft=1800,
        max_sqft=2400,
        styles=("farmhouse",),
        options_per_style=1,
    )
    plan = generate_floor_plans(req)[0]
    assert plan.layout_violations == []

    # Render Cairo thumbnail preview for both levels
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 330, 215)
    cr = cairo.Context(surf)
    _draw_plan_preview(None, cr, 330, 215, plan, 0)  # type: ignore[arg-type]
    _draw_plan_preview(None, cr, 330, 215, plan, 1)  # type: ignore[arg-type]

    # Populate live CanvasArea, save/re-open as both .xml and .esk
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    canvas = CanvasArea(cfg)
    populate_canvas_from_plan(plan, canvas)
    assert len(canvas.levels) == 2
    assert len(canvas.stairs) == 1
    assert validate_project_layout(canvas) == []

    xml_path = tmp_path / "generated.xml"
    save_project(canvas, 1280, 900, str(xml_path))
    reopened_xml = CanvasArea(cfg)
    open_project(reopened_xml, str(xml_path))
    assert len(reopened_xml.rooms) == len(canvas.rooms)
    assert validate_project_layout(reopened_xml) == []

    esk_path = tmp_path / "generated.esk"
    save_project(canvas, 1280, 900, str(esk_path))
    reopened_esk = CanvasArea(cfg)
    open_project(reopened_esk, str(esk_path))
    assert len(reopened_esk.rooms) == len(canvas.rooms)
    assert validate_project_layout(reopened_esk) == []

    # SceneIR + native 3D mesh compilation
    scene_ir = build_scene_ir_from_canvas(canvas)
    assert len(scene_ir.walls) > 10
    assert len(scene_ir.roofs) == 2
    if native_3d.is_native_3d_available():
        stats = native_3d.scene_mesh_stats(scene_ir)
        assert stats["triangle_count"] > 100  # type: ignore[operator]

    # Headless GUI smoke test for LayoutChecksDialog
    dlg = LayoutChecksDialog(None, canvas)
    dlg.refresh()
    assert "0 layout issues found" in dlg.summary_label.get_text()
    dlg.destroy()


@pytest.mark.parametrize("levels", [1, 2])
def test_seed_variation_generates_distinct_violation_free_plans(levels: int) -> None:
    signatures: set[tuple[str, tuple[tuple[str, tuple[float, float]], ...]]] = set()
    for seed in range(8):
        req = FloorPlanRequest(
            bedrooms=3,
            bathrooms=2.5,
            levels=levels,
            garage_cars=2,
            min_sqft=1600,
            max_sqft=2400,
            include_office=True,
            include_dining=True,
            include_laundry=True,
            styles=("craftsman",),
            options_per_style=2,
            seed=seed,
        )
        plans = generate_floor_plans(req)
        assert len(plans) == 2
        for plan in plans:
            assert plan.layout_violations == [], f"seed={seed}: {plan.layout_violations}"
            rooms = tuple(
                (r.name, tuple(r.points[0]))
                for r in plan.canvas.rooms  # type: ignore[attr-defined]
            )
            signatures.add((plan.variant_name, rooms))
    assert len(signatures) >= 6


def test_generator_dialog_auto_refresh_and_refresh_button() -> None:
    dlg = FloorPlanGeneratorDialog(None, on_apply_plan=lambda _p, _s: None)
    try:
        initial_seed = dlg._seed
        initial_ids = [p.plan_id for p in dlg._plans]
        assert initial_ids

        # Refresh / New Plans advances seed and produces a new batch of plan IDs
        dlg.refresh_new_plans()
        assert dlg._seed == initial_seed + 1
        refreshed_ids = [p.plan_id for p in dlg._plans]
        assert refreshed_ids != initial_ids

        # Changing options schedules a debounced auto-refresh and updates plans when fired
        dlg.bed_spin.set_value(4)
        assert dlg._refresh_source_id is not None
        dlg._run_scheduled_refresh()
        assert dlg._refresh_source_id is None
        assert all(p.bedrooms == 4 for p in dlg._plans)

        dlg.level_combo.set_active_id("2")
        assert dlg._refresh_source_id is not None
        dlg._run_scheduled_refresh()
        assert all(p.levels == 2 for p in dlg._plans)
        assert dlg.level_toggle_box.get_visible() is True

        dlg.dining_check.set_active(False)
        assert dlg._refresh_source_id is not None
        dlg._on_close_request(dlg)
        assert dlg._refresh_source_id is None
    finally:
        dlg.destroy()


def test_open_floor_plan_option_overrides_style_and_auto_refreshes() -> None:
    assert FloorPlanRequest(open_floor_plan="INVALID").normalized().open_floor_plan == "style_default"

    for levels in (1, 2):
        # Force Open Floor Plan on traditionally divided styles (victorian, colonial)
        open_plans = generate_floor_plans(
            FloorPlanRequest(
                bedrooms=3,
                bathrooms=2.0 if levels == 1 else 2.5,
                levels=levels,
                styles=("victorian", "colonial"),
                options_per_style=2,
                open_floor_plan="open",
                seed=7,
            )
        )
        assert len(open_plans) == 4
        for plan in open_plans:
            assert plan.layout_violations == [], f"open L{levels}: {plan.layout_violations}"
            assert "Open Concept" in plan.summary
            room_names = {r.name for r in plan.canvas.rooms}
            assert "Great Room" in room_names
            assert "Living Room" not in room_names

        # Force Traditional (Divided) on open-concept styles (craftsman, modern)
        trad_plans = generate_floor_plans(
            FloorPlanRequest(
                bedrooms=3,
                bathrooms=2.0 if levels == 1 else 2.5,
                levels=levels,
                styles=("craftsman", "modern"),
                options_per_style=2,
                open_floor_plan="traditional",
                seed=7,
            )
        )
        assert len(trad_plans) == 4
        for plan in trad_plans:
            assert plan.layout_violations == [], f"trad L{levels}: {plan.layout_violations}"
            assert "Traditional" in plan.summary
            room_names = {r.name for r in plan.canvas.rooms}
            assert "Living Room" in room_names
            assert "Great Room" not in room_names

        # Traditional must include dividing interior walls with framed openings vs Open
        open_frames = sum(
            1 for _wall, d, _ratio in open_plans[0].canvas.doors if d.door_type == "frame"
        )
        trad_frames = sum(
            1 for _wall, d, _ratio in trad_plans[0].canvas.doors if d.door_type == "frame"
        )
        assert trad_frames > open_frames

    dlg = FloorPlanGeneratorDialog(None, on_apply_plan=lambda _p, _s: None)
    try:
        dlg.layout_concept_combo.set_active_id("traditional")
        assert dlg._refresh_source_id is not None
        dlg._run_scheduled_refresh()
        assert all("Traditional" in p.summary for p in dlg._plans)

        dlg.layout_concept_combo.set_active_id("open")
        assert dlg._refresh_source_id is not None
        dlg._run_scheduled_refresh()
        assert all("Open Concept" in p.summary for p in dlg._plans)
    finally:
        dlg.destroy()


def test_square_footage_range_enforced_1story_and_2story() -> None:
    cases = [
        (1, 2, 1.0, 700, 900),
        (1, 3, 2.0, 1050, 1250),
        (1, 3, 2.0, 1400, 1500),
        (1, 3, 2.0, 1800, 2000),
        (1, 3, 2.0, 2600, 3200),
        (2, 2, 1.5, 1200, 1500),
        (2, 3, 2.0, 1500, 1800),
        (2, 3, 2.5, 1600, 2000),
        (2, 4, 2.5, 2200, 2600),
        (2, 4, 3.0, 3200, 3800),
    ]
    for levels, beds, baths, lo, hi in cases:
        plans = generate_floor_plans(
            FloorPlanRequest(
                bedrooms=beds,
                bathrooms=baths,
                levels=levels,
                min_sqft=lo,
                max_sqft=hi,
                styles=("craftsman",),
                options_per_style=4,
                seed=42,
            )
        )
        assert len(plans) == 4
        for plan in plans:
            assert lo <= round(plan.living_sqft) <= hi, (
                f"L{levels} {beds}bd/{baths}ba [{lo}-{hi}] got {plan.living_sqft:.1f}"
            )
            assert plan.layout_violations == [], (
                f"L{levels} {beds}bd/{baths}ba [{lo}-{hi}]: {plan.layout_violations}"
            )


def test_dialog_sqft_bounds_sync_and_range_note() -> None:
    dlg = FloorPlanGeneratorDialog(None, on_apply_plan=lambda _p, _s: None)
    try:
        # Lowering Max Sq Ft below Min Sq Ft pulls Min Sq Ft down instead of snapping Max back up
        dlg.min_sqft_spin.set_value(1600)
        dlg.max_sqft_spin.set_value(1200)
        assert int(dlg.max_sqft_spin.get_value()) == 1200
        assert int(dlg.min_sqft_spin.get_value()) == 1200

        # Raising Min Sq Ft above Max Sq Ft pushes Max Sq Ft up
        dlg.min_sqft_spin.set_value(2500)
        assert int(dlg.max_sqft_spin.get_value()) == 2500

        # Updating Sq Ft range and running scheduled refresh updates generated plan areas
        dlg.min_sqft_spin.set_value(2600)
        dlg.max_sqft_spin.set_value(3100)
        assert dlg._refresh_source_id is not None
        dlg._run_scheduled_refresh()
        assert all(2600 <= round(p.living_sqft) <= 3100 for p in dlg._plans)
        assert dlg.range_note_lbl.get_visible() is False

        # Physically impossible range for 5bd/3.5ba surfaces subtle warning note
        dlg.bed_spin.set_value(5)
        dlg.bath_combo.set_active_id("3.5")
        dlg.min_sqft_spin.set_value(700)
        dlg.max_sqft_spin.set_value(800)
        dlg._run_scheduled_refresh()
        assert dlg.range_note_lbl.get_visible() is True

        # Restoring feasible range hides warning note
        dlg.min_sqft_spin.set_value(2200)
        dlg.max_sqft_spin.set_value(2800)
        dlg._run_scheduled_refresh()
        assert dlg.range_note_lbl.get_visible() is False
    finally:
        dlg.destroy()


def test_open_floor_plan_minimizes_hallways() -> None:
    from EstiSketch.floor_plan_generator.builder import polygon_area

    def _hallway_sqft(plan) -> float:
        return sum(
            polygon_area(r.points) / 144.0
            for r in plan.canvas.rooms
            if getattr(r, "room_type", "") == "hallway"
        )

    # 1-story 1-bed/1-bath open plan eliminates the hallway completely (0 sq ft)
    one_bed = generate_floor_plans(
        FloorPlanRequest(
            bedrooms=1,
            bathrooms=1.0,
            levels=1,
            garage_cars=2,
            min_sqft=850,
            max_sqft=1150,
            include_laundry=False,
            styles=("modern",),
            options_per_style=4,
            open_floor_plan="open",
            seed=42,
        )
    )
    assert len(one_bed) == 4
    for plan in one_bed:
        assert _hallway_sqft(plan) == 0.0
        assert plan.layout_violations == [], f"1bd open: {plan.layout_violations}"

    # 1-story & 2-story 3-bed plans strictly reduce hallway area vs traditional
    for levels, baths, lo, hi in [(1, 2.0, 1400, 1900), (2, 2.5, 1900, 2400)]:
        open_plans = generate_floor_plans(
            FloorPlanRequest(
                bedrooms=3,
                bathrooms=baths,
                levels=levels,
                garage_cars=2,
                min_sqft=lo,
                max_sqft=hi,
                styles=("craftsman",),
                options_per_style=4,
                open_floor_plan="open",
                seed=42,
            )
        )
        trad_plans = generate_floor_plans(
            FloorPlanRequest(
                bedrooms=3,
                bathrooms=baths,
                levels=levels,
                garage_cars=2,
                min_sqft=lo,
                max_sqft=hi,
                styles=("craftsman",),
                options_per_style=4,
                open_floor_plan="traditional",
                seed=42,
            )
        )
        for op, tp in zip(open_plans, trad_plans):
            assert op.layout_violations == [], f"L{levels} open: {op.layout_violations}"
            assert tp.layout_violations == [], f"L{levels} trad: {tp.layout_violations}"
            assert _hallway_sqft(op) < _hallway_sqft(tp) * 0.82, (
                f"L{levels}: open={_hallway_sqft(op):.1f} vs trad={_hallway_sqft(tp):.1f}"
            )
        avg_open = sum(_hallway_sqft(p) for p in open_plans) / len(open_plans)
        avg_trad = sum(_hallway_sqft(p) for p in trad_plans) / len(trad_plans)
        assert avg_open < avg_trad * 0.72, (
            f"L{levels} avg: open={avg_open:.1f} vs trad={avg_trad:.1f}"
        )
        if levels == 2:
            for op in open_plans:
                lvl1_id = op.canvas.levels[0].id
                lvl1_layers = {ly.id for ly in op.canvas.layers if ly.level_id == lvl1_id}
                lvl1_halls = [
                    r for r in op.canvas.rooms
                    if r.layer_id in lvl1_layers and getattr(r, "room_type", "") == "hallway"
                ]
                assert lvl1_halls == []

    # Open 1-story plans with Home Office + Garage keep office off shortened corridor
    office_open = generate_floor_plans(
        FloorPlanRequest(
            bedrooms=3,
            bathrooms=2.0,
            levels=1,
            garage_cars=2,
            include_office=True,
            styles=("craftsman",),
            options_per_style=4,
            open_floor_plan="open",
            seed=42,
        )
    )
    office_trad = generate_floor_plans(
        FloorPlanRequest(
            bedrooms=3,
            bathrooms=2.0,
            levels=1,
            garage_cars=2,
            include_office=True,
            styles=("craftsman",),
            options_per_style=4,
            open_floor_plan="traditional",
            seed=42,
        )
    )
    for op, tp in zip(office_open, office_trad):
        assert op.layout_violations == [], f"office open: {op.layout_violations}"
        assert _hallway_sqft(op) < _hallway_sqft(tp), (
            f"office open={_hallway_sqft(op):.1f} vs trad={_hallway_sqft(tp):.1f}"
        )
