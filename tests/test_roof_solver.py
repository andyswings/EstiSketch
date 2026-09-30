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




