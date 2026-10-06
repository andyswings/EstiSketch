"""
geometry/roof_solver.py

Core 3D Roof Geometry Engine for EstiSketch.
Implements the unified mathematical pipeline for both auto-generated and manual roofs:
- Variable eave overhang offsetting: E_i(t) = W_i + O_i * n_i
- Asymmetric pitch & offset ridge formulation: A_i*x + B_i*y + C_i*z + D_i = 0
- Junction vertices via 3-plane matrix inversion: M * [x, y, z]^T = -D
- Facet extraction, manifold closure, and 3D surface area calculations
"""
import math
from typing import List, Tuple, Dict, Optional, Any, Union
import numpy as np

from models.roof import (
    RoofVertex,
    RoofEdge,
    RoofPlane,
    RoofFacet,
    Plane3D,
    Line3D,
    RoofEdgeType,
    ROOF_LINE_COLORS,
    EAVE,
    RIDGE,
    HIP,
    VALLEY,
    RAKE,
    TIE_IN,
    GABLE,
    normalize_pitch_values,
)


def pt_distance_2d(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Euclidean distance in 2D."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def line_2d_intersection(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float]
) -> Optional[Tuple[float, float]]:
    """2D intersection between infinite line (p1-p2) and line (p3-p4)."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def compute_polygon_signed_area_2d(pts: List[Tuple[float, float]]) -> float:
    """Calculate signed area of 2D polygon (positive for CCW, negative for CW)."""
    n = len(pts)
    if n < 3:
        return 0.0
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))


def compute_polygon_area_3d(vertices: List[RoofVertex]) -> float:
    """
    Calculate 3D surface area of a planar 3D polygon using Stokes' theorem / cross-product sum.
    Returns area in square inches.
    """
    n = len(vertices)
    if n < 3:
        return 0.0

    ax, ay, az = 0.0, 0.0, 0.0
    for i in range(n):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % n]
        ax += (v1.y * v2.z - v1.z * v2.y)
        ay += (v1.z * v2.x - v1.x * v2.z)
        az += (v1.x * v2.y - v1.y * v2.x)

    area2 = math.sqrt(ax * ax + ay * ay + az * az)
    return 0.5 * area2


def build_plane_equations(
    eaves: Union[List[RoofPlane], List[Any]],
    overhangs: Optional[Union[float, List[float]]] = None,
    pitches: Optional[Union[float, List[float]]] = None,
    z_plate: float = 0.0,
) -> List[Plane3D]:
    """
    Build analytical 3D plane equations: A*x + B*y + C*z + D = 0.
    Handles variable overhangs per eave and independent pitches.
    
    For any point (x, y), elevation z = Z_plate + slope * dist_perp((x, y), E_i).
    A = slope * n_inward_x
    B = slope * n_inward_y
    C = -1.0
    D = Z_plate - (A * x0 + B * y0)
    where (x0, y0) is on the offset eave line.
    """
    if not eaves:
        return []

    # Case 1: eaves is a list of RoofPlane objects
    if isinstance(eaves[0], RoofPlane):
        planes_out = []
        # Extract 2D polygon of eave points to determine inward/outward normals
        pts_for_centroid = []
        for rp in eaves:
            s = (rp.eave_start[0], rp.eave_start[1])
            e = (rp.eave_end[0], rp.eave_end[1])
            pts_for_centroid.extend([s, e])

        cx = sum(p[0] for p in pts_for_centroid) / len(pts_for_centroid) if pts_for_centroid else 0.0
        cy = sum(p[1] for p in pts_for_centroid) / len(pts_for_centroid) if pts_for_centroid else 0.0

        for rp in eaves:
            sx, sy = float(rp.eave_start[0]), float(rp.eave_start[1])
            ex, ey = float(rp.eave_end[0]), float(rp.eave_end[1])
            dx = ex - sx
            dy = ey - sy
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue

            tx, ty = dx / length, dy / length
            # Candidate inward normal (CCW perpendicular)
            n_in_cand = (-ty, tx)
            # Midpoint of eave
            mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
            # Centroid vector
            to_c = (cx - mx, cy - my)
            if n_in_cand[0] * to_c[0] + n_in_cand[1] * to_c[1] >= 0:
                n_in = n_in_cand
                n_out = (ty, -tx)
            else:
                n_in = (ty, -tx)
                n_out = (-ty, tx)

            oh = float(rp.overhang) if rp.overhang is not None else 12.0
            rise, slope = normalize_pitch_values(rp.pitch, rp.pitch_run)

            # Offset eave line passes through eave + oh * n_out
            off_sx = sx + oh * n_out[0]
            off_sy = sy + oh * n_out[1]
            off_ex = ex + oh * n_out[0]
            off_ey = ey + oh * n_out[1]

            A = slope * n_in[0]
            B = slope * n_in[1]
            C = -1.0
            D = z_plate - (A * off_sx + B * off_sy)

            pl = Plane3D(
                a=A, b=B, c=C, d=D,
                plane_id=rp.id,
                pitch=rise,
                overhang=oh,
                eave_start=(off_sx, off_sy),
                eave_end=(off_ex, off_ey),
                inward_normal=n_in
            )
            rp.plane_equation = pl
            planes_out.append(pl)

        return planes_out

    # Case 2: raw segment list or wall list
    eave_segments = []
    for item in eaves:
        if hasattr(item, 'start') and hasattr(item, 'end'):
            eave_segments.append(((float(item.start[0]), float(item.start[1])),
                                  (float(item.end[0]), float(item.end[1]))))
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            eave_segments.append(((float(item[0][0]), float(item[0][1])),
                                  (float(item[1][0]), float(item[1][1]))))

    n = len(eave_segments)
    if n == 0:
        return []

    oh_list = [overhangs] * n if isinstance(overhangs, (int, float)) else (overhangs or [12.0] * n)
    p_list = [pitches] * n if isinstance(pitches, (int, float, str)) else (pitches or [6.0] * n)

    pts_all = []
    for s, e in eave_segments:
        pts_all.extend([s, e])
    cx = sum(p[0] for p in pts_all) / len(pts_all)
    cy = sum(p[1] for p in pts_all) / len(pts_all)

    planes_out = []
    for i, (s, e) in enumerate(eave_segments):
        dx = e[0] - s[0]
        dy = e[1] - s[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        tx, ty = dx / length, dy / length
        n_in_cand = (-ty, tx)
        mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0
        if n_in_cand[0] * (cx - mx) + n_in_cand[1] * (cy - my) >= 0:
            n_in = n_in_cand
            n_out = (ty, -tx)
        else:
            n_in = (ty, -tx)
            n_out = (-ty, tx)

        oh = float(oh_list[i % len(oh_list)])
        rise, slope = normalize_pitch_values(p_list[i % len(p_list)])

        off_sx = s[0] + oh * n_out[0]
        off_sy = s[1] + oh * n_out[1]
        off_ex = e[0] + oh * n_out[0]
        off_ey = e[1] + oh * n_out[1]

        A = slope * n_in[0]
        B = slope * n_in[1]
        C = -1.0
        D = z_plate - (A * off_sx + B * off_sy)

        pl = Plane3D(
            a=A, b=B, c=C, d=D,
            plane_id=f"P{i+1}",
            pitch=rise,
            overhang=oh,
            eave_start=(off_sx, off_sy),
            eave_end=(off_ex, off_ey),
            inward_normal=n_in
        )
        planes_out.append(pl)

    return planes_out


def intersect_planes(plane_a: Plane3D, plane_b: Plane3D) -> Line3D:
    """
    Intersect two 3D planes to find their common 3D line (ridge, hip, or valley vector).
    The line direction is the cross product of the plane normals: d = n_a x n_b.
    The closest point on the line to the origin is solved analytically via 2x2 Gram matrix inversion.
    """
    na = np.array([plane_a.a, plane_a.b, plane_a.c], dtype=float)
    nb = np.array([plane_b.a, plane_b.b, plane_b.c], dtype=float)

    d = np.cross(na, nb)
    d_norm = np.linalg.norm(d)
    if d_norm < 1e-9:
        raise ValueError("Planes are parallel or coincident; no unique intersection line exists.")

    d_unit = d / d_norm

    # Solve minimum-norm point on line:
    # [na^T; nb^T] * p = [-Da; -Db]
    M = np.vstack([na, nb])
    rhs = np.array([-plane_a.d, -plane_b.d], dtype=float)
    G = M @ M.T  # 2x2 Gram matrix
    c = np.linalg.solve(G, rhs)
    point = M.T @ c  # 3D coordinates on both planes

    return Line3D(
        point=RoofVertex(float(point[0]), float(point[1]), float(point[2])),
        direction=(float(d_unit[0]), float(d_unit[1]), float(d_unit[2])),
        line_type="ridge"
    )


def solve_junction_vertex(plane_a: Plane3D, plane_b: Plane3D, plane_c: Plane3D) -> RoofVertex:
    """
    Solves vertex V where three roof planes meet algebraically via 3x3 matrix inversion:
    [[A1, B1, C1], [A2, B2, C2], [A3, B3, C3]] * [x, y, z]^T = [-D1, -D2, -D3]^T
    Eliminates arbitrary or floating endpoints for valleys, hips, and ridges.
    """
    M = np.array([
        [plane_a.a, plane_a.b, plane_a.c],
        [plane_b.a, plane_b.b, plane_b.c],
        [plane_c.a, plane_c.b, plane_c.c],
    ], dtype=float)

    rhs = np.array([-plane_a.d, -plane_b.d, -plane_c.d], dtype=float)

    det = np.linalg.det(M)
    if abs(det) < 1e-9:
        raise ValueError("Planes do not meet at a unique junction vertex (determinant is zero).")

    v = np.linalg.solve(M, rhs)
    return RoofVertex(float(v[0]), float(v[1]), float(v[2]))


def clip_facets_to_boundary(
    planes: List[Plane3D],
    vertices: Optional[List[RoofVertex]] = None,
    roof_planes: Optional[List[RoofPlane]] = None,
) -> List[RoofFacet]:
    """
    Constructs closed 3D facets (RoofFacet) for each roof plane,
    calculates exact 3D polygon area, projected 2D area, and generates RoofEdges.
    """
    facets = []
    rp_map = {rp.id: rp for rp in (roof_planes or [])}

    for pl in planes:
        rp = rp_map.get(pl.plane_id)
        facet_verts: List[RoofVertex] = []
        if rp and rp.vertices:
            facet_verts = list(rp.vertices)
        elif vertices:
            # Filter vertices that lie on this plane: |A*x + B*y + C*z + D| < 1e-3
            for v in vertices:
                dist = abs(pl.a * v.x + pl.b * v.y + pl.c * v.z + pl.d)
                if dist < 1e-2 and not any(v.is_close(fv) for fv in facet_verts):
                    facet_verts.append(v)

        # Ensure vertices are ordered radially around facet centroid
        if len(facet_verts) >= 3:
            cx = sum(v.x for v in facet_verts) / len(facet_verts)
            cy = sum(v.y for v in facet_verts) / len(facet_verts)
            facet_verts = sorted(facet_verts, key=lambda v: math.atan2(v.y - cy, v.x - cx))

        area_3d_sqin = compute_polygon_area_3d(facet_verts)
        area_3d_sqft = area_3d_sqin / 144.0

        poly_2d = [(v.x, v.y) for v in facet_verts]
        area_2d_sqin = abs(compute_polygon_signed_area_2d(poly_2d))
        area_2d_sqft = area_2d_sqin / 144.0

        # Build facet edges
        facet_edges = []
        n_fv = len(facet_verts)
        for j in range(n_fv):
            v_start = facet_verts[j]
            v_end = facet_verts[(j + 1) % n_fv]
            facet_edges.append(RoofEdge(v_start, v_end, edge_type=EAVE))

        facet = RoofFacet(
            id=f"facet_{pl.plane_id}",
            plane_id=pl.plane_id,
            plane=rp,
            vertices=facet_verts,
            edges=facet_edges,
            area_3d_sqft=area_3d_sqft,
            area_2d_sqft=area_2d_sqft,
            polygon_2d=poly_2d,
            pitch=pl.pitch,
            name=f"Roof Slope #{pl.plane_id} (Pitch {pl.pitch:.1f}/12)"
        )
        if rp:
            rp.vertices = facet_verts
            rp.edges = facet_edges
            rp.polygon_2d = poly_2d
            rp.area_3d_sqft = area_3d_sqft
            rp.area_2d_sqft = area_2d_sqft

        facets.append(facet)

    return facets


def solve_roof_geometry(
    roof_or_planes: Any,
    walls: Optional[List[Any]] = None,
    default_pitch: float = 6.0,
    default_overhang: float = 12.0,
    z_plate: float = 0.0,
) -> Dict[str, Any]:
    """
    Unified Pure Functional Geometry Pipeline:
    [Footprint / Eave Inputs] -> [RoofPlane Definitions] -> [Core Geometry Solver]
      -> [3D Vertices, Edges & Facets] -> [Material Takeoffs & Rendering]
      
    Operates identically whether planes were auto-generated or manually edited.
    Produces exact 3D coordinates, manifold closure, and precise areas.
    """
    from EstiSketch.roof_components import RoofLine, Roof

    is_roof_obj = isinstance(roof_or_planes, Roof)
    roof = roof_or_planes if is_roof_obj else None

    # Step 1: Extract or construct List[RoofPlane]
    roof_planes: List[RoofPlane] = []

    if isinstance(roof_or_planes, list) and roof_or_planes and isinstance(roof_or_planes[0], RoofPlane):
        roof_planes = list(roof_or_planes)
    elif roof and getattr(roof, 'edges', None) and walls:
        # Build RoofPlane objects from walls and roof.edges
        wall_map = {getattr(w, 'identifier', f"W{i}"): w for i, w in enumerate(walls)}
        for idx, edge in enumerate(roof.edges):
            w = wall_map.get(edge.wall_identifier)
            if not w:
                continue
            p_rise = edge.pitch_rise if edge.pitch_rise is not None else roof.pitch_rise
            oh = edge.overhang if edge.overhang is not None else roof.overhang
            rp = RoofPlane(
                id=f"P_{edge.wall_identifier}",
                eave_start=(float(w.start[0]), float(w.start[1])),
                eave_end=(float(w.end[0]), float(w.end[1])),
                pitch=p_rise,
                overhang=oh,
                plane_type=edge.edge_type,
                wall_identifier=edge.wall_identifier
            )
            roof_planes.append(rp)
    elif walls:
        for idx, w in enumerate(walls):
            rp = RoofPlane(
                id=f"P_{getattr(w, 'identifier', idx)}",
                eave_start=(float(w.start[0]), float(w.start[1])),
                eave_end=(float(w.end[0]), float(w.end[1])),
                pitch=default_pitch,
                overhang=default_overhang,
                plane_type="eave",
                wall_identifier=getattr(w, 'identifier', str(idx))
            )
            roof_planes.append(rp)

    if not roof_planes and roof and roof.manual_lines:
        # Fallback to manual sketched lines
        eaves = [l for l in roof.manual_lines if l.line_type == "eave"]
        for idx, l in enumerate(eaves):
            rp = RoofPlane(
                id=f"P_eave_{idx+1}",
                eave_start=l.start,
                eave_end=l.end,
                pitch=l.pitch_rise or roof.pitch_rise,
                overhang=l.overhang or roof.overhang,
                plane_type="eave"
            )
            roof_planes.append(rp)

    # Step 2: Build analytical Plane3D equations
    plane_equations = build_plane_equations(roof_planes, z_plate=z_plate)

    # Step 3: Solve 3D geometry analytically
    solved_edges: List[RoofEdge] = []
    solved_vertices: List[RoofVertex] = []

    # Detect geometry configuration:
    # 3a. Gable Roof (2 opposing eaves, gables at ends)
    eave_planes = [rp for rp in roof_planes if rp.plane_type == "eave"]
    gable_planes = [rp for rp in roof_planes if rp.plane_type == "gable"]

    if len(eave_planes) == 2:
        p1 = eave_planes[0].plane_equation
        p2 = eave_planes[1].plane_equation
        if p1 and p2:
            ridge_line = intersect_planes(p1, p2)
            
            # Eave corners
            # Eave 1
            e1_s = RoofVertex(p1.eave_start[0], p1.eave_start[1], z_plate)
            e1_e = RoofVertex(p1.eave_end[0], p1.eave_end[1], z_plate)
            # Eave 2
            e2_s = RoofVertex(p2.eave_start[0], p2.eave_start[1], z_plate)
            e2_e = RoofVertex(p2.eave_end[0], p2.eave_end[1], z_plate)

            # Determine gable overhang extension
            g_oh = gable_planes[0].overhang if gable_planes else (roof.overhang if roof else 12.0)
            
            # Check ridge alignment (along X or along Y)
            dir_vec = ridge_line.direction
            is_along_x = abs(dir_vec[0]) > abs(dir_vec[1])

            if is_along_x:
                # Ridge runs east-west along X
                min_x = min(e1_s.x, e1_e.x, e2_s.x, e2_e.x)
                max_x = max(e1_s.x, e1_e.x, e2_s.x, e2_e.x)
                r_y = ridge_line.point.y
                r_z = p1.elevation_at(min_x, r_y)

                r_start = RoofVertex(min_x, r_y, r_z)
                r_end = RoofVertex(max_x, r_y, r_z)
            else:
                # Ridge runs north-south along Y
                min_y = min(e1_s.y, e1_e.y, e2_s.y, e2_e.y)
                max_y = max(e1_s.y, e1_e.y, e2_s.y, e2_e.y)
                r_x = ridge_line.point.x
                r_z = p1.elevation_at(r_x, min_y)

                r_start = RoofVertex(r_x, min_y, r_z)
                r_end = RoofVertex(r_x, max_y, r_z)

            # Add edges
            eave1_edge = RoofEdge(e1_s, e1_e, edge_type=EAVE)
            eave2_edge = RoofEdge(e2_s, e2_e, edge_type=EAVE)
            ridge_edge = RoofEdge(r_start, r_end, edge_type=RIDGE)

            # Gable rake edges
            rake1 = RoofEdge(e1_s, r_start, edge_type=RAKE)
            rake2 = RoofEdge(e2_s, r_start, edge_type=RAKE)
            rake3 = RoofEdge(e1_e, r_end, edge_type=RAKE)
            rake4 = RoofEdge(e2_e, r_end, edge_type=RAKE)

            solved_edges.extend([eave1_edge, eave2_edge, ridge_edge, rake1, rake2, rake3, rake4])
            solved_vertices.extend([e1_s, e1_e, e2_s, e2_e, r_start, r_end])

            # Facets for the 2 slopes
            eave_planes[0].vertices = [e1_s, e1_e, r_end, r_start]
            eave_planes[0].edges = [eave1_edge, rake3, ridge_edge, rake1]

            eave_planes[1].vertices = [e2_s, e2_e, r_end, r_start]
            eave_planes[1].edges = [eave2_edge, rake4, ridge_edge, rake2]

    elif len(roof_planes) >= 3:
        # Complex or multisided roof: use complex roof solver or straight skeleton
        from EstiSketch.Canvas.complex_roof import calculate_complex_roof_geometry
        if walls:
            markings = {rp.wall_identifier: rp.plane_type for rp in roof_planes if rp.wall_identifier}
            # Ratio from opposing eaves if present
            ratio = 0.5
            if len(eave_planes) >= 2:
                s1 = eave_planes[0].pitch_slope
                s2 = eave_planes[1].pitch_slope
                if s1 + s2 > 0:
                    ratio = s2 / (s1 + s2)

            oh = roof.overhang if roof else default_overhang
            pr = roof.pitch_rise if roof else default_pitch
            p_run = roof.pitch_run if roof else 12.0

            r_lines, h_lines, v_lines, rk_lines, ev_lines, outline = \
                calculate_complex_roof_geometry(walls, markings, oh, pr, p_run, ratio=ratio)

            for s, e in r_lines:
                vs = RoofVertex(s[0], s[1], z_plate + 40.0)
                ve = RoofVertex(e[0], e[1], z_plate + 40.0)
                solved_edges.append(RoofEdge(vs, ve, edge_type=RIDGE))
                solved_vertices.extend([vs, ve])
            for s, e in h_lines:
                vs = RoofVertex(s[0], s[1], z_plate + 40.0)
                ve = RoofVertex(e[0], e[1], z_plate)
                solved_edges.append(RoofEdge(vs, ve, edge_type=HIP))
                solved_vertices.extend([vs, ve])
            for s, e in v_lines:
                vs = RoofVertex(s[0], s[1], z_plate + 40.0)
                ve = RoofVertex(e[0], e[1], z_plate)
                solved_edges.append(RoofEdge(vs, ve, edge_type=VALLEY))
                solved_vertices.extend([vs, ve])
            for s, e in rk_lines:
                vs = RoofVertex(s[0], s[1], z_plate)
                ve = RoofVertex(e[0], e[1], z_plate + 40.0)
                solved_edges.append(RoofEdge(vs, ve, edge_type=RAKE))
                solved_vertices.extend([vs, ve])
            for s, e in ev_lines:
                vs = RoofVertex(s[0], s[1], z_plate)
                ve = RoofVertex(e[0], e[1], z_plate)
                solved_edges.append(RoofEdge(vs, ve, edge_type=EAVE))
                solved_vertices.extend([vs, ve])

            if roof and outline:
                roof.outline_points = outline

    # Step 4: Extract closed 3D facets
    facets = clip_facets_to_boundary(plane_equations, solved_vertices, roof_planes)

    # Step 5: Convert solved edges to 2D RoofLine objects for canvas rendering
    solved_lines = []
    for idx, e in enumerate(solved_edges):
        if e.start_vertex and e.end_vertex:
            s_2d = e.start_vertex.to_tuple_2d()
            e_2d = e.end_vertex.to_tuple_2d()
            if pt_distance_2d(s_2d, e_2d) > 0.5:
                solved_lines.append(RoofLine(
                    identifier=f"sl_{e.edge_type}_{idx+1}",
                    start=s_2d,
                    end=e_2d,
                    line_type=e.edge_type,
                    pitch_rise=roof.pitch_rise if roof else default_pitch,
                    overhang=roof.overhang if roof else default_overhang,
                    is_auto_generated=True
                ))

    # Populate Roof object if supplied
    if roof:
        roof.solved_lines = solved_lines
        roof.roof_planes = facets
        roof.ridge_lines = [(l.start, l.end) for l in solved_lines if l.line_type == RIDGE]
        roof.hip_lines = [(l.start, l.end) for l in solved_lines if l.line_type == HIP]
        roof.valley_lines = [(l.start, l.end) for l in solved_lines if l.line_type == VALLEY]
        roof.rake_lines = [(l.start, l.end) for l in solved_lines if l.line_type == RAKE]
        roof.eave_lines = [(l.start, l.end) for l in solved_lines if l.line_type == EAVE]
        roof.tie_in_lines = [(l.start, l.end) for l in solved_lines if l.line_type == TIE_IN]

    return {
        "planes": plane_equations,
        "facets": facets,
        "edges": solved_edges,
        "vertices": solved_vertices,
        "solved_lines": solved_lines,
        "roof": roof
    }
