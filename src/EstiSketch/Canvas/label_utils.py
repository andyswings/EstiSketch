"""Shared helpers for orienting wall-aligned text labels (SweetHome3D style)."""
import math

_EPS = 1e-9


def upright_angle(theta: float) -> float:
    """Return the text rotation closest to ``theta`` that reads right-side up.

    Text follows the wall angle and is flipped by 180 degrees when it would
    otherwise be upside down. With the y-down canvas, the readable range is
    [-90deg, 90deg), so exactly vertical walls read bottom-to-top.

    Args:
        theta: Wall angle in radians (any range).

    Returns:
        Rotation in radians, normalised to [-pi/2, pi/2).
    """
    t = math.atan2(math.sin(theta), math.cos(theta))  # (-pi, pi]
    half_pi = math.pi / 2
    if t >= half_pi - _EPS or t < -half_pi - _EPS:
        t -= math.copysign(math.pi, t)
    return t
