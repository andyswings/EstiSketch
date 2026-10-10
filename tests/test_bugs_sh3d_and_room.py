import os
import zipfile
import tempfile
import xml.etree.ElementTree as ET
import math
from types import SimpleNamespace
import pytest
import gi
gi.require_version("Gtk", "4.0")

from EstiSketch.components import Wall, Room
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.sh3d_importer import import_sh3d
from EstiSketch import config


@pytest.fixture
def canvas():
    cfg = SimpleNamespace(**config.load_config())
    return CanvasArea(cfg)


def create_dummy_sh3d(walls_xml: str) -> str:
    """Helper to create a temporary .sh3d archive with the given wall XML entries."""
    temp_dir = tempfile.mkdtemp()
    home_xml_path = os.path.join(temp_dir, "Home.xml")
    home_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<home wallHeight="250.0">
{walls_xml}
</home>"""
    with open(home_xml_path, "w", encoding="utf-8") as f:
        f.write(home_content)

    sh3d_path = os.path.join(temp_dir, "test.sh3d")
    with zipfile.ZipFile(sh3d_path, "w") as zf:
        zf.write(home_xml_path, "Home.xml")

    return sh3d_path


def test_sh3d_import_wall_mitering(canvas):
    """
    Test that importing an SH3D file groups connected walls into wall sets
    with snapped endpoints and closed loops so that Cairo renders miter joins.
    """
    # 4 walls forming a 200cm x 100cm room, placed out of order in XML
    # Coordinates in cm:
    # W1: (0, 0) -> (200, 0)
    # W2: (200, 0) -> (200, 100)
    # W3: (200, 100) -> (0, 100)  (reversed order in XML: listed as (0, 100) -> (200, 100) backwards or out of order)
    # W4: (0, 100) -> (0, 0)
    walls_xml = """
    <wall id="w1" xStart="0.0" yStart="0.0" xEnd="200.0" yEnd="0.0" thickness="15.0" height="250.0"/>
    <wall id="w3" xStart="0.0" yStart="100.0" xEnd="200.0" yEnd="100.0" thickness="15.0" height="250.0"/>
    <wall id="w2" xStart="200.0" yStart="0.0" xEnd="200.0" yEnd="100.0" thickness="15.0" height="250.0"/>
    <wall id="w4" xStart="0.0" yStart="100.0" xEnd="0.0" yEnd="0.0" thickness="15.0" height="250.0"/>
    """
    sh3d_path = create_dummy_sh3d(walls_xml)
    try:
        imported = import_sh3d(sh3d_path, canvas)
        wall_sets = imported["wall_sets"]

        # The walls form a closed room, so they should be grouped into a single wall set
        assert len(wall_sets) == 1, f"Expected 1 wall set, got {len(wall_sets)}"
        ws = wall_sets[0]
        assert len(ws) == 4, f"Expected 4 walls in set, got {len(ws)}"

        # Every consecutive wall must connect end-to-start with exact float equality (< 1e-6)
        for i in range(len(ws) - 1):
            assert abs(ws[i].end[0] - ws[i+1].start[0]) < 1e-6, f"Joint {i}->{i+1} X mismatch"
            assert abs(ws[i].end[1] - ws[i+1].start[1]) < 1e-6, f"Joint {i}->{i+1} Y mismatch"

        # The loop must be closed: the last wall connects back to the first wall
        assert abs(ws[-1].end[0] - ws[0].start[0]) < 1e-6, "Loop closure X mismatch"
        assert abs(ws[-1].end[1] - ws[0].start[1]) < 1e-6, "Loop closure Y mismatch"

    finally:
        if os.path.exists(sh3d_path):
            os.remove(sh3d_path)


def test_sh3d_import_curved_wall(canvas):
    """
    Test that importing an SH3D file with arcExtent properly imports the curved wall.
    """
    walls_xml = """
    <wall id="w1" xStart="0.0" yStart="0.0" xEnd="100.0" yEnd="0.0" thickness="10.0" height="250.0" arcExtent="1.5707963"/>
    """
    sh3d_path = create_dummy_sh3d(walls_xml)
    try:
        imported = import_sh3d(sh3d_path, canvas)
        wall = imported["wall_sets"][0][0]
        assert getattr(wall, "is_curved", False) is True
        assert wall.arc_center is not None
        assert wall.arc_radius is not None
        assert wall.arc_radius > 0
    finally:
        if os.path.exists(sh3d_path):
            os.remove(sh3d_path)


def test_auto_generated_room_with_curved_walls(canvas):
    """
    Test that auto-generating a room from a wall set containing curved walls
    samples points along the arc so the room polygon follows the curve.
    """
    # Create 4 walls: 3 straight and 1 curved bulging outwards to x < 0
    # Center (-50, 50), radius ~70.71, arc between (0, 100) and (0, 0)
    w0 = Wall(start=(0.0, 0.0), end=(100.0, 0.0), width=4.5, height=96.0)
    w1 = Wall(start=(100.0, 0.0), end=(100.0, 100.0), width=4.5, height=96.0)
    w2 = Wall(start=(100.0, 100.0), end=(0.0, 100.0), width=4.5, height=96.0)
    
    # Curved wall from (0, 100) to (0, 0) with center (-50, 50), radius ~70.7106
    # Midpoint of chord is (0, 50). At angle 0 from center (-50, 50), arc passes through (-50 + 70.71, 50) = (20.71, 50)
    # Or center (50, 50) with radius 50*sqrt(2) bulging out to x = -20.71
    cx, cy = (50.0, 50.0)
    radius = math.hypot(0.0 - cx, 100.0 - cy)  # 50*sqrt(2) ≈ 70.710678
    # When going from (0, 100) to (0, 0) with center (50, 50):
    # start_angle = 3*pi/4, end_angle = 5*pi/4 (or -3*pi/4).
    # Normalizing angle_diff: (-3*pi/4) - (3*pi/4) = -6*pi/4 = -3*pi/2 -> +pi/2 (CCW)
    # Bulge reaches x = 50 - radius ≈ -20.71 at angle pi
    w3 = Wall(
        start=(0.0, 100.0),
        end=(0.0, 0.0),
        width=4.5,
        height=96.0,
        is_curved=True,
        arc_center=(cx, cy),
        arc_radius=radius
    )

    canvas.wall_sets = [[w0, w1, w2, w3]]
    canvas.tool_mode = "draw_rooms"

    # Double click inside the center of the room: model coords (50, 50)
    # device_to_model uses PIXELS_PER_INCH = 2.0 by default, so widget coord (100, 100) -> model (50, 50)
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    widget_x, widget_y = canvas.model_to_device(50.0, 50.0, ppi)
    
    canvas._handle_room_click(2, widget_x, widget_y)

    assert len(canvas.rooms) == 1, "Expected room to be auto-generated"
    room = canvas.rooms[0]
    
    # The room polygon must NOT be just the 4 straight endpoints!
    # It must contain intermediate sampled points along w3's arc
    assert len(room.points) > 4, f"Expected >4 points for curved room, got {len(room.points)}"
    
    # Check that points on w3 actually reach the curved bulge (x < 0)
    min_x = min(p[0] for p in room.points)
    assert min_x < -15.0, f"Expected room points to bulge out to x < -15, but min_x is {min_x}"


def test_auto_generated_room_click_in_curved_bulge(canvas):
    """
    Test that double-clicking inside the curved bulge of a wall
    (outside the straight chord polygon) is recognized as inside the room
    and creates the room.
    """
    w0 = Wall(start=(0.0, 0.0), end=(100.0, 0.0), width=4.5, height=96.0)
    w1 = Wall(start=(100.0, 0.0), end=(100.0, 100.0), width=4.5, height=96.0)
    w2 = Wall(start=(100.0, 100.0), end=(0.0, 100.0), width=4.5, height=96.0)
    cx, cy = (50.0, 50.0)
    radius = math.hypot(0.0 - cx, 100.0 - cy)
    w3 = Wall(
        start=(0.0, 100.0),
        end=(0.0, 0.0),
        width=4.5,
        height=96.0,
        is_curved=True,
        arc_center=(cx, cy),
        arc_radius=radius
    )

    canvas.wall_sets = [[w0, w1, w2, w3]]
    canvas.tool_mode = "draw_rooms"

    # Click in the curved bulge: at (-10, 50)
    # In the straight polygon [(0,0), (100,0), (100,100), (0,100)], (-10, 50) is OUTSIDE!
    # But in the curved room, it is INSIDE!
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    widget_x, widget_y = canvas.model_to_device(-10.0, 50.0, ppi)
    
    canvas._handle_room_click(2, widget_x, widget_y)

    assert len(canvas.rooms) == 1, "Expected room to be auto-generated when clicking inside curved bulge"


def test_auto_generated_room_two_curved_walls(canvas):
    """
    Test that a closed loop formed by 2 curved walls (e.g. eye/lens shape)
    is recognized as a closed polygon and creates a room following both curves.
    """
    # Two curved walls between (0, 50) and (100, 50)
    # W0 curves up with center (50, 0), radius 50*sqrt(2)
    # W1 curves down with center (50, 100), radius 50*sqrt(2)
    radius = math.hypot(50.0, 50.0)
    w0 = Wall(
        start=(0.0, 50.0),
        end=(100.0, 50.0),
        width=4.5,
        height=96.0,
        is_curved=True,
        arc_center=(50.0, 0.0),
        arc_radius=radius
    )
    w1 = Wall(
        start=(100.0, 50.0),
        end=(0.0, 50.0),
        width=4.5,
        height=96.0,
        is_curved=True,
        arc_center=(50.0, 100.0),
        arc_radius=radius
    )

    canvas.wall_sets = [[w0, w1]]
    canvas.tool_mode = "draw_rooms"

    assert canvas._is_closed_polygon([w0, w1]) is True

    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    widget_x, widget_y = canvas.model_to_device(50.0, 50.0, ppi)
    canvas._handle_room_click(2, widget_x, widget_y)

    assert len(canvas.rooms) == 1, "Expected room to be auto-generated for 2-curved-wall loop"
    room = canvas.rooms[0]
    assert len(room.points) >= 16, f"Expected sampled vertices for both curved walls, got {len(room.points)}"


def test_auto_generated_room_straight_walls_regression(canvas):
    """
    Test that standard straight-wall rooms preserve exact 4-corner polygons.
    """
    w0 = Wall(start=(0.0, 0.0), end=(100.0, 0.0), width=4.5, height=96.0)
    w1 = Wall(start=(100.0, 0.0), end=(100.0, 100.0), width=4.5, height=96.0)
    w2 = Wall(start=(100.0, 100.0), end=(0.0, 100.0), width=4.5, height=96.0)
    w3 = Wall(start=(0.0, 100.0), end=(0.0, 0.0), width=4.5, height=96.0)

    canvas.wall_sets = [[w0, w1, w2, w3]]
    canvas.tool_mode = "draw_rooms"

    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    widget_x, widget_y = canvas.model_to_device(50.0, 50.0, ppi)
    canvas._handle_room_click(2, widget_x, widget_y)

    assert len(canvas.rooms) == 1
    room = canvas.rooms[0]
    assert len(room.points) == 4, f"Straight wall room should have exactly 4 vertices, got {len(room.points)}"
    assert room.points == [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]


def test_sh3d_import_multiple_disjoint_rooms(canvas):
    """
    Test that multiple disjoint rooms in an SH3D file are imported into separate
    connected wall sets, each mitered properly.
    """
    walls_xml = """
    <!-- Room 1 -->
    <wall id="r1_w1" xStart="0.0" yStart="0.0" xEnd="100.0" yEnd="0.0" thickness="10.0" height="250.0"/>
    <wall id="r1_w2" xStart="100.0" yStart="0.0" xEnd="100.0" yEnd="100.0" thickness="10.0" height="250.0"/>
    <wall id="r1_w3" xStart="100.0" yStart="100.0" xEnd="0.0" yEnd="100.0" thickness="10.0" height="250.0"/>
    <wall id="r1_w4" xStart="0.0" yStart="100.0" xEnd="0.0" yEnd="0.0" thickness="10.0" height="250.0"/>
    <!-- Room 2 (translated by 200cm) -->
    <wall id="r2_w1" xStart="200.0" yStart="0.0" xEnd="300.0" yEnd="0.0" thickness="10.0" height="250.0"/>
    <wall id="r2_w2" xStart="300.0" yStart="0.0" xEnd="300.0" yEnd="100.0" thickness="10.0" height="250.0"/>
    <wall id="r2_w3" xStart="300.0" yStart="100.0" xEnd="200.0" yEnd="100.0" thickness="10.0" height="250.0"/>
    <wall id="r2_w4" xStart="200.0" yStart="100.0" xEnd="200.0" yEnd="0.0" thickness="10.0" height="250.0"/>
    """
    sh3d_path = create_dummy_sh3d(walls_xml)
    try:
        imported = import_sh3d(sh3d_path, canvas)
        wall_sets = imported["wall_sets"]
        assert len(wall_sets) == 2, f"Expected 2 wall sets, got {len(wall_sets)}"
        for ws in wall_sets:
            assert len(ws) == 4
            for i in range(len(ws) - 1):
                assert abs(ws[i].end[0] - ws[i+1].start[0]) < 1e-6
                assert abs(ws[i].end[1] - ws[i+1].start[1]) < 1e-6
            assert abs(ws[-1].end[0] - ws[0].start[0]) < 1e-6
            assert abs(ws[-1].end[1] - ws[0].start[1]) < 1e-6
    finally:
        if os.path.exists(sh3d_path):
            os.remove(sh3d_path)

