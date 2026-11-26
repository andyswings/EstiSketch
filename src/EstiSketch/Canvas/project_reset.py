"""Reset a canvas to the empty state used by File > New.

This module is free of GTK/Cairo imports so it can be tested headlessly.
"""
from __future__ import annotations

from typing import Any

from ..components import Layer, Level
from .utils import generate_identifier

# Every list of drawn/project objects held by the canvas. Cleared in place so any
# alias held elsewhere stays consistent with the canvas.
CONTENT_LIST_ATTRS: tuple[str, ...] = (
    "wall_sets", "walls", "rooms", "doors", "windows", "texts", "dimensions",
    "dimension_chains", "leader_callouts", "polylines", "polyline_sets",
    "circles", "arcs", "roofs", "stairs", "fixtures", "floor_openings", "groups",
    "blueprints", "selected_items", "clipboard", "undo_stack", "redo_stack",
    "current_room_points", "current_opening_points", "dimension_chain_points",
)

# In-progress drawing state that must not survive into a new project.
TRANSIENT_NONE_ATTRS: tuple[str, ...] = (
    "current_wall", "current_room_preview", "current_opening_preview",
    "current_polyline_start", "current_polyline_preview", "wall_curve_point",
    "dimension_start", "dimension_end", "dimension_offset_preview",
    "dimension_chain_offset", "dimension_chain_preview_point", "leader_tip",
    "leader_elbow", "leader_preview_point", "circle_center",
    "circle_radius_preview", "arc_start", "arc_end", "arc_preview_point",
    "editing_wall", "editing_handle", "dragging_group", "rotating_group",
    "ghost_level_id", "alignment_candidate", "raw_current_end",
    "edit_face_guide", "active_blueprint", "calibrating_blueprint",
)

TRANSIENT_FALSE_ATTRS: tuple[str, ...] = (
    "drawing_wall", "wall_curve_mode", "drawing_polyline", "drawing_dimension",
    "drawing_dimension_chain", "drawing_leader", "drawing_circle", "drawing_arc",
    "box_selecting",
)


def reset_canvas_content(canvas: Any) -> None:
    """Remove all project content from ``canvas`` and restore default level/layer.

    Clears every object list, in-progress drawing state, selection, clipboard and
    undo/redo history, then recreates the single default "Level 1" / "Layer 0".
    Project-level settings (north angle, takeoff state, print settings) return to
    their defaults so a new project never inherits the previous one's data.

    Args:
        canvas: The ``CanvasArea`` (or a compatible object) to reset.
    """
    for name in CONTENT_LIST_ATTRS:
        value = getattr(canvas, name, None)
        if isinstance(value, list):
            value.clear()
    surfaces = getattr(canvas, "_blueprint_surfaces", None)
    if isinstance(surfaces, dict):
        surfaces.clear()
    for name in TRANSIENT_NONE_ATTRS:
        if hasattr(canvas, name):
            setattr(canvas, name, None)
    for name in TRANSIENT_FALSE_ATTRS:
        if hasattr(canvas, name):
            setattr(canvas, name, False)

    canvas.existing_ids = []
    level_id = generate_identifier("level", canvas.existing_ids)
    canvas.existing_ids.append(level_id)
    layer_id = generate_identifier("layer", canvas.existing_ids)
    canvas.existing_ids.append(layer_id)
    canvas.levels = [Level(id=level_id, name="Level 1", elevation=0.0)]
    canvas.active_level_id = level_id
    canvas.layers = [Layer(id=layer_id, name="Layer 0", visible=True, locked=False,
                           opacity=1.0, level_id=level_id)]
    canvas.active_layer_id = layer_id

    canvas.north_angle = 0.0
    canvas.cut_lower_ceiling_under_stairs = False
    canvas.print_settings = None
    canvas.takeoff_state = {
        "assumptions": {}, "overrides": {}, "custom_items": [], "reference": None,
    }
