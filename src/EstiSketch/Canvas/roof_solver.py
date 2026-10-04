"""
Roof Topology & Clean-up Solver for EstiSketch.

Provides algorithms to snap sketched roof lines (ridges, hips, valleys, eaves),
calculate asymmetric pitch offsets, intersect lines at clean junctions,
and extract closed 3D roof plane polygons for takeoff estimation.
"""

import math
from typing import List, Tuple, Dict, Optional, Set
from ..roof_components import Roof, RoofLine, RoofEdge


def pt_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def slope_multiplier(pitch_rise: float, pitch_run: float = 12.0) -> float:
    """Calculate 3D slope factor (secant multiplier) from pitch rise/run."""
    return math.sqrt(1.0 + (pitch_rise / pitch_run) ** 2)


def snap_point(pt: Tuple[float, float], targets: List[Tuple[float, float]], tolerance: float = 12.0) -> Tuple[float, float]:
    """Snap point pt to nearest target point if within tolerance distance (in canvas units/inches)."""
    best_pt = pt
    min_dist = float('inf')
    for target in targets:
        d = pt_distance(pt, target)
        if d <= tolerance and d < min_dist:
            min_dist = d
            best_pt = target
    return best_pt


def line_intersection(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float]
) -> Optional[Tuple[float, float]]:
    """Calculate 2D infinite line intersection between line (p1-p2) and line (p3-p4)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None  # Parallel lines

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)
    return (ix, iy)


def solve_asymmetric_ridge_offset(
    span_width: float, pitch1: float, pitch2: float
) -> float:
    """
    Calculate the distance from Eave 1 to the ridge line for unequal pitches across a span.
    Given pitch1 and pitch2 (rises in 12):
        H = run1 * (pitch1 / 12) = run2 * (pitch2 / 12)
        run1 + run2 = span_width
        => run1 * pitch1 = (span_width - run1) * pitch2
        => run1 = span_width * pitch2 / (pitch1 + pitch2)
    """
    if pitch1 + pitch2 <= 0:
        return span_width / 2.0
    return span_width * pitch2 / (pitch1 + pitch2)


def cluster_and_snap_endpoints(
    lines: List[RoofLine], snap_targets: List[Tuple[float, float]], tolerance: float = 18.0
) -> List[RoofLine]:
    """
    Cluster endpoints of lines so that endpoints that are close to each other or to snap targets
    are snapped to exact identical vertex coordinates.
    """
    if not lines:
        return []

    # Collect all endpoints
    all_pts = list(snap_targets)
    for line in lines:
        all_pts.append(line.start)
        all_pts.append(line.end)

    # Build cluster points
    clusters: List[Tuple[float, float]] = []
    for pt in all_pts:
        matched = False
        for i, c in enumerate(clusters):
            if pt_distance(pt, c) <= tolerance:
                # Merge into cluster centroid
                matched = True
                break
        if not matched:
            clusters.append(pt)

    # Re-map line endpoints to closest cluster centroid
    solved_lines = []
    for line in lines:
        if line.line_type == "ridge":
            # Ridge endpoints should only snap to other roof line endpoints (e.g. hips/valleys), not wall corners
            roof_clusters = [c for c in clusters if not any(pt_distance(c, st) < 0.5 for st in snap_targets)]
            new_start = snap_point(line.start, roof_clusters, tolerance) if roof_clusters else line.start
            new_end = snap_point(line.end, roof_clusters, tolerance) if roof_clusters else line.end
        elif line.line_type in ("hip", "valley"):
            # Start at ridge/skeleton junction snaps to roof line endpoints;
            # End at overhang corner snaps to roof line clusters (eave/rake overhang corners), never wall corners!
            roof_clusters = [c for c in clusters if not any(pt_distance(c, st) < 0.5 for st in snap_targets)]
            new_start = snap_point(line.start, roof_clusters, tolerance) if roof_clusters else line.start
            new_end = snap_point(line.end, roof_clusters, tolerance) if roof_clusters else line.end
        else:
            new_start = snap_point(line.start, clusters, tolerance)
            new_end = snap_point(line.end, clusters, tolerance)

        # Ignore zero-length lines
        if pt_distance(new_start, new_end) > 0.5:
            solved_lines.append(RoofLine(
                identifier=line.identifier,
                start=new_start,
                end=new_end,
                line_type=line.line_type,
                pitch_rise=line.pitch_rise,
                overhang=line.overhang,
                is_auto_generated=line.is_auto_generated
            ))

    return solved_lines


def _order_points_polygon(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Sort polygon vertices radially around centroid in counter-clockwise order."""
    unique_pts: List[Tuple[float, float]] = []
    for p in pts:
        if not any(pt_distance(p, u) < 0.5 for u in unique_pts):
            unique_pts.append(p)
    if len(unique_pts) < 3:
        return unique_pts
    cx = sum(p[0] for p in unique_pts) / len(unique_pts)
    cy = sum(p[1] for p in unique_pts) / len(unique_pts)
    return sorted(unique_pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))


def _polygon_area_2d(pts: List[Tuple[float, float]]) -> float:
    """Calculate 2D plan polygon area using Shoelace formula (in sq inches)."""
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def extract_3d_roof_planes(
    lines: List[RoofLine], default_pitch: float = 6.0
) -> List[Dict]:
    """
    Extract roof planes from closed loops formed by roof lines.
    Calculates 2D plan polygon area and projects into 3D sloped surface area.
    Supports individual facets (e.g. slopes of gable, facets of hip) with per-plane pitch.
    """
    planes = []
    if len(lines) < 3:
        return planes

    eave_lines = [l for l in lines if l.line_type == "eave"]
    ridge_lines = [l for l in lines if l.line_type == "ridge"]

    # If we have eave lines and ridge lines, extract slopes corresponding to each eave
    if eave_lines and ridge_lines:
        for idx, eave in enumerate(eave_lines, 1):
            eave_mid = ((eave.start[0] + eave.end[0]) / 2.0, (eave.start[1] + eave.end[1]) / 2.0)
            # Find closest ridge to this eave
            best_ridge = min(ridge_lines, key=lambda r: distance_point_to_segment(eave_mid, r.start, r.end)[0])

            # Form facet polygon from eave endpoints and ridge endpoints
            facet_pts = _order_points_polygon([eave.start, eave.end, best_ridge.start, best_ridge.end])
            area_2d_sqin = _polygon_area_2d(facet_pts)
            if area_2d_sqin > 10.0:
                pitch = eave.pitch_rise if eave.pitch_rise is not None else default_pitch
                area_2d_sqft = area_2d_sqin / 144.0
                mult = slope_multiplier(pitch, 12.0)
                planes.append({
                    "name": f"Roof Slope #{idx} (Pitch {pitch:.1f}/12)",
                    "pitch": pitch,
                    "polygon_2d": facet_pts,
                    "area_2d_sqft": area_2d_sqft,
                    "area_3d_sqft": area_2d_sqft * mult
                })

    # If distinct facets were extracted, return them
    if planes:
        return planes

    # Fallback: estimate overall footprint perimeter polygon
    endpoints = []
    for l in lines:
        endpoints.append(l.start)
        endpoints.append(l.end)

    sorted_verts = _order_points_polygon(endpoints)
    if len(sorted_verts) >= 3:
        area_2d_sqin = _polygon_area_2d(sorted_verts)
        area_2d_sqft = area_2d_sqin / 144.0
        mult = slope_multiplier(default_pitch, 12.0)
        planes.append({
            "name": f"Main Roof Slope (Pitch {default_pitch:.1f}/12)",
            "pitch": default_pitch,
            "polygon_2d": sorted_verts,
            "area_2d_sqft": area_2d_sqft,
            "area_3d_sqft": area_2d_sqft * mult
        })

    return planes


def straighten_line_angle(start: Tuple[float, float], end: Tuple[float, float], tolerance_deg: float = 15.0) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    If a line segment is within tolerance_deg of horizontal (0/180°), vertical (90/270°),
    or 45° diagonal (45/135/225/315°), adjust end point so the line is perfectly straight.
    """
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        return start, end

    angle_rad = math.atan2(dy, dx)
    angle_deg = (math.degrees(angle_rad)) % 360.0

    targets = [0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 360.0]
    best_target = None
    min_diff = float('inf')

    for t in targets:
        diff = abs(angle_deg - t)
        if diff < min_diff:
            min_diff = diff
            best_target = t % 360.0

    if min_diff <= tolerance_deg and best_target is not None:
        target_rad = math.radians(best_target)
        new_end_x = start[0] + length * math.cos(target_rad)
        new_end_y = start[1] + length * math.sin(target_rad)
        return start, (new_end_x, new_end_y)

    return start, end


def distance_point_to_segment(pt: Tuple[float, float], seg_start: Tuple[float, float], seg_end: Tuple[float, float]) -> Tuple[float, Tuple[float, float]]:
    """Calculate distance from point pt to line segment (seg_start, seg_end)."""
    px, py = pt
    x1, y1 = seg_start
    x2, y2 = seg_end

    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-9:
        return math.hypot(px - x1, py - y1), (x1, y1)

    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy

    dist = math.hypot(px - proj_x, py - proj_y)
    return dist, (proj_x, proj_y)


def snap_point_to_line_segments(
    pt: Tuple[float, float], segments: List[Tuple[Tuple[float, float], Tuple[float, float]]], tolerance: float = 24.0
) -> Tuple[float, float]:
    """Snap point to nearest line segment if within tolerance distance."""
    best_pt = pt
    min_dist = float('inf')

    for seg_start, seg_end in segments:
        d, proj_pt = distance_point_to_segment(pt, seg_start, seg_end)
        if d <= tolerance and d < min_dist:
            min_dist = d
            best_pt = proj_pt

    return best_pt


def intersect_and_clean_lines(
    lines: List[RoofLine], snap_targets: List[Tuple[float, float]], tolerance: float = 24.0, wall_segments: Optional[List[Tuple[Tuple[float, float], Tuple[float, float]]]] = None
) -> List[RoofLine]:
    """
    1. Angle-straighten lines to 0°, 90°, or 45°.
    2. Snap endpoints to wall segments and vertex snap targets.
    3. Solve infinite 2D line intersections and trim endpoints to meet cleanly.
    4. Re-cluster and return solved RoofLine objects.
    """
    if not lines:
        return []

    # First pass: Straighten angles & snap to wall segments
    straightened_lines = []
    for l in lines:
        if getattr(l, 'is_auto_generated', False) or l.line_type in ("hip", "valley"):
            st_start, st_end = l.start, l.end
        else:
            st_start, st_end = straighten_line_angle(l.start, l.end, tolerance_deg=15.0)

        if wall_segments and l.line_type not in ("ridge", "hip", "valley"):
            st_start = snap_point_to_line_segments(st_start, wall_segments, tolerance=tolerance)
            st_end = snap_point_to_line_segments(st_end, wall_segments, tolerance=tolerance)

        straightened_lines.append(RoofLine(
            identifier=l.identifier,
            start=st_start,
            end=st_end,
            line_type=l.line_type,
            pitch_rise=l.pitch_rise,
            overhang=l.overhang,
            is_auto_generated=l.is_auto_generated
        ))

    # Cluster endpoints
    clustered = cluster_and_snap_endpoints(straightened_lines, snap_targets, tolerance)

    # Line intersection solving
    mutable_lines = []
    for l in clustered:
        mutable_lines.append({
            "id": l.identifier,
            "start": list(l.start),
            "end": list(l.end),
            "type": l.line_type,
            "pitch": l.pitch_rise,
            "overhang": l.overhang,
            "auto": l.is_auto_generated
        })

    n = len(mutable_lines)
    for i in range(n):
        for j in range(i + 1, n):
            l1 = mutable_lines[i]
            l2 = mutable_lines[j]

            # Hip and valley lines pass through wall corners to reach the overhang.
            # Do NOT trim hips or valleys against wall edge lines (eave/rake/tie_in).
            t1, t2 = l1["type"], l2["type"]
            if (t1 in ("hip", "valley") and t2 in ("eave", "rake", "tie_in")) or \
               (t2 in ("hip", "valley") and t1 in ("eave", "rake", "tie_in")):
                continue

            p1 = (l1["start"][0], l1["start"][1])
            p2 = (l1["end"][0], l1["end"][1])
            p3 = (l2["start"][0], l2["start"][1])
            p4 = (l2["end"][0], l2["end"][1])

            ix_iy = line_intersection(p1, p2, p3, p4)
            if ix_iy is not None:
                ix, iy = ix_iy
                d1_start = pt_distance((l1["start"][0], l1["start"][1]), (ix, iy))
                d1_end = pt_distance((l1["end"][0], l1["end"][1]), (ix, iy))
                d2_start = pt_distance((l2["start"][0], l2["start"][1]), (ix, iy))
                d2_end = pt_distance((l2["end"][0], l2["end"][1]), (ix, iy))

                max_proj = 48.0  # Max allowable extension in inches
                if min(d1_start, d1_end) <= max_proj and min(d2_start, d2_end) <= max_proj:
                    if d1_start < d1_end:
                        l1["start"] = [ix, iy]
                    elif not (l1.get("auto") or t1 in ("hip", "valley")):
                        l1["end"] = [ix, iy]

                    if d2_start < d2_end:
                        l2["start"] = [ix, iy]
                    elif not (l2.get("auto") or t2 in ("hip", "valley")):
                        l2["end"] = [ix, iy]

    # Reconstruct RoofLine instances
    intersected_lines = []
    for ml in mutable_lines:
        s = (ml["start"][0], ml["start"][1])
        e = (ml["end"][0], ml["end"][1])
        if pt_distance(s, e) > 0.5:
            intersected_lines.append(RoofLine(
                identifier=ml["id"],
                start=s,
                end=e,
                line_type=ml["type"],
                pitch_rise=ml["pitch"],
                overhang=ml["overhang"],
                is_auto_generated=ml["auto"]
            ))

    # Final clustering pass
    final_lines = cluster_and_snap_endpoints(intersected_lines, snap_targets, tolerance)
    return final_lines


def solve_and_clean_roof(roof: Roof, walls: Optional[list] = None) -> Roof:
    """
    Main entry point for the Roof Topology & Clean-Up Engine.
    """
    snap_targets: List[Tuple[float, float]] = []
    wall_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    # Extract wall corners and segments if walls provided
    if walls:
        for wall in walls:
            if hasattr(wall, 'start') and hasattr(wall, 'end'):
                snap_targets.append(wall.start)
                snap_targets.append(wall.end)
                wall_segments.append((wall.start, wall.end))

    # Gather manual sketched lines
    sketched = list(roof.manual_lines)
    has_custom_lines = any(not getattr(l, 'is_auto_generated', False) for l in sketched)

    # If all existing manual lines are auto-generated (or empty), and walls and roof.edges exist,
    # regenerate auto lines so changes in overhang, pitch overrides, or wall positions are applied.
    if not has_custom_lines and walls and roof.edges:
        sketched = []

    # If no manual lines exist and roof has no marked walls/edges, collect from legacy lists (ridge_lines, hip_lines, etc.)
    if not sketched and not (walls and roof.edges):
        legacy_sources = [
            (roof.ridge_lines, "ridge"),
            (roof.hip_lines, "hip"),
            (roof.valley_lines, "valley"),
            (roof.rake_lines, "rake"),
            (roof.eave_lines, "eave"),
            (roof.tie_in_lines, "tie_in"),
        ]
        line_idx = 1
        for line_list, ltype in legacy_sources:
            if line_list:
                for p1, p2 in line_list:
                    rl = RoofLine(
                        identifier=f"legacy_{ltype}_{line_idx}",
                        start=p1,
                        end=p2,
                        line_type=ltype,
                        pitch_rise=roof.pitch_rise,
                        is_auto_generated=True
                    )
                    sketched.append(rl)
                    line_idx += 1

    # If marked walls/edges exist, ensure perimeter RoofLines and ridge/hip lines exist
    if walls and roof.edges:
        marked_eaves = []
        marked_gables = []
        marked_tie_ins = []
        for edge in roof.edges:
            for wall in walls:
                if getattr(wall, 'identifier', None) == edge.wall_identifier:
                    p_rise = getattr(edge, 'pitch_rise', None) or roof.pitch_rise
                    oh = getattr(edge, 'overhang', None) or roof.overhang
                    if edge.edge_type == 'eave':
                        marked_eaves.append((wall, p_rise, oh))
                    elif edge.edge_type == 'gable':
                        marked_gables.append((wall, p_rise, oh))
                    elif edge.edge_type == 'tie_in':
                        marked_tie_ins.append((wall, p_rise, oh))

        # Sync edge pitch_rise and overhang to existing sketched lines (for custom/edited lines)
        for wall, p_rise, oh in marked_eaves:
            for line in sketched:
                if line.identifier == f"auto_eave_{wall.identifier}" or (line.line_type == "eave" and getattr(line, "is_auto_generated", False)):
                    line.pitch_rise = p_rise
                    line.overhang = oh
        for wall, p_rise, oh in marked_gables:
            for line in sketched:
                if line.identifier == f"auto_rake_{wall.identifier}" or (line.line_type == "rake" and getattr(line, "is_auto_generated", False)):
                    line.pitch_rise = p_rise
                    line.overhang = oh

        # Add perimeter RoofLines for all marked wall edges if not already present
        if not any(l.line_type == "eave" for l in sketched):
            for wall, p_rise, oh in marked_eaves:
                sketched.append(RoofLine(
                    identifier=f"auto_eave_{wall.identifier}",
                    start=wall.start,
                    end=wall.end,
                    line_type="eave",
                    pitch_rise=p_rise,
                    overhang=oh,
                    is_auto_generated=True
                ))
        if not any(l.line_type == "rake" for l in sketched):
            for wall, p_rise, oh in marked_gables:
                sketched.append(RoofLine(
                    identifier=f"auto_rake_{wall.identifier}",
                    start=wall.start,
                    end=wall.end,
                    line_type="rake",
                    pitch_rise=p_rise,
                    overhang=oh,
                    is_auto_generated=True
                ))
        if not any(l.line_type == "tie_in" for l in sketched):
            for wall, p_rise, oh in marked_tie_ins:
                sketched.append(RoofLine(
                    identifier=f"auto_tie_in_{wall.identifier}",
                    start=wall.start,
                    end=wall.end,
                    line_type="tie_in",
                    pitch_rise=p_rise,
                    is_auto_generated=True
                ))

        # Populate ridge, hip, and valley lines from roof geometry or complex roof solver
        if roof.ridge_lines and not any(l.line_type == "ridge" for l in sketched):
            for idx, (r_start, r_end) in enumerate(roof.ridge_lines):
                sketched.append(RoofLine(
                    identifier=f"auto_ridge_{idx}" if idx > 0 else "auto_ridge",
                    start=r_start,
                    end=r_end,
                    line_type="ridge",
                    pitch_rise=roof.pitch_rise,
                    overhang=roof.overhang,
                    is_auto_generated=True
                ))
        if roof.hip_lines and not any(l.line_type == "hip" for l in sketched):
            for idx, (h_start, h_end) in enumerate(roof.hip_lines):
                sketched.append(RoofLine(
                    identifier=f"auto_hip_{idx}",
                    start=h_start,
                    end=h_end,
                    line_type="hip",
                    pitch_rise=roof.pitch_rise,
                    overhang=roof.overhang,
                    is_auto_generated=True
                ))
        if roof.valley_lines and not any(l.line_type == "valley" for l in sketched):
            for idx, (v_start, v_end) in enumerate(roof.valley_lines):
                sketched.append(RoofLine(
                    identifier=f"auto_valley_{idx}",
                    start=v_start,
                    end=v_end,
                    line_type="valley",
                    pitch_rise=roof.pitch_rise,
                    overhang=roof.overhang,
                    is_auto_generated=True
                ))
        if roof.rake_lines and not any(l.line_type == "rake" for l in sketched):
            for idx, (rk_start, rk_end) in enumerate(roof.rake_lines):
                sketched.append(RoofLine(
                    identifier=f"auto_rake_{idx}",
                    start=rk_start,
                    end=rk_end,
                    line_type="rake",
                    pitch_rise=roof.pitch_rise,
                    overhang=roof.overhang,
                    is_auto_generated=True
                ))

        # If still no ridge or hip lines, run complex roof geometry solver
        if not any(l.line_type in ("ridge", "hip") for l in sketched):
            from .complex_roof import calculate_complex_roof_geometry
            markings = {e.wall_identifier: e.edge_type for e in roof.edges}
            marked_walls = [w for w in walls if getattr(w, 'identifier', '') in markings]
            if len(marked_walls) >= 3:
                ratio = 0.5
                if len(marked_eaves) >= 2:
                    p1 = marked_eaves[0][1]
                    p2 = marked_eaves[1][1]
                    if p1 + p2 > 0:
                        ratio = p2 / (p1 + p2)
                r_lines, h_lines, v_lines, rk_lines, ev_lines, outline = \
                    calculate_complex_roof_geometry(marked_walls, markings, roof.overhang, roof.pitch_rise, roof.pitch_run, ratio=ratio)
                for idx, (s, e) in enumerate(r_lines):
                    sketched.append(RoofLine(
                        identifier=f"auto_ridge_{idx}" if idx > 0 else "auto_ridge",
                        start=s, end=e, line_type="ridge",
                        pitch_rise=roof.pitch_rise, overhang=roof.overhang, is_auto_generated=True
                    ))
                for idx, (s, e) in enumerate(h_lines):
                    sketched.append(RoofLine(
                        identifier=f"auto_hip_{idx}",
                        start=s, end=e, line_type="hip",
                        pitch_rise=roof.pitch_rise, overhang=roof.overhang, is_auto_generated=True
                    ))
                for idx, (s, e) in enumerate(v_lines):
                    sketched.append(RoofLine(
                        identifier=f"auto_valley_{idx}",
                        start=s, end=e, line_type="valley",
                        pitch_rise=roof.pitch_rise, overhang=roof.overhang, is_auto_generated=True
                    ))
                for idx, (s, e) in enumerate(rk_lines):
                    sketched.append(RoofLine(
                        identifier=f"auto_rake_{idx}",
                        start=s, end=e, line_type="rake",
                        pitch_rise=roof.pitch_rise, overhang=roof.overhang, is_auto_generated=True
                    ))
                if outline and not roof.outline_points:
                    roof.outline_points = outline

    # Save to manual_lines if manual_lines was empty or only had auto-generated lines
    if not has_custom_lines and sketched:
        roof.manual_lines = [RoofLine(
            identifier=l.identifier,
            start=l.start,
            end=l.end,
            line_type=l.line_type,
            pitch_rise=l.pitch_rise or roof.pitch_rise,
            overhang=l.overhang or roof.overhang,
            is_auto_generated=l.is_auto_generated
        ) for l in sketched]
    elif not roof.manual_lines and sketched:
        roof.manual_lines = [RoofLine(
            identifier=l.identifier,
            start=l.start,
            end=l.end,
            line_type=l.line_type,
            pitch_rise=l.pitch_rise or roof.pitch_rise,
            overhang=l.overhang or roof.overhang,
            is_auto_generated=l.is_auto_generated
        ) for l in sketched]

    # Clean & cluster line endpoints + solve line intersections & straighten angles
    cleaned_lines = intersect_and_clean_lines(sketched, snap_targets, tolerance=24.0, wall_segments=wall_segments)

    # Update coordinates of roof.manual_lines so manual lines are straightened as well!
    for cl in cleaned_lines:
        for ml in roof.manual_lines:
            if ml.identifier == cl.identifier:
                ml.start = cl.start
                ml.end = cl.end
                break

    # Store solved lines on roof object
    roof.solved_lines = cleaned_lines

    # Separate into line type lists for rendering & takeoff
    roof.ridge_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'ridge']
    roof.hip_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'hip']
    roof.valley_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'valley']
    roof.rake_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'rake']
    roof.eave_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'eave']
    roof.tie_in_lines = [(l.start, l.end) for l in cleaned_lines if l.line_type == 'tie_in']

    # Extract 3D roof plane polygons
    roof.roof_planes = extract_3d_roof_planes(cleaned_lines, roof.pitch_rise)

    return roof


