"""Phase 2 tests: foundation measurements and line items (golden: simple_house)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import AssumptionSet, TakeoffEngine, run_checks  # noqa: E402
from EstiSketch.TakeoffEngine.foundation import (  # noqa: E402
    FOUNDATION_DEFAULTS, bolts_for_piece, foundation_checks, foundation_items,
    form_board_check, plate_pieces)
from EstiSketch.TakeoffEngine.geometry import (  # noqa: E402
    collapse_collinear, is_rectangle, offset_polygon, snap_to)
from EstiSketch.TakeoffEngine.measurements import foundation_measurements  # noqa: E402
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _wall(a, b, width=5.5):
    return SimpleNamespace(start=a, end=b, width=width)


def _room(points, **kw):
    d = dict(points=points, is_slab=True, slab_thickness=4.0, slab_reinforcement="rebar_grid",
             slab_edge_type="thickened", holes=[], identifier="r")
    d.update(kw)
    return SimpleNamespace(**d)


def _plan(walls_pts, room_pts, **room_kw):
    ws = [_wall(walls_pts[i], walls_pts[(i + 1) % len(walls_pts)]) for i in range(len(walls_pts))]
    return SimpleNamespace(wall_sets=[ws], rooms=[_room(room_pts, **room_kw)])


def _engine(**project):
    a = AssumptionSet(FOUNDATION_DEFAULTS)
    for k, v in project.items():
        a.set_project(k, v)
    return TakeoffEngine(foundation_items(), a)


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE)
    return c


def test_snap_and_geometry_helpers():
    assert snap_to(479.94, 0.25) == 480.0
    assert snap_to(288.07, 0.25) == 288.0
    assert len(collapse_collinear([(0, 0), (5, 0), (10, 0), (10, 10), (0, 10)])) == 4
    assert is_rectangle([(0, 0), (10, 0), (10, 5), (0, 5)])
    assert not is_rectangle([(0, 0), (10, 0), (12, 5), (0, 5)])
    out = offset_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [1, 1, 1, 1])
    xs = sorted(p[0] for p in out)
    assert xs[0] == pytest.approx(-1) and xs[-1] == pytest.approx(11)


def test_simple_house_measurements_use_outside_dimensions(house):
    m = foundation_measurements(house)
    s = m["slabs"][0]
    assert (s["length_ft"], s["width_ft"]) == (40.0, 24.0)
    assert s["area_sqft"] == pytest.approx(960.0)
    assert s["perimeter_ft"] == pytest.approx(128.0)
    assert m["plate_runs_ft"] == [40.0, 24.0, 40.0, 24.0]
    assert m["wall_lf_outside"] == pytest.approx(128.0)


def test_simple_house_golden_foundation(house):
    res = _engine().compute(foundation_measurements(house))
    assert res.by_id("rebar_20").computed == 68
    assert res.by_id("rebar_chairs").computed == 32
    assert res.by_id("form_boards").computed == 17
    assert res.by_id("concrete_yd").computed == 15   # corrected: no double count
    assert res.by_id("j_bolts").computed == 36
    assert not any(r.error for r in res.results)


def test_old_spreadsheet_concrete_method_available_as_setting(house):
    res = _engine(thickened_count_full_depth=1.0).compute(foundation_measurements(house))
    assert res.by_id("concrete_yd").raw == pytest.approx((320 + 128 * 8 / 12) / 27 + 1)


def test_rebar_breakdown(house):
    r = _engine().compute(foundation_measurements(house)).by_id("rebar_20")
    assert r.raw == pytest.approx((128 * 2 + 2 * 960 / 2) / 18)   # 14.2 + 26.7 + 26.7


def test_settings_change_results(house):
    m = foundation_measurements(house)
    assert _engine(chair_spacing_ft=2.0).compute(m).by_id("rebar_chairs").computed == 64
    assert _engine(rebar_grid_spacing_ft=1.0).compute(m).by_id("rebar_20").computed == 121


def test_plate_layout_and_bolts():
    assert plate_pieces(40, 16) == [16, 16, 8]
    assert plate_pieces(16, 16) == [16]
    assert bolts_for_piece(16, 6, 9) == 4
    assert bolts_for_piece(8, 6, 9) == 3
    assert bolts_for_piece(1.0, 6, 9) == 1


def test_non_thickened_slab_has_no_edge_items():
    plan = _plan([(0, 0), (120, 0), (120, 120), (0, 120)], [(0, 0), (120, 0), (120, 120), (0, 120)],
                 slab_edge_type="monolithic", slab_reinforcement="wire_mesh")
    res = _engine().compute(foundation_measurements(plan))
    assert res.by_id("rebar_20").computed == 0
    assert res.by_id("rebar_chairs").computed == 0
    assert res.by_id("concrete_yd").raw > 1.0


def test_l_shaped_slab_is_flagged_not_silent():
    pts = [(0, 0), (240, 0), (240, 120), (120, 120), (120, 240), (0, 240)]
    plan = _plan(pts, pts)
    m = foundation_measurements(plan)
    assert not m["slabs"][0]["rectangular"]
    assert m["slabs"][0]["area_sqft"] > (240 * 240 - 120 * 120) / 144.0   # outside face is larger
    msgs = [c.message for c in run_checks(foundation_checks(), m, _engine().compute(m))]
    assert any("not rectangular" in x for x in msgs)


def test_no_slab_is_an_error():
    plan = SimpleNamespace(wall_sets=[], rooms=[])
    m = foundation_measurements(plan)
    out = run_checks(foundation_checks(), m, _engine().compute(m))
    assert any(c.severity == "error" and c.name == "slab present" for c in out)


def test_form_board_depth_check(house):
    m = foundation_measurements(house)
    assert not run_checks([form_board_check(AssumptionSet(FOUNDATION_DEFAULTS))], m, _engine().compute(m))
    m["slabs"][0]["thickness_in"] = 6.0
    out = run_checks([form_board_check(AssumptionSet(FOUNDATION_DEFAULTS))], m, _engine().compute(m))
    assert "2x6" in out[0].message
    m["slabs"][0]["thickness_in"] = 4.0


def test_dimension_snapping_prevents_off_by_a_hair_roundup():
    # 24'-0 1/16" sketch error must not turn 12 runs into 13
    plan = _plan([(0, 0), (474.44, 0), (474.44, 282.6), (0, 282.6)],
                 [(0, 0), (474.44, 0), (474.44, 282.6), (0, 282.6)])
    s = foundation_measurements(plan)["slabs"][0]
    assert s["length_ft"] == 40.0 and s["width_ft"] == 24.0
