"""Phase 3 line items: wall framing (sill seal, plates, studs, gable framing, openings, headers)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from .checks import Check
from .line_item import LineItem, NONE
from .lumber import interp, lumber_size_for_thickness, pack_boards, split_run

WALL_DEFAULTS: Dict[str, float] = {
    "stud_spacing_in": 16.0,
    "stud_actual_thickness_in": 1.5,
    "plate_stock_ft": 16.0,
    "corner_studs": 3.0,               # California corner: studs per corner assembly (clip-backed)
    "bottom_plate_layers": 1.0,
    "top_plate_layers": 2.0,
    "wall_plate_stack_in": 4.5,        # 1 bottom + 2 top plates, subtracted to get stud length
    "stud_precut_loss_in": 3.375,      # nominal length minus precut length (8' -> 92-5/8")
    "kerf_in": 0.125,
    "cut_short_tolerance_in": 0.25,
    # gables
    "gable_stud_extra_in": 0.0,
    "gable_min_extra_in": 0.5,
    # openings
    "jack_thickness_in": 1.5,
    "wide_opening_in": 72.0,           # openings wider than this get double jacks per side
    "opening_head_height_in": 80.0,
    "header_flat_in": 1.5,
    "sill_stack_in": 3.0,
    "min_cripple_in": 4.0,
    "header_stock_ft": 16.0,
    "header_max_in_2x6": 0.0,          # span table: widest opening each doubled header size covers
    "header_max_in_2x8": 0.0,
    "header_max_in_2x10": 72.0,
    "header_max_in_2x12": 96.0,
}

HEADER_SIZES = [("2x6", 5.5), ("2x8", 7.25), ("2x10", 9.25), ("2x12", 11.25)]
STUD_STOCK_FT = [8, 9, 10, 12, 14, 16]
GABLE_STOCK_FT = [8, 10, 12, 14, 16]


def _usable(stock_ft: int, a) -> float:
    return stock_ft * 12.0 - a["stud_precut_loss_in"]


def stud_stock_for(height_in: float, a) -> int:
    need = height_in - a["wall_plate_stack_in"]
    for s in STUD_STOCK_FT:
        if _usable(s, a) >= need - 1e-6:
            return s
    return STUD_STOCK_FT[-1]


def stud_positions(run, a) -> List[float]:
    """Interior stud centers (in) along a run: 16" OC from the run start, clear of end/corner assemblies."""
    sp = a["stud_spacing_in"]
    end_clear = run["thickness_in"] if run["closed"] else 1.5
    out, i = [], 1
    while i * sp < run["length_in"] - end_clear - 1e-9:
        out.append(i * sp)
        i += 1
    return out


def jacks_per_side(width_in: float, a) -> int:
    return 2 if width_in > a["wide_opening_in"] else 1


def _run_by_id(m) -> Dict[str, Any]:
    return {r["id"]: r for r in m["wall_runs"]}


def header_size(width_in: float, a):
    """Smallest doubled-header size whose span limit covers `width_in`, or None if none does."""
    for name, _ in HEADER_SIZES:
        if width_in <= a[f"header_max_in_{name}"] + 1e-9:
            return name
    return None


def opening_framing(m, a) -> Dict[str, Any]:
    """Per-opening studs removed, kings, jacks, cripples (counts) and header cut pieces."""
    runs = _run_by_id(m)
    rows = []
    for o in m["openings"]:
        r = runs[o["run_id"]]
        sp = a["stud_spacing_in"]
        half = o["width_in"] / 2.0
        c = o["center_in"]
        zone = half + 2 * a["jack_thickness_in"] - 0.75 + 0.01  # studs this close are replaced by king/jack
        removed = sum(1 for x in stud_positions(r, a) if abs(x - c) <= zone)
        jacks = 2 * jacks_per_side(o["width_in"], a)
        wall_h = r["base_height_in"]  # gable triangles are framed separately (gable studs)
        head_h = a["opening_head_height_in"] if o["kind"] == "window" else o["height_in"] + 2.0
        header_asm = 9.25 + a["header_flat_in"]
        above = wall_h - 3.0 - (head_h + header_asm)   # under the double top plate
        cripple_above = []
        cripple_below = []
        if above >= a["min_cripple_in"]:
            n = sum(1 for x in stud_positions(r, a) if abs(x - c) < half)
            cripple_above = [above] * max(n, 0)
        if o["kind"] == "window":
            sill_h = head_h - o["height_in"]
            ln = sill_h - a["sill_stack_in"]  # bottom plate + rough sill under the cripples
            n = sum(1 for x in stud_positions(r, a) if abs(x - c) < half)
            if ln >= a["min_cripple_in"]:
                cripple_below = [ln] * n
        rows.append({"opening": o, "run": r, "removed": removed, "kings": 2, "jacks": jacks,
                     "cripples": cripple_above + cripple_below, "size": header_size(o["width_in"], a),
                     "header_len_in": o["width_in"] + 2 * a["jack_thickness_in"]})
    return {"rows": rows}


def run_studs(m, a) -> List[Tuple[str, int, int]]:
    """[(lumber size, stock ft, count)] for wall studs, kings, jacks, corners (not gable studs/cripples)."""
    counts: Dict[Tuple[str, int], int] = {}
    of = opening_framing(m, a)
    removed_by_run: Dict[str, int] = {}
    extras_by_run: Dict[str, int] = {}
    for row in of["rows"]:
        rid = row["run"]["id"]
        removed_by_run[rid] = removed_by_run.get(rid, 0) + row["removed"]
        extras_by_run[rid] = extras_by_run.get(rid, 0) + row["kings"] + row["jacks"]
    for r in m["wall_runs"]:
        size = lumber_size_for_thickness(r["thickness_in"])
        key = (size, stud_stock_for(r["base_height_in"], a))
        # closed loop: each run owns the full corner assemblies at its two ends, shared with its neighbours
        # (corner_studs/2 per end); open run: a stud at each end
        n = len(stud_positions(r, a)) + (int(a["corner_studs"]) if r["closed"] else 2)
        n += extras_by_run.get(r["id"], 0) - removed_by_run.get(r["id"], 0)
        counts[key] = counts.get(key, 0) + n
    return [(k[0], k[1], v) for k, v in sorted(counts.items())]


def gable_stud_rows(m, a) -> List[Tuple[str, int, int]]:
    """Gable studs: the triangle above each run's base height, studs at the same 16" OC layout.

    Tall middle studs are paired with short ones cut from the same board (one board yields a long and a
    short stud), so stock needed is about half the studs."""
    kerf = a["kerf_in"]
    counts: Dict[Tuple[str, int], int] = {}
    for r in m["wall_runs"]:
        base = r["base_height_in"]
        lengths = []
        for x in stud_positions(r, a):
            extra = interp(r["profile"], x) - base
            if extra > a["gable_min_extra_in"]:
                lengths.append(extra + a["gable_stud_extra_in"])
        if not lengths:
            continue
        lengths.sort()
        stock = next((s for s in GABLE_STOCK_FT if s * 12.0 >= lengths[-1]), GABLE_STOCK_FT[-1])
        usable = stock * 12.0 - kerf
        lo, hi, boards = 0, len(lengths) - 1, 0
        while lo <= hi:
            if lo < hi and lengths[hi] + lengths[lo] + kerf <= usable:
                lo += 1
            hi -= 1
            boards += 1
        key = (lumber_size_for_thickness(r["thickness_in"]), stock)
        counts[key] = counts.get(key, 0) + boards
    return [(k[0], k[1], v) for k, v in sorted(counts.items())]


def cripple_rows(m, a) -> List[Tuple[str, int, int]]:
    """Cripple studs cut from stud stock (several per stud)."""
    pieces: Dict[Tuple[str, int], List[float]] = {}
    for row in opening_framing(m, a)["rows"]:
        r = row["run"]
        key = (lumber_size_for_thickness(r["thickness_in"]), stud_stock_for(r["base_height_in"], a))
        pieces.setdefault(key, []).extend(row["cripples"])
    out = []
    for key, p in sorted(pieces.items()):
        n, _ = pack_boards(p, _usable(key[1], a), a["kerf_in"], a["cut_short_tolerance_in"])
        if n:
            out.append((key[0], key[1], n))
    return out


def _plate_rows(m, a, layers, label):
    stock = a["plate_stock_ft"] * 12.0
    by_size: Dict[str, List[float]] = {}
    for r in m["wall_runs"]:
        size = lumber_size_for_thickness(r["thickness_in"])
        for _ in range(int(layers)):
            by_size.setdefault(size, []).extend(split_run(r["length_in"], stock))
    rows = []
    for size, pieces in sorted(by_size.items()):
        n, _ = pack_boards(pieces, stock, a["kerf_in"], a["cut_short_tolerance_in"])
        rows.append((size, f"{size}x{int(a['plate_stock_ft'])}' {label}", n))
    return rows


def _gable_plate_rows(m, a):
    stock = a["plate_stock_ft"] * 12.0
    by_size: Dict[str, List[float]] = {}
    for r in m["wall_runs"]:
        pts = r["profile"]
        for (x0, h0), (x1, h1) in zip(pts, pts[1:]):
            if abs(h1 - h0) > a["gable_min_extra_in"] and x1 > x0:
                by_size.setdefault(lumber_size_for_thickness(r["thickness_in"]), []).extend(
                    split_run(math.hypot(x1 - x0, h1 - h0), stock))
    rows = []
    for size, pieces in sorted(by_size.items()):
        n, _ = pack_boards(pieces, stock, a["kerf_in"], a["cut_short_tolerance_in"])
        rows.append((size, f"{size}x{int(a['plate_stock_ft'])}' gable upper top plate", n))
    return rows


def _header_rows(m, a):
    stock = a["header_stock_ft"] * 12.0
    bearing: Dict[str, List[float]] = {}
    flats: Dict[str, List[float]] = {}
    for row in opening_framing(m, a)["rows"]:
        if row["size"] is None:
            continue
        bearing.setdefault(row["size"], []).extend([row["header_len_in"]] * 2)  # doubled
        fsize = lumber_size_for_thickness(row["run"]["thickness_in"])
        flats.setdefault(fsize, []).append(row["header_len_in"])
    rows = []
    for size, pieces in sorted(bearing.items()):
        n, _ = pack_boards(pieces, stock, a["kerf_in"], a["cut_short_tolerance_in"])
        rows.append((f"hdr_{size}", f"{size}x{int(a['header_stock_ft'])}' headers (doubled)", n))
    for size, pieces in sorted(flats.items()):
        n, _ = pack_boards(pieces, stock, a["kerf_in"], a["cut_short_tolerance_in"])
        rows.append((f"flat_{size}", f"{size}x{int(a['header_stock_ft'])}' header flat (frame top)", n))
    return rows


def _stock_rows(rows, label):
    return [(f"{size}_{stock}", f"{size} x {stock}' {label}", n) for size, stock, n in rows]


def wall_framing_items() -> List[LineItem]:
    none = lambda m, a: 0.0
    return [
        LineItem("sill_seal", "Sill seal", "Framing", "ft", lambda m, a: m["wall_lf_outside"],
                 explanation="Linear feet of walls (outside-face run lengths).", requires=["wall_runs"]),
        LineItem("bottom_plates", "Bottom plates", "Framing", "ea", none,
                 explanation="Runs laid out in plate stock, remainders packed together.",
                 multi=lambda m, a: _plate_rows(m, a, a["bottom_plate_layers"], "treated bottom plate"),
                 rounding=NONE, requires=["wall_runs"]),
        LineItem("top_plates", "Top plates", "Framing", "ea", none,
                 explanation="Two layers over every run, laid out in plate stock.",
                 multi=lambda m, a: _plate_rows(m, a, a["top_plate_layers"], "top plates"),
                 rounding=NONE, requires=["wall_runs"]),
        LineItem("gable_top_plate", "Gable upper top plate", "Framing", "ea", none,
                 explanation="Sloped top of each gable run (from wall heights), one layer.",
                 multi=_gable_plate_rows, rounding=NONE, requires=["wall_runs"]),
        LineItem("studs", "Studs", "Framing", "ea", none,
                 explanation="Interior studs at spacing + corner assemblies + kings and jacks - studs removed "
                             "by openings.",
                 multi=lambda m, a: _stock_rows(run_studs(m, a), "studs"), rounding=NONE,
                 requires=["wall_runs", "openings"]),
        LineItem("gable_studs", "Gable studs", "Framing", "ea", none,
                 explanation="Studs in the triangle above the base wall height; tall and short studs share boards.",
                 multi=lambda m, a: _stock_rows(gable_stud_rows(m, a), "gable studs"), rounding=NONE,
                 requires=["wall_runs"]),
        LineItem("cripples", "Cripple studs", "Framing", "ea", none,
                 explanation="Cripples above headers and below sills, cut from studs.",
                 multi=lambda m, a: _stock_rows(cripple_rows(m, a), "studs for cripples"), rounding=NONE,
                 requires=["wall_runs", "openings"]),
        LineItem("headers", "Headers", "Framing", "ea", none,
                 explanation="Doubled header (size from the span table) + one flat board under each.",
                 multi=_header_rows, rounding=NONE, requires=["wall_runs", "openings"]),
    ]


def wall_framing_checks(assumptions) -> List[Check]:
    def orphans(m, r):
        n = int(m.get("orphan_openings", 0))
        return f"{n} door/window(s) are not attached to a wall and were ignored" if n else ""

    def oversize_header(m, r):
        a = assumptions.resolve_all()
        bad = [o for o in m["openings"] if header_size(o["width_in"], a) is None]
        return (f"{len(bad)} opening(s) are wider than the header span table covers "
                f"(widest {max(o['width_in'] for o in bad):g}\"); set a size or override") if bad else ""

    def long_header(m, r):
        a = assumptions.resolve_all()
        bad = [o for o in m["openings"] if o["width_in"] + 2 * a["jack_thickness_in"] > a["header_stock_ft"] * 12]
        return f"{len(bad)} header(s) are longer than the header stock" if bad else ""

    def no_walls(m, r):
        return "no walls in the plan" if not m["wall_runs"] else ""

    return [Check("walls present", no_walls, "error"), Check("orphan openings", orphans),
            Check("header span", oversize_header), Check("header stock", long_header)]
