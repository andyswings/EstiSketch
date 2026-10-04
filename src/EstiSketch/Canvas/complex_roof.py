"""
Complex Roof Geometry Solver for EstiSketch.

Implements architectural algorithms for auto-generating roof geometry
on complex home footprints, including:
- L-shaped houses (two intersecting ridges, valley line, hip line, gable/hip ends)
- T-shaped houses (main ridge, wing ridge, two valley lines, gable/hip ends)
- Multisided homes (hexagons, octagons, convex polygons via 2D straight skeleton)
- Rectangular gable and hip roofs
"""

import math
from typing import List, Tuple, Dict, Optional, Any
from ..roof_components import RoofLine


def pt_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def points_close(p1: Tuple[float, float], p2: Tuple[float, float], tol: float = 1.0) -> bool:
    """Check if two points are within tolerance distance."""
    return pt_distance(p1, p2) <= tol


def order_walls_into_loop(walls: list, markings: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Order wall objects into a connected closed loop.
    Returns list of dicts: {'start': (x, y), 'end': (x, y), 'wall': wall, 'edge_type': str}
    """
    if not walls or len(walls) < 3:
        return []

    markings = markings or {}

    # Extract wall data
    wall_data = []
    for w in walls:
        w_id = getattr(w, 'identifier', '')
        edge_type = markings.get(w_id, 'eave')
        wall_data.append({
            'start': (float(w.start[0]), float(w.start[1])),
            'end': (float(w.end[0]), float(w.end[1])),
            'wall': w,
            'edge_type': edge_type
        })

    ordered = [wall_data[0]]
    remaining = list(wall_data[1:])

    while remaining:
        last_end = ordered[-1]['end']
        found = False
        for i, item in enumerate(remaining):
            if points_close(item['start'], last_end, 1.0):
                ordered.append(item)
                remaining.pop(i)
                found = True
                break
            elif points_close(item['end'], last_end, 1.0):
                # Reverse segment direction
                reversed_item = {
                    'start': item['end'],
                    'end': item['start'],
                    'wall': item['wall'],
                    'edge_type': item['edge_type']
                }
                ordered.append(reversed_item)
                remaining.pop(i)
                found = True
                break
        if not found:
            break

    # Verify closure
    if len(ordered) >= 3 and points_close(ordered[-1]['end'], ordered[0]['start'], 2.0):
        return ordered

    return ordered if len(ordered) >= 3 else []


def get_polygon_signed_area(pts: List[Tuple[float, float]]) -> float:
    """Calculate signed area of a 2D polygon (shoelace formula)."""
    n = len(pts)
    if n < 3:
        return 0.0
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    return area2 / 2.0


def classify_polygon_shape(ordered_walls: List[Dict[str, Any]]) -> Tuple[str, List[int], List[int]]:
    """
    Classify building polygon into:
    - 'rectangle' (4 walls, 0 inside corners)
    - 'l_shape' (6 walls, 1 inside corner)
    - 't_shape' (8 walls, 2 inside corners)
    - 'multisided_convex' (>= 5 walls, 0 inside corners)
    - 'general'
    Returns (shape_name, reflex_indices, convex_indices).
    """
    n = len(ordered_walls)
    if n < 3:
        return 'degenerate', [], []

    pts = [item['start'] for item in ordered_walls]
    area = get_polygon_signed_area(pts)
    area2 = area * 2.0

    reflex_indices = []
    convex_indices = []

    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n]
        d1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
        d2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])
        cross = d1[0] * d2[1] - d1[1] * d2[0]

        # In standard or screen coords, reflex occurs when cross * area2 < 0
        if cross * area2 < -1e-5:
            reflex_indices.append(i)
        else:
            convex_indices.append(i)

    if n == 4 and len(reflex_indices) == 0:
        return 'rectangle', reflex_indices, convex_indices
    elif n == 6 and len(reflex_indices) == 1:
        return 'l_shape', reflex_indices, convex_indices
    elif n == 8 and len(reflex_indices) == 2:
        return 't_shape', reflex_indices, convex_indices
    elif len(reflex_indices) == 0:
        return 'multisided_convex', reflex_indices, convex_indices
    else:
        return 'general', reflex_indices, convex_indices


def get_offset_corner(
    p_prev: Tuple[float, float],
    p_curr: Tuple[float, float],
    p_next: Tuple[float, float],
    overhang: float,
    winding_flip: float
) -> Tuple[float, float]:
    """
    Calculate the exact overhang outline corner at p_curr by intersecting
    adjacent outward-offset edges.
    """
    dx1 = p_curr[0] - p_prev[0]
    dy1 = p_curr[1] - p_prev[1]
    l1 = math.hypot(dx1, dy1)
    if l1 < 1e-6:
        return p_curr
    nx1 = (-dy1 / l1) * winding_flip
    ny1 = (dx1 / l1) * winding_flip

    dx2 = p_next[0] - p_curr[0]
    dy2 = p_next[1] - p_curr[1]
    l2 = math.hypot(dx2, dy2)
    if l2 < 1e-6:
        return p_curr
    nx2 = (-dy2 / l2) * winding_flip
    ny2 = (dx2 / l2) * winding_flip

    # Outward-offset lines:
    p1 = (p_curr[0] + nx1 * overhang, p_curr[1] + ny1 * overhang)
    p2 = (p1[0] + dx1, p1[1] + dy1)
    p3 = (p_curr[0] + nx2 * overhang, p_curr[1] + ny2 * overhang)
    p4 = (p3[0] + dx2, p3[1] + dy2)

    denom = (p1[0] - p2[0]) * (p3[1] - p4[1]) - (p1[1] - p2[1]) * (p3[0] - p4[0])
    if abs(denom) < 1e-9:
        # Parallel adjacent segments (e.g. collinear walls)
        return p1

    t = ((p1[0] - p3[0]) * (p3[1] - p4[1]) - (p1[1] - p3[1]) * (p3[0] - p4[0])) / denom
    ix = p1[0] + t * (p2[0] - p1[0])
    iy = p1[1] + t * (p2[1] - p1[1])
    return (ix, iy)


def calculate_polygon_outline(ordered_walls: List[Dict[str, Any]], overhang: float) -> List[Tuple[float, float]]:
    """Calculate the roof outline polygon offset by overhang."""
    n = len(ordered_walls)
    if n < 3:
        return []

    pts = [item['start'] for item in ordered_walls]
    signed_area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        signed_area += (p2[0] - p1[0]) * (p2[1] + p1[1])
    winding_flip = 1.0 if signed_area > 0 else -1.0

    outline = []
    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n]
        corner = get_offset_corner(p_prev, p_curr, p_next, overhang, winding_flip)
        outline.append(corner)

    return outline


def generate_l_shaped_roof(
    ordered_walls: List[Dict[str, Any]],
    overhang: float,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5
) -> Tuple[List, List, List, List, List, List]:
    """
    Generate roof geometry for an L-shaped house:
    - Two separate ridge lines, centered along each wing of the house
    - Valley line from the ridge intersection through the inside corner to the overhang
    - Hip line from the ridge intersection through the outside corner to the overhang
    - Gable or Hip end treatment on both wings
    """
    n = 6
    pts = [item['start'] for item in ordered_walls]

    # Signed area for winding
    signed_area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        signed_area += (p2[0] - p1[0]) * (p2[1] + p1[1])
    winding_flip = 1.0 if signed_area > 0 else -1.0

    # Find the single reflex vertex (inside corner)
    area = get_polygon_signed_area(pts)
    area2 = area * 2.0
    reflex_idx = -1
    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n]
        cross = (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) - (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0])
        if cross * area2 < -1e-5:
            reflex_idx = i
            break

    if reflex_idx == -1:
        reflex_idx = 0

    r = reflex_idx
    v_in = pts[r]
    v_out = pts[(r + 3) % n]

    # Ridge intersection I is exactly midway between inside corner and outside corner
    I = ((v_in[0] + v_out[0]) / 2.0, (v_in[1] + v_out[1]) / 2.0)

    # Valley line: from I through v_in extending to overhang corner
    v_in_prev = pts[(r - 1) % n]
    v_in_next = pts[(r + 1) % n]
    valley_end = get_offset_corner(v_in_prev, v_in, v_in_next, overhang, winding_flip)
    valley_lines = [(I, valley_end)]

    # Hip line: from I through v_out extending to overhang corner
    v_out_prev = pts[((r + 3) - 1) % n]
    v_out_next = pts[((r + 3) + 1) % n]
    hip_end = get_offset_corner(v_out_prev, v_out, v_out_next, overhang, winding_flip)
    hip_lines = [(I, hip_end)]

    ridge_lines = []
    rake_lines = []
    eave_lines = []

    # Helper to process wing ends
    def process_wing_end(p1, p2, edge_type, wall_obj):
        mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        width = pt_distance(p1, p2)
        dx = mid[0] - I[0]
        dy = mid[1] - I[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return
        ux, uy = dx / dist, dy / dist

        # Find extended corners for p1 and p2
        # p1 is corner between previous wall and this end wall
        # p2 is corner between this end wall and next wall
        idx1 = pts.index(p1)
        idx2 = pts.index(p2)
        c1_ext = get_offset_corner(pts[(idx1 - 1) % n], p1, pts[(idx1 + 1) % n], overhang, winding_flip)
        c2_ext = get_offset_corner(pts[(idx2 - 1) % n], p2, pts[(idx2 + 1) % n], overhang, winding_flip)

        if edge_type == 'gable':
            # Ridge extends past gable wall by overhang
            r_end = (mid[0] + ux * overhang, mid[1] + uy * overhang)
            ridge_lines.append((I, r_end))
            rake_lines.append((c1_ext, c2_ext))
        else:
            # Hip end: Ridge terminates width/2 before end wall
            inset = width / 2.0
            r_end = (mid[0] - ux * inset, mid[1] - uy * inset)
            ridge_lines.append((I, r_end))
            hip_lines.append((r_end, c1_ext))
            hip_lines.append((r_end, c2_ext))
            eave_lines.append((c1_ext, c2_ext))

    # Wing A end wall is segment (r - 2)
    end_a_seg = ordered_walls[(r - 2) % n]
    p_a1 = pts[(r - 2) % n]
    p_a2 = pts[(r - 1) % n]
    process_wing_end(p_a1, p_a2, end_a_seg.get('edge_type', 'eave'), end_a_seg.get('wall'))

    # Wing B end wall is segment (r + 1)
    end_b_seg = ordered_walls[(r + 1) % n]
    p_b1 = pts[(r + 1) % n]
    p_b2 = pts[(r + 2) % n]
    process_wing_end(p_b1, p_b2, end_b_seg.get('edge_type', 'eave'), end_b_seg.get('wall'))

    # Add eave lines for all other walls marked eave
    for idx, item in enumerate(ordered_walls):
        if idx not in ((r - 2) % n, (r + 1) % n) and item.get('edge_type') == 'eave':
            p1 = pts[idx]
            p2 = pts[(idx + 1) % n]
            c1_ext = get_offset_corner(pts[(idx - 1) % n], p1, p2, overhang, winding_flip)
            c2_ext = get_offset_corner(p1, p2, pts[(idx + 2) % n], overhang, winding_flip)
            eave_lines.append((c1_ext, c2_ext))

    outline_points = calculate_polygon_outline(ordered_walls, overhang)
    return ridge_lines, hip_lines, valley_lines, rake_lines, eave_lines, outline_points


def generate_t_shaped_roof(
    ordered_walls: List[Dict[str, Any]],
    overhang: float,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5
) -> Tuple[List, List, List, List, List, List]:
    """
    Generate roof geometry for a T-shaped house:
    - Main ridge running along the main body of the house
    - Wing ridge running along the stem wing
    - Two valley lines from the ridge intersection through each inside corner
    - Gable or Hip end treatment on all 3 ends (2 main ends, 1 stem end)
    """
    n = 8
    pts = [item['start'] for item in ordered_walls]

    signed_area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        signed_area += (p2[0] - p1[0]) * (p2[1] + p1[1])
    winding_flip = 1.0 if signed_area > 0 else -1.0

    area = get_polygon_signed_area(pts)
    area2 = area * 2.0

    reflex = []
    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n]
        cross = (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) - (p_curr[1] - p_prev[1]) * (p_next[0] - p_curr[0])
        if cross * area2 < -1e-5:
            reflex.append(i)

    if len(reflex) != 2:
        return generate_convex_multisided_roof(ordered_walls, overhang, pitch_rise, pitch_run)

    r1, r2 = reflex[0], reflex[1]
    if (r2 - r1) % n == 3:
        r_start, r_end = r1, r2
    else:
        r_start, r_end = r2, r1

    v_in1 = pts[r_start]
    v_in2 = pts[r_end]

    # Stem wing corners
    stem_c1 = pts[(r_start + 1) % n]
    stem_c2 = pts[(r_start + 2) % n]
    stem_mid = ((stem_c1[0] + stem_c2[0]) / 2.0, (stem_c1[1] + stem_c2[1]) / 2.0)
    stem_width = pt_distance(stem_c1, stem_c2)

    base_mid = ((v_in1[0] + v_in2[0]) / 2.0, (v_in1[1] + v_in2[1]) / 2.0)
    stem_dx = stem_mid[0] - base_mid[0]
    stem_dy = stem_mid[1] - base_mid[1]
    stem_len = math.hypot(stem_dx, stem_dy) or 1.0
    s_ux, s_uy = stem_dx / stem_len, stem_dy / stem_len

    # Main back wall is segment (r_start + 5)
    bw_p1 = pts[(r_start + 5) % n]
    bw_p2 = pts[(r_start + 6) % n]
    main_width = abs((base_mid[0] - bw_p1[0]) * (-s_ux) + (base_mid[1] - bw_p1[1]) * (-s_uy))
    if main_width < 1.0:
        main_width = stem_width

    # Ridge intersection I is inside the main body midway across its width
    I = (base_mid[0] - s_ux * (main_width / 2.0), base_mid[1] - s_uy * (main_width / 2.0))

    # Two valley lines from I to extended inside corners
    v1_ext = get_offset_corner(pts[(r_start - 1) % n], v_in1, pts[(r_start + 1) % n], overhang, winding_flip)
    v2_ext = get_offset_corner(pts[(r_end - 1) % n], v_in2, pts[(r_end + 1) % n], overhang, winding_flip)
    valley_lines = [(I, v1_ext), (I, v2_ext)]
    hip_lines = []
    ridge_lines = []
    rake_lines = []
    eave_lines = []

    # 1. Stem wing ridge
    stem_seg = ordered_walls[(r_start + 1) % n]
    stem_type = stem_seg.get('edge_type', 'eave')
    c1_ext = get_offset_corner(pts[r_start], stem_c1, stem_c2, overhang, winding_flip)
    c2_ext = get_offset_corner(stem_c1, stem_c2, pts[r_end], overhang, winding_flip)

    if stem_type == 'gable':
        r_stem_end = (stem_mid[0] + s_ux * overhang, stem_mid[1] + s_uy * overhang)
        ridge_lines.append((I, r_stem_end))
        rake_lines.append((c1_ext, c2_ext))
    else:
        inset = stem_width / 2.0
        r_stem_end = (stem_mid[0] - s_ux * inset, stem_mid[1] - s_uy * inset)
        ridge_lines.append((I, r_stem_end))
        hip_lines.append((r_stem_end, c1_ext))
        hip_lines.append((r_stem_end, c2_ext))
        eave_lines.append((c1_ext, c2_ext))

    # 2. Main body ridge ends
    # End 1 is segment (r_start + 4)
    end1_seg = ordered_walls[(r_start + 4) % n]
    p_e1_1 = pts[(r_start + 4) % n]
    p_e1_2 = pts[(r_start + 5) % n]
    e1_mid = ((p_e1_1[0] + p_e1_2[0]) / 2.0, (p_e1_1[1] + p_e1_2[1]) / 2.0)
    e1_w = pt_distance(p_e1_1, p_e1_2)
    e1_dx, e1_dy = e1_mid[0] - I[0], e1_mid[1] - I[1]
    e1_dist = math.hypot(e1_dx, e1_dy) or 1.0
    e1_ux, e1_uy = e1_dx / e1_dist, e1_dy / e1_dist

    e1_c1_ext = get_offset_corner(pts[(r_start + 3) % n], p_e1_1, p_e1_2, overhang, winding_flip)
    e1_c2_ext = get_offset_corner(p_e1_1, p_e1_2, pts[(r_start + 6) % n], overhang, winding_flip)

    if end1_seg.get('edge_type') == 'gable':
        r1_end = (e1_mid[0] + e1_ux * overhang, e1_mid[1] + e1_uy * overhang)
        ridge_lines.append((I, r1_end))
        rake_lines.append((e1_c1_ext, e1_c2_ext))
    else:
        inset = e1_w / 2.0
        r1_end = (e1_mid[0] - e1_ux * inset, e1_mid[1] - e1_uy * inset)
        ridge_lines.append((I, r1_end))
        hip_lines.append((r1_end, e1_c1_ext))
        hip_lines.append((r1_end, e1_c2_ext))
        eave_lines.append((e1_c1_ext, e1_c2_ext))

    # End 2 is segment (r_start + 6)
    end2_seg = ordered_walls[(r_start + 6) % n]
    p_e2_1 = pts[(r_start + 6) % n]
    p_e2_2 = pts[(r_start + 7) % n]
    e2_mid = ((p_e2_1[0] + p_e2_2[0]) / 2.0, (p_e2_1[1] + p_e2_2[1]) / 2.0)
    e2_w = pt_distance(p_e2_1, p_e2_2)
    e2_dx, e2_dy = e2_mid[0] - I[0], e2_mid[1] - I[1]
    e2_dist = math.hypot(e2_dx, e2_dy) or 1.0
    e2_ux, e2_uy = e2_dx / e2_dist, e2_dy / e2_dist

    e2_c1_ext = get_offset_corner(pts[(r_start + 5) % n], p_e2_1, p_e2_2, overhang, winding_flip)
    e2_c2_ext = get_offset_corner(p_e2_1, p_e2_2, pts[(r_start + 8) % n], overhang, winding_flip)

    if end2_seg.get('edge_type') == 'gable':
        r2_end = (e2_mid[0] + e2_ux * overhang, e2_mid[1] + e2_uy * overhang)
        ridge_lines.append((I, r2_end))
        rake_lines.append((e2_c1_ext, e2_c2_ext))
    else:
        inset = e2_w / 2.0
        r2_end = (e2_mid[0] - e2_ux * inset, e2_mid[1] - e2_uy * inset)
        ridge_lines.append((I, r2_end))
        hip_lines.append((r2_end, e2_c1_ext))
        hip_lines.append((r2_end, e2_c2_ext))
        eave_lines.append((e2_c1_ext, e2_c2_ext))

    outline_points = calculate_polygon_outline(ordered_walls, overhang)
    return ridge_lines, hip_lines, valley_lines, rake_lines, eave_lines, outline_points


def generate_convex_multisided_roof(
    ordered_walls: List[Dict[str, Any]],
    overhang: float,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0
) -> Tuple[List, List, List, List, List, List]:
    """
    Generate hip roof for arbitrary convex polygons (e.g. hexagons, octagons, pentagons)
    using 2D straight skeleton wavefront simulation.
    Handles elongated polygons (producing a central ridge with hips)
    and regular polygons (pyramid hip roof).
    """
    n = len(ordered_walls)
    pts = [item['start'] for item in ordered_walls]

    signed_area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        signed_area += (p2[0] - p1[0]) * (p2[1] + p1[1])
    winding_flip = 1.0 if signed_area > 0 else -1.0

    # Ensure CCW orientation for wavefront
    area = get_polygon_signed_area(pts)
    is_ccw = area > 0
    work_pts = list(pts) if is_ccw else list(reversed(pts))
    m = len(work_pts)

    # Map extended corners for work_pts
    ext_corners = []
    for i in range(m):
        p_prev = work_pts[(i - 1) % m]
        p_curr = work_pts[i]
        p_next = work_pts[(i + 1) % m]
        c_ext = get_offset_corner(p_prev, p_curr, p_next, overhang, winding_flip)
        ext_corners.append(c_ext)

    # Check if polygon is regular / equi-radial from centroid (e.g. regular octagon, hexagon, square)
    cx = sum(p[0] for p in work_pts) / m
    cy = sum(p[1] for p in work_pts) / m
    center = (cx, cy)
    dists = [math.hypot(p[0] - cx, p[1] - cy) for p in work_pts]
    min_d, max_d = min(dists), max(dists)
    if max_d > 0 and (max_d - min_d) / max_d < 0.02:
        # Regular polygon hip roof: all vertices connect directly to centroid
        hip_lines = [(center, c_ext) for c_ext in ext_corners]
        outline_points = calculate_polygon_outline(ordered_walls, overhang)
        return [], hip_lines, [], [], [], outline_points

    class Edge:
        def __init__(self, idx, p1, p2):
            self.idx = idx
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.hypot(dx, dy) or 1.0
            self.normal = (-dy / length, dx / length)

    class VertexNode:
        def __init__(self, pt, orig_idx, e_prev, e_next, t=0.0):
            self.pt = pt
            self.orig_idx = orig_idx  # index into work_pts if t == 0
            self.t_start = t
            self.e_prev = e_prev
            self.e_next = e_next
            n1 = e_prev.normal
            n2 = e_next.normal
            denom = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
            if abs(denom) < 1e-9:
                self.b = (0.0, 0.0)
            else:
                self.b = ((n1[0] + n2[0]) / denom, (n1[1] + n2[1]) / denom)

        def pos_at(self, t):
            dt = t - self.t_start
            return (self.pt[0] + dt * self.b[0], self.pt[1] + dt * self.b[1])

    edges = [Edge(i, work_pts[i], work_pts[(i + 1) % m]) for i in range(m)]
    nodes = [VertexNode(work_pts[i], i, edges[(i - 1) % m], edges[i], t=0.0) for i in range(m)]

    skeleton_raw = []

    def ray_intersection(n1, n2):
        b_diff_x = n1.b[0] - n2.b[0]
        b_diff_y = n1.b[1] - n2.b[1]
        rhs_x = n2.pt[0] - n1.pt[0] - n2.t_start * n2.b[0] + n1.t_start * n1.b[0]
        rhs_y = n2.pt[1] - n1.pt[1] - n2.t_start * n2.b[1] + n1.t_start * n1.b[1]
        det = b_diff_x * b_diff_x + b_diff_y * b_diff_y
        if det < 1e-9:
            return None
        t = (rhs_x * b_diff_x + rhs_y * b_diff_y) / det
        min_t = max(n1.t_start, n2.t_start) + 1e-4
        if t >= min_t:
            p = n1.pos_at(t)
            p_check = n2.pos_at(t)
            if math.hypot(p[0] - p_check[0], p[1] - p_check[1]) < 1.0:
                return (t, p)
        return None

    cur_nodes = list(nodes)
    while len(cur_nodes) > 2:
        best_t = float('inf')
        best_idx = -1
        best_p = None
        count = len(cur_nodes)
        for i in range(count):
            j = (i + 1) % count
            res = ray_intersection(cur_nodes[i], cur_nodes[j])
            if res and res[0] < best_t:
                best_t = res[0]
                best_idx = i
                best_p = res[1]

        if best_idx == -1 or best_t == float('inf') or best_p is None:
            break

        i = best_idx
        j = (best_idx + 1) % count
        node_i = cur_nodes[i]
        node_j = cur_nodes[j]

        if pt_distance(node_i.pt, best_p) > 0.5:
            skeleton_raw.append({
                'start': node_i.pt, 'end': best_p,
                't_start': node_i.t_start, 't_end': best_t,
                'orig_idx': node_i.orig_idx if node_i.t_start == 0 else -1
            })
        if pt_distance(node_j.pt, best_p) > 0.5:
            skeleton_raw.append({
                'start': node_j.pt, 'end': best_p,
                't_start': node_j.t_start, 't_end': best_t,
                'orig_idx': node_j.orig_idx if node_j.t_start == 0 else -1
            })

        new_node = VertexNode(best_p, -1, node_i.e_prev, node_j.e_next, t=best_t)
        if i < j:
            cur_nodes = cur_nodes[:i] + [new_node] + cur_nodes[j + 1:]
        else:
            cur_nodes = [new_node] + cur_nodes[j + 1:i]

    if len(cur_nodes) == 2:
        p1 = cur_nodes[0].pt
        p2 = cur_nodes[1].pt
        if pt_distance(p1, p2) > 0.5:
            skeleton_raw.append({
                'start': p1, 'end': p2,
                't_start': cur_nodes[0].t_start, 't_end': cur_nodes[1].t_start,
                'orig_idx': -1
            })
            for nd in cur_nodes:
                if nd.orig_idx >= 0:
                    d1 = pt_distance(nd.pt, p1)
                    d2 = pt_distance(nd.pt, p2)
                    target = p1 if d1 <= d2 else p2
                    skeleton_raw.append({
                        'start': nd.pt, 'end': target,
                        't_start': nd.t_start, 't_end': cur_nodes[0].t_start,
                        'orig_idx': nd.orig_idx
                    })
        else:
            p_center = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
            for nd in cur_nodes:
                if nd.orig_idx >= 0:
                    skeleton_raw.append({
                        'start': nd.pt, 'end': p_center,
                        't_start': nd.t_start, 't_end': cur_nodes[0].t_start,
                        'orig_idx': nd.orig_idx
                    })

    # Convert skeleton_raw into hip_lines and ridge_lines
    hip_lines = []
    ridge_lines = []
    valley_lines = []

    seen_orig = set()
    for item in skeleton_raw:
        s = item['start']
        e = item['end']
        orig = item['orig_idx']
        if orig >= 0:
            if orig not in seen_orig:
                seen_orig.add(orig)
                # Hip line: connects ridge/skeleton node to the extended overhang corner
                c_ext = ext_corners[orig]
                hip_lines.append((e, c_ext))
        else:
            # Internal line = Ridge line
            ridge_lines.append((s, e))

    for i in range(m):
        if i not in seen_orig:
            c_ext = ext_corners[i]
            if cur_nodes:
                best_target = min(cur_nodes, key=lambda n: pt_distance(n.pt, work_pts[i])).pt
            else:
                best_target = center
            hip_lines.append((best_target, c_ext))

    outline_points = calculate_polygon_outline(ordered_walls, overhang)
    return ridge_lines, hip_lines, valley_lines, [], [], outline_points


def calculate_complex_roof_geometry(
    walls: list,
    markings: Dict[str, str],
    overhang: float = 12.0,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5
) -> Tuple[List, List, List, List, List, List]:
    """
    Master geometry solver for all roof types.
    Returns:
    (ridge_lines, hip_lines, valley_lines, rake_lines, eave_lines, outline_points)
    """
    ordered_walls = order_walls_into_loop(walls, markings)
    if not ordered_walls:
        return [], [], [], [], [], []

    shape, reflex_idx, _ = classify_polygon_shape(ordered_walls)

    # 1. L-shaped house
    if shape == 'l_shape':
        return generate_l_shaped_roof(ordered_walls, overhang, pitch_rise, pitch_run, ratio)

    # 2. T-shaped house
    if shape == 't_shape':
        return generate_t_shaped_roof(ordered_walls, overhang, pitch_rise, pitch_run, ratio)

    # 3. 4-wall rectangle
    if shape == 'rectangle':
        has_gables = any(item.get('edge_type') == 'gable' for item in ordered_walls)
        if has_gables:
            # Standard rectangular gable
            eave_walls = [item['wall'] for item in ordered_walls if item.get('edge_type') == 'eave']
            gable_walls = [item['wall'] for item in ordered_walls if item.get('edge_type') == 'gable']
            if len(eave_walls) == 2 and len(gable_walls) == 2:
                from .roof_solver import distance_point_to_segment
                e1 = eave_walls[0]
                ridge_pts = []
                for gw in gable_walls[:2]:
                    d1 = distance_point_to_segment(gw.start, e1.start, e1.end)[0]
                    d2 = distance_point_to_segment(gw.end, e1.start, e1.end)[0]
                    p_from = gw.start if d1 <= d2 else gw.end
                    p_to = gw.end if d1 <= d2 else gw.start
                    r_pt = (p_from[0] + ratio * (p_to[0] - p_from[0]), p_from[1] + ratio * (p_to[1] - p_from[1]))
                    ridge_pts.append(r_pt)
                rdx = ridge_pts[1][0] - ridge_pts[0][0]
                rdy = ridge_pts[1][1] - ridge_pts[0][1]
                rlen = math.hypot(rdx, rdy) or 1.0
                ux, uy = rdx / rlen, rdy / rlen
                r_start = (ridge_pts[0][0] - ux * overhang, ridge_pts[0][1] - uy * overhang)
                r_end = (ridge_pts[1][0] + ux * overhang, ridge_pts[1][1] + uy * overhang)
                outline = calculate_polygon_outline(ordered_walls, overhang)
                return [(r_start, r_end)], [], [], [], [], outline
        else:
            # Rectangular hip
            return generate_convex_multisided_roof(ordered_walls, overhang, pitch_rise, pitch_run)

    # 4. Multisided convex or general polygons
    return generate_convex_multisided_roof(ordered_walls, overhang, pitch_rise, pitch_run)
