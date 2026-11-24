"""Phase 5 tests: wall-based gable roof geometry, framing and roofing."""
import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import AssumptionSet, TakeoffEngine, run_checks  # noqa: E402
from EstiSketch.TakeoffEngine.measurements import plan_measurements  # noqa: E402
from EstiSketch.TakeoffEngine.roof import (  # noqa: E402
    ROOF_DEFAULTS, framing_method, roof_checks, roof_geometry, roof_items)
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _a(**over):
    a = AssumptionSet(ROOF_DEFAULTS)
    for k, v in over.items():
        a.set_project(k, v)
    return a


def _eng(**over):
    return TakeoffEngine(roof_items(), _a(**over))


def _wall(a, b, h0=96.0, h1=None, width=5.5):
    return SimpleNamespace(start=a, end=b, width=width, height=h0, height_at_end=h1 or h0)


def _gable_house(w=474.5, d=282.5, rise=48.0):
    """Gable walls are the short (x = w, x = 0) sides; eave walls run along x."""
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    return [_wall(pts[0], pts[1]),
            _wall(pts[1], (w, d / 2), 96, 96 + rise), _wall((w, d / 2), pts[2], 96 + rise, 96),
            _wall(pts[2], pts[3]),
            _wall(pts[3], (0, d / 2), 96, 96 + rise), _wall((0, d / 2), pts[0], 96 + rise, 96)]


def _roof(**kw):
    d = dict(roof_type="gable", pitch_rise=4.0, pitch_run=12.0, overhang=24.0, material="asphalt_shingle")
    d.update(kw)
    return SimpleNamespace(**d)


def _plan(walls=None, roofs=None):
    return SimpleNamespace(wall_sets=[walls if walls is not None else _gable_house()], rooms=[], doors=[],
                           windows=[], roofs=[_roof()] if roofs is None else roofs)


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE)
    return c


def test_geometry_matches_hand_math():
    g = roof_geometry(plan_measurements(_plan()), _a().resolve_all())
    assert g["slope_len_ft"] == pytest.approx(14 * math.sqrt(1 + (4 / 12) ** 2))   # 14' 9 1/16"
    assert g["length_ft"] == 44 and g["ridge_ft"] == 44
    assert g["area_sqft"] == pytest.approx(2 * 14.7573 * 44, abs=0.1)
    assert g["perimeter_ft"] == pytest.approx(88 + 4 * 14.7573, abs=0.01)
    assert g["horizontal_perimeter_ft"] == 144


def test_overhang_and_pitch_come_from_the_roof_object():
    base = roof_geometry(plan_measurements(_plan()), _a().resolve_all())
    big = roof_geometry(plan_measurements(_plan(roofs=[_roof(overhang=12.0, pitch_rise=6.0)])), _a().resolve_all())
    assert big["length_ft"] == 42 and big["slope_len_ft"] < base["slope_len_ft"] * 1.1
    assert big["slope_factor"] == pytest.approx(math.sqrt(1 + 0.25))


def test_golden_simple_house_roofing(house):
    res = _eng().compute(plan_measurements(house))
    got = {r.item.id: r.computed for r in res.results}
    assert got["roof_trusses:trusses"] == 21
    assert got["outlookers"] == 8
    assert got["fascia_backers"] == 10
    assert got["bird_blocking"] == 5
    assert got["soffit_nailers"] == 9
    assert got["shingles"] == 14 and got["underlayment"] == 14
    assert got["drip_edge"] == 148 and got["soffit"] == 148 and got["fascia"] == 148
    assert got["ridge_cap"] == 44
    assert got["roofing_nails"] == 5600
    assert got["roof_sheathing"] == 42 and got["roof_sheathing_nails"] == 4032
    assert "roof_stick:rafters" not in got and not any(r.error for r in res.results)


def test_roof_is_independent_of_split_gable_walls(house):
    # fixture has split gable walls and stale roof edges; walls alone give the roof
    m = plan_measurements(house)
    assert m["roof"]["supported"] and m["roof"]["wall_pitch_rise"] == pytest.approx(4.08, abs=0.01)


def test_default_method_is_trusses_and_stick_blocked_by_span():
    m = plan_measurements(_plan())      # 24' span
    assert framing_method(m, _a().resolve_all()) == "trusses"
    assert framing_method(m, _a(roof_framing_method=1.0).resolve_all()) == "trusses"   # too wide
    assert framing_method(m, _a(roof_framing_method=1.0, stick_max_span_ft=30).resolve_all()) == "stick"
    msgs = [c.message for c in run_checks(roof_checks(_a(roof_framing_method=1.0)), m,
                                          _eng(roof_framing_method=1.0).compute(m))]
    assert any("too long for stick" in x for x in msgs)


def test_stick_framing_rows_for_a_narrow_house():
    m = plan_measurements(_plan(_gable_house(w=474.5, d=186.5, rise=32)))      # 16' span
    res = _eng(roof_framing_method=2.0).compute(m)
    ids = {r.item.id: r.computed for r in res.results}
    assert "roof_trusses:trusses" not in ids
    assert ids["roof_stick:rafters"] == 2 * 21 and ids["roof_stick:joists"] == 21
    assert ids["roof_stick:ridge"] == 1


def test_auto_picks_trusses_when_span_is_too_great():
    res = _eng(roof_framing_method=2.0).compute(plan_measurements(_plan()))
    assert "roof_trusses:trusses" in {r.item.id for r in res.results}


def test_truss_spacing_setting():
    m = plan_measurements(_plan())
    assert _eng(truss_spacing_in=16.0).compute(m).by_id("roof_trusses:trusses").computed == 31


def test_waste_and_nail_settings():
    m = plan_measurements(_plan())
    assert _eng(shingle_waste_pct=0.0).compute(m).by_id("shingles").computed == 13
    assert _eng(nails_per_square=380).compute(m).by_id("roofing_nails").computed == 14 * 380


def test_no_roof_and_unsupported_shapes_are_errors_not_guesses():
    for plan, text in [(_plan(roofs=[]), "no roof"),
                       (_plan(roofs=[_roof(roof_type="hip")]), "not supported"),
                       (_plan(walls=[_wall((0, 0), (100, 0)), _wall((100, 0), (100, 100)),
                                     _wall((100, 100), (0, 0))]), "four-sided"),
                       (_plan(walls=[SimpleNamespace(start=a, end=b, width=5.5, height=96.0, height_at_end=96.0)
                                     for a, b in [((0, 0), (240, 0)), ((240, 0), (240, 120)),
                                                  ((240, 120), (0, 120)), ((0, 120), (0, 0))]]), "two opposite")]:
        m = plan_measurements(plan)
        res = _eng().compute(m)
        out = run_checks(roof_checks(_a()), m, res)
        assert any(c.severity == "error" and text in c.message for c in out), text
        assert all(r.error for r in res.results if r.item.id == "shingles")


def test_pitch_mismatch_and_material_checks():
    m = plan_measurements(_plan(roofs=[_roof(pitch_rise=6.0, material="metal")]))
    msgs = [c.message for c in run_checks(roof_checks(_a()), m, _eng().compute(m))]
    assert any("wall heights imply" in x for x in msgs)
    assert any("metal" in x for x in msgs)


def test_multiple_roofs_warn():
    m = plan_measurements(_plan(roofs=[_roof(), _roof()]))
    assert any("only the first" in c.message for c in run_checks(roof_checks(_a()), m, _eng().compute(m)))


def test_flat_walls_with_marked_gable_and_eave_roof_edges():
    """Standard workflow: 4 flat 96\" walls with 2 marked 'gable' and 2 marked 'eave' in roof.edges."""
    pts = [(0, 0), (360, 0), (360, 120), (0, 120)]
    walls = [
        SimpleNamespace(identifier=f"w{i}", start=pts[i], end=pts[(i + 1) % 4],
                        width=5.5, height=96.0, height_at_end=96.0)
        for i in range(4)
    ]
    edges = [
        SimpleNamespace(wall_identifier="w0", edge_type="eave"),
        SimpleNamespace(wall_identifier="w1", edge_type="gable"),
        SimpleNamespace(wall_identifier="w2", edge_type="eave"),
        SimpleNamespace(wall_identifier="w3", edge_type="gable"),
    ]
    roof = _roof(pitch_rise=6.0, overhang=24.0, edges=edges)
    plan = _plan(walls=walls, roofs=[roof])

    m = plan_measurements(plan)
    assert m["roof"]["supported"] is True
    assert m["roof"]["wall_pitch_rise"] is None

    res = _eng().compute(m)
    assert not any(r.error for r in res.results)
    assert res.by_id("shingles").computed > 0
    assert res.by_id("roof_trusses:trusses").computed > 0
    assert run_checks(roof_checks(_a()), m, res) == []

