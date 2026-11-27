"""Pure-Python 3D architectural geometry solvers shared by SceneIR and Blender HB5.

All input project entities use EstiSketch 2D Y-down inches unless functions
explicitly specify meters (``*_m``) or centered Y-up coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .parsed import (
    INCH_TO_M,
    Line2D,
    ParsedFixture,
    ParsedProject,
    ParsedRoof,
    ParsedRoofEdge,
    ParsedRoom,
    ParsedStair,
    ParsedWall,
    Point2D,
    Point3D,
    RoomHoleCutout,
    SolvedGableInfill,
    SolvedRoofFacet,
    SolvedRoofGeometry,
)


def compute_plan_center(project: ParsedProject) -> Point2D:
    """Return the bounding-box center ``(cx, cy)`` in inches across walls and rooms."""
    xs: list[float] = []
    ys: list[float] = []
    for w in project.walls:
        xs.extend((w.start[0], w.end[0]))
        ys.extend((w.start[1], w.end[1]))
    for r in project.rooms:
        for x, y in r.points:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0)
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def inches_to_blender_xy(
    x_in: float, y_in: float, cx: float, cy: float
) -> Point2D:
    """Convert EstiSketch 2D Y-down inches to centered Y-up meters."""
    return ((x_in - cx) * INCH_TO_M, -(y_in - cy) * INCH_TO_M)


def tessellate_curved_wall_points(
    start: Point2D,
    end: Point2D,
    arc_center: Point2D | None,
    arc_radius: float | None,
    max_seg_deg: float = 12.0,
) -> list[Point2D]:
    """Return polyline vertices along a curved wall arc in inches (or ``[start, end]``)."""
    if arc_center is None or arc_radius is None or arc_radius <= 1e-6:
        return [start, end]

    cx, cy = arc_center
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    delta = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
    if abs(delta) < 1e-4:
        return [start, end]

    steps = max(2, math.ceil(math.degrees(abs(delta)) / max_seg_deg))
    pts = [start]
    for i in range(1, steps):
        t = i / steps
        ang = a0 + delta * t
        pts.append((cx + arc_radius * math.cos(ang), cy + arc_radius * math.sin(ang)))
    pts.append(end)
    return pts


def compute_opening_local_x(ratio: float, wall_len_m: float, width_m: float) -> float:
    """Compute clamped local X start offset in meters along a wall for an opening."""
    if wall_len_m <= 0.0:
        return 0.0
    max_x = max(0.0, wall_len_m - max(0.0, width_m))
    raw_x = ratio * wall_len_m - width_m / 2.0
    return max(0.0, min(raw_x, max_x))


@dataclass
class WallOpeningCut:
    """Local span along a single wall segment overlapped by a door or window (meters)."""

    wall: ParsedWall
    x_start_m: float
    x_end_m: float
    same_direction: bool
    min_height_m: float


@dataclass
class OpeningChainPlacement:
    """Opening placement across a straight chain of collinear connected walls (meters)."""

    x_local_m: float
    width_m: float
    min_height_m: float
    cuts: list[WallOpeningCut]


def collinear_parsed_wall_chain(
    host_pw: ParsedWall,
    all_walls: list[ParsedWall],
    join_tol_in: float = 0.5,
    line_tol_in: float = 0.5,
) -> list[ParsedWall]:
    """Return ``host_pw`` plus all straight same-level walls connected collinearly."""
    hx = host_pw.end[0] - host_pw.start[0]
    hy = host_pw.end[1] - host_pw.start[1]
    host_len = math.hypot(hx, hy)
    if host_pw.is_curved or host_pw.symbolic or host_len <= 1e-6:
        return [host_pw]

    ux, uy = hx / host_len, hy / host_len
    ox, oy = host_pw.start

    def _on_line(w: ParsedWall) -> bool:
        for px, py in (w.start, w.end):
            if abs((px - ox) * uy - (py - oy) * ux) > line_tol_in:
                return False
        return True

    def _close(a: Point2D, b: Point2D) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_in

    def _is_candidate(w: ParsedWall) -> bool:
        if w is host_pw or w.symbolic or w.is_curved or w.level_id != host_pw.level_id:
            return False
        if math.hypot(w.end[0] - w.start[0], w.end[1] - w.start[1]) <= 1e-6:
            return False
        return _on_line(w)

    candidates = [w for w in all_walls if _is_candidate(w)]

    chain = [host_pw]
    grew = True
    while grew:
        grew = False
        for cand in list(candidates):
            if any(
                _close(m_pt, c_pt)
                for member in chain
                for m_pt in (member.start, member.end)
                for c_pt in (cand.start, cand.end)
            ):
                chain.append(cand)
                candidates.remove(cand)
                grew = True
    return chain


def resolve_opening_chain_placement(
    host_pw: ParsedWall,
    ratio: float,
    opening_width_in: float,
    all_walls: list[ParsedWall],
) -> OpeningChainPlacement:
    """Resolve placement and per-wall cuts for an opening that may straddle split walls."""
    hx = host_pw.end[0] - host_pw.start[0]
    hy = host_pw.end[1] - host_pw.start[1]
    host_len_in = math.hypot(hx, hy)
    if host_len_in <= 1e-6:
        return OpeningChainPlacement(
            x_local_m=0.0,
            width_m=max(0.1, opening_width_in * INCH_TO_M),
            min_height_m=min(host_pw.height, host_pw.height_at_end) * INCH_TO_M,
            cuts=[],
        )

    ux, uy = hx / host_len_in, hy / host_len_in
    ox, oy = host_pw.start

    def _proj(pt: Point2D) -> float:
        return (pt[0] - ox) * ux + (pt[1] - oy) * uy

    chain = collinear_parsed_wall_chain(host_pw, all_walls)
    projected: list[tuple[ParsedWall, float, float, float, float]] = []
    for w in chain:
        ps = _proj(w.start)
        pe = _proj(w.end)
        projected.append((w, ps, pe, min(ps, pe), max(ps, pe)))

    chain_lo = min(item[3] for item in projected)
    chain_hi = max(item[4] for item in projected)
    chain_len_in = max(0.0, chain_hi - chain_lo)

    width_m = max(0.1, min(opening_width_in * INCH_TO_M, chain_len_in * INCH_TO_M))
    eff_width_in = width_m / INCH_TO_M
    raw_start_in = ratio * host_len_in - eff_width_in / 2.0
    max_start_in = max(chain_lo, chain_hi - eff_width_in)
    open_start_in = max(chain_lo, min(raw_start_in, max_start_in))
    open_end_in = open_start_in + eff_width_in

    cuts: list[WallOpeningCut] = []
    for w, ps, pe, s_lo, s_hi in projected:
        ov_lo = max(open_start_in, s_lo)
        ov_hi = min(open_end_in, s_hi)
        if ov_hi - ov_lo <= 1e-3:
            continue
        w_len_in = abs(pe - ps)
        if w_len_in <= 1e-6:
            continue
        same_dir = pe >= ps
        if same_dir:
            wx0_in = ov_lo - ps
            wx1_in = ov_hi - ps
        else:
            wx0_in = ps - ov_hi
            wx1_in = ps - ov_lo
        wx0_in = max(0.0, min(w_len_in, wx0_in))
        wx1_in = max(0.0, min(w_len_in, wx1_in))
        t0 = wx0_in / w_len_in
        t1 = wx1_in / w_len_in
        h0 = w.height + (w.height_at_end - w.height) * t0
        h1 = w.height + (w.height_at_end - w.height) * t1
        cuts.append(
            WallOpeningCut(
                wall=w,
                x_start_m=wx0_in * INCH_TO_M,
                x_end_m=wx1_in * INCH_TO_M,
                same_direction=same_dir,
                min_height_m=min(h0, h1) * INCH_TO_M,
            )
        )

    min_height_m = (
        min(c.min_height_m for c in cuts)
        if cuts
        else min(host_pw.height, host_pw.height_at_end) * INCH_TO_M
    )
    return OpeningChainPlacement(
        x_local_m=open_start_in * INCH_TO_M,
        width_m=width_m,
        min_height_m=min_height_m,
        cuts=cuts,
    )


@dataclass
class StripSegment:
    """2D oriented strip segment (meters) with offsets along its left normal."""

    p0: Point2D
    p1: Point2D
    y0: float
    y1: float


def _intersect_2d_lines(
    p: Point2D,
    dp: Point2D,
    q: Point2D,
    dq: Point2D,
) -> Point2D | None:
    """Return intersection of lines ``p + t*dp`` and ``q + u*dq``, or ``None`` if parallel."""
    det = dp[0] * dq[1] - dp[1] * dq[0]
    if abs(det) < 1e-5:
        return None
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    t = (dx * dq[1] - dy * dq[0]) / det
    return (p[0] + t * dp[0], p[1] + t * dp[1])


def _is_duplicate_seg(
    p0: Point2D,
    p1: Point2D,
    q0: Point2D,
    q1: Point2D,
    tol: float,
) -> bool:
    """True when two segments share both endpoints in either order within ``tol``."""
    same = math.hypot(p0[0] - q0[0], p0[1] - q0[1]) <= tol
    same_end = math.hypot(p1[0] - q1[0], p1[1] - q1[1]) <= tol
    if same and same_end:
        return True
    swap = math.hypot(p0[0] - q1[0], p0[1] - q1[1]) <= tol
    swap_end = math.hypot(p1[0] - q0[0], p1[1] - q0[1]) <= tol
    return swap and swap_end


def compute_mitered_strip_polygons(
    segments: list[StripSegment],
    join_tol_m: float = 0.015,
    miter_limit: float = 4.0,
) -> list[list[Point2D]]:
    """Compute mitered 2D quad polygons for connected 2D strips (footers, rim bands).

    Args:
        segments: List of ``StripSegment`` in meters.
        join_tol_m: Endpoint matching tolerance in meters.
        miter_limit: Maximum corner extension as a multiple of strip offset width.

    Returns:
        List of 4-vertex polygons ``[s0, e0, e1, s1]`` parallel to ``segments``
        (or ``[]`` for degenerate zero-length segments).
    """
    meta: list[tuple[Point2D, Point2D] | None] = []
    for seg in segments:
        dx = seg.p1[0] - seg.p0[0]
        dy = seg.p1[1] - seg.p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            meta.append(None)
        else:
            d = (dx / length, dy / length)
            n = (-d[1], d[0])
            meta.append((d, n))

    def _pt_close(a: Point2D, b: Point2D) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_m

    def _miter_endpoint(
        idx: int,
        pt: Point2D,
        is_start: bool,
        cur_0: Point2D,
        cur_1: Point2D,
    ) -> tuple[Point2D, Point2D]:
        seg = segments[idx]
        m_idx = meta[idx]
        if m_idx is None:
            return (cur_0, cur_1)
        d, n = m_idx
        non_collinear: list[int] = []
        for j, other in enumerate(segments):
            m_other = meta[j]
            if j == idx or m_other is None:
                continue
            if _is_duplicate_seg(seg.p0, seg.p1, other.p0, other.p1, join_tol_m):
                continue
            if not (_pt_close(other.p0, pt) or _pt_close(other.p1, pt)):
                continue
            od, _ = m_other
            cross = d[0] * od[1] - d[1] * od[0]
            if abs(cross) < 1e-3:
                return (cur_0, cur_1)
            non_collinear.append(j)

        unique_nbs: list[int] = []
        for j in non_collinear:
            oj = segments[j]
            if not any(
                _is_duplicate_seg(
                    oj.p0, oj.p1, segments[k].p0, segments[k].p1, join_tol_m
                )
                for k in unique_nbs
            ):
                unique_nbs.append(j)

        if len(unique_nbs) != 1:
            return (cur_0, cur_1)

        nb_idx = unique_nbs[0]
        other = segments[nb_idx]
        m_nb = meta[nb_idx]
        if m_nb is None:
            return (cur_0, cur_1)
        od, on = m_nb
        same_flow = _pt_close(other.p1, pt) if is_start else _pt_close(other.p0, pt)
        other_y0, other_y1 = (other.y0, other.y1) if same_flow else (other.y1, other.y0)

        max_off = max(abs(seg.y0), abs(seg.y1), abs(other.y0), abs(other.y1), 0.1)
        max_dist = miter_limit * max_off

        ix0 = _intersect_2d_lines(
            (pt[0] + n[0] * seg.y0, pt[1] + n[1] * seg.y0),
            d,
            (pt[0] + on[0] * other_y0, pt[1] + on[1] * other_y0),
            od,
        )
        ix1 = _intersect_2d_lines(
            (pt[0] + n[0] * seg.y1, pt[1] + n[1] * seg.y1),
            d,
            (pt[0] + on[0] * other_y1, pt[1] + on[1] * other_y1),
            od,
        )
        ok0 = ix0 is not None and math.hypot(ix0[0] - pt[0], ix0[1] - pt[1]) <= max_dist
        ok1 = ix1 is not None and math.hypot(ix1[0] - pt[0], ix1[1] - pt[1]) <= max_dist
        out_0 = ix0 if (ix0 is not None and ok0) else cur_0
        out_1 = ix1 if (ix1 is not None and ok1) else cur_1
        return (out_0, out_1)

    result: list[list[Point2D]] = []
    for idx, seg in enumerate(segments):
        m = meta[idx]
        if m is None:
            result.append([])
            continue
        d, n = m
        sq_s0 = (seg.p0[0] + n[0] * seg.y0, seg.p0[1] + n[1] * seg.y0)
        sq_s1 = (seg.p0[0] + n[0] * seg.y1, seg.p0[1] + n[1] * seg.y1)
        sq_e0 = (seg.p1[0] + n[0] * seg.y0, seg.p1[1] + n[1] * seg.y0)
        sq_e1 = (seg.p1[0] + n[0] * seg.y1, seg.p1[1] + n[1] * seg.y1)

        s0, s1 = _miter_endpoint(idx, seg.p0, True, sq_s0, sq_s1)
        e0, e1 = _miter_endpoint(idx, seg.p1, False, sq_e0, sq_e1)

        dot0 = (e0[0] - s0[0]) * d[0] + (e0[1] - s0[1]) * d[1]
        dot1 = (e1[0] - s1[0]) * d[0] + (e1[1] - s1[1]) * d[1]
        if dot0 <= 1e-5 or dot1 <= 1e-5:
            result.append([sq_s0, sq_e0, sq_e1, sq_s1])
        else:
            result.append([s0, e0, e1, s1])
    return result


def _flip_parsed_wall(pw: ParsedWall, project: ParsedProject) -> None:
    """Reverse a wall's direction while preserving finishes, footers, and openings."""
    pw.start, pw.end = pw.end, pw.start
    pw.height, pw.height_at_end = pw.height_at_end, pw.height
    pw.left_finish, pw.right_finish = pw.right_finish, pw.left_finish
    pw.left_color, pw.right_color = pw.right_color, pw.left_color
    pw.left_baseboard, pw.right_baseboard = pw.right_baseboard, pw.left_baseboard
    pw.footer_left_offset, pw.footer_right_offset = (
        pw.footer_right_offset,
        pw.footer_left_offset,
    )
    key = (pw.set_index, pw.wall_index)
    for pd in project.doors:
        if (pd.set_index, pd.wall_index) == key:
            pd.ratio = 1.0 - pd.ratio
            if pd.orientation == "inswing":
                pd.orientation = "outswing"
            elif pd.orientation == "outswing":
                pd.orientation = "inswing"
            if pd.swing == "left":
                pd.swing = "right"
            elif pd.swing == "right":
                pd.swing = "left"
    for pw_win in project.windows:
        if (pw_win.set_index, pw_win.wall_index) == key:
            pw_win.ratio = 1.0 - pw_win.ratio


def orient_interior_wall_chains(
    project: ParsedProject, join_tol_in: float = 0.5
) -> int:
    """Orient connected interior wall L-/Z-chains head-to-tail for HB5 mitering.

    Only flips straight, non-symbolic interior walls at clean 2-wall non-collinear
    corners (skipping T-junctions and exterior walls). Returns the count of flipped walls.
    """
    walls_by_level: dict[str, list[ParsedWall]] = {}
    for pw in project.walls:
        if pw.exterior_wall or pw.symbolic or pw.is_curved:
            continue
        if math.hypot(pw.end[0] - pw.start[0], pw.end[1] - pw.start[1]) <= 1e-4:
            continue
        walls_by_level.setdefault(pw.level_id, []).append(pw)

    flipped = 0
    for lvl_walls in walls_by_level.values():
        clusters: list[Point2D] = []
        wall_clusters: list[tuple[int, int]] = []

        def _cluster_id(pt: Point2D) -> int:
            for cid, cpt in enumerate(clusters):
                if math.hypot(pt[0] - cpt[0], pt[1] - cpt[1]) <= join_tol_in:
                    return cid
            clusters.append(pt)
            return len(clusters) - 1

        at_cluster: dict[int, list[int]] = {}
        for idx, pw in enumerate(lvl_walls):
            c_s = _cluster_id(pw.start)
            c_e = _cluster_id(pw.end)
            wall_clusters.append((c_s, c_e))
            at_cluster.setdefault(c_s, []).append(idx)
            if c_e != c_s:
                at_cluster.setdefault(c_e, []).append(idx)

        adj: dict[int, list[tuple[int, int]]] = {i: [] for i in range(len(lvl_walls))}
        for cid, members in at_cluster.items():
            if len(members) != 2:
                continue
            ia, ib = members[0], members[1]
            wa, wb = lvl_walls[ia], lvl_walls[ib]
            dax, day = wa.end[0] - wa.start[0], wa.end[1] - wa.start[1]
            dbx, dby = wb.end[0] - wb.start[0], wb.end[1] - wb.start[1]
            la, lb = math.hypot(dax, day), math.hypot(dbx, dby)
            if la <= 1e-4 or lb <= 1e-4:
                continue
            cross = (dax * dby - day * dbx) / (la * lb)
            if abs(cross) <= 1e-3:
                continue
            adj[ia].append((cid, ib))
            adj[ib].append((cid, ia))

        visited: set[int] = set()

        def _walk_from(start_idx: int) -> None:
            nonlocal flipped
            nbs = adj[start_idx]
            if not nbs:
                visited.add(start_idx)
                return
            first_cid = nbs[0][0]
            w0 = lvl_walls[start_idx]
            c_s, c_e = wall_clusters[start_idx]
            if len(nbs) == 1 and c_s == first_cid and c_e != first_cid:
                _flip_parsed_wall(w0, project)
                wall_clusters[start_idx] = (c_e, c_s)
                flipped += 1

            curr = start_idx
            visited.add(curr)
            while True:
                curr_end_cid = wall_clusters[curr][1]
                next_idx: int | None = None
                for cid, nb in adj[curr]:
                    if cid == curr_end_cid and nb not in visited:
                        next_idx = nb
                        break
                if next_idx is None:
                    break
                wn = lvl_walls[next_idx]
                nc_s, nc_e = wall_clusters[next_idx]
                if nc_e == curr_end_cid and nc_s != curr_end_cid:
                    _flip_parsed_wall(wn, project)
                    wall_clusters[next_idx] = (nc_e, nc_s)
                    flipped += 1
                visited.add(next_idx)
                curr = next_idx

        for idx in range(len(lvl_walls)):
            if idx not in visited and len(adj[idx]) == 1:
                _walk_from(idx)
        for idx in range(len(lvl_walls)):
            if idx not in visited and len(adj[idx]) >= 1:
                _walk_from(idx)

    return flipped


def solve_hb5_miter_angles(
    a_rot: float,
    a_thick: float,
    b_rot: float,
    b_thick: float,
    max_shear_ratio: float = 8.0,
) -> tuple[float, float]:
    """Solve HB5 ``(Right Angle on A, Left Angle on B)`` in radians at a corner."""
    turn = b_rot - a_rot
    while turn > math.pi:
        turn -= 2.0 * math.pi
    while turn <= -math.pi:
        turn += 2.0 * math.pi
    if abs(turn) < 1e-6:
        return (0.0, 0.0)

    ca, sa = math.cos(a_rot), math.sin(a_rot)
    cb, sb = math.cos(b_rot), math.sin(b_rot)
    nax, nay = -sa, ca
    nbx, nby = -sb, cb

    det = ca * (-sb) - (-cb) * sa
    if abs(det) < 1e-9:
        return (-turn / 2.0, turn / 2.0)

    rhs_x = b_thick * nbx - a_thick * nax
    rhs_y = b_thick * nby - a_thick * nay
    shear_a = (rhs_x * (-sb) - (-cb) * rhs_y) / det
    shear_b = (ca * rhs_y - rhs_x * sa) / det

    if abs(shear_a) > max_shear_ratio * a_thick or abs(shear_b) > max_shear_ratio * b_thick:
        return (-turn / 2.0, turn / 2.0)

    right_a = math.atan2(shear_a, a_thick) if a_thick else 0.0
    left_b = math.atan2(shear_b, b_thick) if b_thick else 0.0
    return (right_a, left_b)


def compute_level_wall_miters(
    wall_entries: list[tuple[str, Point2D, Point2D, float, bool]],
    join_tol_m: float = 0.015,
) -> dict[str, tuple[float, float]]:
    """Compute ``{key: (left_angle_rad, right_angle_rad)}`` for walls on one level."""
    left_angles: dict[str, float] = {item[0]: 0.0 for item in wall_entries}
    right_angles: dict[str, float] = {item[0]: 0.0 for item in wall_entries}

    dirs: list[tuple[float, float, float] | None] = []
    for _, p0, p1, _, _ in wall_entries:
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            dirs.append(None)
        else:
            dirs.append((dx / length, dy / length, math.atan2(dy, dx)))

    def _pt_close(a: Point2D, b: Point2D) -> bool:
        return math.hypot(a[0] - b[0], a[1] - b[1]) <= join_tol_m

    def _has_collinear_at(idx: int, pt: Point2D) -> bool:
        d_i = dirs[idx]
        if d_i is None:
            return False
        _, p0_i, p1_i, _, _ = wall_entries[idx]
        for j, (_, p0_j, p1_j, _, _) in enumerate(wall_entries):
            d_j = dirs[j]
            if j == idx or d_j is None:
                continue
            if _is_duplicate_seg(p0_i, p1_i, p0_j, p1_j, join_tol_m):
                continue
            if not (_pt_close(p0_j, pt) or _pt_close(p1_j, pt)):
                continue
            cross = d_i[0] * d_j[1] - d_i[1] * d_j[0]
            if abs(cross) < 1e-3:
                return True
        return False

    for i, (key_a, p0_a, p1_a, thick_a, ext_a) in enumerate(wall_entries):
        d_a = dirs[i]
        if d_a is None or _has_collinear_at(i, p1_a):
            continue

        cands: list[tuple[int, str, float, float, bool]] = []
        for j, (key_b, p0_b, p1_b, thick_b, ext_b) in enumerate(wall_entries):
            d_b = dirs[j]
            if j == i or d_b is None:
                continue
            if _is_duplicate_seg(p0_a, p1_a, p0_b, p1_b, join_tol_m):
                continue
            if not _pt_close(p0_b, p1_a):
                continue
            cross = d_a[0] * d_b[1] - d_a[1] * d_b[0]
            if abs(cross) < 1e-3 or _has_collinear_at(j, p0_b):
                continue
            cands.append((j, key_b, thick_b, d_b[2], ext_b))

        same_kind = [c for c in cands if c[4] == ext_a]
        if same_kind:
            cands = same_kind
        if len(cands) == 1:
            _, key_b, thick_b, rot_b, _ = cands[0]
            ra, lb = solve_hb5_miter_angles(d_a[2], thick_a, rot_b, thick_b)
            right_angles[key_a] = ra
            left_angles[key_b] = lb

    return {k: (left_angles[k], right_angles[k]) for k in left_angles}


def compute_sun_rotation_euler(north_angle_deg: float) -> Point3D:
    """Return sun ``rotation_euler`` in radians adjusted clockwise by ``north_angle_deg``."""
    return (math.radians(48.0), math.radians(15.0), math.radians(-35.0 - north_angle_deg))


def compute_window_sill_height_m(
    win_height_m: float,
    wall_min_h_m: float,
    head_height_m: float = 80.0 * INCH_TO_M,
) -> float:
    """Compute window sill height in meters aligned cleanly to an ~80\" head."""
    max_sill = max(0.0, wall_min_h_m - win_height_m - 0.05)
    target_head = min(head_height_m, max(win_height_m + 0.05, wall_min_h_m - 0.10))
    return max(0.0, min(target_head - win_height_m, max_sill))


def compute_baseboard_spans(
    wall_len_m: float,
    door_intervals: list[tuple[float, float]],
    min_span_m: float = 0.03,
) -> list[tuple[float, float]]:
    """Return uninterrupted ``(start_m, end_m)`` baseboard spans in meters along a wall."""
    if wall_len_m < min_span_m:
        return []
    cleaned: list[tuple[float, float]] = []
    for x0, x1 in door_intervals:
        a = max(0.0, min(x0, x1))
        b = min(wall_len_m, max(x0, x1))
        if b - a > 1e-4:
            cleaned.append((a, b))
    cleaned.sort()

    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in cleaned:
        if a - cursor >= min_span_m:
            spans.append((cursor, a))
        cursor = max(cursor, b)
    if wall_len_m - cursor >= min_span_m:
        spans.append((cursor, wall_len_m))
    return spans


def resolve_curved_wall_segment(
    seg_lengths: list[float], ratio: float
) -> tuple[int, float]:
    """Map an opening ratio ``[0, 1]`` along a multi-segment wall to ``(seg_idx, ratio)``."""
    if not seg_lengths:
        return (0, 0.5)
    total = sum(seg_lengths)
    if total <= 1e-6:
        return (0, 0.5)
    clamped = max(0.0, min(1.0, ratio))
    target = clamped * total
    acc = 0.0
    for idx, slen in enumerate(seg_lengths):
        if target <= acc + slen + 1e-9 or idx == len(seg_lengths) - 1:
            local_r = (target - acc) / slen if slen > 1e-6 else 0.5
            return (idx, max(0.0, min(1.0, local_r)))
        acc += slen
    return (len(seg_lengths) - 1, 0.5)


@dataclass
class _EavePlaneDef:
    start: Point2D
    end: Point2D
    inward_normal: Point2D
    slope: float
    pitch_rise: float
    z_plate: float  # inches

    def elevation_at(self, x: float, y: float) -> float:
        dx = x - self.start[0]
        dy = y - self.start[1]
        proj = dx * self.inward_normal[0] + dy * self.inward_normal[1]
        return self.z_plate + self.slope * proj


def _pt_in_poly_2d(px: float, py: float, poly: list[Point2D]) -> bool:
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-18) + x1):
            inside = not inside
    return inside


def _dist_pt_to_seg_2d(p: Point2D, a: Point2D, b: Point2D) -> tuple[float, float]:
    """Return ``(distance, clamped_t)`` from point ``p`` to segment ``a -> b``."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        return (math.hypot(p[0] - a[0], p[1] - a[1]), 0.0)
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    proj = (a[0] + t * dx, a[1] + t * dy)
    return (math.hypot(p[0] - proj[0], p[1] - proj[1]), t)


def _line_intersect_2d(
    p1: Point2D,
    p2: Point2D,
    p3: Point2D,
    p4: Point2D,
) -> tuple[float, float, float, float] | None:
    """Return ``(ix, iy, t, u)`` for lines ``p1->p2`` and ``p3->p4``, or ``None``."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1), t, u)


def _clean_polygon_pts(pts: list[Point2D], tol: float = 0.25) -> list[Point2D]:
    cleaned: list[Point2D] = []
    for pt in pts:
        if not cleaned or math.hypot(pt[0] - cleaned[-1][0], pt[1] - cleaned[-1][1]) > tol:
            cleaned.append((float(pt[0]), float(pt[1])))
    if len(cleaned) >= 2:
        gap = math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1])
        if gap <= tol:
            cleaned.pop()
    return cleaned


def _order_walls_polygon(walls: list[ParsedWall]) -> list[Point2D]:
    """Order bound perimeter walls into a closed 2D loop of vertices (inches)."""
    if len(walls) < 3:
        return []
    segs = [(w.start, w.end) for w in walls]
    ordered = [segs[0]]
    rem = list(segs[1:])
    while rem:
        cur_end = ordered[-1][1]
        matched_idx = -1
        flip = False
        best_d = 2.0
        for idx, (s, e) in enumerate(rem):
            ds = math.hypot(s[0] - cur_end[0], s[1] - cur_end[1])
            de = math.hypot(e[0] - cur_end[0], e[1] - cur_end[1])
            if ds < best_d:
                best_d = ds
                matched_idx = idx
                flip = False
            if de < best_d:
                best_d = de
                matched_idx = idx
                flip = True
        if matched_idx < 0:
            break
        s, e = rem.pop(matched_idx)
        ordered.append((e, s) if flip else (s, e))
    if len(ordered) != len(segs):
        return []
    end_gap = math.hypot(
        ordered[-1][1][0] - ordered[0][0][0],
        ordered[-1][1][1] - ordered[0][0][1],
    )
    if end_gap > 2.0:
        return []
    return _clean_polygon_pts([s for s, _ in ordered])


def _polygon_signed_area_2d(pts: list[Point2D]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    return 0.5 * sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )


def _extract_planar_faces(
    outline: list[Point2D],
    interior_lines: list[Line2D],
    snap_tol: float = 0.75,
) -> tuple[list[Point2D], list[list[int]]]:
    """Decompose an outline polygon + interior roof lines into minimal 2D faces."""
    outline_clean = _clean_polygon_pts(outline, tol=0.25)
    if len(outline_clean) < 3:
        return [], []
    if not interior_lines:
        return outline_clean, [list(range(len(outline_clean)))]

    raw_segs: list[Line2D] = [
        (outline_clean[i], outline_clean[(i + 1) % len(outline_clean)])
        for i in range(len(outline_clean))
    ]
    for s, e in interior_lines:
        if math.hypot(e[0] - s[0], e[1] - s[1]) > 0.5:
            raw_segs.append((s, e))

    cand_pts: list[Point2D] = []
    for s, e in raw_segs:
        cand_pts.append(s)
        cand_pts.append(e)
    for i in range(len(raw_segs)):
        for j in range(i + 1, len(raw_segs)):
            res = _line_intersect_2d(
                raw_segs[i][0], raw_segs[i][1], raw_segs[j][0], raw_segs[j][1]
            )
            if res is not None:
                ix, iy, t, u = res
                if -0.02 <= t <= 1.02 and -0.02 <= u <= 1.02:
                    cand_pts.append((ix, iy))

    verts: list[Point2D] = []

    def _get_vid(pt: Point2D) -> int:
        best_i = -1
        best_d = snap_tol
        for vi, v in enumerate(verts):
            d = math.hypot(pt[0] - v[0], pt[1] - v[1])
            if d <= best_d:
                best_d = d
                best_i = vi
        if best_i >= 0:
            return best_i
        verts.append((float(pt[0]), float(pt[1])))
        return len(verts) - 1

    for pt in cand_pts:
        _get_vid(pt)

    edges_set: set[tuple[int, int]] = set()
    for s, e in raw_segs:
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-4:
            continue
        ux, uy = dx / seg_len, dy / seg_len
        on_seg: list[tuple[float, int]] = []
        for vi, v in enumerate(verts):
            proj = (v[0] - s[0]) * ux + (v[1] - s[1]) * uy
            if -snap_tol <= proj <= seg_len + snap_tol:
                perp = abs((v[0] - s[0]) * (-uy) + (v[1] - s[1]) * ux)
                if perp <= snap_tol:
                    on_seg.append((proj, vi))
        on_seg.sort(key=lambda item: item[0])
        ordered_vids: list[int] = []
        for _, vi in on_seg:
            if not ordered_vids or ordered_vids[-1] != vi:
                ordered_vids.append(vi)
        for k in range(len(ordered_vids) - 1):
            u_id, v_id = ordered_vids[k], ordered_vids[k + 1]
            if u_id != v_id:
                edge = (u_id, v_id) if u_id < v_id else (v_id, u_id)
                edges_set.add(edge)

    if not edges_set:
        return outline_clean, [list(range(len(outline_clean)))]

    adj: dict[int, list[int]] = {}
    for u_id, v_id in edges_set:
        adj.setdefault(u_id, []).append(v_id)
        adj.setdefault(v_id, []).append(u_id)
    for u_id, nbrs in adj.items():
        ux, uy = verts[u_id]
        nbrs.sort(key=lambda vid: math.atan2(verts[vid][1] - uy, verts[vid][0] - ux))

    used_dir: set[tuple[int, int]] = set()
    cycles: list[tuple[float, list[int]]] = []
    max_steps = len(verts) * 2 + 4
    for u_id, v_id in list(edges_set):
        for start_dir in ((u_id, v_id), (v_id, u_id)):
            if start_dir in used_dir:
                continue
            cur_u, cur_v = start_dir
            face_vids = [cur_u]
            steps = 0
            closed = False
            while steps < max_steps:
                used_dir.add((cur_u, cur_v))
                nbrs = adj.get(cur_v, [])
                if len(nbrs) < 2:
                    break
                pos = nbrs.index(cur_u)
                nxt = nbrs[(pos - 1) % len(nbrs)]
                cur_u, cur_v = cur_v, nxt
                if (cur_u, cur_v) == start_dir:
                    closed = True
                    break
                face_vids.append(cur_u)
                steps += 1
            if closed and len(face_vids) >= 3:
                area = _polygon_signed_area_2d([verts[i] for i in face_vids])
                if abs(area) > 10.0:
                    cycles.append((area, face_vids))

    interior_faces = [f for area, f in cycles if area > 0.0]
    if not interior_faces and cycles:
        cycles.sort(key=lambda item: abs(item[0]))
        interior_faces = [f for _, f in cycles[:-1]] or [cycles[0][1]]

    return verts, interior_faces


def solve_roof_3d(roof: ParsedRoof, project: ParsedProject) -> SolvedRoofGeometry:
    """Reconstruct watertight 3D roof facets and gable-end wall infills in inches."""
    level_by_id = {lvl.id: lvl for lvl in project.levels}
    wall_by_id = {w.identifier: w for w in project.walls if not w.symbolic}

    def _wall_plate_z(w: ParsedWall) -> float:
        lvl = level_by_id.get(w.level_id, project.levels[0])
        return lvl.elevation + min(w.height, w.height_at_end)

    def _wall_top_max_z(w: ParsedWall) -> float:
        lvl = level_by_id.get(w.level_id, project.levels[0])
        return lvl.elevation + max(w.height, w.height_at_end)

    bound_walls: list[ParsedWall] = [
        wall_by_id[e.wall_identifier]
        for e in roof.edges
        if e.wall_identifier in wall_by_id
    ]
    eave_edges = [e for e in roof.edges if e.edge_type == "eave"]

    if bound_walls:
        default_z_plate = _wall_plate_z(bound_walls[0])
        for edge in eave_edges:
            if edge.wall_identifier in wall_by_id:
                default_z_plate = _wall_plate_z(wall_by_id[edge.wall_identifier])
                break
    else:
        lvl = level_by_id.get(roof.level_id, project.levels[0])
        default_z_plate = lvl.elevation + lvl.height

    outline = _clean_polygon_pts(roof.outline_points, tol=0.25)
    if len(outline) < 3 and bound_walls:
        xs = [c for w in bound_walls for c in (w.start[0], w.end[0])]
        ys = [c for w in bound_walls for c in (w.start[1], w.end[1])]
        oh = roof.overhang
        outline = [
            (min(xs) - oh, min(ys) - oh),
            (max(xs) + oh, min(ys) - oh),
            (max(xs) + oh, max(ys) + oh),
            (min(xs) - oh, max(ys) + oh),
        ]

    wall_poly = _order_walls_polygon(bound_walls)
    test_poly = wall_poly if len(wall_poly) >= 3 else outline
    test_step = 6.0 if len(wall_poly) >= 3 else max(6.0, roof.overhang + 12.0)
    poly_cx = sum(p[0] for p in outline) / len(outline) if outline else 0.0
    poly_cy = sum(p[1] for p in outline) / len(outline) if outline else 0.0

    raw_eave_segs: list[Line2D] = list(roof.eave_lines)
    if not raw_eave_segs:
        for edge in eave_edges:
            if edge.wall_identifier in wall_by_id:
                w = wall_by_id[edge.wall_identifier]
                raw_eave_segs.append((w.start, w.end))

    eave_defs: list[_EavePlaneDef] = []
    pitch_run = roof.pitch_run or 12.0
    for s, e in raw_eave_segs:
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        seg_len = math.hypot(dx, dy)
        if seg_len <= 1e-4:
            continue
        mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0

        matched_edge: ParsedRoofEdge | None = None
        matched_wall: ParsedWall | None = None
        best_score = 1e9
        for edge in eave_edges:
            w = wall_by_id.get(edge.wall_identifier)
            if w is None:
                continue
            wmx = (w.start[0] + w.end[0]) / 2.0
            wmy = (w.start[1] + w.end[1]) / 2.0
            d_mid = math.hypot(mx - wmx, my - wmy)
            if d_mid < best_score and d_mid <= max(24.0, w.width + roof.overhang):
                best_score = d_mid
                matched_edge = edge
                matched_wall = w

        p_rise = (
            matched_edge.pitch_rise
            if (matched_edge and matched_edge.pitch_rise is not None)
            else roof.pitch_rise
        )
        slope = p_rise / pitch_run
        z_plate = _wall_plate_z(matched_wall) if matched_wall is not None else default_z_plate

        ux, uy = dx / seg_len, dy / seg_len
        n1 = (-uy, ux)
        n2 = (uy, -ux)
        in1 = _pt_in_poly_2d(mx + test_step * n1[0], my + test_step * n1[1], test_poly)
        in2 = _pt_in_poly_2d(mx + test_step * n2[0], my + test_step * n2[1], test_poly)
        if in1 and not in2:
            n_in = n1
        elif in2 and not in1:
            n_in = n2
        else:
            dot1 = (poly_cx - mx) * n1[0] + (poly_cy - my) * n1[1]
            n_in = n1 if dot1 >= 0.0 else n2

        eave_defs.append(
            _EavePlaneDef(
                start=s,
                end=e,
                inward_normal=n_in,
                slope=slope,
                pitch_rise=p_rise,
                z_plate=z_plate,
            )
        )

    interior_lines: list[Line2D] = (
        list(roof.ridge_lines) + list(roof.hip_lines) + list(roof.valley_lines)
    )

    synthesized_ridges: list[Line2D] = []
    if not interior_lines and len(eave_defs) == 2 and len(outline) >= 3:
        ep0, ep1 = eave_defs[0], eave_defs[1]
        a0 = ep0.slope * ep0.inward_normal[0]
        b0 = ep0.slope * ep0.inward_normal[1]
        d0 = ep0.z_plate - (a0 * ep0.start[0] + b0 * ep0.start[1])
        a1 = ep1.slope * ep1.inward_normal[0]
        b1 = ep1.slope * ep1.inward_normal[1]
        d1 = ep1.z_plate - (a1 * ep1.start[0] + b1 * ep1.start[1])
        da, db, dc = a0 - a1, b0 - b1, d0 - d1
        norm2 = da * da + db * db
        if norm2 > 1e-12:
            p0_r = (-dc * da / norm2, -dc * db / norm2)
            p1_r = (p0_r[0] - db, p0_r[1] + da)
            hits: list[tuple[float, Point2D]] = []
            for k in range(len(outline)):
                oa = outline[k]
                ob = outline[(k + 1) % len(outline)]
                res = _line_intersect_2d(p0_r, p1_r, oa, ob)
                if res is not None:
                    ix, iy, t, u = res
                    if -1e-4 <= u <= 1.0 + 1e-4:
                        hits.append((t, (ix, iy)))
            hits.sort(key=lambda item: item[0])
            uniq_hits: list[Point2D] = []
            for _, pt in hits:
                if not uniq_hits:
                    uniq_hits.append(pt)
                elif math.hypot(pt[0] - uniq_hits[-1][0], pt[1] - uniq_hits[-1][1]) > 0.5:
                    uniq_hits.append(pt)
            if len(uniq_hits) >= 2:
                seg = (uniq_hits[0], uniq_hits[-1])
                interior_lines.append(seg)
                synthesized_ridges.append(seg)

    verts_2d, face_indices = _extract_planar_faces(outline, interior_lines)
    if not verts_2d or not face_indices:
        return SolvedRoofGeometry(
            roof_id=roof.identifier, level_id=roof.level_id, material=roof.material
        )

    face_eave: list[_EavePlaneDef | None] = []
    for f_vids in face_indices:
        fcx = sum(verts_2d[vi][0] for vi in f_vids) / len(f_vids)
        fcy = sum(verts_2d[vi][1] for vi in f_vids) / len(f_vids)
        best_eave: _EavePlaneDef | None = None
        best_score = -1e9
        for ep in eave_defs:
            edx = ep.end[0] - ep.start[0]
            edy = ep.end[1] - ep.start[1]
            elen = math.hypot(edx, edy)
            if elen <= 1e-4:
                continue
            eux, euy = edx / elen, edy / elen
            emx, emy = (ep.start[0] + ep.end[0]) / 2.0, (ep.start[1] + ep.end[1]) / 2.0
            rx, ry = fcx - ep.start[0], fcy - ep.start[1]
            inward_d = rx * ep.inward_normal[0] + ry * ep.inward_normal[1]

            edge_bonus = 0.0
            for k in range(len(f_vids)):
                va = verts_2d[f_vids[k]]
                vb = verts_2d[f_vids[(k + 1) % len(f_vids)]]
                fdx, fdy = vb[0] - va[0], vb[1] - va[1]
                flen = math.hypot(fdx, fdy)
                if flen <= 1e-4:
                    continue
                if abs((fdx / flen) * eux + (fdy / flen) * euy) > 0.98:
                    dist_e, _ = _dist_pt_to_seg_2d((emx, emy), va, vb)
                    if dist_e <= roof.overhang + 16.0:
                        edge_bonus = max(edge_bonus, 1000.0 - dist_e)

            inward_score = 100.0 - inward_d if inward_d >= -2.0 else -500.0 + inward_d
            score = edge_bonus + inward_score
            if score > best_score:
                best_score = score
                best_eave = ep
        face_eave.append(best_eave)

    vert_zs: dict[int, float] = {}
    for f_idx, f_vids in enumerate(face_indices):
        ep = face_eave[f_idx]
        for vi in f_vids:
            vx, vy = verts_2d[vi]
            z = ep.elevation_at(vx, vy) if ep is not None else default_z_plate
            if vi not in vert_zs or z > vert_zs[vi]:
                vert_zs[vi] = z

    facets: list[SolvedRoofFacet] = []
    for f_idx, f_vids in enumerate(face_indices):
        ep = face_eave[f_idx]
        p_rise = ep.pitch_rise if ep is not None else roof.pitch_rise
        v3d = [(verts_2d[vi][0], verts_2d[vi][1], vert_zs[vi]) for vi in f_vids]
        facets.append(SolvedRoofFacet(vertices_3d=v3d, pitch_rise=p_rise))

    gable_infills: list[SolvedGableInfill] = []
    ridge_candidates = list(roof.ridge_lines) + synthesized_ridges
    for edge in roof.edges:
        if edge.edge_type != "gable":
            continue
        pw = wall_by_id.get(edge.wall_identifier)
        if pw is None or abs(pw.height - pw.height_at_end) > 2.0:
            continue
        z_base = _wall_top_max_z(pw)
        a = pw.start
        b = pw.end
        w_dx = b[0] - a[0]
        w_dy = b[1] - a[1]
        w_len = math.hypot(w_dx, w_dy)
        if w_len <= 1.0:
            continue
        w_ux, w_uy = w_dx / w_len, w_dy / w_len

        covered_by_upper = False
        for ow in project.walls:
            if ow.symbolic or ow.identifier == pw.identifier:
                continue
            o_base = level_by_id.get(ow.level_id, project.levels[0]).elevation
            o_top = _wall_top_max_z(ow)
            if o_base > z_base + 14.0 or o_top <= z_base + 12.0:
                continue
            odx = ow.end[0] - ow.start[0]
            ody = ow.end[1] - ow.start[1]
            olen = math.hypot(odx, ody)
            if olen <= 1.0:
                continue
            if abs((odx / olen) * w_ux + (ody / olen) * w_uy) < 0.98:
                continue
            perp = abs((ow.start[0] - a[0]) * (-w_uy) + (ow.start[1] - a[1]) * w_ux)
            if perp > max(pw.width, ow.width) + 2.0:
                continue
            p0 = (ow.start[0] - a[0]) * w_ux + (ow.start[1] - a[1]) * w_uy
            p1 = (ow.end[0] - a[0]) * w_ux + (ow.end[1] - a[1]) * w_uy
            overlap = min(w_len, max(p0, p1)) - max(0.0, min(p0, p1))
            if overlap >= 0.5 * w_len:
                covered_by_upper = True
                break
        if covered_by_upper:
            continue

        p_peak: Point2D | None = None
        for r_s, r_e in ridge_candidates:
            res = _line_intersect_2d(a, b, r_s, r_e)
            if res is None:
                continue
            ix, iy, t_wall, u_ridge = res
            if 0.05 < t_wall < 0.95 and -0.05 <= u_ridge <= 1.05:
                p_peak = (ix, iy)
                break
        if p_peak is None:
            p_peak = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)

        z_peak = z_base
        for facet in facets:
            fverts = facet.vertices_3d
            for k in range(len(fverts)):
                v0 = fverts[k]
                v1 = fverts[(k + 1) % len(fverts)]
                dist, t_seg = _dist_pt_to_seg_2d(p_peak, (v0[0], v0[1]), (v1[0], v1[1]))
                if dist <= 1.5:
                    z_eval = v0[2] + t_seg * (v1[2] - v0[2])
                    if z_eval > z_peak:
                        z_peak = z_eval
        if z_peak <= z_base + 0.5 and eave_defs:
            z_peak = max(ep.elevation_at(p_peak[0], p_peak[1]) for ep in eave_defs)

        if z_peak > z_base + 2.0:
            gable_infills.append(
                SolvedGableInfill(
                    p_start=a,
                    p_end=b,
                    p_peak=p_peak,
                    z_base=z_base,
                    z_peak=z_peak,
                    thickness=pw.width,
                    level_id=pw.level_id,
                )
            )

    return SolvedRoofGeometry(
        roof_id=roof.identifier,
        level_id=roof.level_id,
        material=roof.material,
        facets=facets,
        gable_infills=gable_infills,
    )


def _l_stair_layout_in(
    total_steps: int,
    steps_before_landing: int,
    tread_depth: float,
    landing_depth: float,
    width: float,
    winder_count: int = 0,
) -> dict[str, float]:
    """Compute flight step counts and run lengths (inches) for an L-shaped stair."""
    winders = max(0, min(winder_count or 0, 5, max(total_steps - 2, 0)))
    flight_total = max(1, total_steps - winders)
    if 0 < steps_before_landing < flight_total:
        steps_before = steps_before_landing
    else:
        steps_before = flight_total // 2
    steps_after = flight_total - steps_before
    if winders > 0:
        run_before = steps_before * tread_depth
        run_after = steps_after * tread_depth
        actual_ld = width
    else:
        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0.0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0.0
        actual_ld = landing_depth
    return {
        "steps_before": float(steps_before),
        "steps_after": float(steps_after),
        "run_before": run_before,
        "run_after": run_after,
        "landing_depth": actual_ld,
        "winder_count": float(winders),
    }


def _winder_tread_polys_local(
    width: float, count: int, turn: str = "left"
) -> list[list[Point2D]]:
    """Return wedge polygons (inches) tiling a ``width x width`` turn square."""
    if count < 1:
        return []

    def _bpt(phi: float) -> Point2D:
        if phi <= math.pi / 4.0 + 1e-12:
            return (width, width * math.tan(phi))
        return (width / math.tan(phi), width)

    polys: list[list[Point2D]] = []
    for i in range(count):
        phi_hi = (math.pi / 2.0) * (1.0 - i / count)
        phi_lo = (math.pi / 2.0) * (1.0 - (i + 1) / count)
        pts: list[Point2D] = [(0.0, 0.0), _bpt(phi_hi)]
        if phi_lo < math.pi / 4.0 < phi_hi:
            pts.append((width, width))
        pts.append(_bpt(phi_lo))
        polys.append(pts)
    if turn == "right":
        polys = [[(u, width - v) for (u, v) in poly] for poly in polys]
    return polys


def _expand_convex_poly_2d(poly: list[Point2D], margin: float) -> list[Point2D]:
    if margin <= 1e-6 or len(poly) < 3:
        return poly
    pts = list(poly)
    if _polygon_signed_area_2d(pts) < 0:
        pts.reverse()
    n = len(pts)
    lines: list[Line2D] = []
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1.0
        nx, ny = dy / d, -dx / d
        lines.append(
            ((x1 + nx * margin, y1 + ny * margin), (x2 + nx * margin, y2 + ny * margin))
        )
    out: list[Point2D] = []
    for i in range(n):
        p1, p2 = lines[i - 1]
        p3, p4 = lines[i]
        res = _line_intersect_2d(p1, p2, p3, p4)
        out.append((res[0], res[1]) if res is not None else p3)
    return out


def compute_stair_footprint_parts(stair: ParsedStair) -> list[list[Point2D]]:
    """Return a single clean, non-self-intersecting footprint polygon (inches) for ``stair``.

    Emitting one unified simple polygon (including ``opening_clearance``) rather than adjacent
    or overlapping sub-rectangles guarantees ``earcutr`` receives disjoint hole contours for
    3D floor and ceiling slab cutouts.
    """
    width = max(12.0, stair.width)
    hw = width / 2.0
    sx, sy = stair.start_point
    ang = stair.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)
    margin = max(0.0, stair.opening_clearance)

    def _xf(pts: list[Point2D]) -> list[Point2D]:
        return [(sx + u * ca - v * sa, sy + u * sa + v * ca) for u, v in pts]

    def _rect(u0: float, v0: float, u1: float, v1: float) -> list[Point2D]:
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]

    stype = stair.stair_type
    if stype == "spiral":
        r = max(2.0, stair.inner_radius) + width + margin
        n = 32
        return [
            [
                (
                    sx + r * math.cos(2.0 * math.pi * i / n),
                    sy + r * math.sin(2.0 * math.pi * i / n),
                )
                for i in range(n)
            ]
        ]

    if stype == "l-shaped":
        lay = _l_stair_layout_in(
            stair.num_steps,
            stair.steps_before_landing,
            stair.tread_depth,
            stair.landing_depth,
            width,
            stair.winder_count,
        )
        rb, ra, ld = lay["run_before"], lay["run_after"], lay["landing_depth"]
        u0 = -margin
        u_end = rb + ld + margin
        u_turn = rb + ld - width - margin
        if ra <= 1e-6 or u_turn <= u0 + 1e-3:
            u_min = min(u0, u_turn) if ra > 1e-6 else u0
            if ra <= 1e-6:
                v0, v1 = -hw - margin, hw + margin
            elif stair.turn_direction == "left":
                v0, v1 = -hw - ra - margin, hw + margin
            else:
                v0, v1 = -hw - margin, hw + ra + margin
            return [_xf(_rect(u_min, v0, u_end, v1))]

        if stair.turn_direction == "left":
            v_pos = hw + margin
            v_mid = -hw - margin
            v_far = -hw - ra - margin
            local_poly = [
                (u0, v_pos),
                (u_end, v_pos),
                (u_end, v_far),
                (u_turn, v_far),
                (u_turn, v_mid),
                (u0, v_mid),
            ]
        else:
            v_neg = -hw - margin
            v_mid = hw + margin
            v_far = hw + ra + margin
            local_poly = [
                (u0, v_neg),
                (u_end, v_neg),
                (u_end, v_far),
                (u_turn, v_far),
                (u_turn, v_mid),
                (u0, v_mid),
            ]
        return [_xf(local_poly)]

    if stype == "u-shaped":
        ld = stair.landing_depth or width
        well = max(0.0, stair.inner_radius if stair.inner_radius != 6.0 else 0.0)
        total = stair.num_steps
        before = (
            stair.steps_before_landing
            if 0 < stair.steps_before_landing < total
            else total // 2
        )
        after = total - before
        rb = (before - 1) * stair.tread_depth if before > 0 else 0.0
        ra = (after - 1) * stair.tread_depth if after > 0 else 0.0
        u_end = rb + ld + margin
        u_f1 = -margin
        u_f2 = rb - ra - margin
        u_well = rb - margin

        # Emit an 8-vertex U-polygon only when the expanded inner well remains open.
        if well > 2.0 * margin + 1e-3 and u_well > max(u_f1, u_f2) + 1e-3:
            if stair.turn_direction == "left":
                local_poly = [
                    (u_f1, hw + margin),
                    (u_end, hw + margin),
                    (u_end, -hw - well - width - margin),
                    (u_f2, -hw - well - width - margin),
                    (u_f2, -hw - well + margin),
                    (u_well, -hw - well + margin),
                    (u_well, -hw - margin),
                    (u_f1, -hw - margin),
                ]
            else:
                local_poly = [
                    (u_f1, -hw - margin),
                    (u_end, -hw - margin),
                    (u_end, hw + well + width + margin),
                    (u_f2, hw + well + width + margin),
                    (u_f2, hw + well - margin),
                    (u_well, hw + well - margin),
                    (u_well, hw + margin),
                    (u_f1, hw + margin),
                ]
            return [_xf(local_poly)]

        if stair.turn_direction == "left":
            v1 = hw + margin
            v2 = -hw - well - width - margin
            v_mid = -hw - 0.5 * well
        else:
            v1 = -hw - margin
            v2 = hw + well + width + margin
            v_mid = hw + 0.5 * well

        if abs(u_f1 - u_f2) <= 1e-3:
            return [_xf(_rect(min(u_f1, u_f2), min(v1, v2), u_end, max(v1, v2)))]
        if u_f2 > u_f1:
            local_poly = [
                (u_f1, v1),
                (u_end, v1),
                (u_end, v2),
                (u_f2, v2),
                (u_f2, v_mid),
                (u_f1, v_mid),
            ]
        else:
            local_poly = [
                (u_f1, v1),
                (u_end, v1),
                (u_end, v2),
                (u_f2, v2),
                (u_f2, v1),
                (u_f1, v_mid),
            ]
        return [_xf(local_poly)]

    run = max(stair.tread_depth, stair.total_run)
    return [_xf(_rect(-margin, -hw - margin, run + margin, hw + margin))]


def _polys_overlap_2d(poly_a: list[Point2D], poly_b: list[Point2D]) -> bool:
    """Fast 2D overlap test (AABB + vertex/centroid containment + edge intersection)."""
    if len(poly_a) < 3 or len(poly_b) < 3:
        return False
    ax0, ax1 = min(p[0] for p in poly_a), max(p[0] for p in poly_a)
    ay0, ay1 = min(p[1] for p in poly_a), max(p[1] for p in poly_a)
    bx0, bx1 = min(p[0] for p in poly_b), max(p[0] for p in poly_b)
    by0, by1 = min(p[1] for p in poly_b), max(p[1] for p in poly_b)
    if ax1 < bx0 - 1e-3 or bx1 < ax0 - 1e-3 or ay1 < by0 - 1e-3 or by1 < ay0 - 1e-3:
        return False
    for pt in poly_a:
        if _pt_in_poly_2d(pt[0], pt[1], poly_b):
            return True
    for pt in poly_b:
        if _pt_in_poly_2d(pt[0], pt[1], poly_a):
            return True
    ca = (sum(p[0] for p in poly_a) / len(poly_a), sum(p[1] for p in poly_a) / len(poly_a))
    cb = (sum(p[0] for p in poly_b) / len(poly_b), sum(p[1] for p in poly_b) / len(poly_b))
    if _pt_in_poly_2d(ca[0], ca[1], poly_b) or _pt_in_poly_2d(cb[0], cb[1], poly_a):
        return True
    for i in range(len(poly_a)):
        a0, a1 = poly_a[i], poly_a[(i + 1) % len(poly_a)]
        for j in range(len(poly_b)):
            b0, b1 = poly_b[j], poly_b[(j + 1) % len(poly_b)]
            res = _line_intersect_2d(a0, a1, b0, b1)
            if res is not None and 0.0 <= res[2] <= 1.0 and 0.0 <= res[3] <= 1.0:
                return True
    return False


def compute_room_hole_cutouts(project: ParsedProject) -> dict[str, list[RoomHoleCutout]]:
    """Compute floor and ceiling cutouts (inches) per room ID from stairs & openings."""
    out: dict[str, list[RoomHoleCutout]] = {}
    rooms_by_level: dict[str, list[ParsedRoom]] = {}
    for room in project.rooms:
        rooms_by_level.setdefault(room.level_id, []).append(room)
    sorted_levels = sorted(project.levels, key=lambda lvl: lvl.elevation)

    for stair in project.stairs:
        parts = compute_stair_footprint_parts(stair)
        src = f"stair:{stair.identifier}"
        if stair.end_level_id:
            for room in rooms_by_level.get(stair.end_level_id, []):
                for part in parts:
                    if _polys_overlap_2d(room.points, part):
                        out.setdefault(room.identifier, []).append(
                            RoomHoleCutout(
                                points=part, cuts_floor=True, cuts_ceiling=False, source_id=src
                            )
                        )
        diff_level = stair.start_level_id != stair.end_level_id
        should_cut_ceil = bool(stair.start_level_id) and (
            diff_level or project.cut_lower_ceiling_under_stairs
        )
        if should_cut_ceil:
            for room in rooms_by_level.get(stair.start_level_id, []):
                for part in parts:
                    if _polys_overlap_2d(room.points, part):
                        out.setdefault(room.identifier, []).append(
                            RoomHoleCutout(
                                points=part, cuts_floor=False, cuts_ceiling=True, source_id=src
                            )
                        )

    for fo in project.floor_openings:
        src = f"opening:{fo.identifier}"
        for room in rooms_by_level.get(fo.level_id, []):
            if _polys_overlap_2d(room.points, fo.points):
                out.setdefault(room.identifier, []).append(
                    RoomHoleCutout(
                        points=list(fo.points),
                        cuts_floor=not fo.ceiling_only,
                        cuts_ceiling=fo.ceiling_only,
                        source_id=src,
                    )
                )
        if not fo.ceiling_only:
            cur_lvl = next((lvl for lvl in sorted_levels if lvl.id == fo.level_id), None)
            if cur_lvl is not None:
                below = [lvl for lvl in sorted_levels if lvl.elevation < cur_lvl.elevation - 1e-3]
                if below:
                    lower_lvl = below[-1]
                    for room in rooms_by_level.get(lower_lvl.id, []):
                        if _polys_overlap_2d(room.points, fo.points):
                            out.setdefault(room.identifier, []).append(
                                RoomHoleCutout(
                                    points=list(fo.points),
                                    cuts_floor=False,
                                    cuts_ceiling=True,
                                    source_id=src,
                                )
                            )
    return out


def compute_hb5_stair_transform(
    stair: ParsedStair, z_start_in: float, cx: float, cy: float
) -> tuple[Point3D, float]:
    """Convert bottom-center stair pose (inches) to HB5 bottom-left ``(loc_m, rot_z_rad)``."""
    sx_m, sy_m = inches_to_blender_xy(stair.start_point[0], stair.start_point[1], cx, cy)
    theta_b = -stair.direction_angle
    rot_z = theta_b - math.pi / 2.0
    half_w_m = (stair.width * INCH_TO_M) / 2.0
    loc_x = sx_m - half_w_m * math.sin(theta_b)
    loc_y = sy_m + half_w_m * math.cos(theta_b)
    loc_z = z_start_in * INCH_TO_M
    return ((loc_x, loc_y, loc_z), rot_z)


def compute_stair_railing_paths_3d(
    stair: ParsedStair, z_start_in: float
) -> list[list[Point3D]]:
    """Return 3D railing base polylines ``[(x_in, y_in, z_in), ...]`` in EstiSketch inches."""
    if not stair.has_left_rail and not stair.has_right_rail:
        return []

    width = max(12.0, stair.width)
    hw = width / 2.0
    total_rise = max(6.0, stair.total_rise)
    z0 = z_start_in
    z1 = z_start_in + total_rise
    sx, sy = stair.start_point
    ang = stair.direction_angle
    ca, sa = math.cos(ang), math.sin(ang)

    def _w(u: float, v: float, z: float) -> Point3D:
        return (sx + u * ca - v * sa, sy + u * sa + v * ca, z)

    left_3d: list[list[Point3D]] = []
    right_3d: list[list[Point3D]] = []
    stype = stair.stair_type

    if stype == "straight":
        run = max(stair.tread_depth, stair.total_run)
        left_3d.append([_w(0.0, -hw, z0), _w(run, -hw, z1)])
        right_3d.append([_w(0.0, hw, z0), _w(run, hw, z1)])

    elif stype == "l-shaped":
        lay = _l_stair_layout_in(
            stair.num_steps,
            stair.steps_before_landing,
            stair.tread_depth,
            stair.landing_depth,
            width,
            stair.winder_count,
        )
        sb = int(lay["steps_before"])
        sa_cnt = int(lay["steps_after"])
        rb = lay["run_before"]
        ra = lay["run_after"]
        ld = lay["landing_depth"]
        wc = int(lay["winder_count"])
        tot_steps = max(1, sb + wc + sa_cnt)
        z_land_s = z0 + total_rise * (sb / tot_steps)
        z_land_e = z0 + total_rise * ((sb + wc) / tot_steps) if wc > 0 else z_land_s

        if stair.turn_direction == "left":
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land_s),
                _w(rb + ld, hw, 0.5 * (z_land_s + z_land_e)),
                _w(rb + ld, -hw, z_land_e),
                _w(rb + ld, -hw - ra, z1),
            ])
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land_s),
                _w(rb, -hw, z_land_e),
                _w(rb, -hw - ra, z1),
            ])
        else:
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land_s),
                _w(rb + ld, -hw, 0.5 * (z_land_s + z_land_e)),
                _w(rb + ld, hw, z_land_e),
                _w(rb + ld, hw + ra, z1),
            ])
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land_s),
                _w(rb, hw, z_land_e),
                _w(rb, hw + ra, z1),
            ])

    elif stype == "u-shaped":
        ld = stair.landing_depth or width
        well = max(0.0, stair.inner_radius if stair.inner_radius != 6.0 else 0.0)
        tot = stair.num_steps
        sb = stair.steps_before_landing if 0 < stair.steps_before_landing < tot else tot // 2
        sa_cnt = tot - sb
        rb = (sb - 1) * stair.tread_depth if sb > 0 else 0.0
        ra = (sa_cnt - 1) * stair.tread_depth if sa_cnt > 0 else 0.0
        z_land = z0 + total_rise * (sb / max(1, tot))
        if stair.turn_direction == "left":
            oy = -width - well - hw
            iy = -hw - well
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land),
                _w(rb + ld, hw, z_land),
                _w(rb + ld, oy, z_land),
                _w(rb, oy, z_land),
                _w(rb - ra, oy, z1),
            ])
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land),
                _w(rb, iy, z_land),
                _w(rb - ra, iy, z1),
            ])
        else:
            oy = width + well + hw
            iy = hw + well
            left_3d.append([
                _w(0.0, -hw, z0),
                _w(rb, -hw, z_land),
                _w(rb + ld, -hw, z_land),
                _w(rb + ld, oy, z_land),
                _w(rb, oy, z_land),
                _w(rb - ra, oy, z1),
            ])
            right_3d.append([
                _w(0.0, hw, z0),
                _w(rb, hw, z_land),
                _w(rb, iy, z_land),
                _w(rb - ra, iy, z1),
            ])

    elif stype == "spiral":
        inner_r = max(2.0, stair.inner_radius)
        outer_r = inner_r + width
        rot_rad = math.radians(stair.rotation_degrees or 270.0)
        dir_mult = -1.0 if stair.turn_direction == "left" else 1.0
        steps = max(12, int((stair.rotation_degrees or 270.0) / 15.0))
        inner_pts: list[Point3D] = []
        outer_pts: list[Point3D] = []
        for i in range(steps + 1):
            frac = i / steps
            theta = ang + frac * rot_rad * dir_mult
            z_cur = z0 + frac * total_rise
            inner_pts.append(
                (sx + inner_r * math.cos(theta), sy + inner_r * math.sin(theta), z_cur)
            )
            outer_pts.append(
                (sx + outer_r * math.cos(theta), sy + outer_r * math.sin(theta), z_cur)
            )
        if stair.turn_direction == "left":
            if inner_r >= 4.0:
                left_3d.append(inner_pts)
            right_3d.append(outer_pts)
        else:
            left_3d.append(outer_pts)
            if inner_r >= 4.0:
                right_3d.append(inner_pts)

    paths: list[list[Point3D]] = []
    if stair.has_left_rail:
        paths.extend(left_3d)
    if stair.has_right_rail:
        paths.extend(right_3d)
    return paths


def compute_hb5_fixture_transform(
    fx: ParsedFixture, level_elev_in: float, cx: float, cy: float
) -> tuple[Point3D, float]:
    """Convert centered fixture pose (inches) to HB5 back-left ``(loc_m, rot_z_rad)``."""
    r = math.radians(fx.rotation)
    ca, sa = math.cos(r), math.sin(r)
    lx, ly = -fx.width / 2.0, -fx.depth / 2.0
    bl_x = fx.x + lx * ca - ly * sa
    bl_y = fx.y + lx * sa + ly * ca
    loc_x, loc_y = inches_to_blender_xy(bl_x, bl_y, cx, cy)
    loc_z = (level_elev_in + fx.elevation) * INCH_TO_M
    return ((loc_x, loc_y, loc_z), -r)


def compute_centered_fixture_transform(
    fx: ParsedFixture, level_elev_in: float, cx: float, cy: float
) -> tuple[Point3D, float]:
    """Convert centered fixture pose (inches) to centered ``(loc_m, rot_z_rad)``."""
    cx_m, cy_m = inches_to_blender_xy(fx.x, fx.y, cx, cy)
    loc_z = (level_elev_in + fx.elevation) * INCH_TO_M
    return ((cx_m, cy_m, loc_z), -math.radians(fx.rotation))
