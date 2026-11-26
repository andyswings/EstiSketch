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


def get_edge_offset(item: Dict[str, Any], overhang: float) -> float:
    """Calculate outward offset for an edge: overhang + half wall thickness."""
    wall = item.get('wall')
    width = float(getattr(wall, 'width', 0.0) or 0.0)
    return overhang + 0.5 * width


def get_corner_at_vertex(
    pts: List[Tuple[float, float]],
    ordered_walls: List[Dict[str, Any]],
    i: int,
    overhang: float,
    winding_flip: float
) -> Tuple[float, float]:
    """Calculate the overhang offset corner at vertex i using adjacent wall thicknesses."""
    n = len(pts)
    p_prev = pts[(i - 1) % n]
    p_curr = pts[i]
    p_next = pts[(i + 1) % n]
    off_prev = get_edge_offset(ordered_walls[(i - 1) % n], overhang)
    off_curr = get_edge_offset(ordered_walls[i], overhang)
    return get_offset_corner(
        p_prev, p_curr, p_next,
        overhang, winding_flip,
        overhang_prev=off_prev,
        overhang_next=off_curr
    )


def get_offset_corner(
    p_prev: Tuple[float, float],
    p_curr: Tuple[float, float],
    p_next: Tuple[float, float],
    overhang: float,
    winding_flip: float,
    overhang_prev: Optional[float] = None,
    overhang_next: Optional[float] = None
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

    off1 = overhang if overhang_prev is None else overhang_prev
    off2 = overhang if overhang_next is None else overhang_next

    # Outward-offset lines:
    p1 = (p_curr[0] + nx1 * off1, p_curr[1] + ny1 * off1)
    p2 = (p1[0] + dx1, p1[1] + dy1)
    p3 = (p_curr[0] + nx2 * off2, p_curr[1] + ny2 * off2)
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
    """Calculate the roof outline polygon offset by overhang from exterior wall faces."""
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
        corner = get_corner_at_vertex(pts, ordered_walls, i, overhang, winding_flip)
        outline.append(corner)

    return outline


def _intersect_ray_lines(
    p1: Tuple[float, float],
    d1: Tuple[float, float],
    p2: Tuple[float, float],
    d2: Tuple[float, float],
) -> Optional[Tuple[float, float]]:
    """Intersect infinite lines ``p1 + t*d1`` and ``p2 + u*d2``."""
    denom = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(denom) < 1e-9:
        return None
    rx = p2[0] - p1[0]
    ry = p2[1] - p1[1]
    t = (rx * d2[1] - ry * d2[0]) / denom
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def _ratio_from_pitches(
    p1: Optional[float],
    p2: Optional[float],
    default_pitch: float,
    z1: Optional[float] = None,
    z2: Optional[float] = None,
    span: float = 1.0,
    pitch_run: float = 12.0,
) -> float:
    """Return distance ratio from side 1 across ``span`` for asymmetric pitches/heights."""
    rise1 = float(p1) if p1 is not None else float(default_pitch)
    rise2 = float(p2) if p2 is not None else float(default_pitch)
    s1 = rise1 / max(1e-6, float(pitch_run))
    s2 = rise2 / max(1e-6, float(pitch_run))
    if s1 + s2 <= 0.0:
        return 0.5
    dz = (float(z2) - float(z1)) if (z1 is not None and z2 is not None) else 0.0
    raw = (s2 + dz / max(1.0, float(span))) / (s1 + s2)
    return max(0.05, min(0.95, raw))


def generate_l_shaped_roof(
    ordered_walls: List[Dict[str, Any]],
    overhang: float,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5,
    has_edge_overrides: bool = False,
) -> Tuple[List, List, List, List, List, List]:
    """
    Generate roof geometry for an L-shaped house:
    - Two separate ridge lines, centered (or pitch-offset) along each wing
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
        cross = (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) - (p_curr[1] - p_prev[1]) * (p_next[0] - p_prev[0])
        if cross * area2 < -1e-5:
            reflex_idx = i
            break

    if reflex_idx == -1:
        reflex_idx = 0

    r = reflex_idx
    v_in = pts[r]
    v_out = pts[(r + 3) % n]

    if has_edge_overrides:
        ratio_a = _ratio_from_pitches(
            ordered_walls[(r - 3) % n].get('pitch_rise'),
            ordered_walls[(r - 1) % n].get('pitch_rise'),
            pitch_rise,
            pitch_run=pitch_run,
        )
        ratio_b = _ratio_from_pitches(
            ordered_walls[r].get('pitch_rise'),
            ordered_walls[(r + 2) % n].get('pitch_rise'),
            pitch_rise,
            pitch_run=pitch_run,
        )
    else:
        ratio_a = ratio
        ratio_b = ratio

    p_a1 = pts[(r - 2) % n]
    p_a2 = pts[(r - 1) % n]
    p_b1 = pts[(r + 1) % n]
    p_b2 = pts[(r + 2) % n]

    wing_a_pt = (p_a1[0] + ratio_a * (p_a2[0] - p_a1[0]), p_a1[1] + ratio_a * (p_a2[1] - p_a1[1]))
    wing_b_pt = (p_b1[0] + ratio_b * (p_b2[0] - p_b1[0]), p_b1[1] + ratio_b * (p_b2[1] - p_b1[1]))
    dir_a = (v_in[0] - p_a2[0], v_in[1] - p_a2[1])
    dir_b = (p_b1[0] - v_in[0], p_b1[1] - v_in[1])
    intersect = _intersect_ray_lines(wing_a_pt, dir_a, wing_b_pt, dir_b)
    if intersect is not None and abs(ratio_a - 0.5) + abs(ratio_b - 0.5) > 1e-4:
        I = intersect
    else:
        I = ((v_in[0] + v_out[0]) / 2.0, (v_in[1] + v_out[1]) / 2.0)

    # Valley line: from I through v_in extending to overhang corner
    valley_end = get_corner_at_vertex(pts, ordered_walls, r, overhang, winding_flip)
    valley_lines = [(I, valley_end)]

    # Hip line: from I through v_out extending to overhang corner
    hip_end = get_corner_at_vertex(pts, ordered_walls, (r + 3) % n, overhang, winding_flip)
    hip_lines = [(I, hip_end)]

    ridge_lines = []
    rake_lines = []
    eave_lines = []

    # Helper to process wing ends
    def process_wing_end(p1, p2, edge_type, wall_obj, end_ratio: float):
        mid = (p1[0] + end_ratio * (p2[0] - p1[0]), p1[1] + end_ratio * (p2[1] - p1[1]))
        width = pt_distance(p1, p2)
        dx = mid[0] - I[0]
        dy = mid[1] - I[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return
        ux, uy = dx / dist, dy / dist

        idx1 = pts.index(p1)
        idx2 = pts.index(p2)
        c1_ext = get_corner_at_vertex(pts, ordered_walls, idx1, overhang, winding_flip)
        c2_ext = get_corner_at_vertex(pts, ordered_walls, idx2, overhang, winding_flip)

        wall_w = float(getattr(wall_obj, 'width', 0.0) or 0.0)
        if edge_type == 'gable':
            # Ridge extends past gable wall by overhang + half wall thickness
            r_end = (mid[0] + ux * (overhang + 0.5 * wall_w), mid[1] + uy * (overhang + 0.5 * wall_w))
            ridge_lines.append((I, r_end))
            rake_lines.append((c1_ext, c2_ext))
        else:
            # Hip end: Ridge terminates inset before end wall
            inset = width * min(end_ratio, 1.0 - end_ratio)
            r_end = (mid[0] - ux * inset, mid[1] - uy * inset)
            ridge_lines.append((I, r_end))
            hip_lines.append((r_end, c1_ext))
            hip_lines.append((r_end, c2_ext))
            eave_lines.append((c1_ext, c2_ext))

    # Wing A end wall is segment (r - 2)
    end_a_seg = ordered_walls[(r - 2) % n]
    process_wing_end(p_a1, p_a2, end_a_seg.get('edge_type', 'eave'), end_a_seg.get('wall'), ratio_a)

    # Wing B end wall is segment (r + 1)
    end_b_seg = ordered_walls[(r + 1) % n]
    process_wing_end(p_b1, p_b2, end_b_seg.get('edge_type', 'eave'), end_b_seg.get('wall'), ratio_b)

    # Add eave lines for all other walls marked eave
    for idx, item in enumerate(ordered_walls):
        if idx not in ((r - 2) % n, (r + 1) % n) and item.get('edge_type') == 'eave':
            c1_ext = get_corner_at_vertex(pts, ordered_walls, idx, overhang, winding_flip)
            c2_ext = get_corner_at_vertex(pts, ordered_walls, (idx + 1) % n, overhang, winding_flip)
            eave_lines.append((c1_ext, c2_ext))

    outline_points = calculate_polygon_outline(ordered_walls, overhang)
    return ridge_lines, hip_lines, valley_lines, rake_lines, eave_lines, outline_points


def generate_t_shaped_roof(
    ordered_walls: List[Dict[str, Any]],
    overhang: float,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5,
    has_edge_overrides: bool = False,
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
        cross = (p_curr[0] - p_prev[0]) * (p_next[1] - p_curr[1]) - (p_curr[1] - p_prev[1]) * (p_next[0] - p_prev[0])
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
    stem_ratio = 0.5
    if has_edge_overrides:
        stem_ratio = _ratio_from_pitches(
            ordered_walls[r_start].get('pitch_rise'),
            ordered_walls[(r_start + 2) % n].get('pitch_rise'),
            pitch_rise,
            pitch_run=pitch_run,
        )
    stem_mid = (
        stem_c1[0] + stem_ratio * (stem_c2[0] - stem_c1[0]),
        stem_c1[1] + stem_ratio * (stem_c2[1] - stem_c1[1]),
    )
    stem_width = pt_distance(stem_c1, stem_c2)

    base_mid = (
        v_in1[0] + stem_ratio * (v_in2[0] - v_in1[0]),
        v_in1[1] + stem_ratio * (v_in2[1] - v_in1[1]),
    )
    stem_dx = stem_mid[0] - base_mid[0]
    stem_dy = stem_mid[1] - base_mid[1]
    stem_len = math.hypot(stem_dx, stem_dy) or 1.0
    s_ux, s_uy = stem_dx / stem_len, stem_dy / stem_len

    # Main back wall is segment (r_start + 5)
    bw_p1 = pts[(r_start + 5) % n]
    main_width = abs((base_mid[0] - bw_p1[0]) * (-s_ux) + (base_mid[1] - bw_p1[1]) * (-s_uy))
    if main_width < 1.0:
        main_width = stem_width

    if has_edge_overrides:
        p_back = ordered_walls[(r_start + 5) % n].get('pitch_rise')
        p_f1 = ordered_walls[(r_start + 3) % n].get('pitch_rise')
        p_f2 = ordered_walls[(r_start + 7) % n].get('pitch_rise')
        f_vals = [float(p) for p in (p_f1, p_f2) if p is not None]
        p_front = sum(f_vals) / len(f_vals) if f_vals else None
        main_ratio = _ratio_from_pitches(
            p_front, p_back, pitch_rise, span=main_width, pitch_run=pitch_run
        )
    else:
        main_ratio = ratio

    # Ridge intersection I is inside the main body at main_ratio across its width from front
    I = (base_mid[0] - s_ux * (main_width * main_ratio), base_mid[1] - s_uy * (main_width * main_ratio))

    # Two valley lines from I to extended inside corners
    v1_ext = get_corner_at_vertex(pts, ordered_walls, r_start, overhang, winding_flip)
    v2_ext = get_corner_at_vertex(pts, ordered_walls, r_end, overhang, winding_flip)
    valley_lines = [(I, v1_ext), (I, v2_ext)]
    hip_lines = []
    ridge_lines = []
    rake_lines = []
    eave_lines = []

    # 1. Stem wing ridge
    stem_seg = ordered_walls[(r_start + 1) % n]
    stem_type = stem_seg.get('edge_type', 'eave')
    stem_wall_w = float(getattr(stem_seg.get('wall'), 'width', 0.0) or 0.0)
    c1_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 1) % n, overhang, winding_flip)
    c2_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 2) % n, overhang, winding_flip)

    if stem_type == 'gable':
        r_stem_end = (stem_mid[0] + s_ux * (overhang + 0.5 * stem_wall_w), stem_mid[1] + s_uy * (overhang + 0.5 * stem_wall_w))
        ridge_lines.append((I, r_stem_end))
        rake_lines.append((c1_ext, c2_ext))
    else:
        inset = stem_width * min(stem_ratio, 1.0 - stem_ratio)
        r_stem_end = (stem_mid[0] - s_ux * inset, stem_mid[1] - s_uy * inset)
        ridge_lines.append((I, r_stem_end))
        hip_lines.append((r_stem_end, c1_ext))
        hip_lines.append((r_stem_end, c2_ext))
        eave_lines.append((c1_ext, c2_ext))

    # 2. Main body ridge ends
    # End 1 is segment (r_start + 4): front corner p_e1_1 -> back corner p_e1_2
    end1_seg = ordered_walls[(r_start + 4) % n]
    p_e1_1 = pts[(r_start + 4) % n]
    p_e1_2 = pts[(r_start + 5) % n]
    e1_mid = (p_e1_1[0] + main_ratio * (p_e1_2[0] - p_e1_1[0]), p_e1_1[1] + main_ratio * (p_e1_2[1] - p_e1_1[1]))
    e1_w = pt_distance(p_e1_1, p_e1_2)
    e1_dx, e1_dy = e1_mid[0] - I[0], e1_mid[1] - I[1]
    e1_dist = math.hypot(e1_dx, e1_dy) or 1.0
    e1_ux, e1_uy = e1_dx / e1_dist, e1_dy / e1_dist

    e1_wall_w = float(getattr(end1_seg.get('wall'), 'width', 0.0) or 0.0)
    e1_c1_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 4) % n, overhang, winding_flip)
    e1_c2_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 5) % n, overhang, winding_flip)

    if end1_seg.get('edge_type') == 'gable':
        r1_end = (e1_mid[0] + e1_ux * (overhang + 0.5 * e1_wall_w), e1_mid[1] + e1_uy * (overhang + 0.5 * e1_wall_w))
        ridge_lines.append((I, r1_end))
        rake_lines.append((e1_c1_ext, e1_c2_ext))
    else:
        inset = e1_w * min(main_ratio, 1.0 - main_ratio)
        r1_end = (e1_mid[0] - e1_ux * inset, e1_mid[1] - e1_uy * inset)
        ridge_lines.append((I, r1_end))
        hip_lines.append((r1_end, e1_c1_ext))
        hip_lines.append((r1_end, e1_c2_ext))
        eave_lines.append((e1_c1_ext, e1_c2_ext))

    # End 2 is segment (r_start + 6): back corner p_e2_1 -> front corner p_e2_2
    end2_seg = ordered_walls[(r_start + 6) % n]
    p_e2_1 = pts[(r_start + 6) % n]
    p_e2_2 = pts[(r_start + 7) % n]
    e2_mid = (p_e2_2[0] + main_ratio * (p_e2_1[0] - p_e2_2[0]), p_e2_2[1] + main_ratio * (p_e2_1[1] - p_e2_2[1]))
    e2_w = pt_distance(p_e2_1, p_e2_2)
    e2_dx, e2_dy = e2_mid[0] - I[0], e2_mid[1] - I[1]
    e2_dist = math.hypot(e2_dx, e2_dy) or 1.0
    e2_ux, e2_uy = e2_dx / e2_dist, e2_dy / e2_dist

    end2_wall_w = float(getattr(end2_seg.get('wall'), 'width', 0.0) or 0.0)
    e2_c1_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 6) % n, overhang, winding_flip)
    e2_c2_ext = get_corner_at_vertex(pts, ordered_walls, (r_start + 7) % n, overhang, winding_flip)

    if end2_seg.get('edge_type') == 'gable':
        r2_end = (e2_mid[0] + e2_ux * (overhang + 0.5 * end2_wall_w), e2_mid[1] + e2_uy * (overhang + 0.5 * end2_wall_w))
        ridge_lines.append((I, r2_end))
        rake_lines.append((e2_c1_ext, e2_c2_ext))
    else:
        inset = e2_w * min(main_ratio, 1.0 - main_ratio)
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
    using 2D weighted straight-skeleton wavefront simulation.
    Handles elongated polygons, regular polygons, and asymmetric per-edge pitches.
    """
    n = len(ordered_walls)
    pts = [item['start'] for item in ordered_walls]

    signed_area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        signed_area += (p2[0] - p1[0]) * (p2[1] + p1[1])
    winding_flip = 1.0 if signed_area > 0 else -1.0

    # Ensure CCW orientation for wavefront and preserve aligned edge pitches
    area = get_polygon_signed_area(pts)
    is_ccw = area > 0
    raw_pitches = [
        float(item.get('pitch_rise') if item.get('pitch_rise') is not None else pitch_rise)
        for item in ordered_walls
    ]
    if is_ccw:
        work_pts = list(pts)
        work_pitches = list(raw_pitches)
    else:
        # Vertex i in reversed order corresponds to wall (n - 1 - i)'s end->start
        work_pts = list(reversed(pts))
        work_pitches = [raw_pitches[(n - 2 - i) % n] for i in range(n)]
    m = len(work_pts)
    has_asymmetric = (max(work_pitches) - min(work_pitches)) > 1e-3

    # Map extended corners for work_pts
    ext_corners = []
    for i in range(m):
        orig_i = i if is_ccw else (n - 1 - i)
        c_ext = get_corner_at_vertex(pts, ordered_walls, orig_i, overhang, winding_flip)
        ext_corners.append(c_ext)

    # Calculate centroid and radial distances
    cx = sum(p[0] for p in work_pts) / m
    cy = sum(p[1] for p in work_pts) / m
    center = (cx, cy)
    center_dists = [math.hypot(p[0] - cx, p[1] - cy) for p in work_pts]
    min_d, max_d = min(center_dists), max(center_dists)

    # 1. Triangle (m == 3): All 3 roof planes meet at a single apex (weighted by 1/pitch).
    if m == 3 and not has_asymmetric:
        p0, p1, p2 = work_pts[0], work_pts[1], work_pts[2]
        l0 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])  # side opposite p0
        l1 = math.hypot(p0[0] - p2[0], p0[1] - p2[1])  # side opposite p1
        l2 = math.hypot(p1[0] - p0[0], p1[1] - p1[1] + (p1[1] - p0[1]))
        perim = l0 + l1 + l2
        if perim > 1e-6:
            ix = (l0 * p0[0] + l1 * p1[0] + l2 * p2[0]) / perim
            iy = (l0 * p0[1] + l1 * p1[1] + l2 * p2[1]) / perim
            apex = (ix, iy)
        else:
            apex = (cx, cy)
        hip_lines = [(apex, c_ext) for c_ext in ext_corners]
        outline_points = calculate_polygon_outline(ordered_walls, overhang)
        return [], hip_lines, [], [], [], outline_points

    # 2. Polygons with all equal sides AND uniform pitch: pyramid hip to centroid.
    side_lens = [math.hypot(work_pts[(i + 1) % m][0] - work_pts[i][0], work_pts[(i + 1) % m][1] - work_pts[i][1]) for i in range(m)]
    min_side, max_side = min(side_lens), max(side_lens)
    is_equal_sides = max_side > 0 and ((max_side - min_side) / max_side < 0.03)

    if not has_asymmetric and m == 4 and is_equal_sides:
        # Square hip roof: pyramid hip with 4 hips meeting at centroid, no ridge
        hip_lines = [(center, c_ext) for c_ext in ext_corners]
        outline_points = calculate_polygon_outline(ordered_walls, overhang)
        return [], hip_lines, [], [], [], outline_points

    if not has_asymmetric and m >= 5 and (is_equal_sides or (max_d > 0 and (max_d - min_d) / max_d < 0.02)):
        # Regular multisided convex hip roof (pentagon, hexagon, octagon)
        hip_lines = [(center, c_ext) for c_ext in ext_corners]
        outline_points = calculate_polygon_outline(ordered_walls, overhang)
        return [], hip_lines, [], [], [], outline_points

    ref_pitch = max(0.5, float(pitch_rise or 6.0))

    class Edge:
        def __init__(self, idx, p1, p2, edge_pitch):
            self.idx = idx
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.hypot(dx, dy) or 1.0
            self.normal = (-dy / length, dx / length)
            self.speed = ref_pitch / max(0.5, float(edge_pitch))

    class VertexNode:
        def __init__(self, pt, orig_idx, e_prev, e_next, t=0.0):
            self.pt = pt
            self.orig_idx = orig_idx  # index into work_pts if t == 0
            self.t_start = t
            self.e_prev = e_prev
            self.e_next = e_next
            n1 = e_prev.normal
            n2 = e_next.normal
            v1 = e_prev.speed
            v2 = e_next.speed
            det = n1[0] * n2[1] - n1[1] * n2[0]
            if abs(det) >= 1e-6:
                self.b = (
                    (v1 * n2[1] - v2 * n1[1]) / det,
                    (n1[0] * v2 - n2[0] * v1) / det,
                )
            elif n1[0] * n2[0] + n1[1] * n2[1] > 0.0:
                avg_v = 0.5 * (v1 + v2)
                self.b = (n1[0] * avg_v, n1[1] * avg_v)
            else:
                self.b = (0.0, 0.0)

        def pos_at(self, t):
            dt = t - self.t_start
            return (self.pt[0] + dt * self.b[0], self.pt[1] + dt * self.b[1])

    edges = [Edge(i, work_pts[i], work_pts[(i + 1) % m], work_pitches[i]) for i in range(m)]
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


def _item_dir(item: Dict[str, Any]) -> Tuple[float, float]:
    """Unit direction of an ordered wall item (zero vector if degenerate)."""
    dx = item['end'][0] - item['start'][0]
    dy = item['end'][1] - item['start'][1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _items_collinear(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True when consecutive items continue in the same straight direction."""
    da, db = _item_dir(a), _item_dir(b)
    cross = da[0] * db[1] - da[1] * db[0]
    dot = da[0] * db[0] + da[1] * db[1]
    return abs(cross) < 1e-3 and dot > 0.0


def merge_collinear_items(ordered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge consecutive collinear wall items (e.g. a split wall) into one edge.

    Roof shape classification and the solvers treat every item as a polygon side, so
    a wall split in two would otherwise add a phantom vertex at the split point and
    corrupt ridge/hip/valley generation. The merged item keeps the wall and edge type
    of its longest member so overhang offsets use a representative wall thickness.

    Args:
        ordered: Closed loop from ``order_walls_into_loop`` (model inches).

    Returns:
        A new list with collinear runs collapsed; the input is returned unchanged if
        merging would leave fewer than 3 sides.
    """
    n = len(ordered)
    if n < 4:
        return ordered
    # Start the walk at a real corner so a collinear run is never split by the seam.
    corner = next((i for i in range(n)
                   if not _items_collinear(ordered[i - 1], ordered[i])), None)
    if corner is None:
        return ordered
    rotated = ordered[corner:] + ordered[:corner]

    runs: List[List[Dict[str, Any]]] = [[rotated[0]]]
    for item in rotated[1:]:
        if _items_collinear(runs[-1][-1], item):
            runs[-1].append(item)
        else:
            runs.append([item])
    if len(runs) < 3 or len(runs) == n:
        return ordered

    merged = []
    for run in runs:
        longest = max(run, key=lambda it: pt_distance(it['start'], it['end']))
        merged.append({
            'start': run[0]['start'],
            'end': run[-1]['end'],
            'wall': longest['wall'],
            'edge_type': longest['edge_type'],
            'members': [it['wall'] for it in run],
        })
    return merged


def group_opposite_eave_sides(
    walls: list,
    markings: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """Group eave wall identifiers into the two primary opposing sides.

    Handles collinear split eaves (merging segments belonging to the same facade)
    and multi-eave hip/L/T footprints (choosing the longest pair of opposing eaves
    so Side A and Side B always flank the main ridge rather than adjacent corners).
    """
    ordered = merge_collinear_items(order_walls_into_loop(walls, markings))
    eave_items = [item for item in ordered if item.get('edge_type') == 'eave']
    if len(eave_items) < 2:
        return ([getattr(w, 'identifier', '') for w in _item_walls(eave_items[0])] if eave_items else []), []

    if len(eave_items) == 2:
        return (
            [getattr(w, 'identifier', '') for w in _item_walls(eave_items[0])],
            [getattr(w, 'identifier', '') for w in _item_walls(eave_items[1])],
        )

    best_pair: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
    best_score = -1.0
    for i in range(len(eave_items)):
        a = eave_items[i]
        da = _item_dir(a)
        la = pt_distance(a['start'], a['end'])
        for j in range(i + 1, len(eave_items)):
            b = eave_items[j]
            db = _item_dir(b)
            lb = pt_distance(b['start'], b['end'])
            dot = da[0] * db[0] + da[1] * db[1]
            if dot < -0.7:
                score = min(la, lb) * 1000.0 + (la + lb)
                if score > best_score:
                    best_score = score
                    best_pair = (a, b)

    if best_pair is None:
        best_pair = (eave_items[0], eave_items[1])
    return (
        [getattr(w, 'identifier', '') for w in _item_walls(best_pair[0])],
        [getattr(w, 'identifier', '') for w in _item_walls(best_pair[1])],
    )


def _item_walls(item: Dict[str, Any]) -> List[Any]:
    """Return all underlying Wall objects represented by a loop item."""
    if 'members' in item and item['members']:
        return list(item['members'])
    w = item.get('wall')
    return [w] if w is not None else []


def calculate_complex_roof_geometry(
    walls: list,
    markings: Dict[str, str],
    overhang: float = 12.0,
    pitch_rise: float = 6.0,
    pitch_run: float = 12.0,
    ratio: float = 0.5,
    edge_pitches: Optional[Dict[str, float]] = None,
    edge_elevations: Optional[Dict[str, float]] = None,
) -> Tuple[List, List, List, List, List, List]:
    """
    Master geometry solver for all roof types.
    Returns:
    (ridge_lines, hip_lines, valley_lines, rake_lines, eave_lines, outline_points)
    """
    ordered_walls = order_walls_into_loop(walls, markings)
    if not ordered_walls:
        return [], [], [], [], [], []
    ordered_walls = merge_collinear_items(ordered_walls)

    has_edge_overrides = bool(edge_pitches or edge_elevations)
    if has_edge_overrides:
        for item in ordered_walls:
            members = _item_walls(item)
            if edge_pitches:
                p_vals = [
                    float(edge_pitches[getattr(w, 'identifier', '')])
                    for w in members
                    if getattr(w, 'identifier', '') in edge_pitches
                ]
                if p_vals:
                    item['pitch_rise'] = sum(p_vals) / len(p_vals)
            if edge_elevations:
                z_vals = [
                    float(edge_elevations[getattr(w, 'identifier', '')])
                    for w in members
                    if getattr(w, 'identifier', '') in edge_elevations
                ]
                if z_vals:
                    item['elevation'] = sum(z_vals) / len(z_vals)

    shape, reflex_idx, _ = classify_polygon_shape(ordered_walls)

    # 1. L-shaped house
    if shape == 'l_shape':
        return generate_l_shaped_roof(
            ordered_walls, overhang, pitch_rise, pitch_run, ratio,
            has_edge_overrides=has_edge_overrides,
        )

    # 2. T-shaped house
    if shape == 't_shape':
        return generate_t_shaped_roof(
            ordered_walls, overhang, pitch_rise, pitch_run, ratio,
            has_edge_overrides=has_edge_overrides,
        )

    # 3. 4-wall rectangle
    if shape == 'rectangle':
        has_gables = any(item.get('edge_type') == 'gable' for item in ordered_walls)
        if has_gables:
            # Standard rectangular gable
            # Use the merged item endpoints (not wall.start/end) so split walls span the full side.
            eave_items = [item for item in ordered_walls if item.get('edge_type') == 'eave']
            gable_items = [item for item in ordered_walls if item.get('edge_type') == 'gable']
            if len(eave_items) == 2 and len(gable_items) == 2:
                from .roof_solver import distance_point_to_segment
                e1 = eave_items[0]
                e2 = eave_items[1]
                eff_ratio = ratio
                if has_edge_overrides:
                    mid1 = ((e1['start'][0] + e1['end'][0]) / 2.0, (e1['start'][1] + e1['end'][1]) / 2.0)
                    span = distance_point_to_segment(mid1, e2['start'], e2['end'])[0] or 1.0
                    eff_ratio = _ratio_from_pitches(
                        e1.get('pitch_rise'),
                        e2.get('pitch_rise'),
                        pitch_rise,
                        z1=e1.get('elevation'),
                        z2=e2.get('elevation'),
                        span=span,
                        pitch_run=pitch_run,
                    )
                ridge_pts = []
                for gi in gable_items[:2]:
                    d1 = distance_point_to_segment(gi['start'], e1['start'], e1['end'])[0]
                    d2 = distance_point_to_segment(gi['end'], e1['start'], e1['end'])[0]
                    p_from = gi['start'] if d1 <= d2 else gi['end']
                    p_to = gi['end'] if d1 <= d2 else gi['start']
                    r_pt = (p_from[0] + eff_ratio * (p_to[0] - p_from[0]), p_from[1] + eff_ratio * (p_to[1] - p_from[1]))
                    ridge_pts.append(r_pt)
                rdx = ridge_pts[1][0] - ridge_pts[0][0]
                rdy = ridge_pts[1][1] - ridge_pts[0][1]
                rlen = math.hypot(rdx, rdy) or 1.0
                ux, uy = rdx / rlen, rdy / rlen
                gw0_w = float(getattr(gable_items[0]['wall'], 'width', 0.0) or 0.0)
                gw1_w = float(getattr(gable_items[1]['wall'], 'width', 0.0) or 0.0)
                r_start = (ridge_pts[0][0] - ux * (overhang + 0.5 * gw0_w), ridge_pts[0][1] - uy * (overhang + 0.5 * gw0_w))
                r_end = (ridge_pts[1][0] + ux * (overhang + 0.5 * gw1_w), ridge_pts[1][1] + uy * (overhang + 0.5 * gw1_w))
                outline = calculate_polygon_outline(ordered_walls, overhang)
                return [(r_start, r_end)], [], [], [], [], outline
        else:
            # Rectangular hip
            return generate_convex_multisided_roof(ordered_walls, overhang, pitch_rise, pitch_run)

    # 4. Multisided convex or general polygons
    return generate_convex_multisided_roof(ordered_walls, overhang, pitch_rise, pitch_run)
