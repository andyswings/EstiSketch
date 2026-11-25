import math
import os
import stat

import pytest

from EstiSketch.blender_bridge import estisketch_to_hb5 as bridge
from EstiSketch.blender_bridge import launcher


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SIMPLE_HOUSE_XML = os.path.join(PROJECT_ROOT, "simple_house.xml")


def test_parse_simple_house_xml():
    proj = bridge.parse_estisketch_xml(SIMPLE_HOUSE_XML)

    assert len(proj.levels) == 1
    assert proj.levels[0].name == "Level 1"
    assert proj.levels[0].elevation == pytest.approx(0.0)

    # 6 walls, including sloped gable walls (96" -> 144")
    assert len(proj.walls) == 6
    sloped = [w for w in proj.walls if abs(w.height - w.height_at_end) > 0.01]
    assert len(sloped) == 4
    assert max(w.height_at_end for w in proj.walls) == pytest.approx(144.0)

    # 1 room slab
    assert len(proj.rooms) == 1
    assert proj.rooms[0].is_slab is True
    assert proj.rooms[0].slab_thickness == pytest.approx(4.0)
    assert len(proj.rooms[0].points) == 6

    # simple_house.xml has 1 valid door (the other has set_index=-1) and
    # 4 valid windows (two others have set_index=-1)
    assert len(proj.doors) == 1
    assert proj.doors[0].wall_index == 5
    assert len(proj.windows) == 4


def test_coordinate_transform_y_flip_and_centering():
    proj = bridge.parse_estisketch_xml(SIMPLE_HOUSE_XML)
    cx, cy = bridge.compute_plan_center(proj)

    x0, y0 = bridge.inches_to_blender_xy(cx, cy, cx, cy)
    assert (x0, y0) == (0.0, 0.0)

    # EstiSketch +Y (down) maps to Blender -Y
    x1, y1 = bridge.inches_to_blender_xy(cx + 10.0, cy + 10.0, cx, cy)
    assert x1 == pytest.approx(10.0 * bridge.INCH_TO_M)
    assert y1 == pytest.approx(-10.0 * bridge.INCH_TO_M)


def test_compute_opening_local_x_clamps_within_wall():
    assert bridge.compute_opening_local_x(0.05, 3.0, 0.9) == pytest.approx(0.0)
    assert bridge.compute_opening_local_x(0.5, 4.0, 1.0) == pytest.approx(1.5)
    assert bridge.compute_opening_local_x(0.99, 3.0, 0.9) == pytest.approx(2.1)


def test_tessellate_curved_wall_points():
    pts = bridge.tessellate_curved_wall_points(
        start=(100.0, 0.0),
        end=(0.0, 100.0),
        arc_center=(0.0, 0.0),
        arc_radius=100.0,
        max_seg_deg=15.0,
    )
    assert len(pts) >= 7
    assert pts[0] == (100.0, 0.0)
    assert pts[-1] == (0.0, 100.0)
    for x, y in pts:
        assert math.hypot(x, y) == pytest.approx(100.0, rel=1e-6)


def test_find_blender_executable_configured_path(tmp_path):
    fake_bin = tmp_path / "blender"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IXUSR)

    assert launcher.find_blender_executable(str(fake_bin)) == str(fake_bin)
    assert os.path.isfile(launcher.get_bridge_script_path())
