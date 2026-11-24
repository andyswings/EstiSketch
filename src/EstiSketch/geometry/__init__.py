"""
geometry package for EstiSketch
"""
from .roof_solver import (
    build_plane_equations,
    intersect_planes,
    solve_junction_vertex,
    clip_facets_to_boundary,
    solve_roof_geometry,
    compute_polygon_area_3d,
    compute_polygon_signed_area_2d,
)

__all__ = [
    "build_plane_equations",
    "intersect_planes",
    "solve_junction_vertex",
    "clip_facets_to_boundary",
    "solve_roof_geometry",
    "compute_polygon_area_3d",
    "compute_polygon_signed_area_2d",
]
