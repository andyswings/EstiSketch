"""Phase 5: wall-based gable roof geometry, roof framing and roofing line items.

The roof is derived from the wall heights (gable runs are sloped, eave runs are flat) plus the roof's
pitch/overhang/material settings, so it does not depend on the roof solver (which is unreliable with split
walls). Only simple gable roofs on a four-sided closed wall loop are supported; anything else raises a check
error instead of producing guessed numbers."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .checks import Check
from .line_item import LineItem, NONE

ROOF_DEFAULTS: Dict[str, float] = {
    "roof_framing_method": 0.0,        # 0 = trusses, 1 = stick framed, 2 = auto (stick if span allows)
    "truss_spacing_in": 24.0,
    "stick_max_span_ft": 20.0,         # widest clear span stick framing may be used for
    "rafter_spacing_in": 24.0,
    "outlooker_spacing_in": 24.0,
    "outlooker_extra_in": 24.0,        # outlooker length = overhang + this (lands on first clear-span truss)
    "lumber_stock_ft": 16.0,
    "shingle_waste_pct": 5.0,
    "nails_per_square": 400.0,
    "roof_sheathing_waste_pct": 3.0,
    "roof_sheet_sqft": 32.0,
    "roof_sheathing_nails_per_sqft": 3.0,
    "sloped_wall_min_extra_in": 0.5,
    "pitch_mismatch_tol": 0.25,        # rise per 12 between wall heights and the roof setting
    # span tables for stick framing: widest horizontal span (ft) each size covers
    "joist_max_span_ft_2x6": 9.0, "joist_max_span_ft_2x8": 12.0,
    "joist_max_span_ft_2x10": 15.0, "joist_max_span_ft_2x12": 18.0,
    "rafter_max_run_ft_2x6": 9.0, "rafter_max_run_ft_2x8": 12.0,
    "rafter_max_run_ft_2x10": 15.0, "rafter_max_run_ft_2x12": 18.0,
}
SIZES = ["2x6", "2x8", "2x10", "2x12"]
STOCK_FT = [8, 10, 12, 14, 16, 18, 20, 24]


def _run_wall_ids(run: Dict[str, Any]) -> set:
    return {
        getattr(w_info["wall"], "identifier", "")
        for w_info in run.get("walls", [])
        if getattr(w_info["wall"], "identifier", "")
    }


def _detect_gable_indices(roof: Any, ext: List[Dict[str, Any]], min_extra_in: float) -> Tuple[List[int], bool]:
    """Identify the two opposite gable wall-run indices.

    Returns (gable_indices, from_sloped_walls).
    Priority:
      1. Two opposite walls with sloped wall heights (handles split/raised gable walls).
      2. Roof edges marked as 'gable' or 'eave' matching wall identifiers.
      3. Roof manual/solved lines marked as 'eave' or 'gable' matching wall identifiers.
    """
    sloped = [i for i, r in enumerate(ext) if r["max_height_in"] - r["base_height_in"] > min_extra_in]
    if len(sloped) == 2 and (sloped[1] - sloped[0]) == 2:
        return sloped, True

    run_ids = [_run_wall_ids(r) for r in ext]

    # Check roof.edges (set by "Mark wall as gable / eave" in the Roof toolset)
    edges = getattr(roof, "edges", None) or []
    gable_ids = {getattr(e, "wall_identifier", "") for e in edges if getattr(e, "edge_type", "") == "gable"}
    eave_ids = {getattr(e, "wall_identifier", "") for e in edges if getattr(e, "edge_type", "") == "eave"}

    if gable_ids:
        g_idx = [i for i, ids in enumerate(run_ids) if ids & gable_ids]
        if len(g_idx) == 2 and (g_idx[1] - g_idx[0]) == 2:
            return g_idx, False
    if eave_ids:
        e_idx = [i for i, ids in enumerate(run_ids) if ids & eave_ids]
        if len(e_idx) == 2 and (e_idx[1] - e_idx[0]) == 2:
            return [i for i in range(4) if i not in e_idx], False

    # Fallback: check roof.solved_lines / roof.manual_lines wall_identifiers
    lines = list(getattr(roof, "solved_lines", None) or []) + list(getattr(roof, "manual_lines", None) or [])
    line_eave_ids = {getattr(ln, "wall_identifier", "") for ln in lines if getattr(ln, "line_type", "") == "eave"}
    if line_eave_ids:
        e_idx = [i for i, ids in enumerate(run_ids) if ids & line_eave_ids]
        if len(e_idx) == 2 and (e_idx[1] - e_idx[0]) == 2:
            return [i for i in range(4) if i not in e_idx], False

    return [], False


def roof_measurements(plan, runs, min_extra_in: float = 0.5) -> Dict[str, Any]:
    """Raw gable-roof inputs from the walls and the roof object."""
    roofs = list(getattr(plan, "roofs", []) or [])
    if not roofs:
        return {"roof": {"supported": False, "reason": "no roof in the plan"}}
    roof = roofs[0]
    ext = [r for r in runs if r["exterior"]]
    out: Dict[str, Any] = {"roof": {"supported": False, "reason": ""}}
    info = out["roof"]
    info.update({"roof_count": len(roofs), "roof_type": getattr(roof, "roof_type", "gable"),
                 "material": getattr(roof, "material", ""),
                 "pitch_rise": float(getattr(roof, "pitch_rise", 4.0)),
                 "pitch_run": float(getattr(roof, "pitch_run", 12.0)),
                 "overhang_in": float(getattr(roof, "overhang", 12.0))})
    if info["roof_type"] != "gable":
        info["reason"] = f"{info['roof_type']} roofs are not supported yet"
        return out
    if len(ext) != 4:
        info["reason"] = f"expected a four-sided exterior wall loop, found {len(ext)} wall runs"
        return out
    gable_idx, from_sloped = _detect_gable_indices(roof, ext, min_extra_in)
    if len(gable_idx) != 2 or (gable_idx[1] - gable_idx[0]) != 2:
        info["reason"] = "a gable roof needs two opposite gable walls (sloped wall heights or marked gable/eave roof edges)"
        return out
    gables = [ext[i] for i in gable_idx]
    eaves = [r for i, r in enumerate(ext) if i not in gable_idx]
    wall_pitch_rise: Optional[float] = None
    if from_sloped:
        steep = 0.0
        for g in gables:
            for (x0, h0), (x1, h1) in zip(g["profile"], g["profile"][1:]):
                if x1 > x0:
                    steep = max(steep, abs(h1 - h0) / (x1 - x0))
        wall_pitch_rise = steep * info["pitch_run"]
    info.update({
        "supported": True,
        "gable_len_in": sum(g["length_in"] for g in gables) / 2.0,
        "eave_len_in": sum(e["length_in"] for e in eaves) / 2.0,
        "eave_wall_ft": sum(e["length_in"] for e in eaves) / 12.0,
        "wall_pitch_rise": wall_pitch_rise,
    })
    return out


def roof_geometry(m, a) -> Dict[str, float]:
    r = m["roof"]
    if not r.get("supported"):
        raise ValueError(r.get("reason") or "roof not supported")
    oh = r["overhang_in"]
    run_ft = (r["gable_len_in"] / 2.0 + oh) / 12.0
    slope = math.sqrt(1.0 + (r["pitch_rise"] / r["pitch_run"]) ** 2)
    slope_len = run_ft * slope
    length_ft = (r["eave_len_in"] + 2 * oh) / 12.0
    return {
        "run_ft": run_ft, "slope_factor": slope, "slope_len_ft": slope_len, "length_ft": length_ft,
        "area_sqft": 2 * slope_len * length_ft,
        "perimeter_ft": 2 * length_ft + 4 * slope_len,          # sloped perimeter (eaves + 4 rakes)
        "horizontal_perimeter_ft": 2 * (length_ft + 2 * run_ft),
        "ridge_ft": length_ft, "span_ft": r["gable_len_in"] / 12.0, "eave_wall_ft": r["eave_wall_ft"],
        "overhang_in": oh,
    }


def framing_method(m, a) -> str:
    """'trusses' or 'stick' after applying the user's choice and the span limit."""
    r = m["roof"]
    if not r.get("supported"):
        raise ValueError(r.get("reason") or "roof not supported")
    span = r["gable_len_in"] / 12.0
    ok = span <= a["stick_max_span_ft"] + 1e-9
    choice = int(a["roof_framing_method"])
    if choice == 1:
        return "stick" if ok else "trusses"
    if choice == 2:
        return "stick" if ok else "trusses"
    return "trusses"


def _size_for(value, a, prefix) -> Optional[str]:
    for s in SIZES:
        if value <= a[f"{prefix}_{s}"] + 1e-9:
            return s
    return None


def _stock_for(length_ft: float) -> int:
    return next((s for s in STOCK_FT if s >= length_ft - 1e-9), STOCK_FT[-1])


def _ceil(x: float) -> int:
    return math.ceil(x - 1e-9)


def _pre(m):
    return m["roof"].get("supported", False)


def _squares(m, a) -> float:
    return roof_geometry(m, a)["area_sqft"] * (1 + a["shingle_waste_pct"] / 100.0) / 100.0


def _sheets(m, a) -> float:
    return roof_geometry(m, a)["area_sqft"] * (1 + a["roof_sheathing_waste_pct"] / 100.0) / a["roof_sheet_sqft"]


def _trusses(m, a):
    if framing_method(m, a) != "trusses":
        return 0
    g = roof_geometry(m, a)
    r = m["roof"]
    n = _ceil(r["eave_len_in"] / a["truss_spacing_in"]) + 1
    return n


def _truss_rows(m, a):
    n = _trusses(m, a)
    if not n:
        return []
    g, r = roof_geometry(m, a), m["roof"]
    ft = g["span_ft"]
    feet, inch = int(ft), round((ft - int(ft)) * 12)
    return [("trusses", f"Roof trusses, {feet}'-{inch}\" span, {r['pitch_rise']:g}:{r['pitch_run']:g}, "
                        f"{a['truss_spacing_in']:g}\" OC", n)]


def _stick_rows(m, a):
    if framing_method(m, a) != "stick":
        return []
    g, r = roof_geometry(m, a), m["roof"]
    n_pairs = _ceil(r["eave_len_in"] / a["rafter_spacing_in"]) + 1
    half_span = g["span_ft"] / 2.0
    raf = _size_for(half_span, a, "rafter_max_run_ft")
    joi = _size_for(g["span_ft"], a, "joist_max_span_ft")
    rows = []
    if raf:
        stock = _stock_for(g["slope_len_ft"])
        rows.append(("rafters", f"{raf}x{stock}' rafters", 2 * n_pairs))
        rows.append(("ridge", f"{raf}x{_stock_for(g['ridge_ft'])}' ridge board "
                              f"({_ceil(g['ridge_ft'] / 16.0)} pc at 16')", 1))
    if joi:
        rows.append(("joists", f"{joi}x{_stock_for(g['span_ft'])}' ceiling joists", n_pairs))
    return rows


def _outlookers(m, a):
    g, r = roof_geometry(m, a), m["roof"]
    per_slope = _ceil(g["slope_len_ft"] * 12.0 / a["outlooker_spacing_in"])
    total = 4 * per_slope
    length_in = g["overhang_in"] + a["outlooker_extra_in"]
    per_board = max(int(a["lumber_stock_ft"] * 12.0 // length_in), 1)
    return _ceil(total / per_board)


def roof_items() -> List[LineItem]:
    R = ["roof"]
    g = roof_geometry
    return [
        LineItem("roof_trusses", "Roof trusses", "Roof Framing", "ea", lambda m, a: 0.0,
                 explanation="Trusses at spacing along the eave walls (+1 for the end); method and span limit are "
                             "settings.", multi=_truss_rows, rounding=NONE, hide_if_zero=True, requires=R),
        LineItem("roof_stick", "Stick-framed roof", "Roof Framing", "ea", lambda m, a: 0.0,
                 explanation="Rafters, ridge board and ceiling joists sized from span tables; only used when the "
                             "span allows.", multi=_stick_rows, rounding=NONE, hide_if_zero=True, requires=R),
        LineItem("outlookers", "2x6x16' Outlookers", "Roof Framing", "ea", _outlookers,
                 explanation="Per gable slope: slope length / spacing; each outlooker = overhang + extra; cut from "
                             "16' boards.", rounding=NONE, requires=R),
        LineItem("fascia_backers", "2x6x16' Fascia backers", "Roof Framing", "ea",
                 lambda m, a: g(m, a)["perimeter_ft"] / a["lumber_stock_ft"],
                 explanation="Roof perimeter (eaves + rakes along the slope) / board length.", requires=R),
        LineItem("bird_blocking", "2x6x16' Bird blocking", "Roof Framing", "ea",
                 lambda m, a: g(m, a)["eave_wall_ft"] / a["lumber_stock_ft"],
                 explanation="Total length of the eave walls / board length.", requires=R),
        LineItem("soffit_nailers", "2x4x16' Soffit nailers", "Roof Framing", "ea",
                 lambda m, a: g(m, a)["horizontal_perimeter_ft"] / a["lumber_stock_ft"],
                 explanation="Level perimeter of the roof (plan view) / board length.", requires=R),
        LineItem("roof_sheathing", "7/16\" OSB roof sheathing (4x8)", "Roofing", "sheet", _sheets,
                 explanation="Roof area + waste / 32 sq ft. (Not on the old spreadsheet.)", requires=R),
        LineItem("roof_sheathing_nails", "Roof sheathing nails", "Roofing", "ea",
                 lambda m, a: _ceil(_sheets(m, a)) * a["roof_sheet_sqft"] * a["roof_sheathing_nails_per_sqft"],
                 explanation="Whole sheets x 32 sq ft x nails per sq ft.", requires=R),
        LineItem("shingles", "Squares of shingles", "Roofing", "sq", _squares,
                 explanation="Total roof plane area + waste, in squares of 100 sq ft, rounded up.", requires=R),
        LineItem("underlayment", "Squares of underlayment", "Roofing", "sq", _squares,
                 explanation="Same as the shingles.", requires=R),
        LineItem("drip_edge", "Linear ft drip edge", "Roofing", "ft", lambda m, a: g(m, a)["perimeter_ft"],
                 explanation="Roof perimeter along the slope.", requires=R),
        LineItem("ridge_cap", "Linear ft ridge cap", "Roofing", "ft", lambda m, a: g(m, a)["ridge_ft"],
                 explanation="Ridge length including gable overhangs.", requires=R),
        LineItem("soffit", "Linear ft soffit", "Roofing", "ft", lambda m, a: g(m, a)["perimeter_ft"],
                 explanation="Roof perimeter (a little extra for waste, as on your sheet).", requires=R),
        LineItem("fascia", "Linear ft fascia", "Roofing", "ft", lambda m, a: g(m, a)["perimeter_ft"],
                 explanation="Roof perimeter.", requires=R),
        LineItem("roofing_nails", "Roofing nails", "Roofing", "ea",
                 lambda m, a: _ceil(_squares(m, a)) * a["nails_per_square"],
                 explanation="Whole squares of shingles x nails per square.", requires=R),
    ]


def roof_checks(assumptions) -> List[Check]:
    def supported(m, r):
        roof = m.get("roof", {})
        return "" if roof.get("supported") else f"roof not calculated: {roof.get('reason', 'unknown')}"

    def pitch(m, r):
        roof = m.get("roof", {})
        if not roof.get("supported") or roof.get("wall_pitch_rise") is None:
            return ""
        tol = assumptions.get("pitch_mismatch_tol")
        if abs(roof["wall_pitch_rise"] - roof["pitch_rise"]) > tol:
            return (f"wall heights imply {roof['wall_pitch_rise']:.2f}:{roof['pitch_run']:g} but the roof says "
                    f"{roof['pitch_rise']:g}:{roof['pitch_run']:g}; roof setting is used, check gable heights")
        return ""

    def span(m, r):
        roof = m.get("roof", {})
        if not roof.get("supported"):
            return ""
        a = assumptions.resolve_all()
        span_ft = roof["gable_len_in"] / 12.0
        if span_ft > a["stick_max_span_ft"] and int(a["roof_framing_method"]) != 0:
            return f"span {span_ft:.1f}' is too long for stick framing; trusses are used"
        return ""

    def material(m, r):
        roof = m.get("roof", {})
        if roof.get("supported") and roof.get("material") not in ("asphalt_shingle", ""):
            return f"roofing lines assume asphalt shingles; roof material is {roof['material']}"
        return ""

    def many(m, r):
        n = m.get("roof", {}).get("roof_count", 1)
        return f"{n} roofs in the plan; only the first is calculated" if n > 1 else ""

    return [Check("roof shape", supported, "error"), Check("roof pitch", pitch), Check("roof span", span),
            Check("roof material", material), Check("multiple roofs", many)]
