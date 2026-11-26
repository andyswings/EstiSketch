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


DEMO_DIR = os.path.join(PROJECT_ROOT, "examples", "demo_houses")


def test_solve_roof_simple_house_legacy_gable():
    proj = bridge.parse_estisketch_xml(SIMPLE_HOUSE_XML)
    assert len(proj.roofs) == 1
    roof = proj.roofs[0]
    assert roof.roof_type == "gable"
    assert roof.ridge_lines == []

    solved = bridge.solve_roof_3d(roof, proj)
    assert len(solved.facets) == 2
    zs = [v[2] for f in solved.facets for v in f.vertices_3d]
    assert max(zs) == pytest.approx(143.09, abs=0.25)
    assert min(zs) == pytest.approx(87.08, abs=0.25)
    # Gable walls in simple_house.xml are already sloped (96 -> 144), so no infill
    assert len(solved.gable_infills) == 0


def test_solve_roof_house1_gable():
    xml_path = os.path.join(DEMO_DIR, "house1_gable_2bed_1_5bath_1200sqft.xml")
    proj = bridge.parse_estisketch_xml(xml_path)
    assert len(proj.roofs) == 1
    solved = bridge.solve_roof_3d(proj.roofs[0], proj)
    assert len(solved.facets) == 2
    zs = [v[2] for f in solved.facets for v in f.vertices_3d]
    assert max(zs) == pytest.approx(186.0, abs=0.25)
    assert min(zs) == pytest.approx(85.5, abs=0.25)
    assert len(solved.gable_infills) == 2


def test_solve_roof_house2_two_story_and_garage():
    xml_path = os.path.join(DEMO_DIR, "house2_two_story_3bed_2bath_garage_1800sqft.xml")
    proj = bridge.parse_estisketch_xml(xml_path)
    assert len(proj.levels) == 2
    assert proj.levels[0].floor_thickness == pytest.approx(10.0)
    assert proj.levels[1].floor_thickness == pytest.approx(10.0)
    assert len(proj.roofs) == 2

    garage_roof = next(r for r in proj.roofs if r.roof_type == "gable")
    hip_roof = next(r for r in proj.roofs if r.roof_type == "hip")

    solved_gar = bridge.solve_roof_3d(garage_roof, proj)
    assert len(solved_gar.facets) == 2
    # West garage gable wall sits under Level 2 East wall, so only 1 infill on East
    assert len(solved_gar.gable_infills) == 1

    solved_hip = bridge.solve_roof_3d(hip_roof, proj)
    assert len(solved_hip.facets) == 4
    hip_zs = [v[2] for f in solved_hip.facets for v in f.vertices_3d]
    assert max(hip_zs) == pytest.approx(283.0, abs=0.25)
    assert len(solved_hip.gable_infills) == 0


def test_solve_roof_house3_l_shape_watertight():
    xml_path = os.path.join(DEMO_DIR, "house3_l_shape_2bed_2bath_office_1500sqft.xml")
    proj = bridge.parse_estisketch_xml(xml_path)
    assert len(proj.roofs) == 1
    assert proj.roofs[0].material == "standing_seam_metal"

    solved = bridge.solve_roof_3d(proj.roofs[0], proj)
    assert len(solved.facets) == 4
    assert len(solved.gable_infills) == 2

    # Verify watertight seams: every shared (x, y) coordinate has identical z across facets
    z_by_xy = {}
    for facet in solved.facets:
        for x, y, z in facet.vertices_3d:
            key = (round(x, 3), round(y, 3))
            if key in z_by_xy:
                assert z == pytest.approx(z_by_xy[key], abs=1e-4)
            else:
                z_by_xy[key] = z


def test_house2_stairs_cutouts_transform_and_railings():
    xml_path = os.path.join(DEMO_DIR, "house2_two_story_3bed_2bath_garage_1800sqft.xml")
    proj = bridge.parse_estisketch_xml(xml_path)
    assert len(proj.stairs) == 1
    st = proj.stairs[0]
    assert st.stair_type == "straight"
    assert st.start_point == pytest.approx((252.0, 290.0))

    cutouts = bridge.compute_room_hole_cutouts(proj)
    upper_hall = next(r for r in proj.rooms if r.name == "Upper Hall")
    foyer = next(r for r in proj.rooms if r.name == "Foyer & Stair Hall")

    assert any(c.cuts_floor and not c.cuts_ceiling for c in cutouts[upper_hall.identifier])
    assert any(c.cuts_ceiling and not c.cuts_floor for c in cutouts[foyer.identifier])

    cx, cy = bridge.compute_plan_center(proj)
    loc, rot_z = bridge.compute_hb5_stair_transform(st, 0.0, cx, cy)
    sx_m, sy_m = bridge.inches_to_blender_xy(252.0, 290.0, cx, cy)
    assert loc[0] == pytest.approx(sx_m, abs=1e-5)
    assert loc[1] == pytest.approx(sy_m + (st.width * bridge.INCH_TO_M) / 2.0, abs=1e-5)
    assert loc[2] == pytest.approx(0.0)
    assert rot_z == pytest.approx(-math.pi / 2.0)

    rails = bridge.compute_stair_railing_paths_3d(st, 0.0)
    assert len(rails) == 2
    assert rails[0][0][2] == pytest.approx(0.0)
    assert rails[0][-1][2] == pytest.approx(106.0)


def test_synthetic_stairs_and_floor_opening_cutouts(tmp_path):
    xml_content = """<?xml version='1.0' encoding='utf-8'?>
<Project window_width="800" window_height="600" cut_lower_ceiling_under_stairs="False">
  <Levels>
    <Level id="lvl1" name="Level 1" elevation="0.0" height="96.0" floor_thickness="10.0" />
    <Level id="lvl2" name="Level 2" elevation="106.0" height="96.0" floor_thickness="10.0" />
  </Levels>
  <Layers>
    <Layer id="lay1" name="L1" visible="True" locked="False" opacity="1.0" level_id="lvl1" />
    <Layer id="lay2" name="L2" visible="True" locked="False" opacity="1.0" level_id="lvl2" />
  </Layers>
  <Rooms>
    <Room identifier="r1"><Points><Point x="0" y="0"/><Point x="400" y="0"/><Point x="400" y="400"/><Point x="0" y="400"/></Points><Height>96</Height><Name>Lower</Name><LayerId>lay1</LayerId></Room>
    <Room identifier="r2"><Points><Point x="0" y="0"/><Point x="400" y="0"/><Point x="400" y="400"/><Point x="0" y="400"/></Points><Height>96</Height><Name>Upper</Name><LayerId>lay2</LayerId></Room>
  </Rooms>
  <FloorOpenings>
    <FloorOpening identifier="fo1" opening_type="atrium" ceiling_only="False" layer_id="lay2">
      <Points><Point x="20" y="20"/><Point x="100" y="20"/><Point x="100" y="100"/><Point x="20" y="100"/></Points>
    </FloorOpening>
  </FloorOpenings>
  <Stairs>
    <Stair identifier="st_lflat" layer_id="lay1" start_x="150" start_y="60" direction_angle="0.0" start_level_id="lvl1" end_level_id="lvl2" stair_type="L-shaped" width="36" total_rise="106" riser_height="7.57" num_steps="14" tread_depth="10.5" total_run="136.5" has_left_rail="True" has_right_rail="True" rail_height="36" turn_direction="left" landing_depth="36" steps_before_landing="7" winder_count="0" opening_clearance="0" />
    <Stair identifier="st_lwind" layer_id="lay1" start_x="150" start_y="180" direction_angle="0.0" start_level_id="lvl1" end_level_id="lvl2" stair_type="L-shaped" width="36" total_rise="106" riser_height="7.57" num_steps="14" tread_depth="10.5" total_run="136.5" has_left_rail="True" has_right_rail="True" rail_height="36" turn_direction="right" landing_depth="36" steps_before_landing="5" winder_count="3" opening_clearance="0" />
    <Stair identifier="st_u" layer_id="lay1" start_x="280" start_y="180" direction_angle="0.0" start_level_id="lvl1" end_level_id="lvl2" stair_type="U-shaped" width="36" total_rise="106" riser_height="7.57" num_steps="14" tread_depth="10.5" total_run="136.5" has_left_rail="True" has_right_rail="True" rail_height="36" turn_direction="left" landing_depth="36" steps_before_landing="7" winder_count="0" opening_clearance="0" />
    <Stair identifier="st_sp" layer_id="lay1" start_x="320" start_y="320" direction_angle="0.0" start_level_id="lvl1" end_level_id="lvl2" stair_type="spiral" width="32" total_rise="106" riser_height="7.57" num_steps="14" tread_depth="10.5" total_run="100" has_left_rail="True" has_right_rail="True" rail_height="36" turn_direction="left" inner_radius="6" rotation_degrees="270" />
  </Stairs>
</Project>
"""
    xml_file = tmp_path / "stairs_and_atrium.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    proj = bridge.parse_estisketch_xml(str(xml_file))
    assert len(proj.stairs) == 4
    assert len(proj.floor_openings) == 1
    assert proj.stairs[1].winder_count == 3
    assert proj.stairs[3].inner_radius == pytest.approx(6.0)
    assert proj.stairs[3].rotation_degrees == pytest.approx(270.0)

    cutouts = bridge.compute_room_hole_cutouts(proj)
    assert any(c.source_id == "opening:fo1" and c.cuts_floor for c in cutouts["r2"])
    assert any(c.source_id == "opening:fo1" and c.cuts_ceiling for c in cutouts["r1"])
    assert any(c.source_id == "stair:st_sp" and c.cuts_floor for c in cutouts["r2"])

    for st in proj.stairs:
        rails = bridge.compute_stair_railing_paths_3d(st, 0.0)
        assert len(rails) == 2
        assert rails[0][0][2] == pytest.approx(0.0)
        assert rails[0][-1][2] == pytest.approx(106.0)
