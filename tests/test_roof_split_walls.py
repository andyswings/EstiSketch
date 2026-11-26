"""Headless tests: roofs over walls that were split must match the unsplit roof."""
from __future__ import annotations

from types import SimpleNamespace

from EstiSketch.Canvas.complex_roof import (
    calculate_complex_roof_geometry,
    merge_collinear_items,
    order_walls_into_loop,
)

Point = tuple[float, float]


def _wall(ident: str, start: Point, end: Point) -> SimpleNamespace:
    return SimpleNamespace(identifier=ident, start=start, end=end, width=6.0)


def _rect_walls() -> list[SimpleNamespace]:
    return [
        _wall("n", (0, 0), (400, 0)),
        _wall("e", (400, 0), (400, 240)),
        _wall("s", (400, 240), (0, 240)),
        _wall("w", (0, 240), (0, 0)),
    ]


def _split_rect_walls() -> list[SimpleNamespace]:
    return [
        _wall("n1", (0, 0), (150, 0)),
        _wall("n2", (150, 0), (400, 0)),
        _wall("e", (400, 0), (400, 240)),
        _wall("s1", (400, 240), (200, 240)),
        _wall("s2", (200, 240), (0, 240)),
        _wall("w1", (0, 240), (0, 100)),
        _wall("w2", (0, 100), (0, 0)),
    ]


def _norm(lines: list) -> list:
    return sorted(
        tuple(sorted((round(a[0], 3), round(a[1], 3)) for a in seg)) for seg in lines
    )


def _geometry(walls: list, markings: dict[str, str]) -> tuple:
    return calculate_complex_roof_geometry(walls, markings, 12.0, 6.0, 12.0)


def test_merge_collinear_collapses_split_sides() -> None:
    ordered = order_walls_into_loop(_split_rect_walls())
    merged = merge_collinear_items(ordered)
    assert len(ordered) == 7
    assert len(merged) == 4


def test_split_hip_roof_matches_unsplit() -> None:
    plain = _geometry(_rect_walls(), {})
    split = _geometry(_split_rect_walls(), {})
    for plain_lines, split_lines in zip(plain[:5], split[:5]):  # outline excluded
        assert _norm(plain_lines) == _norm(split_lines)
    assert len(split[0]) == 1  # one ridge
    assert len(split[1]) == 4  # four hips


def test_split_gable_roof_matches_unsplit() -> None:
    plain = _geometry(_rect_walls(), {"n": "eave", "s": "eave", "e": "gable", "w": "gable"})
    marks = {"n1": "eave", "n2": "eave", "s1": "eave", "s2": "eave",
             "e": "gable", "w1": "gable", "w2": "gable"}
    split = _geometry(_split_rect_walls(), marks)
    assert _norm(plain[0]) == _norm(split[0])
    assert len(split[0]) == 1
