import pytest
import math
from EstiSketch.Canvas.complex_roof import (
    calculate_complex_roof_geometry,
    calculate_polygon_outline,
    order_walls_into_loop
)
from EstiSketch.geometry.roof_solver import solve_roof_geometry
from EstiSketch.roof_components import Roof
from EstiSketch.models.roof import RoofEdge


class DummyWall:
    def __init__(self, wall_id, start, end, width=0.0, height=96.0):
        self.identifier = wall_id
        self.start = start
        self.end = end
        self.width = width
        self.height = height


def test_zero_wall_thickness_rectangle():
    """Verify that a 0-thickness wall rectangle works cleanly and measures overhang from centerline."""
    walls_0 = [
        DummyWall("W1", (0.0, 0.0), (240.0, 0.0), width=0.0),
        DummyWall("W2", (240.0, 0.0), (240.0, 120.0), width=0.0),
        DummyWall("W3", (240.0, 120.0), (0.0, 120.0), width=0.0),
        DummyWall("W4", (0.0, 120.0), (0.0, 0.0), width=0.0),
    ]
    markings = {"W1": "eave", "W2": "gable", "W3": "eave", "W4": "gable"}
    overhang = 12.0

    ridge, hips, valleys, rakes, eaves, outline = calculate_complex_roof_geometry(
        walls_0, markings, overhang=overhang
    )
    assert len(ridge) == 1
    r_start, r_end = ridge[0]
    min_rx = min(r_start[0], r_end[0])
    max_rx = max(r_start[0], r_end[0])
    # For width=0: Gable ends at X=0 and X=240 extend by overhang 12 to X=-12 and X=252 (length 264)
    assert abs(min_rx - (-12.0)) < 1e-4
    assert abs(max_rx - 252.0) < 1e-4
    assert abs(r_start[1] - 60.0) < 1e-4
    assert abs(r_end[1] - 60.0) < 1e-4

    # Outline must be a rectangle [-12, 252] x [-12, 132]
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    assert min(xs) == pytest.approx(-12.0)
    assert max(xs) == pytest.approx(252.0)
    assert min(ys) == pytest.approx(-12.0)
    assert max(ys) == pytest.approx(132.0)


def test_monotonic_area_growth_with_wall_thickness():
    """Test that outline dimensions and area grow monotonically with wall thickness 0, 4, 6, 12."""
    thicknesses = [0.0, 4.0, 6.0, 12.0]
    overhang = 12.0
    areas = []

    for thick in thicknesses:
        walls = [
            DummyWall("W1", (0.0, 0.0), (240.0, 0.0), width=thick),
            DummyWall("W2", (240.0, 0.0), (240.0, 120.0), width=thick),
            DummyWall("W3", (240.0, 120.0), (0.0, 120.0), width=thick),
            DummyWall("W4", (0.0, 120.0), (0.0, 0.0), width=thick),
        ]
        markings = {"W1": "eave", "W2": "gable", "W3": "eave", "W4": "gable"}
        ridge, _, _, _, _, outline = calculate_complex_roof_geometry(
            walls, markings, overhang=overhang
        )
        half_w = thick / 2.0
        expected_min_x = - (overhang + half_w)
        expected_max_x = 240.0 + (overhang + half_w)
        expected_min_y = - (overhang + half_w)
        expected_max_y = 120.0 + (overhang + half_w)

        xs = [p[0] for p in outline]
        ys = [p[1] for p in outline]
        assert min(xs) == pytest.approx(expected_min_x)
        assert max(xs) == pytest.approx(expected_max_x)
        assert min(ys) == pytest.approx(expected_min_y)
        assert max(ys) == pytest.approx(expected_max_y)

        # Ridge extends past exterior face
        r_start, r_end = ridge[0]
        min_rx = min(r_start[0], r_end[0])
        max_rx = max(r_start[0], r_end[0])
        assert abs(min_rx - expected_min_x) < 1e-4
        assert abs(max_rx - expected_max_x) < 1e-4

        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        areas.append(area)

    # Monotonically strictly increasing
    for i in range(len(areas) - 1):
        assert areas[i] < areas[i + 1]


def test_l_shaped_wall_thickness():
    """Verify that L-shaped roof outline respects wall thickness on every face."""
    for thick in [0.0, 5.5]:
        walls = [
            DummyWall("W1", (0.0, 0.0), (400.0, 0.0), width=thick),
            DummyWall("W2", (400.0, 0.0), (400.0, 200.0), width=thick),
            DummyWall("W3", (400.0, 200.0), (200.0, 200.0), width=thick),
            DummyWall("W4", (200.0, 200.0), (200.0, 500.0), width=thick),
            DummyWall("W5", (200.0, 500.0), (0.0, 500.0), width=thick),
            DummyWall("W6", (0.0, 500.0), (0.0, 0.0), width=thick),
        ]
        markings = {"W1": "eave", "W2": "gable", "W3": "eave", "W4": "eave", "W5": "gable", "W6": "eave"}
        overhang = 12.0
        ridge, hips, valleys, rakes, eaves, outline = calculate_complex_roof_geometry(
            walls, markings, overhang=overhang
        )
        assert len(ridge) == 2
        half_w = thick / 2.0
        # Check ridge 1 end at W2 (X=400)
        ew_ridge = [r for r in ridge if abs(r[0][1] - 100.0) < 1.0 or abs(r[1][1] - 100.0) < 1.0][0]
        end_x = max(ew_ridge[0][0], ew_ridge[1][0])
        assert end_x == pytest.approx(400.0 + overhang + half_w)


def test_3d_roof_solver_with_wall_thickness():
    """Test that solve_roof_geometry in 3D produces correct planes with wall half-width."""
    walls = [
        DummyWall("W1", (0.0, 0.0), (240.0, 0.0), width=6.0),
        DummyWall("W2", (240.0, 0.0), (240.0, 120.0), width=6.0),
        DummyWall("W3", (240.0, 120.0), (0.0, 120.0), width=6.0),
        DummyWall("W4", (0.0, 120.0), (0.0, 0.0), width=6.0),
    ]
    edges = [
        RoofEdge(wall_identifier="W1", edge_type="eave"),
        RoofEdge(wall_identifier="W2", edge_type="gable"),
        RoofEdge(wall_identifier="W3", edge_type="eave"),
        RoofEdge(wall_identifier="W4", edge_type="gable"),
    ]
    roof = Roof(identifier="ROOF-3D", edges=edges, pitch_rise=6.0, overhang=12.0)
    result = solve_roof_geometry(roof, walls=walls, default_pitch=6.0, default_overhang=12.0)
    planes_3d = result["planes"]
    assert len(planes_3d) == 4
    # Check that wall_half_width of 3.0 offset eave line by 12 + 3 = 15
    p_w1 = next(p for p in planes_3d if p.plane_id == "P_W1")
    assert p_w1.eave_start[1] == pytest.approx(-15.0)

    # Check roof_planes metadata
    roof_planes = result["roof_planes"]
    for rp in roof_planes:
        assert rp.wall_half_width == 3.0
