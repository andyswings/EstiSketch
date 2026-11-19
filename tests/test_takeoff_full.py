"""Phase 7 tests: fasteners, full-house takeoff builder, golden reference, export, and calibration suggestions."""
import csv
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import (  # noqa: E402
    ALL_DEFAULTS,
    AssumptionSet,
    LineItem,
    ReferenceTakeoff,
    TakeoffEngine,
    compare_to_reference,
    export_takeoff_csv,
    export_takeoff_json,
    item_confidence,
    run_takeoff,
    suggest_calibrations,
)
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE_XML = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")
FIXTURE_REF = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house_reference.json")


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE_XML)
    return c


def test_simple_house_matches_golden_reference(house):
    res, checks, _ = run_takeoff(house)
    ref = ReferenceTakeoff.load(FIXTURE_REF)
    variances = compare_to_reference(res, ref)

    assert len(variances) == len(ref.values)
    mismatches = [v for v in variances if v.diff != 0]
    assert mismatches == []
    assert not any(r.error for r in res.results)
    # Only warning on simple_house should be the 3 orphaned openings
    assert [c.name for c in checks] == ["orphan openings"]


def test_fasteners_respect_assumption_settings(house):
    a = AssumptionSet(ALL_DEFAULTS)
    a.set_project("framing_nails_per_sqft", 2.0)
    a.set_project("drywall_screws_per_sqft", 1.25)
    res, _, _ = run_takeoff(house, assumptions=a)
    assert res.by_id("framing_nails").computed == 1920   # 960 * 2.0
    assert res.by_id("drywall_screws").computed == 2550  # 2039.9 * 1.25 = 2549.87 -> 2550


def test_exports_csv_and_json(house, tmp_path):
    res, checks, _ = run_takeoff(
        house,
        overrides={"framing_nails": {"value": 1500.0, "computed_at_override": 1440.0}},
    )
    csv_path = tmp_path / "takeoff.csv"
    export_takeoff_csv(res, str(csv_path))
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id = {row["ID"]: row for row in rows}
    assert float(by_id["framing_nails"]["Qty"]) == 1500.0
    assert float(by_id["framing_nails"]["Computed"]) == 1440.0
    assert float(by_id["framing_nails"]["Override"]) == 1500.0

    json_path = tmp_path / "takeoff.json"
    text = export_takeoff_json(res, checks, str(json_path))
    data = json.loads(text)
    assert len(data["items"]) == len(res.results)
    assert data["checks"][0]["name"] == "orphan openings"


def test_calibration_suggestions_require_consistent_drift():
    items = [
        LineItem("studs", "Studs", "Framing", "ea", lambda m, a: m["s"]),
        LineItem("nails", "Nails", "Fasteners", "ea", lambda m, a: m["n"]),
    ]
    eng = TakeoffEngine(items, AssumptionSet())

    # 3 jobs where studs are consistently ~10% high, nails are mixed (+10%, -10%, 0%)
    pairs = [
        (eng.compute({"s": 110, "n": 1100}), ReferenceTakeoff("j1", {"studs": 100, "nails": 1000})),
        (eng.compute({"s": 220, "n": 900}), ReferenceTakeoff("j2", {"studs": 200, "nails": 1000})),
        (eng.compute({"s": 330, "n": 1000}), ReferenceTakeoff("j3", {"studs": 300, "nails": 1000})),
    ]

    # Fewer than min_jobs -> no suggestions
    assert suggest_calibrations(pairs[:2], min_jobs=3) == []

    # 3 jobs -> suggests only studs (consistently high), not nails (mixed)
    sugs = suggest_calibrations(pairs, min_jobs=3, threshold_pct=5.0)
    assert len(sugs) == 1
    assert sugs[0].item_id == "studs"
    assert sugs[0].direction == "high"
    assert sugs[0].mean_pct_diff == pytest.approx(10.0)

    conf = item_confidence(pairs, tolerance_pct=2.0)
    assert conf["studs"] == "0/3 matched"
    assert conf["nails"] == "1/3 matched"
