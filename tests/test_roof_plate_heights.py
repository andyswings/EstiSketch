import pytest
import math
from EstiSketch.models.roof import RoofEdge, RoofPlane, Plane3D
from EstiSketch.roof_components import Roof
from EstiSketch.geometry.roof_solver import (
    build_plane_equations,
    solve_roof_geometry,
    intersect_planes
)


class DummyWall:
    def __init__(self, wall_id, start, end, width=0.0, height=96.0, height_at_end=None, layer_id="layer-1"):
        self.identifier = wall_id
        self.start = start
        self.end = end
        self.width = width
        self.height = height
        self.height_at_end = height_at_end if height_at_end is not None else height
        self.layer_id = layer_id


class DummyLayer:
    def __init__(self, layer_id, level_id):
        self.id = layer_id
        self.level_id = level_id


class DummyLevel:
    def __init__(self, level_id, elevation):
        self.id = level_id
        self.elevation = elevation


class DummyCanvas:
    def __init__(self, levels=None, layers=None):
        self.levels = levels or [DummyLevel("level-1", 0.0)]
        self.layers = layers or [DummyLayer("layer-1", "level-1")]

    def get_layer_by_id(self, layer_id):
        for l in self.layers:
            if l.id == layer_id:
                return l
        return None

    def get_wall_top_elevations(self, wall):
        base = 0.0
        layer = self.get_layer_by_id(getattr(wall, 'layer_id', None))
        if layer:
            level = next((lvl for lvl in self.levels if lvl.id == layer.level_id), None)
            if level:
                base = level.elevation
        h_start = float(getattr(wall, 'height', 96.0) or 96.0)
        h_end = float(getattr(wall, 'height_at_end', h_start) or h_start)
        return (base + h_start, base + h_end)


def test_equal_plates_reproduce_exact_results():
    """Verify that equal plate heights produce identical horizontal ridges."""
    walls = [
        DummyWall("W1", (0.0, 0.0), (240.0, 0.0), height=96.0),
        DummyWall("W2", (240.0, 0.0), (240.0, 120.0), height=96.0),
        DummyWall("W3", (240.0, 120.0), (0.0, 120.0), height=96.0),
        DummyWall("W4", (0.0, 120.0), (0.0, 0.0), height=96.0),
    ]
    edges = [
        RoofEdge(wall_identifier="W1", edge_type="eave"),
        RoofEdge(wall_identifier="W2", edge_type="gable"),
        RoofEdge(wall_identifier="W3", edge_type="eave"),
        RoofEdge(wall_identifier="W4", edge_type="gable"),
    ]
    roof = Roof(identifier="ROOF-EQ", edges=edges, pitch_rise=6.0, overhang=0.0)
    result = solve_roof_geometry(roof, walls=walls, default_pitch=6.0, default_overhang=0.0)
    planes = result["planes"]
    assert len(planes) == 4

    p_w1 = next(p for p in planes if p.plane_id == "P_W1")
    p_w3 = next(p for p in planes if p.plane_id == "P_W3")

    # At W1 eave (y=0), elevation must be 96.0
    assert p_w1.elevation_at(120.0, 0.0) == pytest.approx(96.0)
    # At W3 eave (y=120), elevation must be 96.0
    assert p_w3.elevation_at(120.0, 120.0) == pytest.approx(96.0)

    # Ridge at midway y=60: elevation = 96.0 + (6/12) * 60 = 96.0 + 30.0 = 126.0
    assert p_w1.elevation_at(120.0, 60.0) == pytest.approx(126.0)
    assert p_w3.elevation_at(120.0, 60.0) == pytest.approx(126.0)


def test_sloped_wall_along_eave_gradient():
    """Verify that a sloped wall (height_at_end != height) creates an exact along-eave gradient."""
    # Eave wall W1 from x=0 to x=240, height rises from 96.0 at start to 120.0 at end
    w1 = DummyWall("W1", (0.0, 0.0), (240.0, 0.0), height=96.0, height_at_end=120.0)
    w2 = DummyWall("W2", (240.0, 0.0), (240.0, 120.0), height=120.0, height_at_end=120.0)
    w3 = DummyWall("W3", (240.0, 120.0), (0.0, 120.0), height=120.0, height_at_end=96.0)
    w4 = DummyWall("W4", (0.0, 120.0), (0.0, 0.0), height=96.0, height_at_end=96.0)
    walls = [w1, w2, w3, w4]

    edges = [
        RoofEdge(wall_identifier="W1", edge_type="eave"),
        RoofEdge(wall_identifier="W2", edge_type="gable"),
        RoofEdge(wall_identifier="W3", edge_type="eave"),
        RoofEdge(wall_identifier="W4", edge_type="gable"),
    ]
    roof = Roof(identifier="ROOF-SLOPE", edges=edges, pitch_rise=6.0, overhang=0.0)
    result = solve_roof_geometry(roof, walls=walls, default_pitch=6.0, default_overhang=0.0)
    planes = result["planes"]
    p_w1 = next(p for p in planes if p.plane_id == "P_W1")

    # At start of W1 (x=0, y=0): elevation must be 96.0
    assert p_w1.elevation_at(0.0, 0.0) == pytest.approx(96.0)
    # At end of W1 (x=240, y=0): elevation must be 120.0
    assert p_w1.elevation_at(240.0, 0.0) == pytest.approx(120.0)
    # At midpoint of W1 (x=120, y=0): elevation must be 108.0
    assert p_w1.elevation_at(120.0, 0.0) == pytest.approx(108.0)

    # And perpendicular inward rise is slope 0.5 (6/12):
    # At (x=0, y=60): z = 96.0 + 0.5 * 60 = 126.0
    assert p_w1.elevation_at(0.0, 60.0) == pytest.approx(126.0)
    # At (x=240, y=60): z = 120.0 + 0.5 * 60 = 150.0
    assert p_w1.elevation_at(240.0, 60.0) == pytest.approx(150.0)


def test_different_levels_eave_plate_heights():
    """Verify that eave walls on different levels start at level.elevation + wall.height."""
    lvl1 = DummyLevel("L1", 0.0)
    lvl2 = DummyLevel("L2", 120.0)  # Second story / upper level at 120"
    lay1 = DummyLayer("layer-1", "L1")
    lay2 = DummyLayer("layer-2", "L2")
    canvas = DummyCanvas(levels=[lvl1, lvl2], layers=[lay1, lay2])

    # W1 on Level 1 (elevation 0 + 96 = 96)
    w1 = DummyWall("W1", (0.0, 0.0), (240.0, 0.0), height=96.0, layer_id="layer-1")
    # W3 on Level 2 (elevation 120 + 96 = 216)
    w3 = DummyWall("W3", (240.0, 120.0), (0.0, 120.0), height=96.0, layer_id="layer-2")

    elev1 = canvas.get_wall_top_elevations(w1)
    elev3 = canvas.get_wall_top_elevations(w3)
    assert elev1 == (96.0, 96.0)
    assert elev3 == (216.0, 216.0)

    plate_heights = {
        "W1": elev1,
        "W3": elev3,
    }
    planes = build_plane_equations(
        [w1, w3], overhangs=[0.0, 0.0], pitches=[6.0, 6.0], plate_heights=plate_heights
    )
    p_w1 = planes[0]
    p_w3 = planes[1]

    # Eave elevations match their respective level plate heights
    assert p_w1.elevation_at(120.0, 0.0) == pytest.approx(96.0)
    assert p_w3.elevation_at(120.0, 120.0) == pytest.approx(216.0)

    # Intersect the two planes to find the 3D ridge line
    ridge_3d = intersect_planes(p_w1, p_w3)
    # The ridge line must lie on BOTH planes (residual < 1e-6)
    pt = ridge_3d.point
    assert abs(p_w1.elevation_at(pt.x, pt.y) - pt.z) < 1e-4
    assert abs(p_w3.elevation_at(pt.x, pt.y) - pt.z) < 1e-4


def test_rotated_and_angled_in_plan_walls():
    """Verify that roofs on rotated / angled in-plan walls solve cleanly."""
    angle = math.radians(30.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    def rot(x, y):
        return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

    p1 = rot(0.0, 0.0)
    p2 = rot(240.0, 0.0)
    p3 = rot(240.0, 120.0)
    p4 = rot(0.0, 120.0)

    w1 = DummyWall("W1", p1, p2, height=96.0)
    w2 = DummyWall("W2", p2, p3, height=96.0)
    w3 = DummyWall("W3", p3, p4, height=96.0)
    w4 = DummyWall("W4", p4, p1, height=96.0)
    walls = [w1, w2, w3, w4]

    edges = [
        RoofEdge(wall_identifier="W1", edge_type="eave"),
        RoofEdge(wall_identifier="W2", edge_type="gable"),
        RoofEdge(wall_identifier="W3", edge_type="eave"),
        RoofEdge(wall_identifier="W4", edge_type="gable"),
    ]
    roof = Roof(identifier="ROOF-ROT", edges=edges, pitch_rise=6.0, overhang=12.0)
    result = solve_roof_geometry(roof, walls=walls, default_pitch=6.0, default_overhang=12.0)
    planes = result["planes"]
    assert len(planes) == 4
    # All planes must be valid and non-degenerate
    for p in planes:
        norm = p.normal_vector()
        assert math.hypot(norm[0], norm[1], norm[2]) > 0.5
