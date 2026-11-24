import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from EstiSketch.Canvas.label_utils import upright_angle  # noqa: E402


@pytest.mark.parametrize("deg,expected", [
    (0, 0), (45, 45), (89, 89), (90, -90), (-90, -90), (135, -45),
    (180, 0), (-135, 45), (270, -90), (-45, -45), (360, 0), (-180, 0),
])
def test_upright_angle(deg, expected):
    got = math.degrees(upright_angle(math.radians(deg)))
    assert got == pytest.approx(expected, abs=1e-6)


def test_never_upside_down():
    for d in range(-720, 721, 7):
        r = upright_angle(math.radians(d))
        assert -math.pi / 2 - 1e-9 <= r < math.pi / 2
