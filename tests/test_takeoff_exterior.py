"""Phase 4 tests: exterior sheathing, wrap, siding, trim, paint."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import AssumptionSet, TakeoffEngine, run_checks  # noqa: E402
from EstiSketch.TakeoffEngine.exterior import (  # noqa: E402
    EXTERIOR_DEFAULTS, exterior_checks, exterior_items)
from EstiSketch.TakeoffEngine.measurements import plan_measurements  # noqa: E402
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _engine(**over):
    a = AssumptionSet(EXTERIOR_DEFAULTS)
    for k, v in over.items():
        a.set_project(k, v)
    return TakeoffEngine(exterior_items(), a)


def _wall(a, b, width=5.5, h0=96.0, h1=None):
    return SimpleNamespace(start=a, end=b, width=width, height=h0, height_at_end=h1 or h0)


def _box(w=240.0, d=120.0):
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    return [_wall(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def _plan(walls, doors=(), windows=()):
    return SimpleNamespace(wall_sets=[walls], rooms=[], doors=list(doors), windows=list(windows))


def _op(w, h, wall, ratio=0.5):
    return (wall, SimpleNamespace(identifier="x", width=w, height=h), ratio)


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE)
    return c


def test_box_area_is_outside_perimeter_times_height():
    m = plan_measurements(_plan(_box()))
    assert m["exterior_wall_area_sqft"] == pytest.approx(2 * (245.5 + 125.5) * 96 / 144.0)
    assert m["exterior_gable_area_sqft"] == 0
    assert m["exterior_corner_trim_ft"] == pytest.approx(4 * 8.0)


def test_gable_area_is_added_to_wall_area():
    pts = [(0, 0), (480, 0), (480, 288), (0, 288)]
    walls = [_wall(pts[0], pts[1]), _wall(pts[1], (480, 144), h1=144), _wall((480, 144), pts[2], h0=144, h1=96),
             _wall(pts[2], pts[3]), _wall(pts[3], pts[0])]
    m = plan_measurements(_plan(walls))
    assert m["exterior_gable_area_sqft"] == pytest.approx(48.0, abs=0.1)   # 288" centerline base x 48" rise / 2


def test_openings_are_not_deducted_by_default():
    walls = _box()
    base = plan_measurements(_plan(walls))["exterior_wall_area_sqft"]
    m = plan_measurements(_plan(walls, windows=[_op(48, 36, walls[0])]))
    assert m["exterior_wall_area_sqft"] == pytest.approx(base)
    assert _engine().compute(m).by_id("siding").raw == pytest.approx(base * 1.10)


def test_deduct_openings_setting():
    walls = _box()
    m = plan_measurements(_plan(walls, windows=[_op(48, 36, walls[0])]))
    res = _engine(deduct_openings=1.0).compute(m)
    assert res.by_id("siding").raw == pytest.approx((m["exterior_wall_area_sqft"] - 12.0) * 1.10)


def test_trim_lengths():
    walls = _box()
    m = plan_measurements(_plan(walls, windows=[_op(48, 36, walls[0])], doors=[_op(36, 80, walls[2])]))
    # window 2*(48+36)=168", door 2*80+36=196"
    assert m["exterior_opening_trim_ft"] == pytest.approx((168 + 196) / 12.0)
    res = _engine().compute(m)
    assert res.by_id("exterior_trim").raw == pytest.approx((32 + 364 / 12.0) * 1.10)


def test_waste_and_coverage_are_settings():
    m = plan_measurements(_plan(_box()))
    a = m["exterior_wall_area_sqft"]
    assert _engine(siding_waste_pct=0.0).compute(m).by_id("siding").raw == pytest.approx(a)
    assert _engine(exterior_paint_sqft_per_gal=100.0).compute(m).by_id("exterior_paint").raw == pytest.approx(a / 100)
    assert _engine(house_wrap_roll_sqft=450.0).compute(m).by_id("house_wrap_rolls").raw == pytest.approx(a * 1.05 / 450)


def test_interior_walls_are_not_exterior():
    m = plan_measurements(_plan([_wall((0, 0), (200, 0))]))
    assert m["exterior_wall_area_sqft"] == 0
    msgs = [c.message for c in run_checks(exterior_checks(), m, _engine().compute(m))]
    assert any("no exterior walls" in x for x in msgs)


def test_simple_house_golden_exterior(house):
    m = plan_measurements(house)
    res = _engine().compute(m)
    # your sheet used 1,120 sq ft (24' x 4' / 2 = 48 per gable); the drawn wall heights give 1,118.2
    assert m["exterior_wall_area_sqft"] == pytest.approx(1120, abs=3)
    assert res.by_id("siding").computed == pytest.approx(1232, abs=3)
    assert res.by_id("house_wrap_sqft").computed == pytest.approx(1176, abs=3)
    assert res.by_id("wall_sheathing").computed == 36
    assert res.by_id("sheathing_nails").computed == 3456
    assert res.by_id("exterior_paint").computed == 4
    assert res.by_id("house_wrap_rolls").computed == 2
    assert res.by_id("exterior_trim").computed == pytest.approx(110, abs=1)
