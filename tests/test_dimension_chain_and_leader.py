import os
import tempfile
import pytest
import math
from types import SimpleNamespace
import gi
gi.require_version("Gtk", "4.0")

from unittest.mock import MagicMock
from EstiSketch.components import DimensionChain, LeaderCallout, Wall, Door, Window, Stair, Room
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch import config
from EstiSketch.project_io import save_project, open_project


@pytest.fixture
def canvas():
    cfg = SimpleNamespace(**config.load_config())
    cv = CanvasArea(cfg)
    return cv


def test_dimension_chain_dataclass_and_sorting():
    # p0=(0, 0), p1=(100, 0) establish baseline. Others added out of order.
    pts = [(0.0, 0.0), (100.0, 0.0), (50.0, 10.0), (25.0, 0.0), (75.0, 2.0)]
    chain = DimensionChain(
        points=pts,
        offset=30.0,
        identifier="dim_chain_1",
        layer_id="default"
    )

    sorted_pts = chain.get_sorted_points()
    assert len(sorted_pts) == 5
    # First point projected should correspond to x=0
    assert sorted_pts[0] == (0.0, 0.0)
    assert sorted_pts[1] == (25.0, 0.0)
    assert sorted_pts[2] == (50.0, 10.0)
    assert sorted_pts[3] == (75.0, 2.0)
    assert sorted_pts[4] == (100.0, 0.0)

    # Total length should be 100.0
    assert pytest.approx(chain.total_length, 0.01) == 100.0
    assert pytest.approx(chain.get_total_length(), 0.01) == 100.0


def test_leader_callout_dataclass():
    leader = LeaderCallout(
        tip=(10.0, 20.0),
        elbow=(30.0, 50.0),
        shoulder=(60.0, 50.0),
        text="2x6 Stud @ 16\" O.C.\nExterior Sheathing",
        identifier="lead_1",
        layer_id="default",
        text_size=14.0,
        box_border=True,
        arrow_type="arrow",
        line_style="solid"
    )
    assert leader.tip == (10.0, 20.0)
    assert leader.elbow == (30.0, 50.0)
    assert leader.shoulder == (60.0, 50.0)
    assert leader.box_border is True
    assert leader.arrow_type == "arrow"
    assert "2x6 Stud" in leader.text


def test_leader_snapping_to_wall_faces(canvas):
    # Wall from (0, 0) to (200, 0), width 10.0, height 96.0
    wall = Wall((0.0, 0.0), (200.0, 0.0), width=10.0, height=96.0, identifier="w1")
    canvas.walls = [wall]

    # Target near wall outer face (y = 5.0)
    snapped_outer = canvas._snap_leader_target(100.0, 6.0)
    assert pytest.approx(snapped_outer[0], 0.01) == 100.0
    assert pytest.approx(snapped_outer[1], 0.01) == 5.0

    # Target near wall inner face (y = -5.0)
    snapped_inner = canvas._snap_leader_target(100.0, -4.0)
    assert pytest.approx(snapped_inner[0], 0.01) == 100.0
    assert pytest.approx(snapped_inner[1], 0.01) == -5.0

    # Target far from wall should not snap
    unsnapped = canvas._snap_leader_target(100.0, 100.0)
    assert unsnapped == (100.0, 100.0)


def test_leader_snapping_to_door_and_window(canvas):
    wall = Wall((0.0, 0.0), (200.0, 0.0), width=10.0, height=96.0, identifier="w1")
    canvas.walls = [wall]
    # Door at center (100, 0) -> ratio 0.5
    door = Door("single", width=36.0, height=80.0, swing="left", orientation="inswing", identifier="d1")
    canvas.doors = [(wall, door, 0.5)]
    # Window at (50, 0) -> ratio 0.25
    window = Window(width=30.0, height=48.0, window_type="standard", identifier="win1")
    canvas.windows = [(wall, window, 0.25)]

    # Snap near door
    snapped_door = canvas._snap_leader_target(103.0, 2.0)
    assert pytest.approx(snapped_door[0], 0.01) == 100.0
    assert pytest.approx(snapped_door[1], 0.01) == 0.0

    # Snap near window
    snapped_window = canvas._snap_leader_target(52.0, -1.0)
    assert pytest.approx(snapped_window[0], 0.01) == 50.0
    assert pytest.approx(snapped_window[1], 0.01) == 0.0


def test_xml_roundtrip_dimension_chains_and_leaders(canvas):
    chain = DimensionChain(
        points=[(10.0, 10.0), (110.0, 10.0), (60.0, 10.0)],
        offset=25.0,
        identifier="chain_test_xml",
        layer_id="default",
        witness_gap=6.0,
        witness_overhang=8.0,
        summary_dimension=True,
        summary_offset=45.0,
        arrow_style="architectural_tick",
        text_size=11.0
    )
    canvas.dimension_chains.append(chain)

    leader = LeaderCallout(
        tip=(50.0, 50.0),
        elbow=(80.0, 80.0),
        shoulder=(120.0, 80.0),
        text="Specification Note\nField Verify",
        identifier="leader_test_xml",
        layer_id="default",
        text_size=13.0,
        box_border=True,
        arrow_type="dot",
        line_style="dashed"
    )
    canvas.leader_callouts.append(leader)

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Save project
        save_project(canvas, 1024, 900, tmp_path)

        # Create new canvas to restore
        cfg = SimpleNamespace(**config.load_config())
        cv2 = CanvasArea(cfg)
        open_project(cv2, tmp_path)

        assert len(cv2.dimension_chains) == 1
        rc = cv2.dimension_chains[0]
        assert rc.identifier == "chain_test_xml"
        assert rc.offset == 25.0
        assert len(rc.points) == 3
        assert rc.points[0] == (10.0, 10.0)
        assert rc.points[1] == (110.0, 10.0)
        assert rc.points[2] == (60.0, 10.0)
        assert rc.summary_dimension is True
        assert rc.summary_offset == 45.0
        assert rc.arrow_style == "architectural_tick"
        assert rc.text_size == 11.0

        assert len(cv2.leader_callouts) == 1
        rl = cv2.leader_callouts[0]
        assert rl.identifier == "leader_test_xml"
        assert rl.tip == (50.0, 50.0)
        assert rl.elbow == (80.0, 80.0)
        assert rl.shoulder == (120.0, 80.0)
        assert "Specification Note" in rl.text
        assert rl.box_border is True
        assert rl.arrow_type == "dot"
        assert rl.line_style == "dashed"
        assert rl.text_size == 13.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_canvas_undo_redo_and_deletion(canvas):
    chain = DimensionChain(
        points=[(0.0, 0.0), (50.0, 0.0)],
        offset=15.0,
        identifier="dim_c1"
    )
    leader = LeaderCallout(
        tip=(0.0, 0.0),
        elbow=(10.0, 10.0),
        shoulder=(20.0, 10.0),
        text="Note",
        identifier="lead_c1"
    )
    canvas.dimension_chains.append(chain)
    canvas.leader_callouts.append(leader)
    canvas.save_state()

    assert len(canvas.dimension_chains) == 1
    assert len(canvas.leader_callouts) == 1

    # Select both and delete
    canvas.selected_items = [
        {"type": "dimension_chain", "object": chain},
        {"type": "leader_callout", "object": leader}
    ]
    canvas.delete_selected()
    canvas.save_state()

    assert len(canvas.dimension_chains) == 0
    assert len(canvas.leader_callouts) == 0

    # Undo deletion
    canvas.undo()
    assert len(canvas.dimension_chains) == 1
    assert len(canvas.leader_callouts) == 1
    assert canvas.dimension_chains[0].identifier == "dim_c1"
    assert canvas.leader_callouts[0].identifier == "lead_c1"

    # Redo deletion
    canvas.redo()
    assert len(canvas.dimension_chains) == 0
    assert len(canvas.leader_callouts) == 0


def test_copy_and_paste(canvas):
    chain = DimensionChain(
        points=[(0.0, 0.0), (100.0, 0.0), (50.0, 0.0)],
        offset=20.0,
        identifier="chain_orig"
    )
    leader = LeaderCallout(
        tip=(10.0, 10.0),
        elbow=(20.0, 30.0),
        shoulder=(40.0, 30.0),
        text="Original Note",
        identifier="leader_orig"
    )
    canvas.dimension_chains.append(chain)
    canvas.leader_callouts.append(leader)

    canvas.selected_items = [
        {"type": "dimension_chain", "object": chain},
        {"type": "leader_callout", "object": leader}
    ]
    canvas.copy_selected()
    canvas.paste()

    assert len(canvas.dimension_chains) == 2
    assert len(canvas.leader_callouts) == 2
    # Pasted items should have new identifiers and offset positions (12, 12)
    pasted_chain = canvas.dimension_chains[1]
    pasted_leader = canvas.leader_callouts[1]
    assert pasted_chain.identifier != "chain_orig"
    assert pasted_leader.identifier != "leader_orig"
    assert pasted_chain.points[0] == (12.0, 12.0)
    assert pasted_leader.tip == (22.0, 22.0)


def test_properties_dock_dimension_chain_and_leader(canvas):
    from EstiSketch.Dialogs.properties_dock import DimensionChainPropertiesWidget, LeaderCalloutPropertiesWidget

    dim_widget = DimensionChainPropertiesWidget(canvas)
    chain = DimensionChain(
        points=[(0.0, 0.0), (100.0, 0.0)],
        offset=20.0,
        identifier="chain_dock"
    )
    dim_widget.set_chain(chain)
    assert dim_widget.offset_spin.get_value() == 20.0

    # Modify offset via spin button
    dim_widget.offset_spin.set_value(35.0)
    assert chain.offset == 35.0

    # Test LeaderCalloutPropertiesWidget
    leader_widget = LeaderCalloutPropertiesWidget(canvas)
    leader = LeaderCallout(
        tip=(0.0, 0.0),
        elbow=(10.0, 10.0),
        shoulder=(20.0, 10.0),
        text="Original",
        identifier="lead_dock",
        text_size=12.0
    )
    leader_widget.set_leader(leader)
    
    # Change text buffer
    buf = leader_widget.text_view.get_buffer()
    buf.set_text("Updated Callout Note")
    assert leader.text == "Updated Callout Note"

    # Change text size
    leader_widget.text_size_spin.set_value(16.0)
    assert leader.text_size == 16.0


def test_dimension_chain_selection_inside_room_and_witness_lines(canvas):
    canvas.tool_mode = "pointer"
    # Create room surrounding area (0, 0) to (300, 300)
    room = Room([(0.0, 0.0), (300.0, 0.0), (300.0, 300.0), (0.0, 300.0)])
    canvas.rooms.append(room)

    # Chain inside room: baseline (50, 100) to (200, 100), offset 20.0 -> dim line at y = 120
    chain = DimensionChain(
        points=[(50.0, 100.0), (200.0, 100.0)],
        offset=20.0,
        identifier="chain_in_room"
    )
    canvas.dimension_chains.append(chain)

    gesture = MagicMock()
    event = MagicMock()
    event.get_modifier_state.return_value = 0
    gesture.get_current_event.return_value = event

    # 1. Click dimension line inside room -> must select dimension chain, NOT room
    click_x, click_y = canvas.model_to_device(120.0, 120.0, 2.0)
    canvas._handle_pointer_click(gesture, 1, click_x, click_y)
    assert len(canvas.selected_items) == 1
    assert canvas.selected_items[0]["type"] == "dimension_chain"
    assert canvas.selected_items[0]["object"] is chain

    # Clear selection
    canvas.selected_items = []

    # 2. Click witness line inside room (x=50, y=110)
    click_x, click_y = canvas.model_to_device(50.0, 110.0, 2.0)
    canvas._handle_pointer_click(gesture, 1, click_x, click_y)
    assert len(canvas.selected_items) == 1
    assert canvas.selected_items[0]["type"] == "dimension_chain"
    assert canvas.selected_items[0]["object"] is chain

    # Clear selection
    canvas.selected_items = []

    # 3. Click anchor point (x=200, y=100)
    click_x, click_y = canvas.model_to_device(200.0, 100.0, 2.0)
    canvas._handle_pointer_click(gesture, 1, click_x, click_y)
    assert len(canvas.selected_items) == 1
    assert canvas.selected_items[0]["type"] == "dimension_chain"
    assert canvas.selected_items[0]["object"] is chain


def test_dimension_chain_handle_dragging_and_editing(canvas):
    canvas.tool_mode = "pointer"
    chain = DimensionChain(
        points=[(50.0, 100.0), (150.0, 100.0)],
        offset=20.0,
        identifier="chain_edit_test"
    )
    canvas.dimension_chains.append(chain)
    canvas.selected_items = [{"type": "dimension_chain", "object": chain}]

    gesture = MagicMock()
    event = MagicMock()
    event.get_modifier_state.return_value = 0
    gesture.get_current_event.return_value = event

    # Test offset handle dragging at (100, 120)
    hx, hy = canvas.model_to_device(100.0, 120.0, 2.0)
    canvas.on_click_pressed(gesture, 1, hx, hy)
    assert getattr(canvas, "editing_dimension_chain", None) is chain
    assert getattr(canvas, "editing_dimension_chain_handle", None) == ("offset", 0)

    canvas.on_drag_begin(gesture, hx, hy)
    assert getattr(canvas, "box_selecting", False) is False

    # Drag downwards by 20 device px (+10 inches in model)
    canvas.on_drag_update(gesture, 0.0, 20.0)
    assert pytest.approx(chain.offset, 0.1) == 30.0

    canvas.on_drag_end(gesture, 0.0, 20.0)
    assert getattr(canvas, "editing_dimension_chain", None) is None
    assert canvas.selected_items[0]["type"] == "dimension_chain"

    # Test point handle dragging at (50, 100)
    px, py = canvas.model_to_device(50.0, 100.0, 2.0)
    canvas.on_click_pressed(gesture, 1, px, py)
    assert getattr(canvas, "editing_dimension_chain", None) is chain
    assert getattr(canvas, "editing_dimension_chain_handle", None) == ("point", 0)

    canvas.on_drag_begin(gesture, px, py)
    assert getattr(canvas, "box_selecting", False) is False

    # Move point 0 by (-10px, -10px) -> (-5 inches, -5 inches)
    canvas.on_drag_update(gesture, -10.0, -10.0)
    assert pytest.approx(chain.points[0][0], 0.1) == 45.0
    assert pytest.approx(chain.points[0][1], 0.1) == 95.0

    canvas.on_drag_end(gesture, -10.0, -10.0)
    assert getattr(canvas, "editing_dimension_chain", None) is None


def test_dimension_chain_creation_auto_selection(canvas):
    canvas.tool_mode = "add_dimension_chain"
    canvas.dimension_chain_points = [(10.0, 10.0), (100.0, 10.0), (50.0, 10.0)]
    canvas.dimension_chain_offset = 18.0

    canvas.finalize_dimension_chain()

    assert len(canvas.dimension_chains) == 1
    new_chain = canvas.dimension_chains[0]
    assert len(canvas.selected_items) == 1
    assert canvas.selected_items[0]["type"] == "dimension_chain"
    assert canvas.selected_items[0]["object"] is new_chain
    assert canvas.drawing_dimension_chain is False


def test_dimension_chain_deletion_via_selected_items(canvas):
    chain1 = DimensionChain(points=[(0.0, 0.0), (50.0, 0.0)], offset=10.0, identifier="c1")
    chain2 = DimensionChain(points=[(0.0, 50.0), (50.0, 50.0)], offset=10.0, identifier="c2")
    canvas.dimension_chains = [chain1, chain2]

    # Delete via direct selection
    canvas.selected_items = [{"type": "dimension_chain", "object": chain1}]
    canvas.delete_selected()
    assert chain1 not in canvas.dimension_chains
    assert len(canvas.dimension_chains) == 1

    # Delete via handle selection
    canvas.selected_items = [{"type": "dimension_chain_handle", "object": (chain2, ("offset", 0))}]
    canvas.delete_selected()
    assert chain2 not in canvas.dimension_chains
    assert len(canvas.dimension_chains) == 0


def test_dimension_chain_creation_3click_workflow(canvas):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    canvas.set_tool_mode("add_dimension_chain")
    # Click 1: pt 1 at (10, 10) in model coords
    dev_x1, dev_y1 = canvas.model_to_device(10.0, 10.0, ppi)
    canvas.on_click(None, 1, dev_x1, dev_y1)
    assert canvas.drawing_dimension_chain is True
    assert len(canvas.dimension_chain_points) == 1

    # Click 2: pt 2 at (100, 10) in model coords
    dev_x2, dev_y2 = canvas.model_to_device(100.0, 10.0, ppi)
    canvas.on_click(None, 1, dev_x2, dev_y2)
    assert len(canvas.dimension_chain_points) == 2

    # Click 3: offset at (50, 35) in model coords (perpendicular distance 25.0 >= 6.0)
    dev_x3, dev_y3 = canvas.model_to_device(50.0, 35.0, ppi)
    canvas.on_click(None, 1, dev_x3, dev_y3)

    # Should finalize immediately!
    assert canvas.drawing_dimension_chain is False
    assert len(canvas.dimension_chains) == 1
    chain = canvas.dimension_chains[0]
    assert len(chain.points) == 2
    assert chain.points[0] == pytest.approx((10.0, 10.0), abs=0.1)
    assert chain.points[1] == pytest.approx((100.0, 10.0), abs=0.1)
    assert pytest.approx(chain.offset, abs=0.5) == 25.0


def test_dimension_chain_creation_multipoint_workflow(canvas):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    canvas.set_tool_mode("add_dimension_chain")
    # Pt 1: (0, 0)
    d1 = canvas.model_to_device(0.0, 0.0, ppi)
    canvas.on_click(None, 1, d1[0], d1[1])
    # Pt 2: (40, 0)
    d2 = canvas.model_to_device(40.0, 0.0, ppi)
    canvas.on_click(None, 1, d2[0], d2[1])
    # Pt 3: (70, 0) - along baseline (d_perp == 0)
    d3 = canvas.model_to_device(70.0, 0.0, ppi)
    canvas.on_click(None, 1, d3[0], d3[1])
    # Pt 4: (100, 0) - along baseline
    d4 = canvas.model_to_device(100.0, 0.0, ppi)
    canvas.on_click(None, 1, d4[0], d4[1])
    assert len(canvas.dimension_chain_points) == 4

    # Drop offset in margin: (50, 20)
    d_off = canvas.model_to_device(50.0, 20.0, ppi)
    canvas.on_click(None, 1, d_off[0], d_off[1])

    assert canvas.drawing_dimension_chain is False
    assert len(canvas.dimension_chains) == 1
    chain = canvas.dimension_chains[0]
    assert len(chain.points) == 4
    assert pytest.approx(chain.offset, abs=0.5) == 20.0


def test_dimension_chain_double_click_and_right_click_finalization(canvas):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    canvas.set_tool_mode("add_dimension_chain")
    d1 = canvas.model_to_device(0.0, 0.0, ppi)
    canvas.on_click(None, 1, d1[0], d1[1])
    d2 = canvas.model_to_device(50.0, 0.0, ppi)
    canvas.on_click(None, 1, d2[0], d2[1])
    # Double-click on 2nd point to finalize with default offset
    canvas.on_click(None, 2, d2[0], d2[1])
    assert canvas.drawing_dimension_chain is False
    assert len(canvas.dimension_chains) == 1
    assert len(canvas.dimension_chains[0].points) == 2

    # Test right-click finalization
    canvas.set_tool_mode("add_dimension_chain")
    canvas.on_click(None, 1, d1[0], d1[1])
    canvas.on_click(None, 1, d2[0], d2[1])
    assert canvas.drawing_dimension_chain is True
    # Right-click
    canvas.on_right_click(None, 1, d2[0], d2[1])
    assert canvas.drawing_dimension_chain is False
    assert len(canvas.dimension_chains) == 2


def test_dimension_chain_tool_mode_reset(canvas):
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    canvas.set_tool_mode("add_dimension_chain")
    d1 = canvas.model_to_device(10.0, 10.0, ppi)
    canvas.on_click(None, 1, d1[0], d1[1])
    assert canvas.drawing_dimension_chain is True

    # Switching tools clears the in-progress state cleanly
    canvas.set_tool_mode("pointer")
    assert canvas.drawing_dimension_chain is False
    assert canvas.dimension_chain_points == []
    assert canvas.dimension_chain_offset is None

    # Re-entering tool starts fresh
    canvas.set_tool_mode("add_dimension_chain")
    assert canvas.drawing_dimension_chain is False
    assert canvas.dimension_chain_points == []


