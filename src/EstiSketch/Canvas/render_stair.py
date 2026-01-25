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

