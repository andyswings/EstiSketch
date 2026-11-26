"""Headless tests: openings may be placed anywhere along collinear (split) walls."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from EstiSketch.geometry.wall_chain import collinear_chain, resolve_opening_on_chain


def _wall(start, end, curved=False):
    return SimpleNamespace(start=start, end=end, is_curved=curved, width=6.0)


def _split():
    a, b = _wall((0, 0), (100, 0)), _wall((100, 0), (200, 0))
    return a, b, [a, b]


def test_chain_includes_collinear_neighbour_only() -> None:
    a, b, walls = _split()
    corner = _wall((200, 0), (200, 80))
    far = _wall((300, 0), (400, 0))
    chain = collinear_chain(a, walls + [corner, far])
    assert set(map(id, chain)) == {id(a), id(b)}


def test_centered_on_junction_keeps_full_width_and_uses_one_host() -> None:
    a, b, walls = _split()
    host, ratio = resolve_opening_on_chain(a, 1.0, 48.0, walls)
    centre_x = host.start[0] + ratio * (host.end[0] - host.start[0])
    assert centre_x == pytest.approx(100.0)  # opening spans x=76..124, across the split
    assert host in (a, b)


def test_cursor_on_second_wall_picks_that_wall_as_host() -> None:
    a, b, walls = _split()
    host, ratio = resolve_opening_on_chain(b, 0.5, 36.0, walls)
    assert host is b and ratio == pytest.approx(0.5)


def test_overhang_past_neighbour_is_allowed_but_clamped_to_chain_ends() -> None:
    a, b, walls = _split()
    host, ratio = resolve_opening_on_chain(a, 0.0, 36.0, walls)
    centre_x = host.start[0] + ratio * (host.end[0] - host.start[0])
    assert centre_x == pytest.approx(18.0)
    host, ratio = resolve_opening_on_chain(b, 1.2, 36.0, walls)
    centre_x = host.start[0] + ratio * (host.end[0] - host.start[0])
    assert centre_x == pytest.approx(182.0)


def test_reversed_wall_direction_is_handled() -> None:
    a = _wall((0, 0), (100, 0))
    b = _wall((200, 0), (100, 0))  # drawn right-to-left
    host, ratio = resolve_opening_on_chain(a, 1.0, 48.0, [a, b])
    centre_x = host.start[0] + ratio * (host.end[0] - host.start[0])
    assert centre_x == pytest.approx(100.0)


def test_single_wall_behaviour_unchanged() -> None:
    w = _wall((0, 0), (200, 0))
    assert resolve_opening_on_chain(w, 0.0, 36.0, [w])[1] == pytest.approx(0.09)
    assert resolve_opening_on_chain(w, 0.5, None, [w])[1] == pytest.approx(0.5)
