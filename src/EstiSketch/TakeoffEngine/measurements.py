"""Plan -> named measurements. Pure functions over plain wall/room objects (no GTK)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .lumber import interp as interp_profile
from .geometry import (collapse_collinear, edge_lengths, is_rectangle, offset_polygon,
                       point_line_distance, signed_area, snap_to)

DEFAULT_WALL_WIDTH_IN = 5.5
CLOSE_TOL_IN = 0.5


def _edge_half_width(a, b, walls, default_width: float) -> float:
    """Half the thickest wall lying along edge a-b (falls back to the default width)."""
    best = 0.0
    for w in walls:
        if point_line_distance(w.start, a, b) < 1.0 and point_line_distance(w.end, a, b) < 1.0:
            best = max(best, float(getattr(w, "width", default_width)))
    return (best or default_width) / 2.0


def outer_outline(points, walls, default_width: float = DEFAULT_WALL_WIDTH_IN):
    """Polygon at the outside face of the walls, given a polygon on the wall centerlines."""
    pts = collapse_collinear(points)
    dists = [_edge_half_width(pts[i], pts[(i + 1) % len(pts)], walls, default_width) for i in range(len(pts))]
    return offset_polygon(pts, dists)


def _slab_record(room, walls, snap_in: float, default_width: float) -> Dict[str, Any]:
    outline = outer_outline(room.points, walls, default_width)
    rect = is_rectangle(outline)
    lens = edge_lengths(outline)
    if rect:
        length_in = snap_to(max(lens[0], lens[1]), snap_in)
        width_in = snap_to(min(lens[0], lens[1]), snap_in)
        area_sqft = length_in * width_in / 144.0
        perim_in = 2 * (length_in + width_in)
    else:
        length_in = width_in = 0.0
        area_sqft = abs(signed_area(outline)) / 144.0
        perim_in = sum(snap_to(l, snap_in) for l in lens)
    # holes (stair openings etc.) reduce slab area
    hole_sqft = 0.0
    for h in getattr(room, "holes", []) or []:
        hp = getattr(h, "points", None)
        if hp:
            hole_sqft += abs(signed_area(hp)) / 144.0
    return {
        "id": getattr(room, "identifier", ""),
        "rectangular": rect,
        "length_ft": length_in / 12.0,
        "width_ft": width_in / 12.0,
        "area_sqft": area_sqft - hole_sqft,
        "perimeter_ft": perim_in / 12.0,
        "thickness_in": float(getattr(room, "slab_thickness", 4.0)),
        "reinforcement": getattr(room, "slab_reinforcement", ""),
        "edge_type": getattr(room, "slab_edge_type", ""),
        "outline_edges_ft": [snap_to(l, snap_in) / 12.0 for l in lens],
    }


def _direction(w):
    dx, dy = w.end[0] - w.start[0], w.end[1] - w.start[1]
    ln = math.hypot(dx, dy)
    return (dx / ln, dy / ln) if ln else None


def _same_dir(d1, d2) -> bool:
    return abs(d1[0] * d2[1] - d1[1] * d2[0]) < 0.01 and d1[0] * d2[0] + d1[1] * d2[1] > 0


def _group_walls(ws, closed: bool):
    """Group consecutive collinear same-direction walls into runs (wrapping around a closed loop)."""
    groups, prev = [], None
    for w in ws:
        d = _direction(w)
        if d is None:
            continue
        if groups and prev is not None and _same_dir(d, prev):
            groups[-1].append(w)
        else:
            groups.append([w])
        prev = d
    if closed and len(groups) > 1 and _same_dir(_direction(groups[0][0]), _direction(groups[-1][0])):
        groups = [groups[-1] + groups[0]] + groups[1:-1]
    return groups


def _wall_len(w) -> float:
    return math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1])


def _heights(w):
    h0 = float(getattr(w, "height", 96.0) or 96.0)
    h1 = getattr(w, "height_at_end", None)
    return h0, float(h1) if h1 else h0


def wall_runs(plan, snap_in: float = 0.25, default_width: float = DEFAULT_WALL_WIDTH_IN) -> List[Dict[str, Any]]:
    """Wall runs (collinear walls merged). Closed loops are measured at the outside face; open sets at centerline.

    Each run has a height `profile` [(distance_along_run_in, height_in)] so gable/sloped tops are measured
    from the wall heights themselves (no dependency on the roof)."""
    runs: List[Dict[str, Any]] = []
    for si, ws in enumerate(plan.wall_sets):
        ws = list(ws)
        if not ws:
            continue
        closed = len(ws) >= 3 and math.hypot(ws[0].start[0] - ws[-1].end[0],
                                             ws[0].start[1] - ws[-1].end[1]) < CLOSE_TOL_IN
        groups = _group_walls(ws, closed)
        if closed and len(groups) >= 3:
            pts = [g[0].start for g in groups]
            widths = [max(float(getattr(w, "width", default_width)) for w in g) for g in groups]
            edges = edge_lengths(offset_polygon(pts, [x / 2.0 for x in widths]))
            lengths = [snap_to(e, snap_in) for e in edges]
            inner = offset_polygon(pts, [-x / 2.0 for x in widths])
            inner_lengths = [snap_to(e, snap_in) for e in edge_lengths(inner)]
            loop_area = abs(signed_area(inner)) / 144.0
        else:
            closed = False
            lengths = [snap_to(sum(_wall_len(w) for w in g), snap_in) for g in groups]
            inner_lengths, loop_area = list(lengths), 0.0
        for gi, g in enumerate(groups):
            L = lengths[gi]
            total = sum(_wall_len(w) for w in g)
            ext = max((L - total) / 2.0, 0.0) if closed else 0.0
            h_first = _heights(g[0])[0]
            profile = [(0.0, h_first)]
            infos, s_pos = [], ext
            for w in g:
                wl = _wall_len(w)
                h0, h1 = _heights(w)
                profile += [(s_pos, h0), (s_pos + wl, h1)]
                infos.append({"wall": w, "start_in": s_pos, "length_in": wl})
                s_pos += wl
            profile.append((L, _heights(g[-1])[1]))
            base_h = min(h for _, h in profile)
            t_in = max(float(getattr(w, "width", default_width)) for w in g)
            if closed:
                # interior face: clip the profile to [t, L - t] (the wall thickness at each corner)
                clipped = [(x, h) for x, h in profile if t_in < x < L - t_in]
                clipped = [(t_in, interp_profile(profile, t_in))] + clipped + [(L - t_in, interp_profile(profile, L - t_in))]
                int_gable_in2 = sum((max(h0 - base_h, 0.0) + max(h1 - base_h, 0.0)) / 2.0 * (x1 - x0)
                                    for (x0, h0), (x1, h1) in zip(clipped, clipped[1:]))
            else:
                int_gable_in2 = 0.0
            gable_in2 = sum((max(h0 - base_h, 0.0) + max(h1 - base_h, 0.0)) / 2.0 * (x1 - x0)
                            for (x0, h0), (x1, h1) in zip(profile, profile[1:]))
            runs.append({
                "id": f"{si}:{gi}", "gable_area_sqft": gable_in2 / 144.0,
                "interior_length_in": inner_lengths[gi] if closed else L,
                "interior_gable_area_sqft": int_gable_in2 / 144.0, "loop_interior_area_sqft": loop_area,
                "gross_area_sqft": (L * base_h + gable_in2) / 144.0, "set_index": si, "closed": closed, "exterior": closed,
                "length_in": L, "length_ft": L / 12.0,
                "thickness_in": max(float(getattr(w, "width", default_width)) for w in g),
                "profile": profile, "base_height_in": min(h for _, h in profile),
                "max_height_in": max(h for _, h in profile), "walls": infos,
            })
    return runs


def wall_plate_runs_ft(wall_sets, snap_in: float, default_width: float = DEFAULT_WALL_WIDTH_IN) -> List[float]:
    """Bottom-plate run lengths in feet."""
    plan = type("P", (), {"wall_sets": wall_sets})()
    return [r["length_ft"] for r in wall_runs(plan, snap_in, default_width)]


def openings(plan, runs) -> Dict[str, Any]:
    """Doors/windows attached to a wall, located along their wall run. Unattached ones are counted, not used."""
    out, orphans = [], 0
    for kind, entries in (("door", getattr(plan, "doors", [])), ("window", getattr(plan, "windows", []))):
        for wall, obj, ratio in entries:
            found = None
            for r in runs:
                for info in r["walls"]:
                    if info["wall"] is wall:
                        found = (r, info)
            if wall is None or found is None:
                orphans += 1
                continue
            r, info = found
            out.append({
                "id": getattr(obj, "identifier", ""), "kind": kind,
                "subtype": getattr(obj, "door_type" if kind == "door" else "window_type", "") or "",
                "width_in": float(obj.width), "height_in": float(obj.height),
                "center_in": info["start_in"] + float(ratio) * info["length_in"],
                "run_id": r["id"], "exterior": r["exterior"],
            })
    return {"openings": out, "orphan_openings": float(orphans)}


def wall_framing_measurements(plan, snap_in: float = 0.25,
                              default_wall_width: float = DEFAULT_WALL_WIDTH_IN) -> Dict[str, Any]:
    runs = wall_runs(plan, snap_in, default_wall_width)
    opening_info = openings(plan, runs)
    opening_list = opening_info["openings"]
    m: Dict[str, Any] = {"wall_runs": runs, "wall_lf_outside": sum(r["length_ft"] for r in runs)}
    m.update(opening_info)
    ext = [r for r in runs if r["exterior"]]
    ext_open = [o for o in opening_list if o["exterior"]]
    m.update({
        "exterior_wall_area_sqft": sum(r["gross_area_sqft"] for r in ext),
        "exterior_gable_area_sqft": sum(r["gable_area_sqft"] for r in ext),
        # each run owns one corner's worth of height (two shared ends)
        "exterior_corner_trim_ft": sum(r["base_height_in"] for r in ext) / 12.0,
        "exterior_opening_area_sqft": sum(o["width_in"] * o["height_in"] for o in ext_open) / 144.0,
        "exterior_opening_trim_ft": sum(
            (2 * (o["width_in"] + o["height_in"]) if o["kind"] == "window" else 2 * o["height_in"] + o["width_in"])
            for o in ext_open) / 12.0,
    })
    return m


def interior_measurements(plan, runs, doors_in: float) -> Dict[str, Any]:
    """Interior-face quantities: wall area (incl. gable triangles), perimeter, floor area, partitions."""
    loops = {}
    for r in runs:
        if r["closed"]:
            loops[r["set_index"]] = r["loop_interior_area_sqft"]
    closed = [r for r in runs if r["closed"]]
    parts = [r for r in runs if not r["closed"]]
    steep = 0.0
    for r in runs:
        for (x0, h0), (x1, h1) in zip(r["profile"], r["profile"][1:]):
            if x1 > x0:
                steep = max(steep, abs(h1 - h0) / (x1 - x0))
    return {
        "interior_floor_area_sqft": sum(loops.values()),
        "interior_perimeter_ft": sum(r["interior_length_in"] for r in closed) / 12.0,
        "interior_wall_flat_sqft": sum(r["interior_length_in"] * r["base_height_in"] for r in closed) / 144.0,
        "interior_gable_area_sqft": sum(r["interior_gable_area_sqft"] for r in closed),
        # interior partitions are finished on both faces
        "partition_wall_sqft": sum(2 * r["interior_length_in"] * r["base_height_in"] for r in parts) / 144.0,
        "partition_length_ft": sum(2 * r["interior_length_in"] for r in parts) / 12.0,
        "wall_slope": steep,
    }


def room_floor_areas(plan, walls, snap_in: float = 0.25) -> Dict[str, float]:
    """Interior floor area (sq ft) by floor type, from room polygons on wall centerlines."""
    out: Dict[str, float] = {}
    for room in getattr(plan, "rooms", []):
        pts = collapse_collinear(room.points)
        if len(pts) < 3:
            continue
        dists = [-_edge_half_width(pts[i], pts[(i + 1) % len(pts)], walls, DEFAULT_WALL_WIDTH_IN)
                 for i in range(len(pts))]
        area = abs(signed_area(offset_polygon(pts, dists))) / 144.0
        for h in getattr(room, "holes", []) or []:
            hp = getattr(h, "points", None)
            if hp:
                area -= abs(signed_area(hp)) / 144.0
        ft = getattr(room, "floor_type", "default") or "default"
        out[ft] = out.get(ft, 0.0) + area
    return out


def plan_measurements(plan, snap_in: float = 0.25, default_wall_width: float = DEFAULT_WALL_WIDTH_IN):
    from .roof import roof_measurements
    m = foundation_measurements(plan, snap_in, default_wall_width)
    m.update(wall_framing_measurements(plan, snap_in, default_wall_width))
    m.update(roof_measurements(plan, m["wall_runs"]))
    m.update(interior_measurements(plan, m["wall_runs"], 0.0))
    walls = [w for ws in plan.wall_sets for w in ws]
    m["floor_areas_sqft"] = room_floor_areas(plan, walls, snap_in)
    return m


def foundation_measurements(plan, snap_in: float = 0.25,
                            default_wall_width: float = DEFAULT_WALL_WIDTH_IN) -> Dict[str, Any]:
    """Measurements needed by foundation line items. `plan` has wall_sets and rooms."""
    all_walls = [w for ws in plan.wall_sets for w in ws]
    slabs = [_slab_record(r, all_walls, snap_in, default_wall_width)
             for r in plan.rooms if getattr(r, "is_slab", False)]
    return {
        "slabs": slabs,
        "slab_count": float(len(slabs)),
        "slab_area_sqft": sum(s["area_sqft"] for s in slabs),
        "slab_perimeter_ft": sum(s["perimeter_ft"] for s in slabs),
        "plate_runs_ft": wall_plate_runs_ft(plan.wall_sets, snap_in, default_wall_width),
        "wall_lf_outside": sum(wall_plate_runs_ft(plan.wall_sets, snap_in, default_wall_width)),
    }
