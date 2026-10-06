import sys
import os
import unittest

# Ensure src/ is in python path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from EstiSketch.Takeoff.building_takeoff import (
    extract_walls_from_canvas,
    generate_width_summary_report,
    generate_wall_report,
    generate_framing_report,
    generate_sheathing_report,
    generate_housewrap_report,
    get_supplier_quote_items,
    export_supplier_quote_txt,
    export_supplier_quote_csv
)


class DummyWall:
    def __init__(self, identifier, start, end, width=5.5, height=96.0):
        self.identifier = identifier
        self.start = start
        self.end = end
        self.width = width
        self.height = height


class DummyCanvas:
    def __init__(self):
        self.pixels_per_inch = 2.0
        self.default_wall_height = 96.0
        w1 = DummyWall("W1", (0, 0), (240, 0), width=5.5)  # 240 inches = 20 ft
        w2 = DummyWall("W2", (240, 0), (240, 180), width=5.5)  # 180 inches = 15 ft
        self.wall_sets = [[w1, w2]]
        self.doors = []
        self.windows = []
        self.rooms = []
        self.roofs = []


class TestBuildingTakeoff(unittest.TestCase):
    def setUp(self):
        self.canvas = DummyCanvas()

    def test_extract_walls_from_canvas(self):
        walls = extract_walls_from_canvas(self.canvas)
        self.assertEqual(len(walls), 2)
        self.assertAlmostEqual(walls[0]['raw_length_ft'], 20.0, places=1)
        self.assertAlmostEqual(walls[1]['raw_length_ft'], 15.0, places=1)

    def test_generate_framing_report(self):
        walls = extract_walls_from_canvas(self.canvas)
        report = generate_framing_report(walls, stud_spacing=16.0, plate_length_in=192.0)
        self.assertIn("FRAMING MATERIAL REPORT", report)
        self.assertIn("Pressure-Treated Bottom Plates", report)

    def test_supplier_quote_items(self):
        class DummyConfig:
            DEFAULT_STUD_SPACING = 16.0
            MAX_WALL_PLATE_INCHES = 192.0

        items = get_supplier_quote_items(self.canvas, DummyConfig())
        self.assertTrue(len(items) > 0)
        descriptions = [it['description'] for it in items]
        self.assertTrue(any("Wall Studs" in d for d in descriptions))
        self.assertTrue(any("Bottom Plate" in d for d in descriptions))

    def test_export_txt_csv(self):
        class DummyConfig:
            DEFAULT_STUD_SPACING = 16.0

        items = get_supplier_quote_items(self.canvas, DummyConfig())
        txt_path = "/tmp/test_quote.txt"
        csv_path = "/tmp/test_quote.csv"

        txt_out = export_supplier_quote_txt(items, DummyConfig(), "Test Proj", txt_path)
        export_supplier_quote_csv(items, DummyConfig(), "Test Proj", csv_path)

        self.assertTrue(os.path.exists(txt_path))
        self.assertTrue(os.path.exists(csv_path))

        if os.path.exists(txt_path):
            os.remove(txt_path)
        if os.path.exists(csv_path):
            os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
