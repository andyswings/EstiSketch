"""
ui/properties_panel.py

Properties Panel & State Binding for EstiSketch Roof Geometry Engine.
Phase 3 implementation:
- Connects overhang input box to selected eave's O_i
- Connects pitch dropdowns/inputs to individual roof planes P_i
- On change, triggers roof_solver.solve() and updates 3D scene and takeoff calculations.
"""
from typing import List, Optional, Any, Dict, Callable

from models.roof import RoofPlane, RoofEdge, RoofVertex
from geometry.roof_solver import solve_roof_geometry

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


def bind_roof_overhang(roof: Any, overhang_inches: float, canvas: Optional[Any] = None, eave_id: Optional[str] = None):
    """
    Connect overhang input to selected eave's O_i or global roof overhang.
    Triggers roof solve and updates takeoff and canvas.
    """
    if not roof:
        return

    # Update overall overhang
    roof.overhang = float(overhang_inches)

    # Update specific eave edge or all eave edges
    if hasattr(roof, 'edges'):
        for edge in roof.edges:
            if edge.edge_type == 'eave':
                if eave_id is None or edge.wall_identifier == eave_id:
                    edge.overhang = float(overhang_inches)

    if hasattr(roof, 'manual_lines'):
        for line in roof.manual_lines:
            if line.line_type == 'eave' and (eave_id is None or line.identifier == eave_id):
                line.overhang = float(overhang_inches)

    # Trigger unified geometry solver
    if canvas:
        if hasattr(canvas, 'recalculate_roof'):
            canvas.recalculate_roof(roof)
        elif hasattr(canvas, 'solve_active_roof'):
            canvas.solve_active_roof(roof)
        if hasattr(canvas, 'queue_draw'):
            canvas.queue_draw()
    else:
        solve_roof_geometry(roof)


def bind_plane_pitch(roof: Any, plane_index_or_id: Any, pitch_value: float, canvas: Optional[Any] = None):
    """
    Connect pitch dropdowns/inputs to individual roof planes P_i.
    Triggers roof solve and updates 3D scene and takeoff calculations.
    """
    if not roof:
        return

    pitch_val = float(pitch_value)

    # Check if roof_planes exist
    if hasattr(roof, 'roof_planes') and roof.roof_planes:
        if isinstance(plane_index_or_id, int) and 0 <= plane_index_or_id < len(roof.roof_planes):
            p = roof.roof_planes[plane_index_or_id]
            if isinstance(p, dict):
                p["pitch"] = pitch_val
            elif hasattr(p, 'pitch'):
                p.pitch = pitch_val
        elif isinstance(plane_index_or_id, str):
            for p in roof.roof_planes:
                p_id = getattr(p, 'id', None) or (p.get('id') if isinstance(p, dict) else None)
                if p_id == plane_index_or_id:
                    if isinstance(p, dict):
                        p["pitch"] = pitch_val
                    elif hasattr(p, 'pitch'):
                        p.pitch = pitch_val

    # Update corresponding eave edge
    if hasattr(roof, 'edges'):
        eaves = [e for e in roof.edges if e.edge_type == 'eave']
        if isinstance(plane_index_or_id, int) and 0 <= plane_index_or_id < len(eaves):
            eaves[plane_index_or_id].pitch_rise = pitch_val
        elif isinstance(plane_index_or_id, str):
            for e in eaves:
                if e.wall_identifier == plane_index_or_id:
                    e.pitch_rise = pitch_val

    # Trigger unified solve
    if canvas:
        if hasattr(canvas, 'recalculate_roof'):
            canvas.recalculate_roof(roof)
        elif hasattr(canvas, 'solve_active_roof'):
            canvas.solve_active_roof(roof)
        if hasattr(canvas, 'queue_draw'):
            canvas.queue_draw()
    else:
        solve_roof_geometry(roof)


class RoofPropertiesPanel:
    """
    Controller and widget for Roof Properties & State Binding.
    Connects overhang inputs and pitch dropdowns/inputs to roof planes.
    """
    def __init__(self, canvas: Optional[Any] = None):
        self.canvas = canvas
        self.current_roof = None
        self._block_updates = False

    def set_roof(self, roof: Any):
        self.current_roof = roof

    def on_overhang_changed(self, overhang_val: float, eave_id: Optional[str] = None):
        if self._block_updates or not self.current_roof:
            return
        bind_roof_overhang(self.current_roof, overhang_val, canvas=self.canvas, eave_id=eave_id)

    def on_pitch_changed(self, plane_id_or_idx: Any, pitch_val: float):
        if self._block_updates or not self.current_roof:
            return
        bind_plane_pitch(self.current_roof, plane_id_or_idx, pitch_val, canvas=self.canvas)

    def trigger_solve(self):
        if not self.current_roof:
            return
        if self.canvas and hasattr(self.canvas, 'solve_active_roof'):
            self.canvas.solve_active_roof(self.current_roof)
        else:
            solve_roof_geometry(self.current_roof)
