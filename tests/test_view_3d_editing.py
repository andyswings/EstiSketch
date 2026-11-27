"""Headless tests for Phase 3 native 3D picking, editing gestures, paint brush, and 2D sync."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from EstiSketch import config, native_3d
from EstiSketch.Canvas.canvas_area import create_canvas_area
from EstiSketch.View3D.editor import (
    Editor3DController,
    _hex_to_rgb,
    canvas_in_to_world_m,
    ndc_from_widget_xy,
    select_from_hit,
    selected_entity_ids_from_canvas,
)
from EstiSketch.components import Door, Fixture, Room, Wall, Window
from EstiSketch.models.roof import EAVE, RoofEdge
from EstiSketch.roof_components import Roof
from EstiSketch.scene_ir import build_scene_ir_from_canvas
from EstiSketch.scene_ir.parsed import INCH_TO_M


def _make_sample_canvas() -> tuple[object, dict[str, object]]:
    """Build a deterministic headless CanvasArea with walls, split chain, openings, room, roof, fixture."""
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    canvas = create_canvas_area(cfg)
    layer_id = getattr(canvas.layers[0], "id", "layer_0")

    # 20' x 16' rectangular enclosure with a collinear split along top wall (0..120, 120..240)
    w_top_a = Wall(
        (0.0, 0.0), (120.0, 0.0), width=6.0, height=96.0, exterior_wall=True, layer_id=layer_id
    )
    w_top_b = Wall(
        (120.0, 0.0), (240.0, 0.0), width=6.0, height=96.0, exterior_wall=True, layer_id=layer_id
    )
    w_right = Wall(
        (240.0, 0.0), (240.0, 192.0), width=6.0, height=96.0, exterior_wall=True, layer_id=layer_id
    )
    w_bot = Wall(
        (240.0, 192.0), (0.0, 192.0), width=6.0, height=96.0, exterior_wall=True, layer_id=layer_id
    )
    w_left = Wall(
        (0.0, 192.0), (0.0, 0.0), width=6.0, height=96.0, exterior_wall=True, layer_id=layer_id
    )
    canvas.wall_sets = [[w_top_a, w_top_b, w_right, w_bot, w_left]]

    door = Door(
        door_type="single",
        width=36.0,
        height=80.0,
        swing="left",
        orientation="inswing",
        layer_id=layer_id,
    )
    window = Window(
        width=36.0, height=48.0, window_type="double_hung", layer_id=layer_id
    )
    canvas.doors = [(w_top_a, door, 0.5)]
    canvas.windows = [(w_top_b, window, 0.6)]

    room = Room(
        points=[(0.0, 0.0), (240.0, 0.0), (240.0, 192.0), (0.0, 192.0)],
        layer_id=layer_id,
    )
    room.name = "Living"
    room.floor_pattern = "tile_12"
    canvas.rooms = [room]

    roof = Roof(
        layer_id=layer_id,
        pitch_rise=6.0,
        overhang=12.0,
        material="asphalt_shingle",
        edges=[
            RoofEdge(wall_identifier=w_top_a.identifier, edge_type=EAVE),
            RoofEdge(wall_identifier=w_bot.identifier, edge_type=EAVE),
        ],
    )
    canvas.roofs = [roof]
    if hasattr(canvas, "recalculate_roof"):
        canvas.recalculate_roof(roof)

    fx = Fixture(
        symbol_type="base_cabinet",
        category="cabinet",
        x=60.0,
        y=120.0,
        width=36.0,
        depth=24.0,
        height=34.5,
        rotation=0.0,
        has_countertop=True,
        countertop_color=_hex_to_rgb("#D4CFC7"),
        fill_color=_hex_to_rgb("#EAE6DF"),
        layer_id=layer_id,
    )
    canvas.fixtures = [fx]
    canvas.save_state()  # Baseline snapshot for undo verification

    refs: dict[str, object] = {
        "w_top_a": w_top_a,
        "w_top_b": w_top_b,
        "w_right": w_right,
        "w_bot": w_bot,
        "w_left": w_left,
        "door": door,
        "window": window,
        "room": room,
        "roof": roof,
        "fx": fx,
    }
    return canvas, refs


@pytest.mark.skipif(
    not native_3d.is_native_3d_available(), reason="compiled _native_3d extension unavailable"
)
def test_native_session_picking_and_visibility_filters() -> None:
    canvas, refs = _make_sample_canvas()
    scene = build_scene_ir_from_canvas(canvas)
    session = native_3d.create_native_session()
    session.load_scene(scene.to_json())
    cx, cy = scene.plan_center_in

    # Pick top-left wall from exterior (-Y in 2D = +Y in 3D -> RightFace) and interior (LeftFace)
    wall_a: Wall = refs["w_top_a"]  # type: ignore[assignment]
    pt_hit_world = canvas_in_to_world_m((24.0, 0.0, 48.0), (cx, cy))
    raw_ext = session.pick_ray(
        (pt_hit_world[0], pt_hit_world[1] + 2.0, pt_hit_world[2]),
        (0.0, -1.0, 0.0),
    )
    hit_ext = native_3d.parse_pick_hit(raw_ext)
    assert hit_ext is not None
    assert hit_ext.entity_id == wall_a.identifier
    assert hit_ext.entity_kind == "wall"
    assert hit_ext.sub_part == "RightFace"

    # Pick from interior side hits LeftFace
    raw_int = session.pick_ray(
        (pt_hit_world[0], pt_hit_world[1] - 2.0, pt_hit_world[2]),
        (0.0, 1.0, 0.0),
    )
    hit_int = native_3d.parse_pick_hit(raw_int)
    assert hit_int is not None
    assert hit_int.entity_id == wall_a.identifier
    assert hit_int.entity_kind == "wall"
    assert hit_int.sub_part == "LeftFace"

    # Pick screen center after preset/fit + preview state methods
    session.set_camera_preset("iso")
    orig, direction = session.screen_ray(0.0, 0.0)
    assert math.isfinite(orig[0]) and abs(math.hypot(*direction) - 1.0) < 1e-4

    # Auto-hide roofs toggles picking through roof to floor
    session.set_auto_hide_roofs(False)
    room: Room = refs["room"]  # type: ignore[assignment]
    roof: Roof = refs["roof"]  # type: ignore[assignment]
    top_center = canvas_in_to_world_m((120.0, 96.0, 240.0), (cx, cy))
    top_hit = native_3d.parse_pick_hit(session.pick_ray(top_center, (0.0, 0.0, -1.0)))
    assert top_hit is not None
    assert top_hit.entity_id == roof.identifier

    session.set_dollhouse_level("level_0")
    session.set_auto_hide_roofs(True)
    floor_hit = native_3d.parse_pick_hit(session.pick_ray(top_center, (0.0, 0.0, -1.0)))
    assert floor_hit is not None
    assert floor_hit.entity_id == room.identifier
    assert floor_hit.sub_part == "Floor"

    # Verify highlight/preview FFI state setters accept valid inputs cleanly
    fx: Fixture = refs["fx"]  # type: ignore[assignment]
    session.set_selected_entities([fx.identifier])
    session.set_hovered_entity(wall_a.identifier, "LeftFace", True)
    session.set_transform_preview(fx.identifier, (0.0, 0.0, 0.0), (0.5, -0.2, 0.0), 0.25)
    session.clear_transform_preview()


def test_selection_sync_and_locked_layer_refusal() -> None:
    canvas, refs = _make_sample_canvas()
    fx: Fixture = refs["fx"]  # type: ignore[assignment]
    w_bot: Wall = refs["w_bot"]  # type: ignore[assignment]
    ctrl = Editor3DController()

    hit_fx = native_3d.PickHit(
        entity_id=fx.identifier,
        entity_kind="fixture",
        sub_part="CabinetBody",
        world_pos_m=(0.0, 0.0, 0.5),
        normal=(0.0, 0.0, 1.0),
        distance_m=2.0,
    )
    res = ctrl.handle_click(canvas, hit_fx)
    assert res.selected_ids == [fx.identifier]
    assert getattr(canvas, "selected_items") == [{"type": "fixture", "object": fx}]
    assert selected_entity_ids_from_canvas(canvas) == [fx.identifier]

    # Lock fixture object and confirm rotate, drag, and paint are refused without undo mutation
    fx.locked = True
    undo_before = len(getattr(canvas, "undo_stack"))
    rot_res = ctrl.rotate_selected_fixture(canvas, 15.0)
    assert not rot_res.mutated
    assert "Locked" in rot_res.hud_message
    assert len(getattr(canvas, "undo_stack")) == undo_before

    ctrl.set_tool("paint")
    paint_res = ctrl.handle_click(canvas, hit_fx)
    assert not paint_res.mutated
    assert len(getattr(canvas, "undo_stack")) == undo_before

    # Lock whole layer and confirm wall cannot be painted
    fx.locked = False
    canvas.layers[0].locked = True  # type: ignore[attr-defined]
    hit_wall = native_3d.PickHit(
        entity_id=w_bot.identifier,
        entity_kind="wall",
        sub_part="LeftFace",
        world_pos_m=(0.0, 0.0, 1.0),
        normal=(0.0, 1.0, 0.0),
        distance_m=2.0,
    )
    layer_res = ctrl.handle_click(canvas, hit_wall)
    assert not layer_res.mutated
    assert "Locked" in layer_res.hud_message
    assert len(getattr(canvas, "undo_stack")) == undo_before


def test_constrained_opening_drag_across_collinear_chain_and_single_undo() -> None:
    canvas, refs = _make_sample_canvas()
    door: Door = refs["door"]  # type: ignore[assignment]
    w_top_b: Wall = refs["w_top_b"]  # type: ignore[assignment]
    ctrl = Editor3DController()
    scene = build_scene_ir_from_canvas(canvas)
    plan_center = scene.plan_center_in

    start_world = canvas_in_to_world_m((60.0, 0.0, 40.0), plan_center)
    hit_door = native_3d.PickHit(
        entity_id=door.identifier,
        entity_kind="opening",
        sub_part="Leaf",
        world_pos_m=start_world,
        normal=(0.0, 1.0, 0.0),
        distance_m=3.0,
    )
    begin = ctrl.begin_drag(
        canvas,
        hit_door,
        ray_origin=(start_world[0], start_world[1] + 2.0, start_world[2]),
        ray_dir=(0.0, -1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert begin.handled

    # Drag door horizontally to x_in = 140 (across split onto w_top_b, but before window on w_top_b)
    target_world = canvas_in_to_world_m((140.0, 0.0, 40.0), plan_center)
    upd1 = ctrl.update_drag(
        canvas,
        ray_origin=(target_world[0], target_world[1] + 2.0, target_world[2]),
        ray_dir=(0.0, -1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert upd1.mutated and upd1.needs_mesh_sync
    assert "Clearance L:" in upd1.hud_message and "R:" in upd1.hud_message

    new_host, new_door, new_ratio = canvas.doors[0]  # type: ignore[attr-defined]
    assert new_door is door
    assert new_host is w_top_b
    assert 0.1 < new_ratio < 0.35

    # Try dragging past the window at w_top_b (ratio 0.6 -> x=192, window spans [174..210]): clamped < 174
    overshoot_world = canvas_in_to_world_m((230.0, 0.0, 40.0), plan_center)
    ctrl.update_drag(
        canvas,
        ray_origin=(overshoot_world[0], overshoot_world[1] + 2.0, overshoot_world[2]),
        ray_dir=(0.0, -1.0, 0.0),
        plan_center_in=plan_center,
    )
    clamped_host, _, clamped_ratio = canvas.doors[0]  # type: ignore[attr-defined]
    clamped_center_x = (
        120.0 + clamped_ratio * 120.0 if clamped_host is w_top_b else clamped_ratio * 120.0
    )
    assert clamped_center_x <= 156.5

    # Exactly one undo snapshot pushed on commit, and undo restores initial host & ratio
    undo_before = len(getattr(canvas, "undo_stack"))
    end_res = ctrl.end_drag(canvas)
    assert end_res.commit_undo
    assert len(getattr(canvas, "undo_stack")) == undo_before + 1
    assert getattr(canvas, "selected_items")[0]["object"] == canvas.doors[0]  # type: ignore[attr-defined]

    canvas.undo()  # type: ignore[attr-defined]
    restored_host, _, restored_ratio = canvas.doors[0]  # type: ignore[attr-defined]
    assert restored_host.identifier == refs["w_top_a"].identifier  # type: ignore[attr-defined]
    assert restored_ratio == pytest.approx(0.5, abs=1e-3)


def test_fixture_floor_drag_clamping_rotation_and_cancel() -> None:
    canvas, refs = _make_sample_canvas()
    fx: Fixture = refs["fx"]  # type: ignore[assignment]
    ctrl = Editor3DController()
    scene = build_scene_ir_from_canvas(canvas)
    plan_center = scene.plan_center_in

    start_world = canvas_in_to_world_m((60.0, 120.0, 18.0), plan_center)
    hit_fx = native_3d.PickHit(
        entity_id=fx.identifier,
        entity_kind="fixture",
        sub_part="CabinetBody",
        world_pos_m=start_world,
        normal=(0.0, 0.0, 1.0),
        distance_m=2.0,
    )
    ctrl.begin_drag(
        canvas,
        hit_fx,
        ray_origin=(start_world[0], start_world[1], start_world[2] + 3.0),
        ray_dir=(0.0, 0.0, -1.0),
        plan_center_in=plan_center,
    )

    # Attempt to drag out past left exterior wall (x = 0): clamp_fixture_out_of_walls stops it
    out_world = canvas_in_to_world_m((-40.0, 120.0, 18.0), plan_center)
    upd = ctrl.update_drag(
        canvas,
        ray_origin=(out_world[0], out_world[1], out_world[2] + 3.0),
        ray_dir=(0.0, 0.0, -1.0),
        plan_center_in=plan_center,
    )
    assert upd.preview_transform is not None
    assert upd.preview_transform[0] == fx.identifier
    assert not upd.needs_mesh_sync  # 60 FPS GPU preview skips full mesh rebuild during drag
    assert fx.x >= 20.5  # Half width (18") + half wall thickness (3") = 21"

    # Cancel restores exact original coordinates without pushing undo
    undo_before = len(getattr(canvas, "undo_stack"))
    cancel_res = ctrl.cancel_drag(canvas)
    assert cancel_res.clear_preview
    assert fx.x == pytest.approx(60.0)
    assert len(getattr(canvas, "undo_stack")) == undo_before

    # Rotate via keyboard step commits once
    select_from_hit(canvas, hit_fx)
    rot_res = ctrl.rotate_selected_fixture(canvas, 15.0)
    assert rot_res.commit_undo
    assert fx.rotation == pytest.approx(15.0)
    assert len(getattr(canvas, "undo_stack")) == undo_before + 1


def test_paint_brush_room_wide_and_eyedropper() -> None:
    canvas, refs = _make_sample_canvas()
    w_top_a: Wall = refs["w_top_a"]  # type: ignore[assignment]
    w_bot: Wall = refs["w_bot"]  # type: ignore[assignment]
    room: Room = refs["room"]  # type: ignore[assignment]
    roof: Roof = refs["roof"]  # type: ignore[assignment]
    fx: Fixture = refs["fx"]  # type: ignore[assignment]

    ctrl = Editor3DController()
    ctrl.set_tool("paint")
    ctrl.brush.wall_finish = "Stucco"
    ctrl.brush.wall_color = "#C87D55"
    ctrl.brush.floor_pattern = "wood_plank"
    ctrl.brush.roof_material = "metal"
    ctrl.brush.countertop_color = "#222222"

    # Single-side exterior wall paint hits RightFace only on w_top_a
    hit_right = native_3d.PickHit(
        entity_id=w_top_a.identifier,
        entity_kind="wall",
        sub_part="RightFace",
        world_pos_m=(0.0, 0.0, 1.0),
        normal=(0.0, 1.0, 0.0),
        distance_m=2.0,
    )
    ctrl.handle_click(canvas, hit_right, shift=False, alt=False)
    assert w_top_a.right_finish == "Stucco"
    assert w_top_a.right_color == pytest.approx(_hex_to_rgb("#C87D55"), abs=1e-3)
    assert w_top_a.left_finish != "Stucco"

    # Room-wide paint (Shift+Click on interior LeftFace of w_top_a -> interior faces of all 5 walls)
    ctrl.brush.wall_finish = "Tile"
    ctrl.brush.wall_color = "#FFFFFF"
    hit_interior = native_3d.PickHit(
        entity_id=w_top_a.identifier,
        entity_kind="wall",
        sub_part="LeftFace",
        world_pos_m=(0.0, 0.0, 1.0),
        normal=(0.0, -1.0, 0.0),
        distance_m=2.0,
    )
    rw_res = ctrl.handle_click(canvas, hit_interior, shift=True, alt=False)
    assert rw_res.mutated
    assert w_top_a.left_finish == "Tile"
    assert w_bot.left_finish == "Tile"
    # Exterior face stays unchanged
    assert w_top_a.right_finish == "Stucco"

    # Floor, roof, countertop painting
    ctrl.handle_click(
        canvas,
        native_3d.PickHit(room.identifier, "room", "Floor", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 1.0),
    )
    assert room.floor_pattern == "wood_plank"
    ctrl.handle_click(
        canvas,
        native_3d.PickHit(roof.identifier, "roof", "RoofDeck", (0.0, 0.0, 3.0), (0.0, 0.0, 1.0), 1.0),
    )
    assert roof.material == "metal"
    ctrl.handle_click(
        canvas,
        native_3d.PickHit(
            fx.identifier, "fixture", "RunCountertop", (0.0, 0.0, 0.9), (0.0, 0.0, 1.0), 1.0
        ),
    )
    assert fx.countertop_color == pytest.approx(_hex_to_rgb("#222222"), abs=1e-3)

    # Alt+Click Eyedropper samples Stucco right wall without mutating undo stack
    undo_before = len(getattr(canvas, "undo_stack"))
    eye_res = ctrl.handle_click(canvas, hit_right, shift=False, alt=True)
    assert eye_res.brush_sampled and not eye_res.mutated
    assert ctrl.brush.wall_finish == "Stucco"
    assert ctrl.brush.wall_color == "#C87D55"
    assert len(getattr(canvas, "undo_stack")) == undo_before


def test_wall_height_and_roof_pitch_direct_dragging() -> None:
    canvas, refs = _make_sample_canvas()
    w_top_a: Wall = refs["w_top_a"]  # type: ignore[assignment]
    roof: Roof = refs["roof"]  # type: ignore[assignment]
    ctrl = Editor3DController()
    scene = build_scene_ir_from_canvas(canvas)
    plan_center = scene.plan_center_in

    # Start near start endpoint TopEdge of w_top_a (t < 0.35 -> adjusts wall.height)
    top_start = canvas_in_to_world_m((12.0, 0.0, 96.0), plan_center)
    hit_top = native_3d.PickHit(
        entity_id=w_top_a.identifier,
        entity_kind="wall",
        sub_part="TopEdge",
        world_pos_m=top_start,
        normal=(0.0, 0.0, 1.0),
        distance_m=3.0,
    )
    b_res = ctrl.begin_drag(
        canvas,
        hit_top,
        ray_origin=(top_start[0], top_start[1] + 2.0, top_start[2]),
        ray_dir=(0.0, -1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert b_res.handled

    drag_z_up = top_start[2] + 12.0 * INCH_TO_M
    u_res = ctrl.update_drag(
        canvas,
        ray_origin=(top_start[0], top_start[1] + 2.0, drag_z_up),
        ray_dir=(0.0, -1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert u_res.mutated
    assert w_top_a.height == pytest.approx(108.0, abs=0.5)
    assert w_top_a.height_at_end == pytest.approx(96.0, abs=0.5)
    ctrl.end_drag(canvas)

    # Select roof first, then drag vertically to update roof.pitch_rise (clamped 1..18)
    roof_pt = canvas_in_to_world_m((120.0, 96.0, 130.0), plan_center)
    hit_roof = native_3d.PickHit(
        entity_id=roof.identifier,
        entity_kind="roof",
        sub_part="RoofDeck",
        world_pos_m=roof_pt,
        normal=(0.0, 0.0, 1.0),
        distance_m=3.0,
    )
    ctrl.handle_click(canvas, hit_roof)
    r_begin = ctrl.begin_drag(
        canvas,
        hit_roof,
        ray_origin=(roof_pt[0], roof_pt[1] - 2.0, roof_pt[2]),
        ray_dir=(0.0, 1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert r_begin.handled
    r_upd = ctrl.update_drag(
        canvas,
        ray_origin=(roof_pt[0], roof_pt[1] - 2.0, roof_pt[2] + 12.0 * INCH_TO_M),
        ray_dir=(0.0, 1.0, 0.0),
        plan_center_in=plan_center,
    )
    assert r_upd.mutated
    assert roof.pitch_rise == pytest.approx(9.0, abs=0.5)
    assert "9/12" in r_upd.hud_message
    ctrl.end_drag(canvas)

    # Widget-to-NDC smoke check
    nx, ny = ndc_from_widget_xy(0.0, 0.0, 800.0, 600.0)
    assert (nx, ny) == pytest.approx((-1.0, 1.0))
