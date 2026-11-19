"""Tests for the takeoff engine core (Phase 1)."""
import math

import pytest

from EstiSketch.TakeoffEngine import (
    AssumptionSet, Check, LineItem, ReferenceTakeoff, TakeoffEngine,
    compare_to_reference, round_qty, run_checks,
)

M = {"slab_perimeter_ft": 128.0, "slab_length_ft": 40.0, "slab_width_ft": 24.0, "roof_squares": 14.0}


def _items():
    return [
        LineItem("chairs", "2 bar rebar chairs", "Foundation", "ea",
                 lambda m, a: m["slab_perimeter_ft"] / a["chair_spacing_ft"],
                 requires=["slab_perimeter_ft"]),
        LineItem("roof_nails", "Roofing nails", "Roofing", "ea",
                 lambda m, a: m["roof_squares"] * a["nails_per_square"], requires=["roof_squares"]),
        LineItem("slab_rebar", "Slab rebar", "Foundation", "ea",
                 lambda m, a: (m["slab_width_ft"] / a["rebar_spacing_ft"] * m["slab_length_ft"]
                               + m["slab_length_ft"] / a["rebar_spacing_ft"] * m["slab_width_ft"]) / a["rebar_net_len_ft"],
                 requires=["slab_width_ft", "slab_length_ft"]),
    ]


def _engine():
    a = AssumptionSet({"chair_spacing_ft": 4.0, "nails_per_square": 400.0,
                       "rebar_spacing_ft": 2.0, "rebar_net_len_ft": 18.0})
    return TakeoffEngine(_items(), a)


def test_round_qty_ignores_float_noise():
    assert round_qty(14.0000000001) == 14.0
    assert round_qty(14.2) == 15.0
    assert round_qty(14.4, "round") == 14.0


def test_golden_values_from_simple_house():
    res = _engine().compute(M)
    assert res.by_id("chairs").computed == 32
    assert res.by_id("roof_nails").computed == 5600
    assert res.by_id("slab_rebar").computed == 54  # 26.67 + 26.67 -> 53.3 -> 54


def test_waste_applied_before_rounding():
    eng = _engine()
    eng.items[0].waste_pct = 10.0
    assert eng.compute(M).by_id("chairs").computed == 36  # 32 * 1.10 = 35.2


def test_assumption_resolution_order():
    a = AssumptionSet({"x": 1.0})
    a.set_project("x", 2.0)
    a.set_item("i", "x", 3.0)
    assert a.get("x") == 2.0 and a.get("x", "i") == 3.0 and a.get("x", "other") == 2.0
    assert len(a.history) == 2
    with pytest.raises(KeyError):
        a.get("missing")


def test_item_level_assumption_changes_only_that_item():
    eng = _engine()
    eng.assumptions.set_item("roof_nails", "nails_per_square", 380.0)
    res = eng.compute(M)
    assert res.by_id("roof_nails").computed == 5320
    assert res.by_id("chairs").computed == 32


def test_missing_measurement_is_reported_not_silent():
    res = _engine().compute({"roof_squares": 14.0})
    assert res.by_id("chairs").error
    assert res.by_id("roof_nails").computed == 5600
    checks = run_checks([], {}, res)
    assert any(c.severity == "error" and c.name == "chairs" for c in checks)


def test_formula_exception_is_reported():
    eng = TakeoffEngine([LineItem("bad", "Bad", "X", "ea", lambda m, a: 1 / 0)], AssumptionSet())
    assert "division" in eng.compute({}).by_id("bad").error


def test_override_and_stale_flow():
    eng = _engine()
    eng.set_override("roof_nails", 6000, current_computed=5600)
    r = eng.compute(M).by_id("roof_nails")
    assert r.final == 6000 and r.computed == 5600 and not r.stale

    changed = dict(M, roof_squares=15.0)
    r = eng.compute(changed).by_id("roof_nails")
    assert r.stale and r.old_computed == 5600 and r.computed == 6000 and r.final == 6000
    assert any("stale" in c.message for c in run_checks([], changed, eng.compute(changed)))

    eng.keep_override("roof_nails", 6000)
    assert not eng.compute(changed).by_id("roof_nails").stale
    eng.clear_override("roof_nails")
    assert eng.compute(changed).by_id("roof_nails").override is None


def test_overrides_roundtrip():
    eng = _engine()
    eng.set_override("chairs", 40, 32)
    other = _engine()
    other.load_overrides(eng.overrides_to_dict())
    assert other.compute(M).by_id("chairs").final == 40


def test_custom_check():
    chk = Check("rebar sanity", lambda m, r: "too few" if r.by_id("slab_rebar").computed < 100 else "")
    out = run_checks([chk], M, _engine().compute(M))
    assert [c.name for c in out] == ["rebar sanity"]


def test_reference_variance_and_roundtrip(tmp_path):
    res = _engine().compute(M)
    ref = ReferenceTakeoff("simple_house", {"chairs": 32, "roof_nails": 17600, "gone": 5})
    path = tmp_path / "ref.json"
    ref.save(str(path))
    ref = ReferenceTakeoff.load(str(path))
    var = {v.item_id: v for v in compare_to_reference(res, ref)}
    assert var["chairs"].diff == 0 and var["chairs"].pct == 0
    assert var["roof_nails"].diff == -12000
    assert var["roof_nails"].pct == pytest.approx(-68.18, abs=0.01)
    assert math.isnan(var["gone"].engine)
