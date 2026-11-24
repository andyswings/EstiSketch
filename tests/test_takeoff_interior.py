"""Phase 6 tests: Doors & Windows schedule and Interior finishes."""
import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import AssumptionSet, TakeoffEngine, run_checks  # noqa: E402
from EstiSketch.TakeoffEngine.interior import (  # noqa: E402
    INTERIOR_DEFAULTS,
    interior_ceiling_area_sqft,
    interior_checks,
    interior_drywall_pre_waste_sqft,
    interior_items,
    interior_wall_area_sqft,
)
from EstiSketch.TakeoffEngine.measurements import plan_measurements  # noqa: E402
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _a(**over):
    a = AssumptionSet(INTERIOR_DEFAULTS)
    for k, v in over.items():
        a.set_project(k, v)
    return a


def _eng(**over):
    return TakeoffEngine(interior_items(), _a(**over))


def _wall(a, b, h0=96.0, h1=None, width=5.5):
    return SimpleNamespace(start=a, end=b, width=width, height=h0, height_at_end=h1 or h0)


def _room(pts, floor_type="tile", holes=()):
    return SimpleNamespace(points=pts, is_slab=True, slab_thickness=4.0, slab_reinforcement="rebar_grid",
                           slab_edge_type="thickened", floor_type=floor_type, holes=list(holes), identifier="r1")


def _gable_box(w=474.5, d=282.5, rise=48.0):
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    return [
        _wall(pts[0], pts[1]),
        _wall(pts[1], (w, d / 2), 96, 96 + rise),
        _wall((w, d / 2), pts[2], 96 + rise, 96),
        _wall(pts[2], pts[3]),
        _wall(pts[3], (0, d / 2), 96, 96 + rise),
        _wall((0, d / 2), pts[0], 96 + rise, 96),
    ]


def _roof(pitch_rise=4.0, pitch_run=12.0, overhang=24.0):
    return SimpleNamespace(roof_type="gable", pitch_rise=pitch_rise, pitch_run=pitch_run,
                           overhang=overhang, material="asphalt_shingle")


def _plan(walls=None, rooms=None, doors=(), windows=(), roofs=None, extra_wall_sets=()):
    ws = [walls if walls is not None else _gable_box()] + list(extra_wall_sets)
    return SimpleNamespace(
        wall_sets=ws,
        rooms=rooms if rooms is not None else [_room([(0, 0), (474.5, 0), (474.5, 282.5), (0, 282.5)])],
        doors=list(doors),
        windows=list(windows),
        roofs=[_roof()] if roofs is None else list(roofs),
    )


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE)
    return c


def test_vaulted_vs_flat_ceiling():
    m = plan_measurements(_plan())
    vaulted = interior_ceiling_area_sqft(m, _a(ceiling_vaulted=1.0).resolve_all())
    flat = interior_ceiling_area_sqft(m, _a(ceiling_vaulted=0.0).resolve_all())
    assert vaulted == pytest.approx(flat * math.sqrt(1.0 + (4.0 / 12.0) ** 2))


def test_gable_walls_included_in_interior_wall_area():
    m = plan_measurements(_plan())
    with_gables = interior_wall_area_sqft(m, _a(include_gable_walls_in_interior=1.0).resolve_all())
    without_gables = interior_wall_area_sqft(m, _a(include_gable_walls_in_interior=0.0).resolve_all())
    assert with_gables - without_gables == pytest.approx(m["interior_gable_area_sqft"])
    assert m["interior_gable_area_sqft"] > 80.0


def test_interior_partitions_counted_both_sides():
    partition = [_wall((200, 0), (200, 200), width=3.5)]
    m_base = plan_measurements(_plan())
    m_part = plan_measurements(_plan(extra_wall_sets=[partition]))
    # 200" long x 96" tall x 2 sides = 266.67 sq ft
    assert m_part["partition_wall_sqft"] == pytest.approx(2 * 200 * 96 / 144.0)
    assert m_part["partition_length_ft"] == pytest.approx(2 * 200 / 12.0)
    assert interior_wall_area_sqft(m_part, _a().resolve_all()) > interior_wall_area_sqft(m_base, _a().resolve_all())


def test_drywall_tape_roll_size_setting(house):
    m = plan_measurements(house)
    rolls_500 = _eng(drywall_tape_roll_ft=500.0).compute(m).by_id("drywall_tape").computed
    rolls_250 = _eng(drywall_tape_roll_ft=250.0).compute(m).by_id("drywall_tape").computed
    assert rolls_500 == 2
    assert rolls_250 == 4


def test_paint_coats_setting(house):
    m = plan_measurements(house)
    one_coat = _eng(paint_coats=1.0).compute(m).by_id("wall_paint").computed
    two_coats = _eng(paint_coats=2.0).compute(m).by_id("wall_paint").computed
    assert one_coat == 4
    assert two_coats == 7


def test_outside_vs_interior_dimensions_setting(house):
    m = plan_measurements(house)
    tile_inside = _eng(use_interior_dimensions=1.0).compute(m).by_id("flooring:tile").computed
    tile_outside = _eng(use_interior_dimensions=0.0).compute(m).by_id("flooring:tile").computed
    assert tile_inside == 993
    assert tile_outside == 1056   # 960 * 1.10


def test_checks_warn_on_missing_rooms_and_vaulted_without_pitch():
    flat_walls = [
        _wall((0, 0), (240, 0)), _wall((240, 0), (240, 120)),
        _wall((240, 120), (0, 120)), _wall((0, 120), (0, 0)),
    ]
    plan = _plan(walls=flat_walls, rooms=[], roofs=[])
    m = plan_measurements(plan)
    a = _a(ceiling_vaulted=1.0)
    msgs = [c.message for c in run_checks(interior_checks(a), m, _eng().compute(m))]
    assert any("no rooms" in msg for msg in msgs)
    assert any("vaulted" in msg for msg in msgs)


def test_simple_house_golden_interior(house):
    m = plan_measurements(house)
    res = _eng().compute(m)
    got = {r.item.id: r.computed for r in res.results}

    # Doors & Windows schedule (orphans excluded)
    assert got["doors_windows:window_sliding_48x36"] == 2
    assert got["doors_windows:window_sliding_36x36"] == 2
    assert got["doors_windows:door_single_36x80"] == 1

    # Drywall, tape, mud
    assert interior_drywall_pre_waste_sqft(m, _a().resolve_all()) == pytest.approx(2039.9, abs=1.0)
    assert got["drywall_sqft"] == 2244
    assert got["drywall_sheets"] == 71
    assert got["drywall_tape"] == 2
    assert got["drywall_mud"] == 5

    # Trim & flooring
    assert got["window_sills"] == 3
    assert got["window_casing"] == 5
    assert got["baseboard"] == 9
    assert got["flooring:tile"] == 993

    # Paint
    assert got["ceiling_paint"] == 3
    assert got["wall_paint"] == 4
    assert got["interior_trim_paint"] == 1
    assert got["exterior_door_paint"] == 1
    assert not any(r.error for r in res.results)
