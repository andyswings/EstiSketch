import os
import sys
import tempfile
import unittest

src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from EstiSketch.components import Room, Stair, Layer, Level
from EstiSketch.geometry.room_holes import (
    sync_stair_holes, stair_footprint_parts, polygon_area, clip_polygon_convex,
    room_floor_area_sqft, room_ceiling_area_sqft, room_slab_volume_cuft)
from EstiSketch.Takeoff.building_takeoff import extract_room_areas


class FakeCanvas:
    def __init__(self):
        self.levels = [Level(id="L1"), Level(id="L2", elevation=106.0)]
        self.layers = [Layer(id="la1", level_id="L1"), Layer(id="la2", level_id="L2")]
        self.rooms = []
        self.stairs = []
        self.cut_lower_ceiling_under_stairs = False

    def get_layer_by_id(self, lid):
        return next((l for l in self.layers if l.id == lid), None)


def square(x, y, s):
    return [(x, y), (x + s, y), (x + s, y + s), (x, y + s)]


def make(stair_kw=None):
    c = FakeCanvas()
    c.rooms.append(Room(square(0, 0, 240), layer_id="la1", identifier="lower"))
    upper = Room(square(0, 0, 240), layer_id="la2", identifier="upper")
    upper.is_slab, upper.slab_thickness = True, 6.0
    c.rooms.append(upper)
    kw = dict(identifier="S1", start_point=(60.0, 100.0), direction_angle=0.0,
              start_level_id="L1", end_level_id="L2", width=36.0, total_run=120.0)
    kw.update(stair_kw or {})
    c.stairs.append(Stair(**kw))
    return c


class TestRoomHoles(unittest.TestCase):
    def test_clip_convex(self):
        res = clip_polygon_convex(square(0, 0, 10), square(5, 5, 10))
        self.assertAlmostEqual(polygon_area(res), 25.0)

    def test_straight_stair_cuts_upper_room_only(self):
        c = make()
        sync_stair_holes(c)
        lower, upper = c.rooms
        self.assertEqual(lower.holes, [])
        self.assertEqual(len(upper.holes), 1)
        self.assertAlmostEqual(polygon_area(upper.holes[0].points), 120 * 36)
        self.assertEqual(upper.holes[0].source_id, "stair:S1")

    def test_area_deduction(self):
        c = make()
        sync_stair_holes(c)
        upper = c.rooms[1]
        expected = (240 * 240 - 120 * 36) / 144.0
        self.assertAlmostEqual(room_floor_area_sqft(upper), expected)
        self.assertAlmostEqual(room_ceiling_area_sqft(upper), expected)
        self.assertAlmostEqual(room_slab_volume_cuft(upper), expected * 0.5)
        areas = {r["id"]: r for r in extract_room_areas(c)}
        self.assertAlmostEqual(areas["upper"]["floor_area_sqft"], expected)
        self.assertAlmostEqual(areas["lower"]["floor_area_sqft"], 240 * 240 / 144.0)

    def test_regenerates_when_stair_moves_and_changes(self):
        c = make()
        sync_stair_holes(c)
        c.stairs[0].start_point = (10.0, 30.0)
        c.stairs[0].total_run = 60.0
        sync_stair_holes(c)
        h = c.rooms[1].holes
        self.assertEqual(len(h), 1)
        self.assertAlmostEqual(polygon_area(h[0].points), 60 * 36)
        xs = [p[0] for p in h[0].points]
        self.assertAlmostEqual(min(xs), 10.0)

    def test_delete_stair_removes_hole(self):
        c = make()
        sync_stair_holes(c)
        c.stairs.clear()
        sync_stair_holes(c)
        self.assertEqual(c.rooms[1].holes, [])

    def test_level_change_moves_hole(self):
        c = make()
        sync_stair_holes(c)
        c.stairs[0].end_level_id = ""
        sync_stair_holes(c)
        self.assertEqual(c.rooms[1].holes, [])

    def test_clipped_to_room_and_spans_two_rooms(self):
        c = make({"start_point": (230.0, 100.0)})  # hangs 110" past the room edge
        sync_stair_holes(c)
        self.assertAlmostEqual(polygon_area(c.rooms[1].holes[0].points), 10 * 36)
        c.rooms.append(Room(square(240, 0, 240), layer_id="la2", identifier="upper2"))
        sync_stair_holes(c)
        self.assertAlmostEqual(polygon_area(c.rooms[2].holes[0].points), 110 * 36)

    def test_lower_ceiling_setting(self):
        c = make()
        sync_stair_holes(c)
        self.assertEqual(c.rooms[0].holes, [])
        c.cut_lower_ceiling_under_stairs = True
        sync_stair_holes(c)
        lower = c.rooms[0]
        self.assertEqual(len(lower.holes), 1)
        self.assertTrue(lower.holes[0].ceiling_only)
        # floor untouched, ceiling cut
        self.assertAlmostEqual(room_floor_area_sqft(lower), 240 * 240 / 144.0)
        self.assertAlmostEqual(room_ceiling_area_sqft(lower), (240 * 240 - 120 * 36) / 144.0)

    def test_clearance_margin(self):
        c = make({"opening_clearance": 2.0})
        sync_stair_holes(c)
        self.assertAlmostEqual(polygon_area(c.rooms[1].holes[0].points), 124 * 40)

    def test_shaped_stairs_parts_do_not_overlap(self):
        for kw in ({"stair_type": "L-shaped", "num_steps": 14},
                   {"stair_type": "L-shaped", "num_steps": 14, "winder_count": 3, "turn_direction": "right"},
                   {"stair_type": "U-shaped", "num_steps": 14, "inner_radius": 4.0},
                   {"stair_type": "U-shaped", "num_steps": 14, "turn_direction": "right"},
                   {"stair_type": "spiral", "inner_radius": 6.0}):
            c = make(dict(kw, start_point=(100.0, 120.0)))
            parts = stair_footprint_parts(c.stairs[0])
            total = sum(polygon_area(p) for p in parts)
            self.assertGreater(total, 0)
            for i in range(len(parts)):
                for j in range(i + 1, len(parts)):
                    inter = polygon_area(clip_polygon_convex(parts[i], parts[j]))
                    self.assertLess(inter, 1e-6, f"{kw}: parts {i},{j} overlap")

    def test_save_load_round_trip(self):
        from unittest.mock import MagicMock
        from EstiSketch.project_io import save_project, open_project
        c = make()
        c.cut_lower_ceiling_under_stairs = True
        c.stairs[0].opening_clearance = 3.0
        sync_stair_holes(c)
        expected = [(len(r.holes), sum(polygon_area(h.points) for h in r.holes))
                    for r in c.rooms]

        def shell(src):
            m = MagicMock()
            for name in ("wall_sets", "rooms", "doors", "windows", "texts", "dimensions",
                         "polyline_sets", "circles", "arcs", "roofs", "stairs",
                         "levels", "layers"):
                setattr(m, name, [])
            m.levels, m.layers = list(src.levels), list(src.layers)
            m.active_level_id, m.active_layer_id = "L1", "la1"
            m.get_layer_by_id = lambda lid: next((l for l in m.layers if l.id == lid), None)
            m.cut_lower_ceiling_under_stairs = False
            return m

        src = shell(c)
        src.rooms, src.stairs = c.rooms, c.stairs
        src.cut_lower_ceiling_under_stairs = True
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.xml")
            save_project(src, 800, 600, path)
            dst = shell(c)
            open_project(dst, path)
        self.assertTrue(dst.cut_lower_ceiling_under_stairs)
        self.assertEqual(dst.stairs[0].opening_clearance, 3.0)
        got = [(len(r.holes), sum(polygon_area(h.points) for h in r.holes))
               for r in dst.rooms]
        self.assertEqual(len(got), 2)
        for (n1, a1), (n2, a2) in zip(expected, got):
            self.assertEqual(n1, n2)
            self.assertAlmostEqual(a1, a2)


class TestOverlappingHoles(unittest.TestCase):
    def _two_stairs(self):
        c = make()
        # Second stair overlaps the first: x 100..220 vs 60..180, y 82..118 vs 102..138
        c.stairs.append(Stair(identifier="S2", start_point=(100.0, 120.0), direction_angle=0.0,
                              start_level_id="L1", end_level_id="L2", width=36.0, total_run=120.0))
        sync_stair_holes(c)
        return c

    def test_union_area_basic(self):
        from EstiSketch.geometry.room_holes import union_area
        self.assertAlmostEqual(union_area([square(0, 0, 10), square(5, 5, 10)]), 175.0)
        self.assertAlmostEqual(union_area([square(0, 0, 10), square(2, 2, 3)]), 100.0)
        self.assertAlmostEqual(union_area([square(0, 0, 10), square(20, 0, 10)]), 200.0)
        # concave L and a square filling its notch
        L = [(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]
        self.assertAlmostEqual(union_area([L, square(5, 5, 5)]), 100.0)

    def test_overlap_counted_once_in_areas(self):
        c = self._two_stairs()
        union = 2 * 120 * 36 - 80 * 16  # overlap x 100..180, y 102..118
        expected = (240 * 240 - union) / 144.0
        upper = c.rooms[1]
        self.assertAlmostEqual(room_floor_area_sqft(upper), expected)
        self.assertAlmostEqual(room_ceiling_area_sqft(upper), expected)
        self.assertAlmostEqual(room_slab_volume_cuft(upper), expected * 0.5)

    def test_overlap_not_refilled_when_rendered(self):
        import cairo
        from EstiSketch.Canvas.wall_room_renderer import draw_rooms
        c = self._two_stairs()
        c.tool_mode, c.current_room_points = "", []
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 260, 260)
        draw_rooms(c, cairo.Context(surf), 1.0)
        surf.flush()
        data, stride = surf.get_data(), surf.get_stride()

        def px(x, y):
            return bytes(data[y * stride + x * 4:y * stride + x * 4 + 4])

        slab_grey = px(230, 230)
        lower_blue = px(140, 110)  # overlap region
        self.assertNotEqual(lower_blue, slab_grey)
        self.assertEqual(px(80, 90), px(140, 110))  # single-stair area == overlap area
        self.assertEqual(px(200, 130), px(140, 110))


class TestRoomAreaReport(unittest.TestCase):
    def test_report_contents(self):
        from EstiSketch.Takeoff.building_takeoff import generate_room_area_report
        c = make()
        text = generate_room_area_report(c)
        self.assertIn("ROOM AREA", text)
        self.assertIn("upper", text)
        self.assertIn("TOTAL", text)


if __name__ == "__main__":
    unittest.main()
