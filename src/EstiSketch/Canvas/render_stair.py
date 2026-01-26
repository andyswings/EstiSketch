"""
Stair rendering logic for EstiSketch canvas.
"""
import math
import cairo
from ..components import Stair


class CanvasStairRendererMixin:
    """Mixin for rendering stair objects."""

    def _draw_stair(self, cr: cairo.Context, stair: Stair, scale: float):
        """Render a staircase in top-down plan view."""
        if not stair.visible:
            return
            
        # Draw on correct layer opacity
        layer = self.get_layer_by_id(stair.layer_id)
        opacity = layer.opacity if layer else 1.0
        
        # Dispatch to appropriate rendering method based on type
        stair_type = getattr(stair, 'stair_type', 'straight')
        if stair_type == 'L-shaped':
            self._draw_l_shaped_stair(cr, stair, scale, opacity)
            return
        elif stair_type == 'U-shaped':
            self._draw_u_shaped_stair(cr, stair, scale, opacity)
            return
        elif stair_type == 'spiral':
            self._draw_spiral_stair(cr, stair, scale, opacity)
            return
        
        # Otherwise render as straight stair
        # Calculate geometry
        start_x, start_y = stair.start_point
        angle = stair.direction_angle
        width = stair.width
        run = stair.total_run
        
        cr.save()
        
        # Transform to stair entry point and rotation
        cr.translate(start_x, start_y)
        cr.rotate(angle)
        
        # --- Draw Outline ---
        # Draw rectangle: (0, -width/2) to (run, width/2)
        # Using -width/2 centers the stair on the start point laterally
        
        # Set colors (black outline, white/transparent fill)
        
        # Check selection status
        is_selected = False
        if hasattr(self, 'selected_items'):
             for item in self.selected_items:
                 if item.get('type') == 'stair' and item.get('object') == stair:
                     is_selected = True
                     break
                     
        if is_selected:
            cr.set_source_rgb(0.2, 0.6, 1.0)  # Blue selection
            line_width = 2.0 / scale
        else:
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            line_width = 1.0 / scale
            
        cr.set_line_width(line_width)
        
        # Main rectangle
        half_width = width / 2.0
        cr.rectangle(0, -half_width, run, width)
        cr.stroke()
        
        # --- Draw Treads ---
        tread_depth = stair.tread_depth
        num_treads = stair.num_steps - 1  # Top riser is at the floor level
        
        cr.set_line_width(0.5 / scale) # Thinner lines for treads
        
        for i in range(1, num_treads + 1):
            x_pos = i * tread_depth
            cr.move_to(x_pos, -half_width)
            cr.line_to(x_pos, half_width)
            cr.stroke()
            
        # --- Draw Railings ---
        rail_inset = 2.0  # Inset railing 2 inches from edge
        rail_width = 1.0 / scale # Visual width
        
        if stair.has_left_rail:
            # "Left" is relative to looking UP the stairs
            # In our coordinate system (x=up), left is -y
            y_pos = -half_width + rail_inset
            
            # Railing line
            cr.set_line_width(rail_width)
            cr.move_to(0, y_pos)
            cr.line_to(run, y_pos)
            cr.stroke()
            
        if stair.has_right_rail:
            y_pos = half_width - rail_inset
            
            # Railing line
            cr.set_line_width(rail_width)
            cr.move_to(0, y_pos)
            cr.line_to(run, y_pos)
            cr.stroke()
            
        # --- Draw Direction Arrow ---
        if stair.show_up_arrow:
            self._draw_stair_arrow(cr, run, scale, opacity)
            
        # --- Draw Labels ---
        if stair.show_step_count:
            self._draw_stair_labels(cr, stair, scale, opacity)
            
        # --- Restore Context ---
        cr.restore()
        
        # Reset color
        cr.set_source_rgb(0, 0, 0)
        
    def _draw_stair_arrow(self, cr, run, scale, opacity):
        """Draw the UP arrow indicating ascent direction."""
        arrow_len = min(run * 0.8, 36.0) # Cap arrow length
        start_x = 12.0 # Start 12 inches in
        end_x = start_x + arrow_len
        
        cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
        cr.set_line_width(1.5 / scale)
        
        # Main line
        cr.move_to(start_x, 0)
        cr.line_to(end_x, 0)
        cr.stroke()
        
        # Arrow head
        head_size = 6.0 / scale
        cr.move_to(end_x - head_size, -head_size)
        cr.line_to(end_x, 0)
        cr.line_to(end_x - head_size, head_size)
        cr.stroke()
        
        # "UP" text
        text_size = 12.0 / scale
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(text_size)
        
        label = "UP"
        extents = cr.text_extents(label)
        
        # Position at start of arrow
        cr.move_to(start_x - extents.width - 4.0/scale, extents.height/2)
        cr.show_text(label)

    def _draw_stair_labels(self, cr, stair, scale, opacity):
        """Draw text labels like step count."""
        label = f"{stair.num_steps}R"
        
        text_size = 10.0 / scale
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(text_size)
        
        extents = cr.text_extents(label)
        
        # Center of stair
        cx = stair.total_run / 2
        cy = 0
        
        # Draw background for legibility
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.7 * opacity)
        padding = 2.0 / scale
        cr.rectangle(cx - extents.width/2 - padding, 
                     cy - extents.height/2 - padding,
                     extents.width + padding*2,
                     extents.height + padding*2)
        cr.fill()
        
        # Draw text
        cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
        cr.move_to(cx - extents.width/2, cy + extents.height/2)
        cr.show_text(label)

    def _draw_l_shaped_stair(self, cr: cairo.Context, stair: Stair, scale: float, opacity: float):
        """Render an L-shaped staircase with landing."""
        start_x, start_y = stair.start_point
        angle = stair.direction_angle
        width = stair.width
        
        # Get L-shaped specific attributes
        landing_depth = getattr(stair, 'landing_depth', 36.0)
        turn_direction = getattr(stair, 'turn_direction', 'left')
        
        # Calculate steps before and after landing
        # Default: distribute evenly, but can be customized via properties
        total_steps = stair.num_steps
        steps_before = total_steps // 2
        steps_after = total_steps - steps_before
        
        # Calculate runs for each flight
        tread_depth = stair.tread_depth
        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0
        
        cr.save()
        
        # Transform to stair entry point and rotation
        cr.translate(start_x, start_y)
        cr.rotate(angle)
        
        # Check selection status
        is_selected = False
        if hasattr(self, 'selected_items'):
             for item in self.selected_items:
                 if item.get('type') == 'stair' and item.get('object') == stair:
                     is_selected = True
                     break
                     
        if is_selected:
            cr.set_source_rgb(0.2, 0.6, 1.0)
            line_width = 2.0 / scale
        else:
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            line_width = 1.0 / scale
            
        cr.set_line_width(line_width)
        half_width = width / 2.0
        
        # --- Draw First Flight ---
        # Rectangle from (0, -half_width) to (run_before, half_width)
        cr.rectangle(0, -half_width, run_before, width)
        cr.stroke()
        
        # Draw treads for first flight
        cr.set_line_width(0.5 / scale)
        for i in range(1, steps_before):
            x_pos = i * tread_depth
            cr.move_to(x_pos, -half_width)
            cr.line_to(x_pos, half_width)
            cr.stroke()
        
        # --- Draw Landing ---
        # Landing is inline with first flight, continuing straight
        landing_x = run_before
        cr.rectangle(landing_x, -half_width, landing_depth, width)
        cr.set_line_width(line_width)
        cr.stroke()
        
        # --- Draw Second Flight ---
        # Perpendicular to first flight, starting from side of landing
        cr.save()
        
        if turn_direction == 'left':
            # Second flight goes to the left (negative Y direction)
            # Start from left edge of landing, at far end
            # Translate X to: landing_x + landing_depth - half_width (to center flight on landing side)
            cr.translate(landing_x + landing_depth - half_width, -half_width)
            cr.rotate(-math.pi / 2)
        else:  # right
            # Second flight goes to the right (positive Y direction)  
            # Start from right edge of landing, at far end
            cr.translate(landing_x + landing_depth - half_width, half_width)
            cr.rotate(math.pi / 2)
        
        # Draw second flight rectangle
        cr.rectangle(0, -half_width, run_after, width)
        cr.set_line_width(line_width)
        cr.stroke()
        
        # Draw treads for second flight
        cr.set_line_width(0.5 / scale)
        for i in range(1, steps_after):
            x_pos = i * tread_depth
            cr.move_to(x_pos, -half_width)
            cr.line_to(x_pos, half_width)
            cr.stroke()
        
        cr.restore()  # Restore from second flight transform
        
        # --- Draw Railings --- (simplified for now)
        # TODO: Add railings along both flights and around landing
        
        # --- Draw UP Arrow --- (along first flight for now)
        if stair.show_up_arrow:
            arrow_len = min(run_before * 0.8, 36.0)
            start_arrow_x = 12.0
            end_arrow_x = start_arrow_x + arrow_len
            
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            cr.set_line_width(1.5 / scale)
            
            # Main line
            cr.move_to(start_arrow_x, 0)
            cr.line_to(end_arrow_x, 0)
            cr.stroke()
            
            # Arrow head
            head_size = 6.0 / scale
            cr.move_to(end_arrow_x - head_size, -head_size)
            cr.line_to(end_arrow_x, 0)
            cr.line_to(end_arrow_x - head_size, head_size)
            cr.stroke()
        
        # --- Draw Step Count Label ---
        if stair.show_step_count:
            label = f"{total_steps}R (L)"
            
            text_size = 10.0 / scale
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(text_size)
            
            extents = cr.text_extents(label)
            
            # Center on landing
            cx = landing_x + landing_depth / 2
            cy = -half_width - landing_depth / 2 if turn_direction == 'left' else half_width + landing_depth / 2
            
            # Draw background
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.7 * opacity)
            padding = 2.0 / scale
            cr.rectangle(cx - extents.width/2 - padding, 
                         cy - extents.height/2 - padding,
                         extents.width + padding*2,
                         extents.height + padding*2)
            cr.fill()
            
            # Draw text
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            cr.move_to(cx - extents.width/2, cy + extents.height/2)
            cr.show_text(label)
        
        cr.restore()  # Restore from main transform

    def _draw_u_shaped_stair(self, cr: cairo.Context, stair: Stair, scale: float, opacity: float):
        """Render a U-shaped staircase (switchback) with landing."""
        start_x, start_y = stair.start_point
        angle = stair.direction_angle
        width = stair.width
        
        # Get U-shaped specific attributes
        landing_depth = getattr(stair, 'landing_depth', 36.0)
        turn_direction = getattr(stair, 'turn_direction', 'left')
        well_width = getattr(stair, 'inner_radius', 0.0)  # Use inner_radius for well width/gap
        
        # Calculate steps before and after landing
        total_steps = stair.num_steps
        steps_before = total_steps // 2
        steps_after = total_steps - steps_before
        
        # Calculate runs for each flight
        tread_depth = stair.tread_depth
        run_before = (steps_before - 1) * tread_depth if steps_before > 0 else 0
        run_after = (steps_after - 1) * tread_depth if steps_after > 0 else 0
        
        cr.save()
        
        # Transform to stair entry point and rotation
        cr.translate(start_x, start_y)
        cr.rotate(angle)
        
        # Check selection status
        is_selected = False
        if hasattr(self, 'selected_items'):
             for item in self.selected_items:
                 if item.get('type') == 'stair' and item.get('object') == stair:
                     is_selected = True
                     break
                     
        if is_selected:
            cr.set_source_rgb(0.2, 0.6, 1.0)
            line_width = 2.0 / scale
        else:
            cr.set_source_rgb(0.0, 0.0, 0.0)
            line_width = 1.0 / scale
            
        cr.set_line_width(line_width)
        half_width = width / 2.0
        
        # For U-shapes, let's offset the flights so the "start point" is centered on the first flight
        # First flight is centered on Y=0 locally
        
        # Landing dimensions
        # Width spans both flights plus the well
        landing_span = (width * 2) + well_width
        
        # --- Draw First Flight ---
        # Rectangle from (0, -half_width) to (run_before, half_width)
        cr.rectangle(0, -half_width, run_before, width)
        cr.stroke()
        
        # Draw treads for first flight
        cr.set_line_width(0.5 / scale)
        for i in range(1, steps_before):
            x_pos = i * tread_depth
            cr.move_to(x_pos, -half_width)
            cr.line_to(x_pos, half_width)
            cr.stroke()
            
        # --- Draw Landing ---
        # Landing is at the end of first flight, spanning across to the second flight side
        landing_x = run_before
        
        cr.set_line_width(line_width)
        
        if turn_direction == 'left':
            # Landing extends to the LEFT (negative Y) relative to ascent
            # First flight is at Y=0. Landing starts at -half_width (top edge) but needs to go down
            # Actually Y is Positive Down in Cairo usually (unless flipped).
            # Let's assume standard orientation:
            # If we walk +X, "Left" is -Y.
            
            # Rectangle:
            # X: landing_x
            # Y: -half_width (top edge of flight 1)
            # W: landing_depth
            # H: -landing_span (going UP in negative Y direction)
            
            # Wait, if Left is -Y, then we need to draw from [landing_x, -half_width] down to [landing_x, -half_width - landing_span] ??
            # Actually let's draw it from the bottom-most Y up?
            # Range Y: [-half_width - width - well_width, half_width]
            
            # Top of flight 1 is -half_width. Bottom is +half_width.
            # Use inner_radius (well_width)
            
            landing_top_y = -half_width - well_width - width
            landing_height = landing_span
            
            cr.rectangle(landing_x, landing_top_y, landing_depth, landing_height)
            
        else: # Right turn
            # Extends to Positive Y
            # Top of flight 1 is -half_width.
            # Landing starts at -half_width and goes down (Positive Y) to cover flight 2
            
            landing_top_y = -half_width
            landing_height = landing_span
            
            cr.rectangle(landing_x, landing_top_y, landing_depth, landing_height)
            
        cr.stroke()
        
        # --- Draw Second Flight ---
        cr.save()
        
        # Position second flight parallel to first
        # It runs in reverse direction (-X) relative to the landing?
        # No, physically it goes UP, but in plan view relative to start, it comes BACK towards start X.
        
        # Let's translate to the start of the second flight on the landing edge, and rotate 180
        
        if turn_direction == 'left':
            # Flight 2 is at Y offset: -(width + well_width)
            offset_y = -(width + well_width)
            
            # Translate to the landing edge where flight 2 begins
            # X: landing_x
            # Y: 0 + offset_y
            cr.translate(landing_x, offset_y)
            
            # Rotate 180 so it draws "forward" into negative X space
            cr.rotate(math.pi)
            
        else: # Right
            # Flight 2 is at Y offset: +(width + well_width)
            offset_y = (width + well_width)
            
            cr.translate(landing_x, offset_y)
            cr.rotate(math.pi)
            
        # Draw second flight rectangle
        # Note: After rotation, drawing positive X goes back towards the start of flight 1
        cr.rectangle(0, -half_width, run_after, width)
        cr.set_line_width(line_width)
        cr.stroke()
        
        # Draw treads for second flight
        cr.set_line_width(0.5 / scale)
        for i in range(1, steps_after):
            x_pos = i * tread_depth
            cr.move_to(x_pos, -half_width)
            cr.line_to(x_pos, half_width)
            cr.stroke()
            
        cr.restore()
        
        # --- Draw UP Arrow ---
        if stair.show_up_arrow:
            arrow_len = min(run_before * 0.8, 36.0)
            start_arrow_x = 12.0
            end_arrow_x = start_arrow_x + arrow_len
            
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            cr.set_line_width(1.5 / scale)
            
            # Main line
            cr.move_to(start_arrow_x, 0)
            cr.line_to(end_arrow_x, 0)
            cr.stroke()
            
             # Arrow head
            head_size = 6.0 / scale
            cr.move_to(end_arrow_x - head_size, -head_size)
            cr.line_to(end_arrow_x, 0)
            cr.line_to(end_arrow_x - head_size, head_size)
            cr.stroke()
            
        # --- Draw Step Count Label ---
        if stair.show_step_count:
            label = f"{total_steps}R (U)"
            
            text_size = 10.0 / scale
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(text_size)
            
            extents = cr.text_extents(label)
            
            # Center on landing
            cx = landing_x + landing_depth / 2
            
            # Y center depends on turn direction
            if turn_direction == 'left':
                 cy = -half_width - (well_width / 2.0) - (width / 2.0) 
                 # Midpoint between 0 and -(width+well_width) is -(width+well_width)/2
                 cy = -(width + well_width) / 2.0
            else:
                 cy = (width + well_width) / 2.0
            
            # Draw background
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.7 * opacity)
            padding = 2.0 / scale
            cr.rectangle(cx - extents.width/2 - padding, 
                         cy - extents.height/2 - padding,
                         extents.width + padding*2,
                         extents.height + padding*2)
            cr.fill()
            
            # Draw text
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            cr.move_to(cx - extents.width/2, cy + extents.height/2)
            cr.show_text(label)
        
        cr.restore()  # Restore from main transform

    def _draw_spiral_stair(self, cr: cairo.Context, stair: Stair, scale: float, opacity: float):
        """Render a spiral staircase."""
        start_x, start_y = stair.start_point
        # Angle determines the ENTRANCE angle (where the first step starts)
        start_angle = stair.direction_angle
        width = stair.width
        
        # Spiral attributes
        inner_radius = getattr(stair, 'inner_radius', 6.0)
        outer_radius = inner_radius + width
        
        # Total rotation (convert degrees to radians)
        rotation_deg = getattr(stair, 'rotation_degrees', 270.0)
        rotation_rad = math.radians(rotation_deg)
        
        turn_direction = getattr(stair, 'turn_direction', 'left')
        
        # Calculate angle per step
        total_steps = stair.num_steps
        step_angle = rotation_rad / total_steps
        
        cr.save()
        
        # Transform to center of spiral
        cr.translate(start_x, start_y)
        # Note: Spiral connects start_point as the CENTER, not the first step edge
        # Actually logic says start_point is usually the entry. 
        # But for spiral, placement usually defines center?
        # Let's assume start_point is the CENTER for now, as planned.
        
        # Check selection
        is_selected = False
        if hasattr(self, 'selected_items'):
             for item in self.selected_items:
                 if item.get('type') == 'stair' and item.get('object') == stair:
                     is_selected = True
                     break
                     
        if is_selected:
            cr.set_source_rgb(0.2, 0.6, 1.0)
            line_width = 2.0 / scale
        else:
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            line_width = 1.0 / scale
            
        cr.set_line_width(line_width)
        
        # Direction multiplier
        # Left (CCW) = negative angle change? depends on coord system.
        # Cairo: +Angle is Clockwise (Standard math is CCW, but Y is flipped?)
        # Let's test: +Angle is CW in GTK/Cairo usually (X right, Y down).
        # So "Left" turn (CCW) should be Negative angle.
        dir_mult = -1.0 if turn_direction == 'left' else 1.0
        
        final_angle = start_angle + (rotation_rad * dir_mult)
        
        # --- Draw Stringers (Arcs) ---
        # Inner Arc
        cr.new_sub_path()
        if turn_direction == 'left': # CCW
            cr.arc_negative(0, 0, inner_radius, start_angle, final_angle)
        else: # CW
            cr.arc(0, 0, inner_radius, start_angle, final_angle)
        cr.stroke()
        
        # Outer Arc
        cr.new_sub_path()
        if turn_direction == 'left': # CCW
             cr.arc_negative(0, 0, outer_radius, start_angle, final_angle)
        else: # CW
             cr.arc(0, 0, outer_radius, start_angle, final_angle)
        cr.stroke()
        
        # Close ends
        # Start Line
        cr.move_to(inner_radius * math.cos(start_angle), inner_radius * math.sin(start_angle))
        cr.line_to(outer_radius * math.cos(start_angle), outer_radius * math.sin(start_angle))
        cr.stroke()
        
        # End Line
        cr.move_to(inner_radius * math.cos(final_angle), inner_radius * math.sin(final_angle))
        cr.line_to(outer_radius * math.cos(final_angle), outer_radius * math.sin(final_angle))
        cr.stroke()
        
        # --- Draw Treads (Radials) ---
        cr.set_line_width(0.5 / scale)
        for i in range(1, total_steps):
            theta = start_angle + (step_angle * i * dir_mult)
            
            x1 = inner_radius * math.cos(theta)
            y1 = inner_radius * math.sin(theta)
            x2 = outer_radius * math.cos(theta)
            y2 = outer_radius * math.sin(theta)
            
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
            
        # Draw Up Arrow (Curved)
        # Draw along center path
        center_radius = (inner_radius + outer_radius) / 2.0
        arrow_angle_end = start_angle + (rotation_rad * 0.8 * dir_mult)
        
        cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
        cr.set_line_width(1.5 / scale)
        cr.new_sub_path()
        if turn_direction == 'left':
            cr.arc_negative(0, 0, center_radius, start_angle, arrow_angle_end)
        else:
            cr.arc(0, 0, center_radius, start_angle, arrow_angle_end)
        cr.stroke()
        
        # Arrow Head
        # Calculate tangent at arrow_angle_end
        # Tangent angle is theta + 90 (or -90)
        tip_x = center_radius * math.cos(arrow_angle_end)
        tip_y = center_radius * math.sin(arrow_angle_end)
        
        # If CCW (Left -neg), tangent is perpendicular
        tangent = arrow_angle_end + (math.pi/2 * dir_mult) # Tangent perpendicular to radius
        
        head_size = 6.0 / scale
        # Back points
        angle1 = tangent + math.radians(150)
        angle2 = tangent - math.radians(150)
        
        p1x = tip_x + head_size * math.cos(angle1)
        p1y = tip_y + head_size * math.sin(angle1)
        p2x = tip_x + head_size * math.cos(angle2)
        p2y = tip_y + head_size * math.sin(angle2)
        
        cr.move_to(tip_x, tip_y)
        cr.line_to(p1x, p1y)
        cr.move_to(tip_x, tip_y)
        cr.line_to(p2x, p2y)
        cr.stroke()
        
        # --- Draw Center Column ---
        # If inner_radius is small, draw a solid circle
        if inner_radius > 0:
             cr.new_sub_path()
             cr.arc(0, 0, inner_radius, 0, 2*math.pi)
             cr.set_line_width(1.0 / scale)
             cr.stroke()
             
        # --- Label ---
        if stair.show_step_count:
            label = f"{total_steps}R (Spiral)"
            extents = cr.text_extents(label)
            
            # Place label at 1/2 rotation point? or center?
            mid_angle = start_angle + (rotation_rad * 0.5 * dir_mult)
            cx = (outer_radius + 4.0/scale) * math.cos(mid_angle) 
            cy = (outer_radius + 4.0/scale) * math.sin(mid_angle)
            
            # Draw background
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.7 * opacity)
            padding = 2.0 / scale
            cr.rectangle(cx - extents.width/2 - padding, 
                         cy - extents.height/2 - padding,
                         extents.width + padding*2,
                         extents.height + padding*2)
            cr.fill()
            
            # Draw text
            cr.set_source_rgba(0.0, 0.0, 0.0, opacity)
            cr.move_to(cx - extents.width/2, cy + extents.height/2)
            cr.show_text(label)

        cr.restore()

