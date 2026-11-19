"""Phase 3 tests: wall measurements, plates, studs, gables, openings, headers."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_open_project import _create_mock_canvas  # noqa: E402

from EstiSketch.TakeoffEngine import AssumptionSet, LineItem, TakeoffEngine, run_checks  # noqa: E402
from EstiSketch.TakeoffEngine.foundation import FOUNDATION_DEFAULTS  # noqa: E402
from EstiSketch.TakeoffEngine.lumber import (  # noqa: E402
    interp, lumber_size_for_thickness, pack_boards, split_run)
from EstiSketch.TakeoffEngine.measurements import plan_measurements, wall_runs  # noqa: E402
from EstiSketch.TakeoffEngine.wall_framing import (  # noqa: E402
    WALL_DEFAULTS, gable_stud_rows, header_size, opening_framing, run_studs, stud_positions,
    stud_stock_for, wall_framing_checks, wall_framing_items)
from EstiSketch.project_io import open_project  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "simple_house.xml")


def _a(**over):
    a = AssumptionSet({**FOUNDATION_DEFAULTS, **WALL_DEFAULTS})
    for k, v in over.items():
        a.set_project(k, v)
    return a


def _engine(**over):
    return TakeoffEngine(wall_framing_items(), _a(**over))


def _wall(a, b, width=5.5, h0=96.0, h1=None):
    return SimpleNamespace(start=a, end=b, width=width, height=h0, height_at_end=h1 or h0)


def _box(w=240.0, d=120.0, height=96.0):
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    return [_wall(pts[i], pts[(i + 1) % 4], h0=height) for i in range(4)]


def _plan(walls, doors=(), windows=()):
    return SimpleNamespace(wall_sets=[walls], rooms=[], doors=list(doors), windows=list(windows))


def _opening(kind, w, h, wall, ratio):
    return (wall, SimpleNamespace(identifier=f"{kind}{w}", width=w, height=h), ratio)


@pytest.fixture(scope="module")
def house():
    c = _create_mock_canvas()
    open_project(c, FIXTURE)
    return c


# ---- helpers -------------------------------------------------------------
def test_pack_boards_kerf_and_tolerance():
    assert pack_boards([96, 96], 192)[0] == 1            # two 8' from one 16' (one cut, trim a hair)
    assert pack_boards([96, 96, 96], 192)[0] == 2
    assert pack_boards([150, 150], 192)[0] == 2
    n, over = pack_boards([300], 192)
    assert over == [300]


def test_split_run_and_sizes():
    assert split_run(480, 192) == [192, 192, 96]
    assert lumber_size_for_thickness(3.5) == "2x4" and lumber_size_for_thickness(5.5) == "2x6"
    assert lumber_size_for_thickness(7.25) == "2x8"


def test_interp():
    p = [(0, 96), (100, 96), (200, 146)]
    assert interp(p, 150) == pytest.approx(121.0)
    assert interp(p, -5) == 96 and interp(p, 500) == 146


def test_stud_stock_by_height():
    a = _a().resolve_all()
    assert stud_stock_for(96, a) == 8
    assert stud_stock_for(108, a) == 9
    assert stud_stock_for(120, a) == 10
    assert stud_stock_for(144, a) == 12


# ---- runs ----------------------------------------------------------------
def test_runs_merge_collinear_and_use_outside_face():
    walls = _box()
    # split the top wall in two
    walls[0:1] = [_wall((0, 0), (100, 0)), _wall((100, 0), (240, 0))]
    runs = wall_runs(_plan(walls))
    assert [r["closed"] for r in runs] == [True] * 4
    assert runs[0]["length_in"] == pytest.approx(245.5)    # 240 + 5.5
    assert runs[1]["length_in"] == pytest.approx(125.5)
    assert len(runs[0]["walls"]) == 2


def test_run_starting_mid_edge_wraps_around():
    pts = [(0, 0), (120, 0), (240, 0), (240, 120), (0, 120)]
    walls = [_wall(pts[i], pts[(i + 1) % 5]) for i in range(5)]
    runs = wall_runs(_plan(walls))
    assert len(runs) == 4 and runs[0]["length_in"] == pytest.approx(245.5)


def test_open_wall_run_is_centerline_and_not_exterior():
    runs = wall_runs(_plan([_wall((0, 0), (100, 0)), _wall((100, 0), (200, 0))]))
    assert len(runs) == 1 and not runs[0]["closed"] and not runs[0]["exterior"]
    assert runs[0]["length_in"] == 200


def test_gable_profile_from_wall_heights():
    pts = [(0, 0), (240, 0), (240, 120), (0, 120)]
    walls = [_wall(pts[0], pts[1]), _wall(pts[1], (240, 60), h0=96, h1=140),
             _wall((240, 60), pts[2], h0=140, h1=96), _wall(pts[2], pts[3]), _wall(pts[3], pts[0])]
    runs = wall_runs(_plan(walls))
    gable = [r for r in runs if r["max_height_in"] > 100][0]
    assert gable["base_height_in"] == 96 and gable["max_height_in"] == 140


# ---- plates, sill seal ----------------------------------------------------
def test_plates_for_a_box():
    res = _engine().compute(plan_measurements(_plan(_box())))
    assert res.by_id("sill_seal").computed == pytest.approx(2 * (245.5 + 125.5) / 12.0, abs=0.2)
    assert res.by_id("bottom_plates:2x6").computed == 4   # 54 ft of plate: 2 full boards + remainders packed
    assert res.by_id("top_plates:2x6").computed == 8
    with pytest.raises(KeyError):
        res.by_id("gable_top_plate:2x6")                    # flat walls have none


def test_wall_size_selects_lumber_size():
    walls = _box()
    for w in walls:
        w.width = 3.5
    res = _engine().compute(plan_measurements(_plan(walls)))
    assert res.by_id("studs:2x4_8").computed > 0
    assert res.by_id("bottom_plates:2x4").computed > 0


# ---- studs ---------------------------------------------------------------
def test_stud_positions_clear_of_corners():
    r = wall_runs(_plan(_box()))[0]
    pos = stud_positions(r, _a().resolve_all())
    assert pos[0] == 16 and pos[-1] == 224 and len(pos) == 14     # 245.5 - 5.5 = 240; 16..224 (240 is the corner)


def test_box_stud_count_breakdown():
    m = plan_measurements(_plan(_box()))
    a = _a().resolve_all()
    got = run_studs(m, a)
    assert got == [("2x6", 8, sum(len(stud_positions(r, a)) for r in m["wall_runs"]) + 4 * 3)]


def test_corner_studs_setting():
    base = run_studs(plan_measurements(_plan(_box())), _a().resolve_all())[0][2]
    four = run_studs(plan_measurements(_plan(_box())), _a(corner_studs=4).resolve_all())[0][2]
    assert four - base == 4


def test_open_run_gets_end_studs():
    m = plan_measurements(_plan([_wall((0, 0), (100, 0))]))
    n = run_studs(m, _a().resolve_all())[0][2]
    assert n == len(stud_positions(m["wall_runs"][0], _a().resolve_all())) + 2


# ---- gables --------------------------------------------------------------
def _gable_box():
    pts = [(0, 0), (480, 0), (480, 288), (0, 288)]
    return [_wall(pts[0], pts[1]), _wall(pts[1], (480, 144), h0=96, h1=144),
            _wall((480, 144), pts[2], h0=144, h1=96), _wall(pts[2], pts[3]), _wall(pts[3], pts[0])]


def test_gable_studs_are_paired_to_half():
    m = plan_measurements(_plan(_gable_box()))
    rows = gable_stud_rows(m, _a().resolve_all())
    assert rows == [("2x6", 8, 9)]   # 17 interior positions on a 24' gable -> 9 boards


def test_tall_gable_needs_longer_stock():
    walls = _gable_box()
    walls[1].height_at_end = walls[2].height = 96 + 200      # absurd rise
    rows = gable_stud_rows(plan_measurements(_plan(walls)), _a().resolve_all())
    assert rows[0][1] >= 14


def test_gable_top_plate_follows_slope():
    res = _engine().compute(plan_measurements(_plan(_gable_box())))
    assert res.by_id("gable_top_plate:2x6").computed == 2          # one sloped board each side


# ---- openings & headers -------------------------------------------------
def test_door_adds_king_jack_and_removes_studs():
    walls = _box()
    base = run_studs(plan_measurements(_plan(walls)), _a().resolve_all())[0][2]
    plan = _plan(walls, doors=[_opening("door", 36, 80, walls[0], 0.5)])
    m = plan_measurements(plan)
    row = opening_framing(m, _a().resolve_all())["rows"][0]
    assert row["kings"] == 2 and row["jacks"] == 2 and row["removed"] >= 1
    assert run_studs(m, _a().resolve_all())[0][2] == base + 4 - row["removed"]


def test_wide_opening_gets_double_jacks():
    walls = _box()
    m = plan_measurements(_plan(walls, doors=[_opening("door", 96, 80, walls[0], 0.5)]))
    assert opening_framing(m, _a().resolve_all())["rows"][0]["jacks"] == 4


def test_window_cripples_below_only_on_8ft_walls():
    walls = _box()
    m = plan_measurements(_plan(walls, windows=[_opening("window", 48, 36, walls[0], 0.5)]))
    row = opening_framing(m, _a().resolve_all())["rows"][0]
    assert row["cripples"] and all(c == pytest.approx(41.0) for c in row["cripples"])
    res = _engine().compute(m)
    assert res.by_id("cripples:2x6_8").computed == 2           # 3 cripples, 2 per stud


def test_cripples_above_on_tall_walls():
    walls = _box(height=120.0)
    m = plan_measurements(_plan(walls, doors=[_opening("door", 36, 80, walls[0], 0.5)]))
    assert opening_framing(m, _a().resolve_all())["rows"][0]["cripples"]


def test_header_span_table():
    a = _a().resolve_all()
    assert header_size(36, a) == "2x10" and header_size(72, a) == "2x10"
    assert header_size(80, a) == "2x12" and header_size(120, a) is None
    a2 = _a(header_max_in_2x6=36).resolve_all()
    assert header_size(36, a2) == "2x6"


def test_header_assembly_and_oversize_check():
    walls = _box()
    plan = _plan(walls, doors=[_opening("door", 120, 80, walls[0], 0.5)],
                 windows=[_opening("window", 36, 36, walls[2], 0.5)])
    a = _a()
    m = plan_measurements(plan)
    res = TakeoffEngine(wall_framing_items(), a).compute(m)
    assert res.by_id("headers:hdr_2x10").computed >= 1
    msgs = [c.message for c in run_checks(wall_framing_checks(a), m, res)]
    assert any("span table" in x for x in msgs)


def test_orphan_openings_ignored_with_warning():
    walls = _box()
    plan = _plan(walls, doors=[(None, SimpleNamespace(identifier="d", width=36, height=80), 0.5)])
    a = _a()
    m = plan_measurements(plan)
    assert m["openings"] == [] and m["orphan_openings"] == 1
    msgs = [c.message for c in run_checks(wall_framing_checks(a), m, TakeoffEngine([], a).compute(m))]
    assert any("not attached" in x for x in msgs)


def test_no_walls_is_an_error():
    a = _a()
    m = plan_measurements(SimpleNamespace(wall_sets=[], rooms=[], doors=[], windows=[]))
    out = run_checks(wall_framing_checks(a), m, TakeoffEngine([], a).compute(m))
    assert any(c.severity == "error" for c in out)


# ---- engine: multi rows, overrides, hide_if_zero --------------------------
def test_multi_rows_can_be_overridden_individually():
    eng = _engine()
    m = plan_measurements(_plan(_box()))
    before = eng.compute(m).by_id("top_plates:2x6").computed
    eng.set_override("top_plates:2x6", before + 2, before)
    r = eng.compute(m).by_id("top_plates:2x6")
    assert r.final == before + 2 and not r.stale


def test_hide_if_zero():
    a = AssumptionSet()
    eng = TakeoffEngine([LineItem("z", "Zero", "X", "ea", lambda m, aa: 0.0, hide_if_zero=True)], a)
    assert eng.compute({}).results == []


# ---- golden: simple_house ------------------------------------------------
def test_simple_house_golden_framing(house):
    m = plan_measurements(house)
    assert m["orphan_openings"] == 3 and len(m["openings"]) == 5
    res = _engine().compute(m)
    assert res.by_id("sill_seal").computed == 128
    assert res.by_id("bottom_plates:2x6").computed == 8
    assert res.by_id("top_plates:2x6").computed == 16
    assert res.by_id("gable_top_plate:2x6").computed == 4
    assert res.by_id("headers:hdr_2x10").computed == 3
    assert res.by_id("headers:flat_2x6").computed == 2
    assert res.by_id("gable_studs:2x6_8").computed == 18
    assert res.by_id("cripples:2x6_8").computed == 5
    assert res.by_id("studs:2x6_8").computed == 109
    assert not any(r.error for r in res.results)
