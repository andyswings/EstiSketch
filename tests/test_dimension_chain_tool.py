"""Tests for the continuous dimension chain tool: creation, live preview,
auto-dimensioning, segment editing, drag snapping, and rendering."""
import math
from types import SimpleNamespace

import pytest
import gi
gi.require_version("Gtk", "4.0")

import cairo
from EstiSketch.components import DimensionChain, Wall, Room
from EstiSketch.Canvas.canvas_area import CanvasArea
from EstiSketch import config


@pytest.fixture
def canvas():
    cfg = SimpleNamespace(**config.load_config())
    cv = CanvasArea(cfg)
    cv.zoom = 1.0
    cv.offset_x = 0.0
    cv.offset_y = 0.0
    cv.tool_mode = "add_dimension_chain"
    cv.snap_manager.snap_enabled = False
    cv.dimension_chains = []
    cv.walls = []
    cv.wall_sets = []
    cv.rooms = []
    return cv


def dev(cv, mx, my):
    """Model coords -> device coords for the click handlers."""
    ppi = getattr(cv.config, "PIXELS_PER_INCH", 2.0)
    return mx * cv.zoom * ppi + cv.offset_x, my * cv.zoom * ppi + cv.offset_y


def click(cv, mx, my, n_press=1):
    x, y = dev(cv, mx, my)
    cv._handle_dimension_chain_click(n_press, x, y)


def lengths(chain):
    seg = DimensionChainHelper.sorted_t(chain)
    return [round(b - a, 6) for a, b in zip(seg, seg[1:])]


class DimensionChainHelper:
    @staticmethod
    def sorted_t(chain):
        p0, p1 = chain.points[0], chain.points[1]
        blen = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        ux, uy = (p1[0] - p0[0]) / blen, (p1[1] - p0[1]) / blen
        return sorted((p[0] - p0[0]) * ux + (p[1] - p0[1]) * uy for p in chain.points)


# ---------------------------------------------------------------- creation
class TestCreation:
    def test_basic_three_click_chain(self, canvas):
        click(canvas, 0, 0)
        assert canvas.drawing_dimension_chain
        click(canvas, 100, 0)
        click(canvas, 100, 40)  # far from baseline, unsnapped -> offset, finishes
        assert len(canvas.dimension_chains) == 1
        chain = canvas.dimension_chains[0]
        assert chain.points == [(0, 0), (100, 0)]
        assert chain.offset == pytest.approx(40.0)
        assert not canvas.drawing_dimension_chain

    def test_intermediate_points_stay_in_same_chain(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 40, 1)   # near baseline (<6") -> intermediate point
        click(canvas, 70, -2)
        assert canvas.drawing_dimension_chain
        assert len(canvas.dimension_chains) == 0
        assert len(canvas.dimension_chain_points) == 4
        click(canvas, 50, 30)  # offset click
        assert len(canvas.dimension_chains) == 1
        assert len(canvas.dimension_chains[0].points) == 4

    def test_snapped_click_off_baseline_adds_point(self, canvas):
        """Regression: a snapped click >6" off the baseline used to start a new chain."""
        canvas.snap_manager.snap_enabled = True
        canvas.walls = [Wall((50.0, 20.0), (150.0, 20.0), width=6.0, height=96.0, identifier="w")]
        canvas.wall_sets = [canvas.walls]
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        canvas.snap_manager.snap_point = lambda *a, **k: ((50.0, 20.0), "endpoint")
        click(canvas, 50, 20)
        assert canvas.drawing_dimension_chain
        assert (50.0, 20.0) in canvas.dimension_chain_points
        assert len(canvas.dimension_chains) == 0

    @pytest.mark.parametrize("snap_type", ["grid", "angle", "axis", "alignment_vertical", "distance", "none"])
    def test_generic_snaps_do_not_count_as_feature_snaps(self, canvas, snap_type):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        canvas.snap_manager.snap_point = lambda *a, **k: ((50.0, 30.0), snap_type)
        click(canvas, 50, 30)
        assert len(canvas.dimension_chains) == 1  # treated as the offset click

    @pytest.mark.parametrize("snap_type", ["endpoint", "midpoint", "wall_centerline", "face_flush", "wall_edge"])
    def test_feature_snaps_add_points(self, canvas, snap_type):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        canvas.snap_manager.snap_point = lambda *a, **k: ((50.0, 30.0), snap_type)
        click(canvas, 50, 30)
        assert canvas.dimension_chains == []
        assert len(canvas.dimension_chain_points) == 3

    def test_second_click_too_close_is_ignored(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 0.1, 0.1)
        assert canvas.dimension_chain_points == [(0, 0)]

    def test_duplicate_intermediate_point_ignored(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 50, 0)
        click(canvas, 50.1, 0)
        assert len(canvas.dimension_chain_points) == 3

    def test_double_click_finishes_chain(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 60, 0)
        click(canvas, 60, 0, n_press=2)
        assert len(canvas.dimension_chains) == 1
        assert len(canvas.dimension_chains[0].points) == 3
        assert abs(canvas.dimension_chains[0].offset) >= 1.0

    def test_finalize_with_one_point_creates_nothing(self, canvas):
        click(canvas, 0, 0)
        canvas.finalize_dimension_chain()
        assert canvas.dimension_chains == []
        assert not canvas.drawing_dimension_chain

    def test_tiny_offset_gets_default(self, canvas):
        canvas.dimension_chain_points = [(0, 0), (100, 0)]
        canvas.drawing_dimension_chain = True
        canvas.dimension_chain_offset = 0.2
        canvas.finalize_dimension_chain()
        assert canvas.dimension_chains[0].offset == 18.0

    def test_negative_offset_preserved(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 50, -30)
        assert canvas.dimension_chains[0].offset == pytest.approx(-30.0)

    def test_vertical_and_diagonal_baselines(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 0, 100)
        click(canvas, 40, 50)
        assert canvas.dimension_chains[0].offset == pytest.approx(-40.0)
        click(canvas, 0, 0)
        click(canvas, 100, 100)
        click(canvas, 100, 0)
        assert abs(canvas.dimension_chains[1].offset) == pytest.approx(100 / math.sqrt(2))

    def test_chain_gets_active_layer_and_unique_id(self, canvas):
        for _ in range(2):
            click(canvas, 0, 0)
            click(canvas, 100, 0)
            click(canvas, 50, 30)
        ids = [c.identifier for c in canvas.dimension_chains]
        assert len(set(ids)) == 2
        assert all(c.layer_id == canvas.active_layer_id for c in canvas.dimension_chains)

    def test_new_chain_is_selected(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 50, 30)
        assert canvas.selected_items[0]["object"] is canvas.dimension_chains[0]

    def test_creation_is_undoable(self, canvas):
        canvas.save_state()
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 50, 30)
        assert len(canvas.dimension_chains) == 1
        canvas.undo()
        assert canvas.dimension_chains == []


# ---------------------------------------------------------------- hover / live preview
class TestHoverPreview:
    def setup_chain(self, canvas):
        canvas.drawing_dimension_chain = True
        canvas.dimension_chain_points = [(0.0, 0.0), (100.0, 0.0)]

    def test_no_points_no_hover(self, canvas):
        assert canvas._chain_hover_point(10, 10) is None

    def test_first_point_hover_follows_cursor(self, canvas):
        canvas.drawing_dimension_chain = True
        canvas.dimension_chain_points = [(0.0, 0.0)]
        assert canvas._chain_hover_point(30, 40) == (30, 40)

    def test_hover_near_baseline_is_a_point(self, canvas):
        self.setup_chain(canvas)
        assert canvas._chain_hover_point(60, 3) == (60, 3)

    def test_hover_far_unsnapped_is_offset_mode(self, canvas):
        self.setup_chain(canvas)
        assert canvas._chain_hover_point(60, 30) is None

    def test_hover_far_but_snapped_is_a_point(self, canvas):
        self.setup_chain(canvas)
        canvas.snap_manager.snap_point = lambda *a, **k: ((60.0, 30.0), "endpoint")
        assert canvas._chain_hover_point(60, 30) == (60.0, 30.0)

    def test_hover_degenerate_baseline(self, canvas):
        canvas.drawing_dimension_chain = True
        canvas.dimension_chain_points = [(0.0, 0.0), (0.0, 0.0)]
        assert canvas._chain_hover_point(5, 5) is None

    def test_preview_renders_with_hover(self, canvas):
        self.setup_chain(canvas)
        canvas.dimension_chain_hover = (60.0, 2.0)
        canvas._last_mouse_pos = (60.0, 2.0)
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 300)
        cr = cairo.Context(surface)
        canvas.draw_dimension_chains(cr)
        canvas.dimension_chain_hover = None  # offset mode: no extra point
        canvas.draw_dimension_chains(cr)
        canvas.dimension_chain_points = [(0.0, 0.0)]
        canvas.dimension_chain_hover = (50.0, 0.0)  # first-segment live label
        canvas.draw_dimension_chains(cr)

    def test_live_label_draws(self, canvas):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 200)
        cr = cairo.Context(surface)
        canvas._draw_chain_live_label(cr, (0, 0), (100, 0), 2.0)
        canvas._draw_chain_live_label(cr, (100, 0), (0, 0), 2.0)  # upside-down flip
        canvas._draw_chain_live_label(cr, (0, 0), (0, 0), 2.0)    # zero length

    def test_hover_cleared_after_finalize(self, canvas):
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        canvas.dimension_chain_hover = (50, 0)
        click(canvas, 50, 30)
        assert canvas.dimension_chain_hover is None


# ---------------------------------------------------------------- auto dimension (double-click)
class TestAutoDimension:
    def test_double_click_wall_creates_chain(self, canvas):
        wall = Wall((0.0, 0.0), (120.0, 0.0), width=6.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        click(canvas, 60, 0.5)  # first press of the double-click
        click(canvas, 60, 0.5, n_press=2)
        assert len(canvas.dimension_chains) == 1
        chain = canvas.dimension_chains[0]
        assert len(chain.points) == 2
        assert abs(chain.points[1][0] - chain.points[0][0]) == pytest.approx(120.0)
        assert abs(chain.points[0][1]) == pytest.approx(3.0)  # on a wall face
        assert not canvas.drawing_dimension_chain
        assert canvas.dimension_chain_points == []

    def test_wall_side_decides_face_and_offset_sign(self, canvas):
        wall = Wall((0.0, 0.0), (120.0, 0.0), width=6.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        assert canvas._auto_dimension_chain_at(60, 2.0, 2.0)
        assert canvas._auto_dimension_chain_at(60, -2.0, 2.0)
        a, b = canvas.dimension_chains
        assert a.points[0][1] == pytest.approx(-b.points[0][1])
        assert a.offset == -b.offset

    def test_vertical_wall(self, canvas):
        wall = Wall((0.0, 0.0), (0.0, 90.0), width=6.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        assert canvas._auto_dimension_chain_at(1.0, 45.0, 2.0)
        pts = canvas.dimension_chains[0].points
        assert abs(pts[1][1] - pts[0][1]) == pytest.approx(90.0)

    def test_double_click_room_edge_creates_chain(self, canvas):
        room = Room([(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)])
        canvas.rooms = [room]
        click(canvas, 50, 0.5)
        click(canvas, 50, 0.5, n_press=2)
        assert len(canvas.dimension_chains) == 1
        assert sorted(canvas.dimension_chains[0].points) == [(0.0, 0.0), (100.0, 0.0)]

    def test_room_closing_edge(self, canvas):
        room = Room([(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)])
        canvas.rooms = [room]
        assert canvas._auto_dimension_chain_at(0.5, 40, 2.0)
        assert sorted(canvas.dimension_chains[0].points) == [(0.0, 0.0), (0.0, 80.0)]

    def test_wall_preferred_over_room(self, canvas):
        wall = Wall((0.0, 0.0), (100.0, 0.0), width=6.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        canvas.rooms = [Room([(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)])]
        canvas._auto_dimension_chain_at(50, 0.5, 2.0)
        assert abs(canvas.dimension_chains[0].points[0][1]) == pytest.approx(3.0)

    def test_double_click_empty_space_does_nothing(self, canvas):
        click(canvas, 500, 500)
        click(canvas, 500, 500, n_press=2)
        assert canvas.dimension_chains == []
        assert not canvas.drawing_dimension_chain

    def test_zero_length_wall_ignored(self, canvas):
        wall = Wall((10.0, 10.0), (10.0, 10.0), width=6.0, height=96.0, identifier="w0")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        assert not canvas._auto_dimension_chain_at(10, 10, 2.0)

    def test_double_click_mid_chain_does_not_auto_dimension(self, canvas):
        wall = Wall((0.0, 0.0), (120.0, 0.0), width=6.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        click(canvas, 0, 0)
        click(canvas, 100, 0)
        click(canvas, 50, 0)
        click(canvas, 50, 0, n_press=2)
        assert len(canvas.dimension_chains) == 1
        assert len(canvas.dimension_chains[0].points) == 3

    def test_locked_or_hidden_wall_still_resolves_geometry(self, canvas):
        wall = Wall((0.0, 0.0), (120.0, 0.0), width=0.0, height=96.0, identifier="w1")
        canvas.walls = [wall]
        canvas.wall_sets = [[wall]]
        assert canvas._auto_dimension_chain_at(60, 0.2, 2.0)  # zero thickness: on centerline
        assert canvas.dimension_chains[0].points[0][1] == pytest.approx(0.0)


# ---------------------------------------------------------------- segment helpers
class TestSegments:
    def make(self, canvas, pts):
        chain = DimensionChain(points=list(pts), offset=20.0, identifier="c", layer_id=canvas.active_layer_id)
        canvas.dimension_chains.append(chain)
        return chain

    def test_segments_sorted_along_baseline(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (70, 0), (30, 0)])
        (ux, uy), items = canvas._chain_segments(chain)
        assert (ux, uy) == (1.0, 0.0)
        assert [i for _, i, _ in items] == [0, 3, 2, 1]

    def test_segments_too_few_or_degenerate(self, canvas):
        assert canvas._chain_segments(self.make(canvas, [(0, 0)])) is None
        assert canvas._chain_segments(self.make(canvas, [(5, 5), (5, 5)])) is None

    def test_baseline_pointing_left(self, canvas):
        chain = self.make(canvas, [(100, 0), (0, 0), (60, 0)])
        (ux, _), items = canvas._chain_segments(chain)
        assert ux == -1.0
        assert [i for _, i, _ in items] == [0, 2, 1]

    def test_set_length_slides_later_points(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._set_chain_segment_length(chain, 0, 60.0)  # segment 0..40 -> 60
        assert lengths(chain) == [60.0, 60.0]
        assert chain.points[0] == (0, 0)
        assert chain.points[2] == (60.0, 0.0)
        assert chain.points[1] == (120.0, 0.0)

    def test_set_length_shorter(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._set_chain_segment_length(chain, 1, 10.0)
        assert lengths(chain) == [40.0, 10.0]

    def test_set_length_last_segment(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._set_chain_segment_length(chain, 1, 25.0)
        assert chain.points[1] == (65.0, 0.0)

    def test_set_length_keeps_perpendicular_position(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 7)])
        canvas._set_chain_segment_length(chain, 0, 50.0)
        assert chain.points[2] == (50.0, 7.0)
        assert chain.points[1] == (110.0, 0.0)

    def test_set_length_diagonal(self, canvas):
        chain = self.make(canvas, [(0, 0), (30, 40), (15, 20)])  # length 50, mid 25
        canvas._set_chain_segment_length(chain, 0, 35.0)
        assert lengths(chain) == pytest.approx([35.0, 25.0])
        assert chain.points[1] == pytest.approx((30 + 6, 40 + 8))

    def test_set_length_on_segment_between_baseline_points(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._set_chain_segment_length(chain, 0, 150.0)
        assert chain.points == [(0, 0), (150.0, 0.0)]

    def test_set_length_with_p0_in_upper_group(self, canvas):
        # Baseline points are not the extremes; baseline direction must survive.
        chain = self.make(canvas, [(50, 0), (80, 0), (0, 0)])
        canvas._set_chain_segment_length(chain, 0, 70.0)  # 0..50 segment
        p0, p1 = chain.points[0], chain.points[1]
        assert p1[0] > p0[0]
        assert lengths(chain) == pytest.approx([70.0, 30.0])

    def test_set_length_is_undoable(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas.save_state()
        canvas._set_chain_segment_length(chain, 0, 60.0)
        canvas.undo()
        assert canvas.dimension_chains[0].points[1] == (100, 0)

    def test_set_length_noop_on_degenerate_chain(self, canvas):
        chain = self.make(canvas, [(5, 5), (5, 5)])
        canvas._set_chain_segment_length(chain, 0, 10.0)
        assert chain.points == [(5, 5), (5, 5)]

    def test_double_click_hit_test_miss(self, canvas):
        self.make(canvas, [(0, 0), (100, 0)])
        canvas.tool_mode = "select"
        x, y = dev(canvas, 50, 200)  # far from the chain's dimension line
        assert canvas._try_edit_chain_segment(x, y) is False

    def test_double_click_hit_test_hit(self, canvas, monkeypatch):
        from EstiSketch.Dialogs import length_input_dialog
        opened = {}

        class FakeDialog:
            def __init__(self, parent=None, title=""):
                opened["title"] = title
                self.entry = SimpleNamespace(set_text=lambda t: opened.update(text=t))

            def connect(self, sig, cb):
                opened["cb"] = cb

            def present(self):
                pass

            def get_length(self):
                return "5'"

            def destroy(self):
                opened["destroyed"] = True

        monkeypatch.setattr(length_input_dialog, "LengthInputDialog", FakeDialog)
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas.tool_mode = "select"
        x, y = dev(canvas, 70, 20)  # on the dimension line, second segment
        assert canvas._try_edit_chain_segment(x, y) is True
        assert "Segment" in opened["title"]
        from gi.repository import Gtk
        opened["cb"](FakeDialog(), Gtk.ResponseType.OK)
        assert lengths(chain)[1] == pytest.approx(60.0)  # 5' = 60"
        assert opened["destroyed"]

    def test_dialog_cancel_and_invalid_input(self, canvas, monkeypatch):
        from EstiSketch.Dialogs import length_input_dialog
        cbs = {}

        class FakeDialog:
            text = "garbage"

            def __init__(self, parent=None, title=""):
                self.entry = SimpleNamespace(set_text=lambda t: None)

            def connect(self, sig, cb):
                cbs["cb"] = cb

            def present(self):
                pass

            def get_length(self):
                return self.text

            def destroy(self):
                pass

        monkeypatch.setattr(length_input_dialog, "LengthInputDialog", FakeDialog)
        from gi.repository import Gtk
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        x, y = dev(canvas, 70, 20)
        canvas._try_edit_chain_segment(x, y)
        cbs["cb"](FakeDialog(), Gtk.ResponseType.OK)       # invalid text
        cbs["cb"](FakeDialog(), Gtk.ResponseType.CANCEL)   # cancelled
        FakeDialog.text = "0"
        cbs["cb"](FakeDialog(), Gtk.ResponseType.OK)       # zero length rejected
        FakeDialog.text = "-5"
        cbs["cb"](FakeDialog(), Gtk.ResponseType.OK)       # negative rejected
        assert chain.points == [(0, 0), (100, 0), (40, 0)]

    def test_locked_chain_not_editable(self, canvas, monkeypatch):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        monkeypatch.setattr(canvas, "is_object_on_locked_layer", lambda o: True)
        x, y = dev(canvas, 70, 20)
        assert canvas._try_edit_chain_segment(x, y) is False


# ---------------------------------------------------------------- dragging with snapping
class TestDragging:
    def make(self, canvas, pts, offset=20.0):
        chain = DimensionChain(points=list(pts), offset=offset, identifier="c", layer_id=canvas.active_layer_id)
        canvas.dimension_chains.append(chain)
        return chain

    def test_offset_drag(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._drag_chain_handle(chain, "offset", 0, 50, -35)
        assert chain.offset == pytest.approx(-35.0)

    def test_offset_drag_degenerate_noop(self, canvas):
        chain = self.make(canvas, [(0, 0)])
        canvas._drag_chain_handle(chain, "offset", 0, 50, 35)
        assert chain.offset == 20.0

    def test_unsnapped_intermediate_slides_along_baseline(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 5)])
        canvas._drag_chain_handle(chain, "point", 2, 63, 80)
        assert chain.points[2] == pytest.approx((63.0, 5.0))

    def test_intermediate_on_diagonal_baseline(self, canvas):
        chain = self.make(canvas, [(0, 0), (60, 80), (30, 40)])
        canvas._drag_chain_handle(chain, "point", 2, 45, 60)
        assert chain.points[2] == pytest.approx((45.0, 60.0))
        canvas._drag_chain_handle(chain, "point", 2, 45, 0)  # off-axis drag is projected
        t = (chain.points[2][0] * 0.6 + chain.points[2][1] * 0.8)
        assert chain.points[2][0] * 0.8 - chain.points[2][1] * 0.6 == pytest.approx(0.0, abs=1e-6)
        assert t == pytest.approx(45 * 0.6)

    def test_baseline_points_move_freely(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._drag_chain_handle(chain, "point", 1, 90, 20)
        assert chain.points[1] == (90, 20)

    def test_cannot_collapse_baseline(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._drag_chain_handle(chain, "point", 1, 0.2, 0.1)
        assert chain.points[1] == (100, 0)
        canvas._drag_chain_handle(chain, "point", 0, 100.1, 0.0)
        assert chain.points[0] == (0, 0)

    def test_snap_to_wall_endpoint_while_dragging(self, canvas):
        canvas.snap_manager.snap_enabled = True
        canvas.walls = [Wall((75.0, 40.0), (175.0, 40.0), width=6.0, height=96.0, identifier="w")]
        canvas.wall_sets = [canvas.walls]
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 75.0 + 0.5, 3.0)
        # x snaps to the wall endpoint x (alignment / endpoint snap), y stays on baseline
        assert chain.points[2][0] == pytest.approx(75.0, abs=0.01)
        assert chain.points[2][1] == pytest.approx(0.0)

    def test_snap_to_other_chain_point(self, canvas):
        canvas.snap_manager.snap_enabled = True
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 99.0, 0.0)
        assert chain.points[2][0] == pytest.approx(100.0, abs=0.01)

    def test_baseline_point_snaps_to_wall_corner(self, canvas):
        canvas.snap_manager.snap_enabled = True
        canvas.walls = [Wall((200.0, 50.0), (300.0, 50.0), width=0.0, height=96.0, identifier="w")]
        canvas.wall_sets = [canvas.walls]
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._drag_chain_handle(chain, "point", 1, 201.0, 49.0)
        assert chain.points[1] == pytest.approx((200.0, 50.0), abs=0.01)

    def test_far_from_everything_does_not_snap(self, canvas):
        canvas.snap_manager.snap_enabled = True
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 63.37, 0.0)
        assert 55 < chain.points[2][0] < 70

    def test_snapping_disabled_gives_exact_position(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 63.37, 0.0)
        assert chain.points[2][0] == pytest.approx(63.37)

    def test_dragged_point_excluded_from_its_own_snap_candidates(self, canvas):
        canvas.snap_manager.snap_enabled = True
        captured = {}
        orig = canvas.snap_manager.snap_point

        def spy(x, y, bx, by, walls, rooms, **kw):
            captured["pts"] = kw.get("in_progress_points")
            return orig(x, y, bx, by, walls, rooms, **kw)

        canvas.snap_manager.snap_point = spy
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 45, 0)
        assert (40, 0) not in captured["pts"]
        assert (0, 0) in captured["pts"] and (100, 0) in captured["pts"]

    def test_bad_handle_index_or_type_ignored(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0)])
        canvas._drag_chain_handle(chain, "point", 9, 5, 5)
        canvas._drag_chain_handle(chain, "point", -1, 5, 5)
        canvas._drag_chain_handle(chain, "bogus", 0, 5, 5)
        assert chain.points == [(0, 0), (100, 0)]

    def test_dragging_intermediate_past_ends_extends_chain(self, canvas):
        chain = self.make(canvas, [(0, 0), (100, 0), (40, 0)])
        canvas._drag_chain_handle(chain, "point", 2, 150, 0)
        assert chain.total_length == pytest.approx(150.0)
        canvas._drag_chain_handle(chain, "point", 2, -20, 0)
        assert chain.total_length == pytest.approx(120.0)


# ---------------------------------------------------------------- data model / rendering / io
class TestModelAndRendering:
    def test_total_length_ignores_perpendicular_spread(self):
        chain = DimensionChain(points=[(0, 0), (100, 0), (50, 80)])
        assert chain.total_length == pytest.approx(100.0)

    def test_total_length_degenerate(self):
        assert DimensionChain(points=[]).total_length == 0.0
        assert DimensionChain(points=[(1, 1)]).total_length == 0.0
        assert DimensionChain(points=[(1, 1), (1, 1)]).total_length == 0.0

    def test_sorted_points_degenerate(self):
        assert DimensionChain(points=[(1, 1)]).get_sorted_points() == [(1, 1)]
        pts = [(1, 1), (1, 1), (3, 3)]
        assert DimensionChain(points=pts).get_sorted_points() == pts

    @pytest.mark.parametrize("pts,offset,style", [
        ([(0, 0), (100, 0)], 20, "architectural_tick"),
        ([(0, 0), (100, 0), (40, 0), (40.001, 0)], -20, "architectural_tick"),
        ([(0, 0), (0, 100), (0, 30)], 15, "arrow"),
        ([(100, 100), (0, 0), (50, 50)], 15, "arrow"),
        ([(0, 0), (100, 0)], 0, "architectural_tick"),
    ])
    def test_draw_chain_variants_do_not_crash(self, canvas, pts, offset, style):
        chain = DimensionChain(points=pts, offset=offset, arrow_style=style, summary_dimension=True,
                               line_style="dashed")
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 400, 400)
        cr = cairo.Context(surface)
        canvas._draw_single_dimension_chain(cr, chain, 2.0)
        canvas._draw_single_dimension_chain(cr, chain, 2.0, is_preview=True)

    def test_draw_degenerate_chains_are_skipped(self, canvas):
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
        cr = cairo.Context(surface)
        for pts in ([], [(0, 0)], [(5, 5), (5, 5)]):
            canvas._draw_single_dimension_chain(cr, DimensionChain(points=pts), 2.0)

    def test_chains_persist_and_roundtrip_after_edit(self, canvas, tmp_path):
        from EstiSketch.project_io import save_project, open_project
        chain = DimensionChain(points=[(0, 0), (100, 0), (40, 0)], offset=20.0, identifier="c1",
                               layer_id=canvas.active_layer_id)
        canvas.dimension_chains.append(chain)
        canvas._set_chain_segment_length(chain, 0, 60.0)
        path = str(tmp_path / "p.estisketch")
        save_project(canvas, 1024, 900, path)
        cv2 = CanvasArea(SimpleNamespace(**config.load_config()))
        open_project(cv2, path)
        assert len(cv2.dimension_chains) == 1
        assert cv2.dimension_chains[0].points[1] == pytest.approx((120.0, 0.0))
