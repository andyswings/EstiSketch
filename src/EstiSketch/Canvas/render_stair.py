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

