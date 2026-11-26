"""Verification tests for the 3 generated demo house XML projects."""

import os
import sys
from types import SimpleNamespace

import cairo
import gi
import pytest

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch.blender_bridge import estisketch_to_hb5 as bridge
from EstiSketch.config import DEFAULT_SETTINGS
from EstiSketch.fixtures_catalog import FURNITURE_CATEGORIES
from EstiSketch.geometry.room_holes import polygon_area
from EstiSketch.project_io import open_project

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEMO_DIR = os.path.join(PROJECT_ROOT, "examples", "demo_houses")

DEMO_SPECS = [
    ("house1_gable_2bed_1_5bath_1200sqft.xml", 1, 1200.0, False),
    ("house2_two_story_3bed_2bath_garage_1800sqft.xml", 2, 1836.0, True),
    ("house3_l_shape_2bed_2bath_office_1500sqft.xml", 1, 1512.0, False),
]


def _make_canvas():
    return CanvasArea(SimpleNamespace(**DEFAULT_SETTINGS))


@pytest.mark.parametrize("filename,expected_levels,expected_sqft,has_garage", DEMO_SPECS)
def test_demo_house_loads_and_matches_program(filename, expected_levels, expected_sqft, has_garage):
    path = os.path.join(DEMO_DIR, filename)
    assert os.path.isfile(path), f"Missing demo XML: {path}"

    canvas = _make_canvas()
    open_project(canvas, path)

    assert len(canvas.levels) == expected_levels
    living_sqft = sum(
        polygon_area(r.points) / 144.0
        for r in canvas.rooms
        if getattr(r, "room_type", "") != "garage"
    )
    assert living_sqft == pytest.approx(expected_sqft, rel=0.05)

    # Zero orphaned doors or windows
    assert len(canvas.doors) >= 6
    assert all(wall is not None for wall, _d, _r in canvas.doors)
    assert len(canvas.windows) >= 8
    assert all(wall is not None for wall, _w, _r in canvas.windows)

    # Variety of windows (>= 4 distinct window types, actually all 5)
    win_types = {w.window_type for _wall, w, _r in canvas.windows}
    assert len(win_types) >= 4

    # Garage check
    garage_rooms = [r for r in canvas.rooms if r.room_type == "garage"]
    garage_doors = [d for _w, d, _r in canvas.doors if d.door_type == "garage"]
    if has_garage:
        assert len(garage_rooms) == 1
        assert garage_rooms[0].is_slab is True
        assert len(garage_doors) == 1
    else:
        assert len(garage_rooms) == 0

    # Furnished + cabinetry/plumbing/appliances
    furn_cats = {f.category for f in canvas.fixtures if f.category in FURNITURE_CATEGORIES}
    assert {"living_furniture", "bedroom_furniture", "dining_furniture"}.issubset(furn_cats)
    if "house3" in filename:
        assert "office_furniture" in furn_cats
    non_furn_cats = {f.category for f in canvas.fixtures if f.category not in FURNITURE_CATEGORIES}
    assert {"kitchen_cabinet", "bathroom_fixture", "kitchen_appliance"}.issubset(non_furn_cats)


def test_demo_house_roofs_and_stairs():
    # House 1: straight gable
    c1 = _make_canvas()
    open_project(c1, os.path.join(DEMO_DIR, "house1_gable_2bed_1_5bath_1200sqft.xml"))
    assert len(c1.roofs) == 1
    r1 = c1.roofs[0]
    assert r1.roof_type == "gable"
    assert len(r1.ridge_lines) == 1
    assert len(r1.outline_points) == 4

    # House 2: 2 roofs (garage gable + main hip) + stair + Level 2 stair hole
    c2 = _make_canvas()
    open_project(c2, os.path.join(DEMO_DIR, "house2_two_story_3bed_2bath_garage_1800sqft.xml"))
    assert len(c2.roofs) == 2
    roof_types = {r.roof_type for r in c2.roofs}
    assert roof_types == {"gable", "hip"}
    hip_roof = next(r for r in c2.roofs if r.roof_type == "hip")
    assert len(hip_roof.hip_lines) == 4
    assert len(hip_roof.ridge_lines) == 1

    assert len(c2.stairs) == 1
    assert c2.stairs[0].start_level_id == c2.levels[0].id
    assert c2.stairs[0].end_level_id == c2.levels[1].id
    upper_hall = next(r for r in c2.rooms if r.name == "Upper Hall")
    assert len(upper_hall.holes) == 1

    # House 3: L-shape intersecting gable (2 ridges, valley, hip, 6-point outline)
    c3 = _make_canvas()
    open_project(c3, os.path.join(DEMO_DIR, "house3_l_shape_2bed_2bath_office_1500sqft.xml"))
    assert len(c3.roofs) == 1
    r3 = c3.roofs[0]
    assert len(r3.ridge_lines) >= 2
    assert len(r3.valley_lines) >= 1
    assert len(r3.outline_points) == 6


@pytest.mark.parametrize("filename,expected_levels,_sqft,_has_garage", DEMO_SPECS)
def test_demo_house_bridge_parser_and_cairo_render(filename, expected_levels, _sqft, _has_garage):
    path = os.path.join(DEMO_DIR, filename)

    # 1. Blender bridge Layer-1 parser reads every wall/room/door/window cleanly
    canvas = _make_canvas()
    open_project(canvas, path)
    parsed = bridge.parse_estisketch_xml(path)
    assert len(parsed.levels) == expected_levels
    assert len(parsed.walls) == sum(len(ws) for ws in canvas.wall_sets)
    assert len(parsed.rooms) == len(canvas.rooms)
    assert len(parsed.doors) == len(canvas.doors)
    assert len(parsed.windows) == len(canvas.windows)

    # 2. Headless Cairo rendering succeeds cleanly for both screen and printing passes
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)
    cr = cairo.Context(surf)
    canvas.zoom = 0.5
    canvas.draw_scene(cr, 800, 600, printing=False)
    canvas.draw_scene(cr, 800, 600, printing=True)
