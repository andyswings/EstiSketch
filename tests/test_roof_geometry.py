"""
tests/test_roof_geometry.py

Phase 4: Headless Invariant Test Suite for the 3D Roof Geometry Engine.
Verifies:
- test_symmetric_gable(): Asserts ridge is centered.
- test_asymmetric_pitch_offset(): Sets 12/12 and 6/12, asserts ridge X matches W / 3.
- test_variable_overhang(): Sets 12" and 24" eaves, asserts eave perimeter offsets accurately.
- test_l_shaped_valley_coincidence(): Asserts valley endpoint strictly matches ridge vertex (||V_valley - V_ridge|| < 10^-4).
- test_manual_override_stability(): Asserts editing a single plane pitch updates only affected vertices while maintaining manifold closure.
"""
import math
import pytest
import numpy as np

from models.roof import (
    RoofPlane,
    RoofEdge,
    RoofVertex,
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
    normalize_pitch_values,
)
from geometry.roof_solver import (
    build_plane_equations,
    intersect_planes,
    solve_junction_vertex,
    clip_facets_to_boundary,
    solve_roof_geometry,
    compute_polygon_area_3d,
)
from EstiSketch.roof_components import RoofLine, Roof
from EstiSketch.Canvas.roof_solver import solve_and_clean_roof


class DummyWall:
    def __init__(self, wall_id, start, end, width=5.5, height=96.0):
        self.identifier = wall_id
        self.start = start
        self.end = end
        self.width = width
        self.height = height


def test_symmetric_gable():
    """
    Asserts ridge is centered for equal pitches across span W.
    Equal pitches (6/12 and 6/12): x = 0.50 * W (centered).
    """
    span_w = 240.0
    length_l = 360.0

    # Two opposing eaves across span W along X
    # Eave 1 at X = 0, Eave 2 at X = 240
    p1 = RoofPlane(
        id="P1",
        eave_start=(0.0, 0.0),
        eave_end=(0.0, length_l),
        pitch=6.0,
        overhang=0.0,
        plane_type="eave"
    )
    p2 = RoofPlane(
        id="P2",
        eave_start=(span_w, length_l),
        eave_end=(span_w, 0.0),
        pitch=6.0,
        overhang=0.0,
        plane_type="eave"
    )

    planes = build_plane_equations([p1, p2])
    assert len(planes) == 2

    # Intersect the two opposing planes
    ridge_line = intersect_planes(planes[0], planes[1])

    # For span along X from 0 to W, ridge coordinate X should be centered at W / 2
    ridge_x = ridge_line.point.x
    expected_x = span_w / 2.0
    assert abs(ridge_x - expected_x) < 1e-4

    # Direction of ridge should be parallel to Y axis (along building length)
    assert abs(ridge_line.direction[0]) < 1e-4
    assert abs(abs(ridge_line.direction[1]) - 1.0) < 1e-4


def test_asymmetric_pitch_offset():
    """
    Sets 12/12 and 6/12, asserts ridge X matches W / 3.
    x_ridge = s2 / (s1 + s2) * W = 0.5 / (1.0 + 0.5) * W = 1/3 * W.
    """
    span_w = 360.0
    length_l = 480.0

    # Plane 1 has 12/12 pitch (slope 1.0), Plane 2 has 6/12 pitch (slope 0.5)
    p1 = RoofPlane(
        id="P1",
        eave_start=(0.0, 0.0),
        eave_end=(0.0, length_l),
        pitch=12.0,  # 12/12
        overhang=0.0,
        plane_type="eave"
    )
    p2 = RoofPlane(
        id="P2",
        eave_start=(span_w, length_l),
        eave_end=(span_w, 0.0),
        pitch=6.0,   # 6/12
        overhang=0.0,
        plane_type="eave"
    )

    planes = build_plane_equations([p1, p2])
    ridge_line = intersect_planes(planes[0], planes[1])

    ridge_x = ridge_line.point.x
    expected_x = span_w / 3.0  # 360 / 3 = 120.0

    assert abs(ridge_x - expected_x) < 1e-4

    # Also test with ratio input: pitch=12/12 (1.0) and pitch=6/12 (0.5)
    p1_ratio = RoofPlane(
        id="P1_r",
        eave_start=(0.0, 0.0),
        eave_end=(0.0, length_l),
        pitch=12 / 12,  # 1.0
        overhang=0.0,
        plane_type="eave"
    )
    p2_ratio = RoofPlane(
        id="P2_r",
        eave_start=(span_w, length_l),
        eave_end=(span_w, 0.0),
        pitch=6 / 12,   # 0.5
        overhang=0.0,
        plane_type="eave"
    )

    planes_ratio = build_plane_equations([p1_ratio, p2_ratio])
    ridge_ratio = intersect_planes(planes_ratio[0], planes_ratio[1])
    assert abs(ridge_ratio.point.x - expected_x) < 1e-4


def test_variable_overhang():
    """
    Sets 12" and 24" eaves, asserts eave perimeter offsets accurately:
    E_i(t) = W_i + O_i * n_i
    Corner intersection matches exact 2D line intersection.
    """
    # A corner formed by Wall 1: (0, 0) -> (240, 0) with overhang 12"
    # and Wall 2: (0, 240) -> (0, 0) with overhang 24"
    # Wall 1 has outward normal (0, -1) => offset line is y = -12
    # Wall 2 has outward normal (-1, 0) => offset line is x = -24
    # Corner intersection is (-24, -12)
    p1 = RoofPlane(
        id="P1",
        eave_start=(0.0, 0.0),
        eave_end=(240.0, 0.0),
        pitch=6.0,
        overhang=12.0,
        plane_type="eave"
    )
    p2 = RoofPlane(
        id="P2",
        eave_start=(0.0, 240.0),
        eave_end=(0.0, 0.0),
        pitch=6.0,
        overhang=24.0,
        plane_type="eave"
    )

    planes = build_plane_equations([p1, p2])

    # Check offset lines:
    # Plane 1 offset line passes through y = -12.0
    pl1 = planes[0]
    assert abs(pl1.eave_start[1] - (-12.0)) < 1e-4
    assert abs(pl1.eave_end[1] - (-12.0)) < 1e-4

    # Plane 2 offset line passes through x = -24.0
    pl2 = planes[1]
    assert abs(pl2.eave_start[0] - (-24.0)) < 1e-4
    assert abs(pl2.eave_end[0] - (-24.0)) < 1e-4

    # 2D corner intersection
    from geometry.roof_solver import line_2d_intersection
    corner = line_2d_intersection(
        pl1.eave_start, pl1.eave_end,
        pl2.eave_start, pl2.eave_end
    )
    assert corner is not None
    assert abs(corner[0] - (-24.0)) < 1e-4
    assert abs(corner[1] - (-12.0)) < 1e-4


def test_l_shaped_valley_coincidence():
    """
    Asserts valley endpoint strictly matches ridge vertex:
    ||V_valley - V_ridge|| < 10^-4.
    Eliminates floating endpoints between valleys and ridges.
    """
    # L-shaped building:
    # Wing 1 (horizontal): X from 0 to 400, Y from 0 to 200 (centerline Y=100)
    # Wing 2 (vertical): X from 0 to 200, Y from 0 to 500 (centerline X=100)
    # Intersection of ridge 1 (Y=100) and ridge 2 (X=100) is at (100, 100).
    # Valley from inside corner (200, 200) runs directly into (100, 100).
    w1 = DummyWall("W1", (0.0, 0.0), (400.0, 0.0))
    w2 = DummyWall("W2", (400.0, 0.0), (400.0, 200.0))
    w3 = DummyWall("W3", (400.0, 200.0), (200.0, 200.0))
    w4 = DummyWall("W4", (200.0, 200.0), (200.0, 500.0))
    w5 = DummyWall("W5", (200.0, 500.0), (0.0, 500.0))
    w6 = DummyWall("W6", (0.0, 500.0), (0.0, 0.0))
    walls = [w1, w2, w3, w4, w5, w6]

    edges = [
        RoofEdge("W1", "eave"),
        RoofEdge("W2", "gable"),
        RoofEdge("W3", "eave"),
        RoofEdge("W4", "eave"),
        RoofEdge("W5", "gable"),
        RoofEdge("W6", "eave"),
    ]
    roof = Roof(identifier="ROOF-L", edges=edges, pitch_rise=6.0, overhang=12.0)

    solve_and_clean_roof(roof, walls)

    # Locate ridge lines and valley line
    ridges = [l for l in roof.solved_lines if l.line_type == "ridge"]
    valleys = [l for l in roof.solved_lines if l.line_type == "valley"]

    assert len(ridges) >= 2
    assert len(valleys) == 1

    # Both ridges meet at (100, 100)
    v_ridge = ridges[0].start
    assert abs(v_ridge[0] - 100.0) < 1e-4
    assert abs(v_ridge[1] - 100.0) < 1e-4

    # Valley starts at the exact ridge vertex
    v_valley = valleys[0].start

    # Strictly check ||V_valley - V_ridge|| < 10^-4
    dist = math.hypot(v_valley[0] - v_ridge[0], v_valley[1] - v_ridge[1])
    assert dist < 1e-4


def test_manual_override_stability():
    """
    Asserts editing a single plane pitch updates only affected vertices
    while maintaining manifold closure (shared common edges with no gaps).
    """
    span_w = 240.0
    length_l = 360.0

    # Initial state: symmetric gable with 6/12 on both sides
    p1 = RoofPlane(
        id="P1",
        eave_start=(0.0, 0.0),
        eave_end=(span_w, 0.0),
        pitch=6.0,
        overhang=12.0,
        plane_type="eave"
    )
    p2 = RoofPlane(
        id="P2",
        eave_start=(span_w, length_l),
        eave_end=(0.0, length_l),
        pitch=6.0,
        overhang=12.0,
        plane_type="eave"
    )

    res_init = solve_roof_geometry([p1, p2])
    facets_init = res_init["facets"]
    assert len(facets_init) == 2

    # Record initial vertices
    p2_eave_verts_init = [(v.x, v.y, v.z) for v in facets_init[1].vertices if abs(v.y - (length_l + 12.0)) < 1.0]

    # Now edit Plane 1 pitch from 6/12 to 12/12
    p1.pitch = 12.0

    res_updated = solve_roof_geometry([p1, p2])
    facets_updated = res_updated["facets"]

    # Verify Plane 2 eave vertices did NOT change
    p2_eave_verts_updated = [(v.x, v.y, v.z) for v in facets_updated[1].vertices if abs(v.y - (length_l + 12.0)) < 1.0]
    for v_old, v_new in zip(p2_eave_verts_init, p2_eave_verts_updated):
        assert abs(v_old[0] - v_new[0]) < 1e-4
        assert abs(v_old[1] - v_new[1]) < 1e-4
        assert abs(v_old[2] - v_new[2]) < 1e-4

    # Verify manifold closure: the ridge vertices on Facet 1 and Facet 2 are IDENTICAL
    facet1_ridge = [v for v in facets_updated[0].vertices if abs(v.y - (length_l + 12.0)) > 1.0 and abs(v.y - (-12.0)) > 1.0]
    facet2_ridge = [v for v in facets_updated[1].vertices if abs(v.y - (length_l + 12.0)) > 1.0 and abs(v.y - (-12.0)) > 1.0]

    assert len(facet1_ridge) > 0
    assert len(facet2_ridge) > 0
    for v1 in facet1_ridge:
        # Must find identical vertex in facet 2 (manifold closure)
        matched = any(v1.is_close(v2, tol=1e-4) for v2 in facet2_ridge)
        assert matched


def test_solve_junction_vertex_matrix_inversion():
    """
    Tests algebraic 3-plane matrix inversion:
    M * [x, y, z]^T = -D
    """
    # 3 planes meeting at (100, 200, 50):
    # Plane 1: z = 0.5 * x  => 0.5*x - z = 0  => (0.5, 0, -1, 0)
    # Plane 2: z = 0.25 * y => 0.25*y - z = 0 => (0, 0.25, -1, 0)
    # Plane 3: x + y + z = 350 => (1, 1, 1, -350)
    pl1 = Plane3D(a=0.5, b=0.0, c=-1.0, d=0.0)
    pl2 = Plane3D(a=0.0, b=0.25, c=-1.0, d=0.0)
    pl3 = Plane3D(a=1.0, b=1.0, c=1.0, d=-350.0)

    v = solve_junction_vertex(pl1, pl2, pl3)
    assert abs(v.x - 100.0) < 1e-4
    assert abs(v.y - 200.0) < 1e-4
    assert abs(v.z - 50.0) < 1e-4


def test_roof_edge_color_coding_preservation():
    """
    Verifies visual color-coding remains intact in the UI:
    Eaves (emerald green), Ridges (crimson red), Hips (amber orange), Valleys (cyan blue).
    """
    assert ROOF_LINE_COLORS["ridge"] == "#E53935"
    assert ROOF_LINE_COLORS["hip"] == "#FB8C00"
    assert ROOF_LINE_COLORS["valley"] == "#00ACC1"
    assert ROOF_LINE_COLORS["rake"] == "#8E24AA"
    assert ROOF_LINE_COLORS["eave"] == "#43A047"
    assert ROOF_LINE_COLORS["tie_in"] == "#D81B60"

    v1 = RoofVertex(0.0, 0.0, 0.0)
    v2 = RoofVertex(10.0, 0.0, 0.0)

    edge_ridge = RoofEdge(v1, v2, edge_type=RIDGE)
    assert edge_ridge.color == "#E53935"

    edge_hip = RoofEdge(v1, v2, edge_type=HIP)
    assert edge_hip.color == "#FB8C00"

    edge_valley = RoofEdge(v1, v2, edge_type=VALLEY)
    assert edge_valley.color == "#00ACC1"

    edge_eave = RoofEdge(v1, v2, edge_type=EAVE)
    assert edge_eave.color == "#43A047"
