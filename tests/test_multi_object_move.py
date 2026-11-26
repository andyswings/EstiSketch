"""Headless tests for multi-object selection & dragging across canvas types."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from EstiSketch import config
from EstiSketch.Canvas import canvas_area
from EstiSketch.Canvas.multi_move import (
    apply_multi_drag_delta,
    capture_multi_drag_snapshot,
    finalize_multi_drag,
)
from EstiSketch.components import (
    Arc,
    Circle,
    Dimension,
    DimensionChain,
    Door,
    Fixture,
    FloorOpening,
    LeaderCallout,
    Polyline,
    Room,
    Stair,
    Text,
    Wall,
)


def _make_canvas():
    cfg = SimpleNamespace(**config.DEFAULT_SETTINGS)
    c = canvas_area.create_canvas_area(cfg)
    c.tool_mode = "pointer"
    c.zoom = 1.0
    c.offset_x = 0.0
    c.offset_y = 0.0
    c.save_state()
    return c


def _drag_canvas(canvas, start_m: tuple[float, float], end_m: tuple[float, float]) -> None:
    """Simulate a pointer press + drag + release in model inches."""
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    sx = start_m[0] * canvas.zoom * ppi + canvas.offset_x
    sy = start_m[1] * canvas.zoom * ppi + canvas.offset_y
    ox = (end_m[0] - start_m[0]) * canvas.zoom * ppi
    oy = (end_m[1] - start_m[1]) * canvas.zoom * ppi

    gesture = SimpleNamespace(
        get_current_event=lambda: SimpleNamespace(
            get_modifier_state=lambda: 0,
            state=0,
        ),
        set_state=lambda _s: None,
    )
    canvas.on_click_pressed(gesture, 1, sx, sy)
    canvas.on_drag_begin(gesture, sx, sy)
    canvas.on_drag_update(gesture, ox, oy)
    canvas.on_drag_end(gesture, ox, oy)
    canvas.on_click(gesture, 1, sx + ox, sy + oy)


def test_multi_wall_drag_preserves_shared_joints_and_stretches_adjacent():
    c = _make_canvas()
    lid = c.active_layer_id
    w1 = Wall((0.0, 0.0), (100.0, 0.0), width=6.0, height=96.0, identifier="w1", layer_id=lid)
    w2 = Wall((100.0, 0.0), (100.0, 100.0), width=6.0, height=96.0, identifier="w2", layer_id=lid)
    w3 = Wall((100.0, 100.0), (0.0, 100.0), width=6.0, height=96.0, identifier="w3", layer_id=lid)
    c.wall_sets = [[w1, w2, w3]]

    # Select w1 and w2, leaving w3 unselected (connected at (100, 100))
    c.selected_items = [
        {"type": "wall", "object": w1},
        {"type": "wall", "object": w2},
    ]

    # Press on w1 (center at 50, 0) and drag (+20, +30)
    _drag_canvas(c, (50.0, 0.0), (70.0, 30.0))

    assert w1.start == pytest.approx((20.0, 30.0))
    assert w1.end == pytest.approx((120.0, 30.0))
    assert w2.start == pytest.approx((120.0, 30.0))
    assert w2.end == pytest.approx((120.0, 130.0))
    # Unselected adjoining w3 start stretched to stay connected to w2.end, w3.end stayed put
    assert w3.start == pytest.approx((120.0, 130.0))
    assert w3.end == pytest.approx((0.0, 100.0))


def test_mixed_object_multi_drag_without_double_move_and_undo():
    c = _make_canvas()
    lid = c.active_layer_id
    w = Wall((0.0, 0.0), (120.0, 0.0), width=6.0, height=96.0, identifier="w1", layer_id=lid)
    door = Door("single", 36.0, 80.0, "left", "in", identifier="d1", layer_id=lid)
    room = Room(
        [(0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0)],
        identifier="r1",
        layer_id=lid,
    )
    opening = FloorOpening(
        [(10.0, 10.0), (40.0, 10.0), (40.0, 40.0), (10.0, 40.0)],
        identifier="fo1",
        layer_id=lid,
    )
    fix = Fixture(
        symbol_type="toilet",
        x=80.0,
        y=80.0,
        width=20.0,
        depth=28.0,
        identifier="fx1",
        layer_id=lid,
    )
    stair = Stair(
        start_point=(50.0, 50.0),
        direction_angle=0.0,
        num_steps=10,
        width=36.0,
        identifier="st1",
        layer_id=lid,
    )
    txt = Text(x=60.0, y=90.0, content="Living", identifier="t1", layer_id=lid)
    dim = Dimension((0.0, -20.0), (120.0, -20.0), 10.0, identifier="dm1", layer_id=lid)
    dchain = DimensionChain([(0.0, 130.0), (60.0, 130.0), (120.0, 130.0)], identifier="dc1", layer_id=lid)
    callout = LeaderCallout(
        tip=(10.0, 10.0), elbow=(30.0, 30.0), shoulder=(50.0, 30.0),
        text="Note", identifier="lc1", layer_id=lid,
    )
    circle = Circle((200.0, 50.0), 15.0, identifier="c1", layer_id=lid)
    arc = Arc((200.0, 120.0), 20.0, 0.0, 1.5, identifier="a1", layer_id=lid)
    poly = Polyline((150.0, 10.0), (180.0, 40.0), identifier="p1", layer_id=lid)

    c.wall_sets = [[w]]
    c.doors = [(w, door, 0.5)]
    c.rooms = [room]
    c.floor_openings = [opening]
    c.fixtures = [fix]
    c.stairs = [stair]
    c.texts = [txt]
    c.dimensions = [dim]
    c.dimension_chains = [dchain]
    c.leader_callouts = [callout]
    c.circles = [circle]
    c.arcs = [arc]
    c.polyline_sets = [[poly]]
    c.save_state()

    # Include both whole room AND room vertices + hosted door to verify zero double-moves
    c.selected_items = [
        {"type": "wall", "object": w},
        {"type": "door", "object": (w, door, 0.5)},
        {"type": "room", "object": room},
        {"type": "vertex", "object": (room, 0)},
        {"type": "vertex", "object": (room, 1)},
        {"type": "floor_opening", "object": opening},
        {"type": "opening_vertex", "object": (opening, 0)},
        {"type": "fixture", "object": fix},
        {"type": "stair", "object": stair},
        {"type": "text", "object": txt},
        {"type": "dimension", "object": dim},
        {"type": "dimension_chain", "object": dchain},
        {"type": "leader_callout", "object": callout},
        {"type": "circle", "object": circle},
        {"type": "arc", "object": arc},
        {"type": "polyline", "object": poly},
    ]

    # Even pressing directly on the text moves ALL selected items, not only the text
    _drag_canvas(c, (60.0, 90.0), (100.0, 75.0))  # dx=+40, dy=-15

    assert w.start == pytest.approx((40.0, -15.0))
    assert w.end == pytest.approx((160.0, -15.0))
    assert room.points[0] == pytest.approx((40.0, -15.0))
    assert room.points[2] == pytest.approx((160.0, 105.0))
    assert opening.points[0] == pytest.approx((50.0, -5.0))
    assert (fix.x, fix.y) == pytest.approx((120.0, 65.0))
    assert stair.start_point == pytest.approx((90.0, 35.0))
    assert (txt.x, txt.y) == pytest.approx((100.0, 75.0))
    assert dim.start == pytest.approx((40.0, -35.0))
    assert dchain.points[1] == pytest.approx((100.0, 115.0))
    assert callout.tip == pytest.approx((50.0, -5.0))
    assert circle.center == pytest.approx((240.0, 35.0))
    assert arc.center == pytest.approx((240.0, 105.0))
    assert poly.start == pytest.approx((190.0, -5.0))


def test_click_without_drag_collapses_multiselection_and_respects_locked():
    c = _make_canvas()
    lid = c.active_layer_id
    locked_lid = c.add_layer("Locked")
    c.get_layer_by_id(locked_lid).locked = True

    c1 = Circle((50.0, 50.0), 20.0, identifier="c1", layer_id=lid)
    c2 = Circle((150.0, 50.0), 20.0, identifier="c2", layer_id=lid)
    c_locked = Circle((250.0, 50.0), 20.0, identifier="c3", layer_id=locked_lid)
    c.circles = [c1, c2, c_locked]

    # Locked object stays fixed while unlocked items move
    snap = capture_multi_drag_snapshot(c, [
        {"type": "circle", "object": c1},
        {"type": "circle", "object": c2},
        {"type": "circle", "object": c_locked},
    ])
    apply_multi_drag_delta(c, snap, 25.0, -10.0)
    finalize_multi_drag(c, snap)
    assert c1.center == pytest.approx((75.0, 40.0))
    assert c2.center == pytest.approx((175.0, 40.0))
    assert c_locked.center == pytest.approx((250.0, 50.0))

    # Plain click without drag on c2's top perimeter collapses selection to [c2]
    c.selected_items = [{"type": "circle", "object": c1}, {"type": "circle", "object": c2}]
    _drag_canvas(c, (175.0, 20.0), (175.0, 20.0))
    assert len(c.selected_items) == 1
    assert c.selected_items[0]["object"] is c2
