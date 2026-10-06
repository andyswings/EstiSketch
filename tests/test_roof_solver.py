import pytest
import math
from EstiSketch.roof_components import RoofLine, RoofEdge, Roof, ROOF_LINE_COLORS
from EstiSketch.Canvas.roof_solver import cluster_and_snap_endpoints, solve_and_clean_roof
from EstiSketch.Takeoff.building_takeoff import generate_roof_takeoff, extract_walls_from_canvas


class DummyWall:
    def __init__(self, wall_id, start, end, width=5.5, height=96.0):
        self.identifier = wall_id
        self.start = start
        self.end = end
        self.width = width
        self.height = height

def test_roof_line_dataclass():
    line = RoofLine(start=(0.0, 0.0), end=(120.0, 0.0), line_type="ridge", pitch_rise=8.0)
    assert line.length_in == 120.0
    assert line.length_ft == 10.0
    assert ROOF_LINE_COLORS["ridge"] == "#E53935"

def test_endpoint_snapping():
    snap_targets = [(0.0, 0.0), (240.0, 0.0), (240.0, 360.0), (0.0, 360.0)]
    # Rough sketched line near (0,0) corner
    rough_line = RoofLine(start=(2.5, 3.0), end=(241.0, 1.5), line_type="eave")
    solved = cluster_and_snap_endpoints([rough_line], snap_targets, tolerance=12.0)
    assert len(solved) == 1
    assert solved[0].start == (0.0, 0.0)
    assert solved[0].end == (240.0, 0.0)


def test_solve_and_clean_roof():
    walls = [
        DummyWall("W1", (0, 0), (240, 0)),
        DummyWall("W2", (240, 0), (240, 360)),
        DummyWall("W3", (240, 360), (0, 360)),
        DummyWall("W4", (0, 360), (0, 0))
    ]
    edges = [
        RoofEdge("W1", "eave"),
        RoofEdge("W2", "eave"),
        RoofEdge("W3", "eave"),
        RoofEdge("W4", "eave")
    ]
    roof = Roof(identifier="ROOF-01", edges=edges, pitch_rise=6.0, overhang=24.0)
    
    # Sketched manual roof lines forming a roof network
    roof.manual_lines.extend([
        RoofLine(start=(0, 0), end=(240, 0), line_type="eave"),
        RoofLine(start=(240, 0), end=(240, 360), line_type="rake"),
        RoofLine(start=(240, 360), end=(0, 360), line_type="eave"),
        RoofLine(start=(0, 360), end=(0, 0), line_type="rake"),
        RoofLine(start=(120, 0), end=(120, 360), line_type="ridge")
    ])
    
    solve_and_clean_roof(roof, walls)
    
    assert len(roof.solved_lines) > 0
    assert len(roof.roof_planes) > 0
    total_area = sum(p["area_3d_sqft"] for p in roof.roof_planes)
    assert total_area > 0.0


def test_takeoff_integration():
    class DummyCanvas:
        def __init__(self):
            self.walls = [
                DummyWall("W1", (0, 0), (240, 0)),
                DummyWall("W2", (240, 0), (240, 360)),
                DummyWall("W3", (240, 360), (0, 360)),
                DummyWall("W4", (0, 360), (0, 0))
            ]
            self.wall_sets = [self.walls]
            self.doors = []
            self.windows = []
            self.rooms = []
            roof = Roof(identifier="ROOF-01", pitch_rise=6.0, overhang=24.0)
            roof.roof_planes = [{"area_3d_sqft": 850.0}]
            roof.solved_lines = [
                RoofLine(start=(120, 0), end=(120, 360), line_type="ridge")
            ]
            self.roofs = [roof]

    class DummyConfig:
        ROOF_WASTE_PCT = 10.0
        ROOF_SHEATHING_THICKNESS = '5/8"'
        ROOF_SHEATHING_TYPE = 'OSB'
        ROOF_FRAMING_TYPE = 'truss'
        ROOF_RAFTER_SPACING_IN = 16.0
        ROOF_USE_LVL_RIDGE = False

    canvas = DummyCanvas()
    config = DummyConfig()
    takeoff = generate_roof_takeoff(canvas, config)
    
    assert takeoff['total_net_area_sqft'] == 850.0
    assert takeoff['total_gross_area_sqft'] == 850.0 * 1.10
    assert takeoff['total_squares_needed'] == math.ceil((850.0 * 1.10) / 100.0)
    assert takeoff['total_ridge_lf'] == 30.0


def test_solve_marked_wall_roof_preserves_ridge():
    # Test that solving a roof generated from marked walls retains the ridge line
    walls = [
        DummyWall("W1", (0, 0), (240, 0)),
        DummyWall("W2", (240, 0), (240, 360)),
        DummyWall("W3", (240, 360), (0, 360)),
        DummyWall("W4", (0, 360), (0, 0))
    ]
    edges = [
        RoofEdge("W1", "eave"),
        RoofEdge("W2", "gable"),
        RoofEdge("W3", "eave"),
        RoofEdge("W4", "gable")
    ]
    roof = Roof(
        identifier="ROOF-GABLE",
        edges=edges,
        roof_type="gable",
        ridge_lines=[((0, 180), (240, 180))],
        pitch_rise=6.0,
        overhang=12.0
    )

    solve_and_clean_roof(roof, walls)

    assert len(roof.ridge_lines) == 1
    assert len(roof.solved_lines) > 0
    assert any(l.line_type == "ridge" for l in roof.solved_lines)


def test_line_straightening():
    from EstiSketch.Canvas.roof_solver import straighten_line_angle
    # Crooked horizontal line (drawn at ~3 degrees)
    start, end = straighten_line_angle((0.0, 100.0), (200.0, 110.0), tolerance_deg=15.0)
    assert abs(end[1] - start[1]) < 1e-5  # Y values equalized (perfectly horizontal)

    # Crooked 45 degree hip line (drawn at ~42 degrees)
    start_hip, end_hip = straighten_line_angle((0.0, 0.0), (100.0, 90.0), tolerance_deg=15.0)
    dx = abs(end_hip[0] - start_hip[0])
    dy = abs(end_hip[1] - start_hip[1])
    assert abs(dx - dy) < 1e-3  # dx and dy equalized (perfect 45 degrees)


def test_asymmetric_pitch_gable_ridge():
    # Eave 1 has 8/12 pitch, Eave 2 has 4/12 pitch across 360" span
    # Ridge should be placed at 1/3 of span (120") from Eave 1
    walls = [
        DummyWall("W1", (0, 0), (240, 0)),
        DummyWall("W2", (240, 0), (240, 360)),
        DummyWall("W3", (240, 360), (0, 360)),
        DummyWall("W4", (0, 360), (0, 0))
    ]
    edges = [
        RoofEdge("W1", "eave", pitch_rise=8.0),
        RoofEdge("W2", "gable"),
        RoofEdge("W3", "eave", pitch_rise=4.0),
        RoofEdge("W4", "gable")
    ]
    roof = Roof(identifier="ROOF-ASYMM", edges=edges, pitch_rise=6.0, overhang=12.0)

    solve_and_clean_roof(roof, walls)

    assert len(roof.ridge_lines) == 1
    r_start, r_end = roof.ridge_lines[0]
    # Ridge Y should be approx 120 (closer to Eave 1 at Y=0) rather than center 180
    assert abs(r_start[1] - 120.0) < 1.0
    assert abs(r_end[1] - 120.0) < 1.0


def test_multi_plane_3d_extraction():
    from EstiSketch.Canvas.roof_solver import extract_3d_roof_planes, slope_multiplier
    # Manual lines for an asymmetrical gable:
    # Eave 1 at Y=0 (pitch 8), Eave 2 at Y=360 (pitch 4), Ridge at Y=120
    lines = [
        RoofLine(identifier="E1", start=(0, 0), end=(240, 0), line_type="eave", pitch_rise=8.0),
        RoofLine(identifier="E2", start=(0, 360), end=(240, 360), line_type="eave", pitch_rise=4.0),
        RoofLine(identifier="R1", start=(0, 120), end=(240, 120), line_type="ridge", pitch_rise=6.0),
    ]
    planes = extract_3d_roof_planes(lines, default_pitch=6.0)

    assert len(planes) == 2
    # Verify slopes have their individual pitches and areas
    plane_pitches = {p["pitch"] for p in planes}
    assert 8.0 in plane_pitches
    assert 4.0 in plane_pitches

    plane_8 = next(p for p in planes if p["pitch"] == 8.0)
    plane_4 = next(p for p in planes if p["pitch"] == 4.0)

    # 2D area for slope 1 (240x120) = 200 sq ft; 3D area = 200 * multiplier(8)
    assert abs(plane_8["area_2d_sqft"] - 200.0) < 1.0
    assert abs(plane_8["area_3d_sqft"] - (200.0 * slope_multiplier(8.0, 12.0))) < 1.0

    # 2D area for slope 2 (240x240) = 400 sq ft; 3D area = 400 * multiplier(4)
    assert abs(plane_4["area_2d_sqft"] - 400.0) < 1.0
    assert abs(plane_4["area_3d_sqft"] - (400.0 * slope_multiplier(4.0, 12.0))) < 1.0


def test_roof_xml_persistence_roundtrip():
    import tempfile
    import os
    from unittest.mock import MagicMock
    from EstiSketch.project_io import save_project, open_project

    mock_canvas = MagicMock()
    mock_canvas.wall_sets = []
    mock_canvas.rooms = []
    mock_canvas.doors = []
    mock_canvas.windows = []
    mock_canvas.texts = []
    mock_canvas.dimensions = []
    mock_canvas.polyline_sets = []
    mock_canvas.circles = []
    mock_canvas.arcs = []
    mock_canvas.stairs = []
    mock_canvas.levels = []
    mock_canvas.layers = []
    mock_canvas.active_level_id = "L1"
    mock_canvas.active_layer_id = "L1"

    roof = Roof(
        identifier="ROOF-XML-TEST",
        layer_id="L1",
        roof_type="gable",
        pitch_rise=7.5,
        pitch_run=12.0,
        overhang=18.0,
        material="Metal Standing Seam"
    )
    roof.edges.append(RoofEdge("W1", "eave", pitch_rise=7.5, overhang=18.0))
    roof.manual_lines.append(RoofLine(
        identifier="ML-1",
        start=(10.0, 20.0),
        end=(210.0, 20.0),
        line_type="ridge",
        pitch_rise=7.5
    ))
    roof.solved_lines.append(RoofLine(
        identifier="SL-1",
        start=(10.0, 20.0),
        end=(210.0, 20.0),
        line_type="ridge",
        pitch_rise=7.5
    ))
    roof.solved_lines.append(RoofLine(
        identifier="SL-2",
        start=(10.0, 0.0),
        end=(210.0, 0.0),
        line_type="eave",
        pitch_rise=7.5
    ))
    roof.solved_lines.append(RoofLine(
        identifier="SL-3",
        start=(10.0, 40.0),
        end=(210.0, 40.0),
        line_type="eave",
        pitch_rise=7.5
    ))
    roof.rake_lines.append(((10.0, 0.0), (10.0, 20.0)))
    roof.eave_lines.append(((10.0, 0.0), (210.0, 0.0)))
    roof.tie_in_lines.append(((0.0, 50.0), (100.0, 50.0)))
    roof.outline_points = [(0.0, 0.0), (220.0, 0.0), (220.0, 40.0), (0.0, 40.0)]

    mock_canvas.roofs = [roof]

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        temp_path = f.name

    try:
        save_project(mock_canvas, 1024, 768, temp_path)

        restore_canvas = MagicMock()
        restore_canvas.wall_sets = []
        restore_canvas.rooms = []
        restore_canvas.doors = []
        restore_canvas.windows = []
        restore_canvas.texts = []
        restore_canvas.dimensions = []
        restore_canvas.polyline_sets = []
        restore_canvas.circles = []
        restore_canvas.arcs = []
        restore_canvas.roofs = []
        restore_canvas.stairs = []
        restore_canvas.levels = []
        restore_canvas.layers = []

        open_project(restore_canvas, temp_path)

        assert len(restore_canvas.roofs) == 1
        restored = restore_canvas.roofs[0]
        assert restored.identifier == "ROOF-XML-TEST"
        assert restored.pitch_rise == 7.5
        assert restored.overhang == 18.0
        assert restored.material == "Metal Standing Seam"

        assert len(restored.edges) == 1
        assert restored.edges[0].wall_identifier == "W1"
        assert restored.edges[0].pitch_rise == 7.5

        assert len(restored.manual_lines) == 1
        assert restored.manual_lines[0].identifier == "ML-1"
        assert restored.manual_lines[0].line_type == "ridge"

        assert len(restored.solved_lines) == 3
        assert len(restored.rake_lines) == 1
        assert len(restored.eave_lines) == 1
        assert len(restored.tie_in_lines) == 1
        assert len(restored.outline_points) == 4
        assert len(restored.roof_planes) > 0
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_canvas_state_undo_redo_roofs():
    from EstiSketch.Canvas.canvas_state import CanvasStateMixin
    from unittest.mock import MagicMock

    class MockStateCanvas(CanvasStateMixin):
        def __init__(self):
            self.undo_stack = []
            self.redo_stack = []
            self.config = MagicMock()
            self.config.UNDO_REDO_LIMIT = 50
            self.wall_sets = []
            self.walls = []
            self.current_wall = None
            self.drawing_wall = False
            self.rooms = []
            self.current_room_points = []
            self.polylines = []
            self.polyline_sets = []
            self.doors = []
            self.windows = []
            self.texts = []
            self.dimensions = []
            self.circles = []
            self.arcs = []
            self.roofs = []
            self.stairs = []
            self.snap_type = "none"

        def queue_draw(self):
            pass

    c = MockStateCanvas()
    c.save_state()
    assert len(c.undo_stack) == 1

    roof = Roof(identifier="ROOF-UNDO-1", pitch_rise=8.0)
    c.roofs.append(roof)
    c.save_state()
    assert len(c.undo_stack) == 2
    assert len(c.roofs) == 1

    c.undo()
    assert len(c.roofs) == 0

    c.redo()
    assert len(c.roofs) == 1
    assert c.roofs[0].identifier == "ROOF-UNDO-1"
    assert c.roofs[0].pitch_rise == 8.0


def test_roof_line_canvas_interactions():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    from typing import Any
    cfg = SimpleNamespace(**config.load_config())
    canvas: Any = CanvasArea(cfg)

    roof = Roof(identifier="ROOF-INT-1", pitch_rise=6.0)
    rline = RoofLine(identifier="RL-1", start=(10.0, 20.0), end=(100.0, 20.0), line_type="ridge")
    roof.manual_lines.append(rline)
    canvas.roofs.append(roof)

    # 1. Test endpoint handle dragging
    canvas.editing_roof_line = rline
    canvas.editing_roof_line_handle = "end"
    canvas.editing_roof_line_roof = roof
    canvas.drag_start_x = 0.0
    canvas.drag_start_y = 0.0
    # Turn off snapping for exact coord test
    canvas.snap_manager.snap_enabled = False

    # Simulate drag update (offset_x=40 device units, zoom=1.0, pixels_per_inch=2.0 -> model offset=20.0)
    ppi = getattr(canvas.config, "PIXELS_PER_INCH", 2.0)
    canvas.on_drag_update(None, offset_x=120.0, offset_y=60.0)
    expected_x, expected_y = canvas.device_to_model(120.0, 60.0, ppi)
    assert rline.end == (expected_x, expected_y)

    # Simulate drag end
    canvas.on_drag_end(None, offset_x=120.0, offset_y=60.0)
    assert canvas.editing_roof_line is None
    assert canvas.editing_roof_line_handle is None

    # 2. Test whole roof line dragging
    initial_start = rline.start
    initial_end = rline.end
    canvas.dragging_roof_lines = [{
        "roof_line": rline,
        "original_start": initial_start,
        "original_end": initial_end,
        "roof": roof
    }]
    canvas.drag_start_x = 0.0
    canvas.drag_start_y = 0.0
    canvas.roof_line_drag_start_model = (0.0, 0.0)

    canvas.on_drag_update(None, offset_x=20.0, offset_y=20.0)
    dx_model, dy_model = canvas.device_to_model(20.0, 20.0, ppi)
    assert rline.start == (initial_start[0] + dx_model, initial_start[1] + dy_model)
    assert rline.end == (initial_end[0] + dx_model, initial_end[1] + dy_model)

    canvas.on_drag_end(None, offset_x=20.0, offset_y=20.0)
    assert canvas.dragging_roof_lines is None

    # 3. Test box selection of roof lines
    canvas.tool_mode = "pointer"
    canvas.box_selecting = True
    canvas.box_select_start = (-100.0, -100.0)
    canvas.box_select_end = (500.0, 500.0)
    canvas.on_drag_end(None, 0.0, 0.0)
    assert any(item.get("type") == "roof_line" and item.get("object") == rline for item in canvas.selected_items)

    # 4. Test delete selected roof line (with fallback lookup of roof)
    canvas.selected_items = [{"type": "roof_line", "object": rline}]
    canvas.delete_selected()
    assert rline not in roof.manual_lines


def test_takeoff_warns_on_empty_roof_points_and_no_fallback():
    import warnings
    from EstiSketch.Takeoff.building_takeoff import generate_roof_takeoff

    class DummyEmptyRoofCanvas:
        def __init__(self):
            self.wall_sets = []
            self.walls = []
            self.doors = []
            self.windows = []
            self.rooms = []
            # Roof with no points at all
            empty_roof = Roof(identifier="ROOF-EMPTY", pitch_rise=6.0, overhang=12.0)
            self.roofs = [empty_roof]

    class DummyConfig:
        ROOF_WASTE_PCT = 10.0
        ROOF_SHEATHING_THICKNESS = '5/8"'
        ROOF_SHEATHING_TYPE = 'OSB'
        ROOF_FRAMING_TYPE = 'truss'
        ROOF_RAFTER_SPACING_IN = 16.0
        ROOF_USE_LVL_RIDGE = False

    canvas = DummyEmptyRoofCanvas()
    config = DummyConfig()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = generate_roof_takeoff(canvas, config)
        # Verify a warning was raised
        assert any("no defined geometry points" in str(item.message) for item in w)
        # Verify it did NOT produce fallback 24x30 / 28x40 sections
        assert result == {}


def test_gable_ridge_overhang_extension_and_retraction():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    # 4 walls forming a 240 x 360 rectangle
    # W1: (0,0)->(240,0) [Eave], W2: (240,0)->(240,360) [Gable],
    # W3: (240,360)->(0,360) [Eave], W4: (0,360)->(0,0) [Gable]
    w1 = DummyWall("W1", (0.0, 0.0), (240.0, 0.0))
    w2 = DummyWall("W2", (240.0, 0.0), (240.0, 360.0))
    w3 = DummyWall("W3", (240.0, 360.0), (0.0, 360.0))
    w4 = DummyWall("W4", (0.0, 360.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4]]

    canvas.mark_walls_as_eave([w1, w3])
    canvas.mark_walls_as_gable([w2, w4])

    # 1. Generate roof with 12" overhang
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None
    assert len(roof.ridge_lines) == 1
    r_start, r_end = roof.ridge_lines[0]
    # Gable walls are at X=0 and X=240, so with 12" overhang ridge should span from -12 to 252 (length = 264)
    ridge_len = math.hypot(r_end[0] - r_start[0], r_end[1] - r_start[1])
    assert abs(ridge_len - 264.0) < 1.0

    # 2. Change overhang to 24"
    roof.overhang = 24.0
    canvas.recalculate_roof(roof)
    r_start24, r_end24 = roof.ridge_lines[0]
    ridge_len24 = math.hypot(r_end24[0] - r_start24[0], r_end24[1] - r_start24[1])
    # With 24" overhang, ridge extends from -24 to 264 (length = 288)
    assert abs(ridge_len24 - 288.0) < 1.0

    # Check that solved_lines also has the extended ridge
    solved_ridge = next(l for l in roof.solved_lines if l.line_type == "ridge")
    assert abs(solved_ridge.length_in - 288.0) < 1.0

    # 3. Retract overhang to 6"
    roof.overhang = 6.0
    canvas.recalculate_roof(roof)
    r_start6, r_end6 = roof.ridge_lines[0]
    ridge_len6 = math.hypot(r_end6[0] - r_start6[0], r_end6[1] - r_start6[1])
    # With 6" overhang, ridge spans from -6 to 246 (length = 252)
    assert abs(ridge_len6 - 252.0) < 1.0


def test_ridgeline_drag_persistence_and_pitch_recalculation():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    w1 = DummyWall("W1", (0.0, 0.0), (240.0, 0.0))
    w2 = DummyWall("W2", (240.0, 0.0), (240.0, 360.0))
    w3 = DummyWall("W3", (240.0, 360.0), (0.0, 360.0))
    w4 = DummyWall("W4", (0.0, 360.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4]]

    canvas.mark_walls_as_eave([w1, w3])
    canvas.mark_walls_as_gable([w2, w4])
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)

    # Initial ridge is at Y = 180 (center between Y=0 and Y=360)
    solved_ridge = next(l for l in roof.solved_lines if l.line_type == "ridge")
    assert abs(solved_ridge.start[1] - 180.0) < 1.0

    # Simulate user dragging ridge line in Y direction by -60 inches (from Y=180 to Y=120)
    canvas.dragging_roof_lines = [{
        "roof_line": solved_ridge,
        "original_start": solved_ridge.start,
        "original_end": solved_ridge.end,
        "roof": roof
    }]
    solved_ridge.start = (solved_ridge.start[0], 120.0)
    solved_ridge.end = (solved_ridge.end[0], 120.0)

    # End drag
    canvas.on_drag_end(None, offset_x=0.0, offset_y=-120.0)

    # Check persistence: ridge should remain at Y=120
    persisted_ridge = next(l for l in roof.solved_lines if l.line_type == "ridge")
    assert abs(persisted_ridge.start[1] - 120.0) < 1.0
    assert abs(persisted_ridge.end[1] - 120.0) < 1.0

    # Check that pitches were recalculated for Side A and Side B
    # Ridge at Y=120 means distance to Eave 1 (Y=0) is 120, distance to Eave 2 (Y=360) is 240
    # Pitch1 = 6 * 360 / (2 * 120) = 9.0; Pitch2 = 6 * 360 / (2 * 240) = 4.5
    eave_edges = [e for e in roof.edges if e.edge_type == "eave"]
    assert abs(eave_edges[0].pitch_rise - 9.0) < 0.2
    assert abs(eave_edges[1].pitch_rise - 4.5) < 0.2


def test_properties_dock_asymmetric_pitch_adjustments():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea
    from EstiSketch.Dialogs.properties_dock import RoofPropertiesWidget

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    w1 = DummyWall("W1", (0.0, 0.0), (240.0, 0.0))
    w2 = DummyWall("W2", (240.0, 0.0), (240.0, 360.0))
    w3 = DummyWall("W3", (240.0, 360.0), (0.0, 360.0))
    w4 = DummyWall("W4", (0.0, 360.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4]]

    canvas.mark_walls_as_eave([w1, w3])
    canvas.mark_walls_as_gable([w2, w4])
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)

    widget = RoofPropertiesWidget()
    widget.canvas = canvas
    widget.set_roof([roof])

    # Switch to asymmetric pitch mode and set Side A = 8.0, Side B = 4.0
    widget.pitch_mode_combo.set_active(1)
    widget.pitch_a_spin.set_value(8.0)
    widget.pitch_b_spin.set_value(4.0)

    # Ridge should now be at 1/3 across 360" span (at Y=120)
    new_ridge = next(l for l in roof.solved_lines if l.line_type == "ridge")
    assert abs(new_ridge.start[1] - 120.0) < 1.0
    assert abs(new_ridge.end[1] - 120.0) < 1.0

    # Verify planes have individual pitches 8.0 and 4.0
    pitches = {p["pitch"] for p in roof.roof_planes}
    assert 8.0 in pitches
    assert 4.0 in pitches


def test_l_shaped_roof_two_gables():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    # 6 walls forming an L-shaped house:
    # Horizontal wing: 400 long, 200 wide (from X=0 to 400, Y=0 to 200)
    # Vertical wing: 500 long, 200 wide (from X=0 to 200, Y=0 to 500)
    # Inside corner at (200, 200), Outside corner at (0, 0)
    w1 = DummyWall("W1", (0.0, 0.0), (400.0, 0.0))
    w2 = DummyWall("W2", (400.0, 0.0), (400.0, 200.0))      # Wing 1 gable end
    w3 = DummyWall("W3", (400.0, 200.0), (200.0, 200.0))
    w4 = DummyWall("W4", (200.0, 200.0), (200.0, 500.0))
    w5 = DummyWall("W5", (200.0, 500.0), (0.0, 500.0))        # Wing 2 gable end
    w6 = DummyWall("W6", (0.0, 500.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4, w5, w6]]

    canvas.mark_walls_as_gable([w2, w5])
    canvas.mark_walls_as_eave([w1, w3, w4, w6])

    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None

    # Verify 2 separate ridge lines:
    # Ridge 1: East-West along Y=100
    # Ridge 2: North-South along X=100
    # Both meet at (100, 100)
    ridges = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "ridge"]
    assert len(ridges) == 2

    # Check intersection point (100, 100)
    ridge_starts = [r[0] for r in ridges]
    assert all(math.hypot(p[0] - 100.0, p[1] - 100.0) < 1.0 for p in ridge_starts)

    # Ridge 1 extends past gable wall at X=400 by overhang 12 (to X=412, Y=100)
    # Ridge 2 extends past gable wall at Y=500 by overhang 12 (to X=100, Y=512)
    ridge_ends = [r[1] for r in ridges]
    has_ew_ridge = any(abs(p[0] - 412.0) < 1.0 and abs(p[1] - 100.0) < 1.0 for p in ridge_ends)
    has_ns_ridge = any(abs(p[0] - 100.0) < 1.0 and abs(p[1] - 512.0) < 1.0 for p in ridge_ends)
    assert has_ew_ridge
    assert has_ns_ridge

    # Valley line from (100, 100) through inside corner (200, 200) to overhang (212, 212)
    valleys = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "valley"]
    assert len(valleys) == 1
    v_start, v_end = valleys[0]
    assert math.hypot(v_start[0] - 100.0, v_start[1] - 100.0) < 1.0
    assert math.hypot(v_end[0] - 212.0, v_end[1] - 212.0) < 1.0

    # Hip line from (100, 100) through outside corner (0, 0) to overhang (-12, -12)
    hips = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "hip"]
    assert len(hips) == 1
    h_start, h_end = hips[0]
    assert math.hypot(h_start[0] - 100.0, h_start[1] - 100.0) < 1.0
    assert math.hypot(h_end[0] - (-12.0), h_end[1] - (-12.0)) < 1.0

    # Verify 3D roof planes extracted
    assert len(roof.roof_planes) >= 4
    total_area = sum(p["area_3d_sqft"] for p in roof.roof_planes)
    assert total_area > 0.0


def test_l_shaped_roof_all_hips():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    w1 = DummyWall("W1", (0.0, 0.0), (400.0, 0.0))
    w2 = DummyWall("W2", (400.0, 0.0), (400.0, 200.0))
    w3 = DummyWall("W3", (400.0, 200.0), (200.0, 200.0))
    w4 = DummyWall("W4", (200.0, 200.0), (200.0, 500.0))
    w5 = DummyWall("W5", (200.0, 500.0), (0.0, 500.0))
    w6 = DummyWall("W6", (0.0, 500.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4, w5, w6]]

    canvas.mark_walls_as_eave([w1, w2, w3, w4, w5, w6])
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None

    # Two ridges terminate width/2 (100") before the end walls:
    # Ridge 1 ends at (300, 100), Ridge 2 ends at (100, 400)
    ridges = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "ridge"]
    assert len(ridges) == 2

    # 1 valley line at inside corner
    valleys = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "valley"]
    assert len(valleys) == 1
    assert math.hypot(valleys[0][1][0] - 212.0, valleys[0][1][1] - 212.0) < 1.0

    # 5 hip lines (1 at junction to outside corner, 2 at Wing 1 end, 2 at Wing 2 end)
    hips = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "hip"]
    assert len(hips) == 5


def test_t_shaped_roof_gables():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    # T-shaped house:
    # Main body: X from 0 to 600, Y from 0 to 200 (width 200, centerline Y=100)
    # Stem wing: X from 200 to 400, Y from 200 to 500 (width 200, centerline X=300)
    t_pts = [(0, 0), (600, 0), (600, 200), (400, 200), (400, 500), (200, 500), (200, 200), (0, 200)]
    walls = [DummyWall(f"W{i+1}", (float(t_pts[i][0]), float(t_pts[i][1])),
                       (float(t_pts[(i+1)%8][0]), float(t_pts[(i+1)%8][1]))) for i in range(8)]
    canvas.wall_sets = [walls]

    # Mark 3 ends as gable (W2: right end, W5: stem end, W8: left end)
    canvas.mark_walls_as_gable([walls[1], walls[4], walls[7]])
    canvas.mark_walls_as_eave([walls[0], walls[2], walls[3], walls[5], walls[6]])

    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None

    # Intersection at (300, 100)
    # Two valleys running from (300, 100) through inside corners (400, 200) and (200, 200)
    valleys = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "valley"]
    assert len(valleys) == 2
    for v_start, v_end in valleys:
        assert math.hypot(v_start[0] - 300.0, v_start[1] - 100.0) < 1.0

    # Ridges meeting at (300, 100)
    ridges = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "ridge"]
    assert len(ridges) >= 2


def test_multisided_hip_roof_octagon():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    # Regular octagon centered at (300, 300), radius 200
    r = 200.0
    cx, cy = 300.0, 300.0
    oct_pts = [(cx + r * math.cos(i * math.pi / 4), cy + r * math.sin(i * math.pi / 4)) for i in range(8)]
    walls = [DummyWall(f"W{i+1}", oct_pts[i], oct_pts[(i+1)%8]) for i in range(8)]
    canvas.wall_sets = [walls]

    canvas.mark_walls_as_eave(walls)
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None

    # All 8 corners have hip lines converging towards center (300, 300)
    hips = [(l.start, l.end) for l in roof.solved_lines if l.line_type == "hip"]
    assert len(hips) == 8
    for h_start, h_end in hips:
        assert math.hypot(h_start[0] - 300.0, h_start[1] - 300.0) < 5.0


def test_l_shaped_roof_overhang_recalculation():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    w1 = DummyWall("W1", (0.0, 0.0), (400.0, 0.0))
    w2 = DummyWall("W2", (400.0, 0.0), (400.0, 200.0))
    w3 = DummyWall("W3", (400.0, 200.0), (200.0, 200.0))
    w4 = DummyWall("W4", (200.0, 200.0), (200.0, 500.0))
    w5 = DummyWall("W5", (200.0, 500.0), (0.0, 500.0))
    w6 = DummyWall("W6", (0.0, 500.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4, w5, w6]]

    canvas.mark_walls_as_gable([w2, w5])
    canvas.mark_walls_as_eave([w1, w3, w4, w6])

    # 1. Generate with 12" overhang
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None
    valley12 = next(l for l in roof.solved_lines if l.line_type == "valley")
    assert math.hypot(valley12.end[0] - 212.0, valley12.end[1] - 212.0) < 1.0

    # 2. Recalculate with 24" overhang
    roof.overhang = 24.0
    canvas.recalculate_roof(roof)
    valley24 = next(l for l in roof.solved_lines if l.line_type == "valley")
    # With 24" overhang, inside corner (200, 200) extends to (224, 224)
    assert math.hypot(valley24.end[0] - 224.0, valley24.end[1] - 224.0) < 1.0

    # Hip extends to (-24, -24)
    hip24 = next(l for l in roof.solved_lines if l.line_type == "hip")
    assert math.hypot(hip24.end[0] - (-24.0), hip24.end[1] - (-24.0)) < 1.0


def test_l_shaped_roof_marking_inference():
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    w1 = DummyWall("W1", (0.0, 0.0), (400.0, 0.0))
    w2 = DummyWall("W2", (400.0, 0.0), (400.0, 200.0))
    w3 = DummyWall("W3", (400.0, 200.0), (200.0, 200.0))
    w4 = DummyWall("W4", (200.0, 200.0), (200.0, 500.0))
    w5 = DummyWall("W5", (200.0, 500.0), (0.0, 500.0))
    w6 = DummyWall("W6", (0.0, 500.0), (0.0, 0.0))
    canvas.wall_sets = [[w1, w2, w3, w4, w5, w6]]

    # User ONLY marks the two gable ends, leaving the other 4 walls unmarked
    canvas.mark_walls_as_gable([w2, w5])

    # Smart inference infers the other 4 walls as eaves and generates the roof
    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None
    assert len(roof.edges) == 6
    assert any(l.line_type == "valley" for l in roof.solved_lines)
    assert any(l.line_type == "hip" for l in roof.solved_lines)


def test_l_shaped_unequal_wings_non_45_degree_hip_valley():
    """
    Test an L-shaped house where the two wings have unequal widths (e.g. 134\" vs 204\").
    Hips and valleys must NOT be forced to 45 degrees, and their ends must meet
    the exact corresponding inside/outside overhang corners.
    """
    from types import SimpleNamespace
    from EstiSketch import config
    from EstiSketch.Canvas.canvas_area import CanvasArea

    cfg = SimpleNamespace(**config.load_config())
    canvas = CanvasArea(cfg)

    # Coordinates with unequal wing widths:
    # Wing 1 (horizontal): Y from 199 to 333 (width = 134", centerline Y = 266)
    # Wing 2 (vertical): X from 373 to 577 (width = 204", centerline X = 475)
    pts = [
        (187.0, 199.0),  # W1: left gable top
        (577.0, 199.0),  # W2: outside corner
        (577.0, 485.0),  # W3: bottom gable right
        (373.0, 485.0),  # W4: bottom gable left
        (373.0, 333.0),  # W5: inside reflex corner
        (187.0, 333.0),  # W6: left gable bottom
    ]
    walls = [DummyWall(f"W{i+1}", pts[i], pts[(i+1)%6]) for i in range(6)]
    canvas.wall_sets = [walls]

    # Mark end walls as gables
    canvas.mark_walls_as_gable([walls[2], walls[5]])
    canvas.mark_walls_as_eave([walls[0], walls[1], walls[3], walls[4]])

    roof = canvas.generate_roof_from_marked_walls(pitch_rise=6, overhang=12.0)
    assert roof is not None

    # Ridge intersection at (475, 266)
    valleys = [l for l in roof.solved_lines if l.line_type == "valley"]
    hips = [l for l in roof.solved_lines if l.line_type == "hip"]
    assert len(valleys) == 1
    assert len(hips) == 1

    valley = valleys[0]
    hip = hips[0]

    # Both originate at the ridge intersection (475, 266)
    assert math.hypot(valley.start[0] - 475.0, valley.start[1] - 266.0) < 1.0
    assert math.hypot(hip.start[0] - 475.0, hip.start[1] - 266.0) < 1.0

    # Valley end meets inside overhang corner: (373 - 12, 333 + 12) = (361, 345)
    assert math.hypot(valley.end[0] - 361.0, valley.end[1] - 345.0) < 1.0

    # Hip end meets outside overhang corner: (577 + 12, 199 - 12) = (589, 187)
    assert math.hypot(hip.end[0] - 589.0, hip.end[1] - 187.0) < 1.0

    # Verify that the lines are NOT 45 degrees:
    # dx = -114, dy = 79 => |dx| != |dy|
    valley_dx = abs(valley.end[0] - valley.start[0])
    valley_dy = abs(valley.end[1] - valley.start[1])
    assert abs(valley_dx - valley_dy) > 20.0  # Significant difference from 45 degrees!

    hip_dx = abs(hip.end[0] - hip.start[0])
    hip_dy = abs(hip.end[1] - hip.start[1])
    assert abs(hip_dx - hip_dy) > 20.0







