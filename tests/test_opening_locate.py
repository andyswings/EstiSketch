import math
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("gi")

from EstiSketch.Canvas.events_tools import CanvasToolsMixin  # noqa: E402
from EstiSketch.Canvas.events_helpers import *  # noqa: E402,F401,F403
import EstiSketch.Canvas.events_helpers as eh  # noqa: E402


def _helpers_cls():
    for v in vars(eh).values():
        if isinstance(v, type) and hasattr(v, "distance_point_to_segment"):
            return v
    pytest.skip("helpers mixin not found")


class Harness(CanvasToolsMixin):
    pass


def _make(walls):
    H = type("H", (CanvasToolsMixin, _helpers_cls()), {})
    h = H.__new__(H)
    h.config = SimpleNamespace(PIXELS_PER_INCH=1.0, DEFAULT_DOOR_TYPE="single",
                               DEFAULT_WINDOW_TYPE="sliding")
    h.zoom = 1.0
    h.offset_x = 0.0
    h.offset_y = 0.0
    h.active_layer_id = "L1"
    h.wall_sets = [walls]
    return h


def _wall(a, b):
    return SimpleNamespace(start=a, end=b, is_curved=False, arc_center=None,
                           arc_radius=None, width=6.0)


def test_locate_midpoint():
    h = _make([_wall((0, 0), (200, 0))])
    wall, ratio = h._locate_on_wall(100, 2)
    assert ratio == pytest.approx(0.5)


def test_locate_none_when_far():
    h = _make([_wall((0, 0), (200, 0))])
    assert h._locate_on_wall(100, 80) is None


def test_ratio_clamped_for_opening_width():
    h = _make([_wall((0, 0), (200, 0))])
    _, ratio = h._locate_on_wall(1, 0, opening_width=36.0)
    assert ratio == pytest.approx(18.0 / 200.0)
    _, ratio = h._locate_on_wall(199, 0, opening_width=36.0)
    assert ratio == pytest.approx(1.0 - 18.0 / 200.0)


def test_default_builders_match_dims():
    h = _make([])
    d = h._build_default_door(identifier="ghost")
    assert d.width == h._default_door_dims()[0]
    assert h._build_default_window().width == 48.0
