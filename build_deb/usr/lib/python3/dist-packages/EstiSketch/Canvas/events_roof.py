"""
Roof event handlers for EstiSketch canvas.

This mixin provides methods for marking walls as roof edges (eave/gable)
and generating roof geometry from marked walls.
"""
import math
from typing import List, Tuple, Optional
from ..roof_components import Roof, RoofEdge


class CanvasRoofEventsMixin:
    """Mixin for roof-related canvas events and operations."""

    def get_walls_marked_for_roof(self) -> dict:
        """
        Get all walls currently marked as roof edges.
        Returns dict mapping wall_identifier -> edge_type ("eave" or "gable").
        """
        if not hasattr(self, '_roof_edge_markings'):
            self._roof_edge_markings = {}
        return self._roof_edge_markings

    def mark_walls_as_eave(self, walls: list = None):
        """
        Mark selected walls as eave edges for roof generation.
        If walls parameter is None, uses currently selected walls.
        """
        if walls is None:
            walls = [item["object"] for item in self.selected_items 
                     if item["type"] == "wall"]
        
        if not walls:
            print("No walls selected to mark as eave")
            return
        
        markings = self.get_walls_marked_for_roof()
        for wall in walls:
            markings[wall.identifier] = "eave"
        
        self.queue_draw()
        print(f"Marked {len(walls)} wall(s) as eave")

    def mark_walls_as_gable(self, walls: list = None):
        """
        Mark selected walls as gable edges for roof generation.
        If walls parameter is None, uses currently selected walls.
        """
        if walls is None:
            walls = [item["object"] for item in self.selected_items 
                     if item["type"] == "wall"]
        
        if not walls:
            print("No walls selected to mark as gable")
            return
        
        markings = self.get_walls_marked_for_roof()
        for wall in walls:
            markings[wall.identifier] = "gable"
        
        self.queue_draw()
        print(f"Marked {len(walls)} wall(s) as gable")

    def clear_roof_markings(self):
        """Clear all roof edge markings."""
        self._roof_edge_markings = {}
        self.queue_draw()

    def get_wall_by_identifier(self, identifier: str):
        """Find a wall by its identifier."""
        for wall_set in self.wall_sets:
            for wall in wall_set:
                if wall.identifier == identifier:
                    return wall
        return None

    def validate_roof_configuration(self) -> Tuple[bool, str, str]:
        """
        Validate current roof markings for roof generation.
        Returns (is_valid, roof_type, error_message).
        
        Phase 1 rules:
        - Must have exactly 4 walls forming a closed loop
        - For gable: 2 eaves (opposite) + 2 gables (opposite)
        - For hip: 4 eaves
        - All walls must be straight (not curved)
        """
        markings = self.get_walls_marked_for_roof()
        
        if not markings:
            return False, "", "No walls marked for roof. Mark walls as eave or gable first."
        
        # Get marked walls
        eave_ids = [wid for wid, etype in markings.items() if etype == "eave"]
        gable_ids = [wid for wid, etype in markings.items() if etype == "gable"]
        
        total_marked = len(eave_ids) + len(gable_ids)
        
        # Phase 1: Must have exactly 4 walls
        if total_marked != 4:
            return False, "", f"Phase 1 requires exactly 4 walls. Currently marked: {total_marked}"
        
        # Check for curved walls
        for wid in list(markings.keys()):
            wall = self.get_wall_by_identifier(wid)
            if wall and getattr(wall, 'is_curved', False):
                return False, "", f"Curved walls not supported in Phase 1. Wall: {wid}"
        
        # Determine roof type
        if len(gable_ids) == 0 and len(eave_ids) == 4:
            return True, "hip", ""
        elif len(gable_ids) == 2 and len(eave_ids) == 2:
            return True, "gable", ""
        elif len(gable_ids) == 4 and len(eave_ids) == 0:
            return False, "", "All gables (no eaves) - complex roof, not supported in Phase 1"
        else:
            return False, "", f"Invalid configuration: {len(eave_ids)} eaves, {len(gable_ids)} gables"

    def _get_wall_midpoint(self, wall) -> Tuple[float, float]:
        """Get the midpoint of a wall."""
        return (
            (wall.start[0] + wall.end[0]) / 2,
            (wall.start[1] + wall.end[1]) / 2
        )

    def _get_wall_length(self, wall) -> float:
        """Get the length of a wall."""
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        return math.sqrt(dx * dx + dy * dy)

    def _calculate_gable_roof_geometry(self, eave_walls, gable_walls, overhang: float):
        """
        Calculate ridge line for a simple gable roof.
        
        The ridge runs parallel to the eave walls, centered between them.
        Ridge endpoints extend beyond gable walls by the overhang distance.
        """
        if len(eave_walls) != 2 or len(gable_walls) != 2:
            return [], [], []
        
        # Get midpoints of gable walls (base ridge endpoints)
        gable1_mid = self._get_wall_midpoint(gable_walls[0])
        gable2_mid = self._get_wall_midpoint(gable_walls[1])
        
        # Calculate ridge direction vector
        ridge_dx = gable2_mid[0] - gable1_mid[0]
        ridge_dy = gable2_mid[1] - gable1_mid[1]
        ridge_len = math.sqrt(ridge_dx * ridge_dx + ridge_dy * ridge_dy)
        
        if ridge_len > 0:
            # Normalize and extend by overhang
            ridge_ux = ridge_dx / ridge_len
            ridge_uy = ridge_dy / ridge_len
            
            # Extend ridge endpoints outward by overhang
            ridge_start = (gable1_mid[0] - ridge_ux * overhang, 
                          gable1_mid[1] - ridge_uy * overhang)
            ridge_end = (gable2_mid[0] + ridge_ux * overhang, 
                        gable2_mid[1] + ridge_uy * overhang)
        else:
            ridge_start = gable1_mid
            ridge_end = gable2_mid
        
        ridge_lines = [(ridge_start, ridge_end)]
        
        # No hips or valleys for simple gable
        hip_lines = []
        valley_lines = []
        
        return ridge_lines, hip_lines, valley_lines

    def _calculate_hip_roof_geometry(self, eave_walls, overhang: float):
        """
        Calculate ridge and hip lines for a simple hip roof.
        
        For a rectangular hip roof:
        - Ridge runs along the longer axis
        - 4 hip lines connect ridge endpoints to corners
        """
        if len(eave_walls) != 4:
            return [], [], []
        
        # Identify opposite wall pairs
        # We assume 4 walls forming a closed loop
        
        # Helper to check if walls share a vertex
        def share_vertex(w1, w2):
             tol = 1.0
             return (self._points_close(w1.start, w2.start, tol) or 
                     self._points_close(w1.start, w2.end, tol) or 
                     self._points_close(w1.end, w2.start, tol) or 
                     self._points_close(w1.end, w2.end, tol))
        
        wall0 = eave_walls[0]
        opposite_to_0 = None
        other_pair = []
        
        for w in eave_walls[1:]:
             if not share_vertex(wall0, w):
                  opposite_to_0 = w
             else:
                  other_pair.append(w)
        
        # Fallback if topology is weird (should show error, but handled robustly)
        if not opposite_to_0:
             # Just take the last one if fails
             opposite_to_0 = eave_walls[-1]
             other_pair = eave_walls[1:-1]
             
        pair1 = [wall0, opposite_to_0]
        pair2 = other_pair
        
        # Determine which pair is "long" (ridge runs parallel) and "short" (ridge ends point to)
        # Compare average lengths
        len1 = (self._get_wall_length(pair1[0]) + self._get_wall_length(pair1[1])) / 2
        len2 = (self._get_wall_length(pair2[0]) + self._get_wall_length(pair2[1])) / 2
        
        if len1 >= len2:
             long_walls = pair1
             short_walls = pair2
        else:
             long_walls = pair2
             short_walls = pair1
        
        # Get width (length of short walls)
        width = self._get_wall_length(short_walls[0])
        inset = width / 2.0
        
        # Get midpoints of shorter walls (base ridge endpoints)
        short1_mid = self._get_wall_midpoint(short_walls[0])
        short2_mid = self._get_wall_midpoint(short_walls[1])
        
        # Calculate ridge direction vector
        dx = short2_mid[0] - short1_mid[0]
        dy = short2_mid[1] - short1_mid[1]
        dist = math.sqrt(dx * dx + dy * dy)
        
        ridge_lines = []
        hip_lines = []
        
        if dist > 0:
            ux = dx / dist
            uy = dy / dist
            
            # Calculate actual ridge endpoints by insetting from the Short walls
            # The hips normally rise at 45 degrees in plan view (equal pitch), 
            # so the ridge starts at distance = width/2 from the end.
            
            if dist <= width:
                 # Square or "tall" rectangle where hips meet at a point or overlap
                 # For a perfect square, dist should be approx width (actually dist is length, so dist = width)
                 # Ridge is a single point at the center
                 center_x = (short1_mid[0] + short2_mid[0]) / 2
                 center_y = (short1_mid[1] + short2_mid[1]) / 2
                 ridge_start = (center_x, center_y)
                 ridge_end = (center_x, center_y)
                 # No ridge line, just a point (pyramid roof)
            else:
                 # Normal rectangular hip roof
                 ridge_start = (short1_mid[0] + ux * inset, short1_mid[1] + uy * inset)
                 ridge_end = (short2_mid[0] - ux * inset, short2_mid[1] - uy * inset)
                 ridge_lines.append((ridge_start, ridge_end))
            
            # Hip lines connect ridge endpoints to OUTLINE corners
            # We need to find which outline corners correspond to the wall corners
            
            # Helper to find closest point in a list to a target point
            def find_closest_point(target, points):
                best_p = None
                min_d = float('inf')
                for p in points:
                    d = math.hypot(p[0] - target[0], p[1] - target[1])
                    if d < min_d:
                        min_d = d
                        best_p = p
                return best_p

            # We need to pass the outline points to this function or calculate them
            # Since outline is calculated later, we can estimate the corner position
            # by offsetting the wall corner outward along the corner bisector.
            # But simpler: calculate outline first in generate_roof and pass it here?
            # Or just calculate the offset corner locally.
            
            # Local calculation of offset corners for hip lines
            # For a 90 degree corner, the offset distance to the corner is overhang * sqrt(2)
            # The direction is the vector from building center to corner (approx)
            
            # Better approach: pass outline points to this function
            # But changing signature requires update in call site.
            # Let's try to find the corresponding outline corners if we had them.
            
            # Alternative: calculate vector from ridge end to wall corner, and extend it?
            # No, that changes pitch.
            
            # Correct vector: The hip line in plan view is the bisector of the corner angle.
            # For a rectangle, it's 45 degrees.
            # So we can just extend the line from ridge_end through wall_corner by overhang * sqrt(2)
            
            extension = overhang * math.sqrt(2)
            
            # Helper to get corners of a wall
            def get_wall_corners(wall):
                return [wall.start, wall.end]
            
            # Helper to extend point
            def extend_corner(start, corner):
                vx = corner[0] - start[0]
                vy = corner[1] - start[1]
                vlen = math.sqrt(vx*vx + vy*vy)
                if vlen > 0:
                    ux = vx / vlen
                    uy = vy / vlen
                    return (corner[0] + ux * extension, corner[1] + uy * extension)
                return corner

            # Corners for first hip end
            for corner in get_wall_corners(short_walls[0]):
                extended = extend_corner(ridge_start, corner)
                hip_lines.append((ridge_start, extended))
                
            # Corners for second hip end
            for corner in get_wall_corners(short_walls[1]):
                extended = extend_corner(ridge_end, corner)
                hip_lines.append((ridge_end, extended))
        
        valley_lines = []
        
        return ridge_lines, hip_lines, valley_lines

    def _calculate_roof_outline(self, walls, overhang: float) -> List[Tuple[float, float]]:
        """
        Calculate the roof outline with uniform overhang.
        Each wall edge is offset outward perpendicular to its direction.
        Corner points are calculated from the intersection of adjacent offset edges.
        """
        if len(walls) < 3:
            return []
        
        # Build ordered list of wall segments forming a closed polygon
        # Collect wall segments as (start, end) tuples
        segments = [(wall.start, wall.end) for wall in walls]
        
        # Order segments into a connected loop
        ordered_segments = self._order_segments_into_loop(segments)
        if not ordered_segments:
            # Fallback: use simple points ordering
            points = []
            for wall in walls:
                if wall.start not in points:
                    points.append(wall.start)
                if wall.end not in points:
                    points.append(wall.end)
            # Simple centroid expansion fallback
            if len(points) < 3:
                return points
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)
            outline = []
            for px, py in points:
                dx = px - cx
                dy = py - cy
                dist = math.sqrt(dx * dx + dy * dy) or 1
                outline.append((px + dx/dist * overhang, py + dy/dist * overhang))
            return outline
        
        # Determine polygon winding direction using signed area
        # Positive = counterclockwise, Negative = clockwise
        signed_area = 0.0
        for i in range(len(ordered_segments)):
            start, end = ordered_segments[i]
            signed_area += (end[0] - start[0]) * (end[1] + start[1])
        
        # If clockwise (positive signed area in screen coords where Y increases downward),
        # we need to flip the normal direction
        # Note: In screen coordinates, Y increases downward, so clockwise has positive signed area
        winding_flip = 1.0 if signed_area > 0 else -1.0
        
        # Calculate offset lines for each segment
        offset_lines = []
        for start, end in ordered_segments:
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                # Calculate normal (perpendicular to edge)
                # For counterclockwise: (-dy, dx) points outward
                # Apply winding flip to ensure outward direction
                nx = (-dy / length) * winding_flip
                ny = (dx / length) * winding_flip
                # Offset the segment by overhang
                offset_start = (start[0] + nx * overhang, start[1] + ny * overhang)
                offset_end = (end[0] + nx * overhang, end[1] + ny * overhang)
                offset_lines.append((offset_start, offset_end))
            else:
                offset_lines.append((start, end))
        
        # Calculate outline points from intersections of adjacent offset lines
        outline = []
        n = len(offset_lines)
        for i in range(n):
            line1 = offset_lines[i]
            line2 = offset_lines[(i + 1) % n]
            intersection = self._line_intersection(line1[0], line1[1], line2[0], line2[1])
            if intersection:
                outline.append(intersection)
            else:
                # Lines are parallel, use the endpoint
                outline.append(line1[1])
        
        return outline

    def _order_segments_into_loop(self, segments):
        """Order wall segments into a connected loop."""
        if not segments:
            return []
        
        ordered = [segments[0]]
        remaining = list(segments[1:])
        
        # Build chain from start
        while remaining:
            last_end = ordered[-1][1]
            found = False
            for i, seg in enumerate(remaining):
                if self._points_close(seg[0], last_end, 0.5):
                    ordered.append(seg)
                    remaining.pop(i)
                    found = True
                    break
                elif self._points_close(seg[1], last_end, 0.5):
                    # Reverse segment
                    ordered.append((seg[1], seg[0]))
                    remaining.pop(i)
                    found = True
                    break
            if not found:
                break
        
        # Check if it's closed
        if len(ordered) >= 3:
            if self._points_close(ordered[-1][1], ordered[0][0], 0.5):
                return ordered
        
        return ordered if len(ordered) >= 3 else []

    def _line_intersection(self, p1, p2, p3, p4):
        """Calculate intersection point of two lines defined by points."""
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4
        
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-10:
            return None  # Lines are parallel
        
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        
        return (ix, iy)

    def generate_roof_from_marked_walls(self, pitch_rise: int = 6, pitch_run: int = 12, 
                                         overhang: float = 12.0, material: str = "asphalt_shingle"):
        """
        Generate a roof object from the currently marked walls.
        
        Args:
            pitch_rise: Rise value (e.g., 6 in 6/12)
            pitch_run: Run value (always 12 for standard notation)
            overhang: Eave overhang in inches
            material: Roof material type
        
        Returns:
            The created Roof object, or None if validation fails.
        """
        if pitch_run != 12:
            print("Warning: Non-standard pitch run. Using normalized pitch.")
        
        # Infer missing markings if user only marked 2 walls
        self._infer_missing_roof_markings()
        
        # Validate configuration
        is_valid, roof_type, error = self.validate_roof_configuration()
        if not is_valid:
            print(f"Cannot generate roof: {error}")
            return None
        
        markings = self.get_walls_marked_for_roof()
        
        # Get wall objects
        eave_walls = []
        gable_walls = []
        all_walls = []
        
        for wall_id, edge_type in markings.items():
            wall = self.get_wall_by_identifier(wall_id)
            if wall:
                all_walls.append(wall)
                if edge_type == "eave":
                    eave_walls.append(wall)
                else:
                    gable_walls.append(wall)
        
        # Calculate geometry based on roof type
        if roof_type == "gable":
            ridge_lines, hip_lines, valley_lines = self._calculate_gable_roof_geometry(
                eave_walls, gable_walls, overhang)
        elif roof_type == "hip":
            ridge_lines, hip_lines, valley_lines = self._calculate_hip_roof_geometry(
                eave_walls, overhang)
        else:
            ridge_lines, hip_lines, valley_lines = [], [], []
        
        # Calculate outline with overhang
        outline = self._calculate_roof_outline(all_walls, overhang)
        
        # Create RoofEdge objects
        edges = []
        for wall_id, edge_type in markings.items():
            edges.append(RoofEdge(wall_identifier=wall_id, edge_type=edge_type))
        
        # Generate identifier
        roof_id = self.generate_identifier("roof", self.existing_ids)
        
        # Create Roof object
        roof = Roof(
            identifier=roof_id,
            layer_id=self.active_layer_id,
            edges=edges,
            roof_type=roof_type,
            pitch_rise=pitch_rise,
            pitch_run=pitch_run,
            overhang=overhang,
            ridge_lines=ridge_lines,
            hip_lines=hip_lines,
            valley_lines=valley_lines,
            outline_points=outline,
            material=material
        )
        
        # Add to canvas
        self.roofs.append(roof)
        
        # Clear markings after successful generation
        self.clear_roof_markings()
        
        # Save state for undo
        self.save_state()
        
        self.queue_draw()
        print(f"Generated {roof_type} roof: {roof_id}")
        
        return roof

    def recalculate_roof(self, roof: Roof):
        """
        Recalculate roof geometry when linked walls change.
        Called automatically when a wall bound to a roof is modified.
        """
        # Get current walls from edges
        eave_walls = []
        gable_walls = []
        all_walls = []
        
        for edge in roof.edges:
            wall = self.get_wall_by_identifier(edge.wall_identifier)
            if wall:
                all_walls.append(wall)
                if edge.edge_type == "eave":
                    eave_walls.append(wall)
                else:
                    gable_walls.append(wall)
        
        # Recalculate geometry
        if roof.roof_type == "gable":
            roof.ridge_lines, roof.hip_lines, roof.valley_lines = \
                self._calculate_gable_roof_geometry(eave_walls, gable_walls, roof.overhang)
        elif roof.roof_type == "hip":
            roof.ridge_lines, roof.hip_lines, roof.valley_lines = \
                self._calculate_hip_roof_geometry(eave_walls, roof.overhang)
        
        # Recalculate outline
        roof.outline_points = self._calculate_roof_outline(all_walls, roof.overhang)
        
        self.queue_draw()

    def recalculate_roofs_for_wall(self, wall_identifier: str):
        """
        Find and recalculate all roofs that contain the specified wall.
        Called when a wall is modified.
        """
        for roof in self.roofs:
            for edge in roof.edges:
                if edge.wall_identifier == wall_identifier:
                    self.recalculate_roof(roof)
                    break  # Only need to recalculate once per roof

    def delete_roof(self, roof: Roof):
        """Remove a roof from the canvas."""
        if roof in self.roofs:
            self.roofs.remove(roof)
            self.queue_draw()
    def _infer_missing_roof_markings(self):
        """
        Attempt to infer missing roof markings.
        If user marked exactly 2 walls as eave/gable, and they are opposite in a 4-wall loop,
        mark the other two walls as the alternate type.
        """
        markings = self.get_walls_marked_for_roof()
        if len(markings) != 2:
            return

        # Get the two marked walls
        marked_ids = list(markings.keys())
        w1 = self.get_wall_by_identifier(marked_ids[0])
        w2 = self.get_wall_by_identifier(marked_ids[1])
        
        if not w1 or not w2:
            return
            
        # Check if they are in the same wall set
        target_wall_set = None
        for wall_set in self.wall_sets:
            if w1 in wall_set and w2 in wall_set:
                target_wall_set = wall_set
                break
        
        if not target_wall_set:
            return
            
        # Check that wall set has exactly 4 walls (Phase 1 constraint)
        if len(target_wall_set) != 4:
            return
            
        # Check if marked walls are opposite (do not share a vertex)
        # Helper to check proximity
        def share_vertex(wa, wb):
             tol = 1.0
             return (self._points_close(wa.start, wb.start, tol) or 
                     self._points_close(wa.start, wb.end, tol) or 
                     self._points_close(wa.end, wb.start, tol) or 
                     self._points_close(wa.end, wb.end, tol))
                     
        if share_vertex(w1, w2):
            self.update_hint("Warning: Marked walls are adjacent. Cannot infer complex roof.")
            return

        # They are opposite. Infer the other two.
        type1 = markings[w1.identifier]
        type2 = markings[w2.identifier]
        
        # Usually types should be same for simple gable inference (2 eaves OR 2 gables)
        # If they mixed types (1 eave, 1 gable opposite), that's a valid shed roof or skewed gable?
        # But for this feature "2 eaves -> assume gables" implies types match.
        
        if type1 != type2:
            return # Mixed types, user might be doing something specific
            
        # Determine target type for missing walls
        target_type = "gable" if type1 == "eave" else "eave"
        
        # Find missing walls
        missing_walls = [w for w in target_wall_set if w not in [w1, w2]]
        
        # Mark them
        count = 0
        for w in missing_walls:
            markings[w.identifier] = target_type
            count += 1
            
        if count > 0:
            print(f"Inferred {count} walls as {target_type} based on 2 {type1} walls.")
            self.queue_draw()
