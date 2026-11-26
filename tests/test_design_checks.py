"""Headless tests for architectural layout checks and interactive wall clamping."""
from __future__ import annotations

from types import SimpleNamespace

import gi

gi.require_version("Gtk", "4.0")

import pytest  # noqa: E402

from EstiSketch import config  # noqa: E402
from EstiSketch.Canvas.canvas_area import CanvasArea  # noqa: E402
from EstiSketch.components import (  # noqa: E402
    Door,
    Fixture,
    Hole,
    Layer,
    Level,
    Room,
    Stair,
    Wall,
)
from EstiSketch.geometry.design_checks import (  # noqa: E402
    bathtub_drain_wall_violations,
    bathroom_clearance_violations,
    clamp_fixture_out_of_walls,
    fixture_door_violations,
    fixture_wall_violations,
    laundry_appliance_violations,
    pocket_door_violations,
    sink_and_vanity_clearance_violations,
    stair_landing_and_access_violations,
)


def _room_box() -> list[Wall]:
    return [
        Wall((0.0, 0.0), (200.0, 0.0), 6.0, 96.0, exterior_wall=True, layer_id="l1"),
        Wall((200.0, 0.0), (200.0, 200.0), 6.0, 96.0, exterior_wall=True, layer_id="l1"),
        Wall((200.0, 200.0), (0.0, 200.0), 6.0, 96.0, exterior_wall=True, layer_id="l1"),
        Wall((0.0, 200.0), (0.0, 0.0), 6.0, 96.0, exterior_wall=True, layer_id="l1"),
    ]


def test_fixture_wall_violations_and_clamping() -> None:
    walls = _room_box()
    layer_map = {"l1": "lvl1"}

    # Flush inside east wall (x_in = 197", bed depth 75" rotated 90 -> center at 159.5")
    bed_ok = Fixture("bed_twin", x=159.5, y=40.0, width=39.0, depth=75.0, rotation=90.0, layer_id="l1")
    assert fixture_wall_violations([bed_ok], walls, layer_map) == []

    # Extending through east exterior wall
    bed_bad = Fixture("bed_twin", x=185.0, y=40.0, width=39.0, depth=75.0, rotation=90.0, layer_id="l1")
    viols = fixture_wall_violations([bed_bad], walls, layer_map)
    assert len(viols) == 1 and "exterior wall" in viols[0]

    # Clamping pushes it back inside flush with inner face (197 - 37.5 = 159.5)
    assert clamp_fixture_out_of_walls(bed_bad, walls, orig_pos=(150.0, 40.0)) is True
    assert bed_bad.x <= 159.5 + 1e-3
    assert fixture_wall_violations([bed_bad], walls, layer_map) == []

    # Dragging across an interior wall resolves to the destination side without resting in it
    int_wall = Wall((100.0, 0.0), (100.0, 200.0), 4.5, 96.0, exterior_wall=False, layer_id="l1")
    chair = Fixture("armchair", x=101.0, y=100.0, width=34.0, depth=34.0, rotation=0.0, layer_id="l1")
    assert clamp_fixture_out_of_walls(chair, [int_wall], orig_pos=(60.0, 100.0)) is True
    assert chair.x >= 100.0 + 2.25 + 17.0 - 1e-3
    assert fixture_wall_violations([chair], [int_wall], layer_map) == []


def test_canvas_fixture_preview_clamped_inside_exterior_wall() -> None:
    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)
    lid = canvas.active_layer_id
    canvas.wall_sets.append([
        Wall((0.0, 0.0), (200.0, 0.0), 6.0, 96.0, exterior_wall=True, layer_id=lid),
        Wall((200.0, 0.0), (200.0, 200.0), 6.0, 96.0, exterior_wall=True, layer_id=lid),
        Wall((200.0, 200.0), (0.0, 200.0), 6.0, 96.0, exterior_wall=True, layer_id=lid),
        Wall((0.0, 200.0), (0.0, 0.0), 6.0, 96.0, exterior_wall=True, layer_id=lid),
    ])
    canvas.active_fixture_type = "bed_twin"
    canvas.active_fixture_rotation = 90.0
    ghost = canvas._build_fixture_preview(195.0, 50.0)
    assert fixture_wall_violations([ghost], canvas.wall_sets[0], {lid: canvas.active_level_id}) == []


def test_fixture_door_violations() -> None:
    w_s = Wall((0.0, 200.0), (200.0, 200.0), 6.0, 96.0, exterior_wall=True, layer_id="l1")
    # Tangent along w_s is +X, normal p = (0, +1); inswing is +p, outswing is -p (inside room)
    d_in = Door("single", 36.0, 80.0, swing="left", orientation="outswing", layer_id="l1")
    d_slide = Door("sliding", 72.0, 80.0, swing="left", orientation="inswing", layer_id="l1")
    layer_map = {"l1": "lvl1"}

    blocker = Fixture("dryer", x=100.0, y=180.0, width=27.0, depth=30.0, layer_id="l1")
    clear = Fixture("dryer", x=40.0, y=180.0, width=27.0, depth=30.0, layer_id="l1")

    assert len(fixture_door_violations([blocker], [(w_s, d_in, 0.5)], layer_map)) == 1
    assert fixture_door_violations([clear], [(w_s, d_in, 0.5)], layer_map) == []
    assert fixture_door_violations([blocker], [(w_s, d_slide, 0.5)], layer_map) == []


def test_stair_landing_flushness_and_accessibility_checks() -> None:
    lvl1 = Level(id="lvl1", name="Level 1", elevation=0.0, height=96.0, floor_thickness=10.0)
    lvl2 = Level(id="lvl2", name="Level 2", elevation=106.0, height=96.0, floor_thickness=10.0)
    layer_map = {"l1": "lvl1", "l2": "lvl2"}

    r1 = Room([(0.0, 0.0), (300.0, 0.0), (300.0, 300.0), (0.0, 300.0)], layer_id="l1")
    r2 = Room([(0.0, 0.0), (300.0, 0.0), (300.0, 300.0), (0.0, 300.0)], layer_id="l2")
    r2.holes = [Hole("stair:st1", [(98.0, 78.0), (222.0, 78.0), (222.0, 122.0), (98.0, 122.0)])]

    stair_ok = Stair(
        identifier="st1", layer_id="l1", start_point=(100.0, 100.0), direction_angle=0.0,
        start_level_id="lvl1", end_level_id="lvl2", stair_type="straight",
        width=36.0, total_rise=106.0, num_steps=14, tread_depth=10.0, total_run=120.0,
    )
    assert stair_landing_and_access_violations(
        [stair_ok], [], [r1, r2], [], [], [lvl1, lvl2], layer_map
    ) == []

    # 1. Total rise mismatch (not flush with 2nd story)
    stair_bad_rise = Stair(
        identifier="st1", layer_id="l1", start_point=(100.0, 100.0), direction_angle=0.0,
        start_level_id="lvl1", end_level_id="lvl2", stair_type="straight",
        width=36.0, total_rise=96.0, num_steps=14, tread_depth=10.0, total_run=120.0,
    )
    v_rise = stair_landing_and_access_violations(
        [stair_bad_rise], [], [r1, r2], [], [], [lvl1, lvl2], layer_map
    )
    assert any("not flush" in m for m in v_rise)

    # 2. Missing top landing: wall crosses directly across top step at x=230"
    w_top_block = Wall((230.0, 0.0), (230.0, 200.0), 4.5, 96.0, layer_id="l2")
    v_top = stair_landing_and_access_violations(
        [stair_ok], [w_top_block], [r1, r2], [], [], [lvl1, lvl2], layer_map
    )
    assert any("top landing" in m for m in v_top)

    # 3. Enclosed bottom landing (surrounded by walls with no door)
    enclosure = [
        Wall((62.0, 80.0), (100.0, 80.0), 4.5, 96.0, layer_id="l1"),
        Wall((62.0, 80.0), (62.0, 120.0), 4.5, 96.0, layer_id="l1"),
        Wall((62.0, 120.0), (100.0, 120.0), 4.5, 96.0, layer_id="l1"),
    ]
    v_enc = stair_landing_and_access_violations(
        [stair_ok], enclosure, [r1, r2], [], [], [lvl1, lvl2], layer_map
    )
    assert any("enclosed" in m for m in v_enc)

    # Adding a 36" door through the west enclosure wall makes the bottom landing accessible
    access_door = Door(
        "single", 36.0, 80.0, swing="left", orientation="outswing", layer_id="l1"
    )
    v_open = stair_landing_and_access_violations(
        [stair_ok], enclosure, [r1, r2], [(enclosure[1], access_door, 0.5)], [], [lvl1, lvl2],
        layer_map,
    )
    assert not any("enclosed" in m for m in v_open)


def test_pocket_door_and_properties_dock_width() -> None:
    from EstiSketch.Dialogs.properties_dock import DoorPropertiesWidget

    w = Wall((0.0, 0.0), (100.0, 0.0), 4.5, 96.0, layer_id="l1")
    layer_map = {"l1": "lvl1"}

    # 36" pocket door needs 74" total width -> at ratio 0.3 (x=30), left pocket goes to -26"
    pkt_bad = Door("pocket", 36.0, 80.0, swing="left", orientation="inswing", layer_id="l1")
    assert pocket_door_violations([(w, pkt_bad, 0.30)], [w], [], layer_map)

    # At ratio 0.7 (x=70), spans [14, 88] cleanly inside [0, 100]
    assert pocket_door_violations([(w, pkt_bad, 0.70)], [w], [], layer_map) == []

    # DoorPropertiesWidget displays 6' 2" (74") for 36" pocket door
    dpw = DoorPropertiesWidget()
    dpw.set_door((w, pkt_bad, 0.70))
    assert dpw.pocket_width_row.get_visible() is True
    assert '74"' in dpw.pocket_width_label.get_text()
    assert "6' 2\"" in dpw.pocket_width_label.get_text()


def test_bathroom_sink_tub_drain_and_laundry_checks() -> None:
    walls = _room_box()
    layer_map = {"l1": "lvl1"}
    bath = Room([(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)], layer_id="l1")
    bath.name = "Full Bath"
    bath.room_type = "bathroom"
    entry = Door("single", 32.0, 80.0, swing="left", orientation="inswing", layer_id="l1")

    # 1. Bathroom door ingress blocked & toilet inside door swing
    toilet_in_swing = Fixture(
        "toilet", x=98.0, y=18.0, width=18.0, depth=28.0, rotation=0.0, layer_id="l1"
    )
    assert fixture_door_violations([toilet_in_swing], [(walls[0], entry, 0.5)], layer_map)
    assert bathroom_clearance_violations(
        [(walls[0], entry, 0.5)], [toilet_in_swing], [bath], walls, layer_map
    )

    # Toilet clear of door swing & with 21" front clearance passes
    toilet_ok = Fixture(
        "toilet", x=180.0, y=20.0, width=18.0, depth=28.0, rotation=0.0, layer_id="l1"
    )
    assert fixture_door_violations([toilet_ok], [(walls[0], entry, 0.5)], layer_map) == []
    assert bathroom_clearance_violations(
        [(walls[0], entry, 0.5)], [toilet_ok], [bath], walls, layer_map
    ) == []

    # 2. Vanity/sink 21" front clearance check
    vanity_bad = Fixture(
        "vanity_single", x=180.0, y=180.0, width=36.0, depth=21.0, rotation=0.0, layer_id="l1"
    )
    assert sink_and_vanity_clearance_violations([vanity_bad], walls, layer_map)
    vanity_ok = Fixture(
        "vanity_single", x=180.0, y=150.0, width=36.0, depth=21.0, rotation=0.0, layer_id="l1"
    )
    assert sink_and_vanity_clearance_violations([vanity_ok], walls, layer_map) == []

    # 3. Bathtub drain end (-X local) must butt against a plumbing wall (stub wall counts)
    tub_floating = Fixture(
        "bathtub", x=100.0, y=180.0, width=60.0, depth=30.0, rotation=0.0, layer_id="l1"
    )
    assert bathtub_drain_wall_violations([tub_floating], walls, layer_map)
    stub_wall = Wall((68.0, 165.0), (68.0, 197.0), 4.5, 96.0, layer_id="l1")
    assert bathtub_drain_wall_violations([tub_floating], walls + [stub_wall], layer_map) == []

    # 4. Laundry front-loader 30" clearance & bi-fold door swing check
    washer_blocked = Fixture(
        "washer", x=180.0, y=180.0, width=27.0, depth=30.0, rotation=0.0, layer_id="l1"
    )
    assert laundry_appliance_violations([washer_blocked], [], walls, layer_map)
    washer_ok = Fixture(
        "washer", x=100.0, y=18.0, width=27.0, depth=30.0, rotation=0.0, layer_id="l1"
    )
    assert laundry_appliance_violations([washer_ok], [], walls, layer_map) == []
    bifold_in = Door("bi-fold", 36.0, 80.0, swing="left", orientation="outswing", layer_id="l1")
    assert fixture_door_violations([washer_ok], [(walls[0], bifold_in, 0.5)], layer_map)
