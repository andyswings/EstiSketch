import pytest
import math
from EstiSketch.components import Stair
from EstiSketch.Canvas.stair_rail_geometry import (
    stair_rail_paths,
    stair_rail_world_paths,
    stair_rail_length_3d,
    stair_railing_linear_ft
)
from EstiSketch.Takeoff.building_takeoff import (
    generate_stair_takeoff,
    generate_stair_takeoff_report,
    get_supplier_quote_items
)


class DummyCanvas:
    def __init__(self, stairs=None):
        self.stairs = stairs or []
        self.walls = []
        self.wall_sets = []
        self.rooms = []
        self.doors = []
        self.windows = []
        self.roofs = []


def test_straight_stair_railings():
    """Verify straight stair railing paths, toggles, and linear footage."""
    stair = Stair()
    stair.identifier = "STAIR-STR"
    stair.stair_type = "straight"
    stair.start_point = (100.0, 100.0)
    stair.direction_angle = 0.0
    stair.width = 36.0
    stair.total_run = 143.0
    stair.total_rise = 106.0
    stair.has_left_rail = True
    stair.has_right_rail = True
    stair.rail_height = 36.0

    paths = stair_rail_paths(stair)
    assert len(paths["left"]) == 1
    assert len(paths["right"]) == 1

    # Left at y = -18, Right at y = +18
    assert paths["left"][0] == [(0.0, -18.0), (143.0, -18.0)]
    assert paths["right"][0] == [(0.0, 18.0), (143.0, 18.0)]

    # 3D length = hypot(143, 106) ~= 178.0 inches per rail
    expected_slope = math.hypot(143.0, 106.0)
    lens = stair_rail_length_3d(stair)
    assert lens["left"] == pytest.approx(expected_slope)
    assert lens["right"] == pytest.approx(expected_slope)
    assert lens["total"] == pytest.approx(2 * expected_slope)

    # Test toggles: turn off left rail
    stair.has_left_rail = False
    lens_no_left = stair_rail_length_3d(stair)
    assert lens_no_left["left"] == 0.0
    assert lens_no_left["right"] == pytest.approx(expected_slope)
    assert lens_no_left["total"] == pytest.approx(expected_slope)


def test_l_shaped_stair_railings():
    """Verify L-shaped stair with left turn and right turn respects inside/outside rails."""
    stair = Stair()
    stair.identifier = "STAIR-L"
    stair.stair_type = "L-shaped"
    stair.width = 36.0
    stair.num_steps = 14
    stair.tread_depth = 11.0
    stair.landing_depth = 36.0
    stair.turn_direction = "left"
    stair.total_rise = 106.0
    stair.has_left_rail = True
    stair.has_right_rail = True

    paths = stair_rail_paths(stair)
    # Left turn: right rail is outer wall, left rail is inner pivot
    assert len(paths["left"]) == 1
    assert len(paths["right"]) == 1
    outer_path = paths["right"][0]
    inner_path = paths["left"][0]

    # Outer path has 3 points (flight 1 start, outer landing corner, flight 2 end)
    assert len(outer_path) == 3
    assert len(inner_path) == 3

    lens = stair_rail_length_3d(stair)
    # Outer rail traverses landing perimeter so outer > inner
    assert lens["right"] > lens["left"]
    assert lens["total"] > 0.0


def test_u_shaped_stair_railings():
    """Verify U-shaped switchback stair railing paths and takeoff."""
    stair = Stair()
    stair.identifier = "STAIR-U"
    stair.stair_type = "U-shaped"
    stair.width = 36.0
    stair.num_steps = 16
    stair.tread_depth = 11.0
    stair.landing_depth = 36.0
    stair.inner_radius = 6.0  # well width
    stair.turn_direction = "left"
    stair.total_rise = 112.0
    stair.has_left_rail = True
    stair.has_right_rail = True

    paths = stair_rail_paths(stair)
    assert len(paths["left"]) == 1
    assert len(paths["right"]) == 1
    # Both paths have 4 points (flight 1, landing transition 1, landing transition 2, flight 2)
    assert len(paths["right"][0]) == 4
    assert len(paths["left"][0]) == 4

    lens = stair_rail_length_3d(stair)
    assert lens["right"] > lens["left"]  # outer wall > inner stairwell
    assert stair_railing_linear_ft(stair) > 20.0  # > 20 linear feet


def test_spiral_stair_railings():
    """Verify spiral stair railing arc paths and 3D helical length."""
    stair = Stair()
    stair.identifier = "STAIR-SPI"
    stair.stair_type = "spiral"
    stair.width = 36.0
    stair.inner_radius = 6.0
    stair.rotation_degrees = 270.0
    stair.total_rise = 108.0
    stair.turn_direction = "left"
    stair.has_left_rail = True
    stair.has_right_rail = True

    paths = stair_rail_paths(stair)
    assert len(paths["left"]) == 1
    assert len(paths["right"]) == 1
    inner_arc = paths["left"][0]
    outer_arc = paths["right"][0]
    assert len(inner_arc) > 10
    assert len(outer_arc) > 10

    lens = stair_rail_length_3d(stair)
    # Outer helix is longer than inner helix
    assert lens["right"] > lens["left"]

    # Verify world paths
    world_paths = stair_rail_world_paths(stair)
    assert len(world_paths["left"]) == 1
    assert len(world_paths["right"]) == 1


def test_stair_takeoff_and_supplier_quotes():
    """Verify stair material takeoff report and supplier quote line items."""
    s1 = Stair()
    s1.identifier = "STAIR-01"
    s1.stair_type = "straight"
    s1.total_run = 143.0
    s1.total_rise = 106.0
    s1.has_left_rail = True
    s1.has_right_rail = True

    s2 = Stair()
    s2.identifier = "STAIR-02"
    s2.stair_type = "L-shaped"
    s2.turn_direction = "right"
    s2.num_steps = 14
    s2.tread_depth = 11.0
    s2.landing_depth = 36.0
    s2.total_rise = 106.0
    s2.has_left_rail = True
    s2.has_right_rail = False

    canvas = DummyCanvas(stairs=[s1, s2])
    data = generate_stair_takeoff(canvas)

    assert data["stair_count"] == 2
    assert data["total_steps"] == 28
    assert data["total_rail_lf"] > 30.0
    assert data["balusters"] > 90
    assert data["newel_posts"] >= 6
    assert data["handrail_12ft_sticks"] >= 3

    report = generate_stair_takeoff_report(canvas)
    assert "ESTISKETCH STAIR & RAILING MATERIAL TAKEOFF REPORT" in report
    assert "STAIR-01" in report
    assert "STAIR-02" in report
    assert "Balusters" in report

    quote_items = get_supplier_quote_items(canvas, None)
    descriptions = [item["description"] for item in quote_items]
    assert any("Molded Handrail" in d for d in descriptions)
    assert any("Newel Posts" in d for d in descriptions)
    assert any("Balusters" in d for d in descriptions)
