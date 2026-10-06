import os
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock
from EstiSketch.project_io import open_project, save_project


def _create_mock_canvas():
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
    mock_canvas.roofs = []
    mock_canvas.stairs = []
    mock_canvas.levels = []
    mock_canvas.layers = []
    mock_canvas.active_level_id = "level-1"
    mock_canvas.active_layer_id = "layer-1"
    return mock_canvas


def test_open_project_missing_window_dimensions():
    """Verify open_project handles XML missing window_width and window_height without throwing TypeError."""
    root = ET.Element("Project")
    ET.SubElement(root, "WallSets")
    ET.SubElement(root, "Rooms")
    
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        temp_path = f.name

    try:
        tree = ET.ElementTree(root)
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)

        mock_canvas = _create_mock_canvas()
        
        w, h = open_project(mock_canvas, temp_path)
        assert w == 800
        assert h == 600
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_open_project_roundtrip():
    """Verify open_project and save_project work together cleanly."""
    mock_canvas = _create_mock_canvas()

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
        temp_path = f.name

    try:
        save_project(mock_canvas, 1024, 768, temp_path)
        w, h = open_project(mock_canvas, temp_path)
        assert w == 1024
        assert h == 768
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
