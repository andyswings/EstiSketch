import math
import cairo
from gi.repository import Gtk, Pango, PangoCairo
import Canvas.door_window_renderer as dwr
import Canvas.wall_room_renderer as wr

class CanvasDrawMixin:
    # Helper: convert a model coordinate (in inches) to device coordinates.
    def model_to_device(self, x, y, pixels_per_inch):
        T = self.zoom * pixels_per_inch
        device_x = T * x + self.offset_x
        device_y = T * y + self.offset_y
        return device_x, device_y

    # Helper: convert a device coordinate (pixels) to a model coordinate (in inches).
    def device_to_model(self, device_x, device_y, pixels_per_inch):
        T = self.zoom * pixels_per_inch
        model_x = (device_x - self.offset_x) / T
        model_y = (device_y - self.offset_y) / T
        return model_x, model_y

    # Helper: compute the visible model range (in inches) given device width and height.
    def get_visible_model_range(self, width, height, pixels_per_inch):
        T = self.zoom * pixels_per_inch
        x_min = -self.offset_x
        x_max = width / T - self.offset_x
        y_min = -self.offset_y
        y_max = height / T - self.offset_y
        return x_min, x_max, y_min, y_max

    # Helper: get the major grid positions (multiples of 96 inches) that are visible.
    def get_major_grid_positions(self, width, height, pixels_per_inch):
        x_min, x_max, y_min, y_max = self.get_visible_model_range(width, height, pixels_per_inch)
        major_spacing = 96  # inches (8 ft)
        x_positions = []
        y_positions = []
        n_min = math.floor(x_min / major_spacing)
        n_max = math.ceil(x_max / major_spacing)
        for n in range(n_min, n_max + 1):
            x_positions.append(n * major_spacing)
        n_min_y = math.floor(y_min / major_spacing)
        n_max_y = math.ceil(y_max / major_spacing)
        for n in range(n_min_y, n_max_y + 1):
            y_positions.append(n * major_spacing)
        return x_positions, y_positions
    
    def inches_to_feet_inches(self, inches):
        feet = int(inches // 12)
        inch = inches % 12
        return f"{feet}'-{inch:.0f}\""

    def on_draw(self, widget: Gtk.Widget, cr: "cairo.Context", width: int, height: int) -> None:
        """
        Render the entire canvas scene.

        Responsibilities:
        - Clear the device-background and set up the model->device transform using
          self.zoom, self.offset_x/offset_y and PIXELS_PER_INCH from self.config.
        - Draw the grid, walls, rooms, doors, windows.
        - Draw finished and in-progress polylines, plus the live rubber-band preview.
        - Draw selection indicators and wall endpoint handles for editing.
        - Draw live measurements, alignment guide, and snap indicator.
        - Restore device coordinates and draw rulers if enabled.

        Notes:
        - After the translate/scale transform, drawing is done in model units (inches).
        - Line widths, dash lengths and handle sizes are adjusted for zoom.
        - Uses configuration values: PIXELS_PER_INCH, DEFAULT_WALL_WIDTH, SHOW_RULERS, SHOW_GRID.
        Args:
            widget: the Gtk widget being drawn.
            cr: the Cairo context.
            width: device width in pixels.
            height: device height in pixels.

        Returns:
            None
        """
        # Clear background (device coordinates)
        cr.identity_matrix()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        # Save state and set up transformation for model coordinates.
        cr.save()
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        zoom_transform = self.zoom * pixels_per_inch # Scale factor for zooming.
        # Transformation: device = model * zoom_transform + self.offset
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(zoom_transform, zoom_transform)

        # Draw grid, walls, rooms, etc. in model coordinates.
        self.draw_grid(cr)
        
        # Draw walls
        wr.draw_walls(self, cr)

        # Draw rooms
        wr.draw_rooms(self, cr, zoom_transform)
            
        # Draw doors
        dwr.draw_doors(self, cr, pixels_per_inch)
        
        # Draw windows
        dwr.draw_windows(self, cr, pixels_per_inch)

        # Draw texts
        self.draw_texts(cr)
        
        # Draw dimensions
        self.draw_dimensions(cr)
        
        # Draw text preview
        if self.tool_mode == "add_text" and hasattr(self, "current_text_preview"):
             x, y, w, h = self.current_text_preview
             cr.set_source_rgba(0, 0, 1, 0.3)
             cr.rectangle(x, y, w, h)
             cr.fill()
             cr.set_source_rgb(0, 0, 1)
             cr.rectangle(x, y, w, h)
             cr.set_line_width(1.0 / zoom_transform)
             cr.stroke()
        
        # Draw finished polylines
        cr.save()
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1.0 / self.zoom)
        for poly_list in self.polyline_sets:
            for pl in poly_list:
                if pl.style == "dashed":
                    cr.set_dash([4/self.zoom, 4/self.zoom])
                else:
                    cr.set_dash([])
                cr.move_to(pl.start[0], pl.start[1])
                cr.line_to(pl.end[0],   pl.end[1])
                cr.stroke()
        cr.restore()

        # Draw in-progress (fixed) segments
        if self.polylines:
            cr.save()
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(1.0 / self.zoom)
            for pl in self.polylines:
                if pl.style == "dashed":
                    cr.set_dash([4/self.zoom, 4/self.zoom])
                else:
                    cr.set_dash([])
                cr.move_to(pl.start[0], pl.start[1])
                cr.line_to(pl.end[0],   pl.end[1])
                cr.stroke()
            cr.restore()

        # Draw the live “rubber-band” segment
        if self.tool_mode == "add_polyline" and self.drawing_polyline and self.current_polyline_preview:
            cr.save()
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(1.0 / self.zoom)
        
            default = getattr(self.config, "POLYLINE_TYPE", "solid")
            if default == "dashed":
                cr.set_dash([4/self.zoom, 4/self.zoom])
            else:
                cr.set_dash([])

            last_pt = self.current_polyline_start or self.polylines[-1].end
            cr.move_to(last_pt[0], last_pt[1])
            cr.line_to(self.current_polyline_preview[0], self.current_polyline_preview[1])
            cr.stroke()
            cr.restore()

        
        # Draw live selection rectangle if box selecting is active.
        if self.tool_mode == "pointer" and self.box_selecting:
            cr.save()
            # Set a dashed line style.
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            zoom_transform = self.zoom * pixels_per_inch
            dash_length = 4 / zoom_transform  # adjust dash length based on zoom
            cr.set_dash([dash_length, dash_length])
            cr.set_source_rgba(0, 0, 1, 0.6)  # blue with 60% opacity

            # Compute the rectangle bounds using the model coordinates for box_select_start and box_select_end.
            x1 = min(self.box_select_start[0], self.box_select_end[0])
            y1 = min(self.box_select_start[1], self.box_select_end[1])
            x2 = max(self.box_select_start[0], self.box_select_end[0])
            y2 = max(self.box_select_start[1], self.box_select_end[1])
            width = x2 - x1
            height = y2 - y1

            # Draw the dashed rectangle.
            cr.rectangle(x1, y1, width, height)
            cr.stroke()
            cr.restore()
        
        # Draw selection indicators.
        if hasattr(self, "selected_items"):
            cr.save()
            
            handle_radius = (self.handle_radius - 2) / (self.zoom * pixels_per_inch)
            
            # We’re still in model coordinates here.
            for item in self.selected_items:
                if item["type"] == "wall":
                    # print("Wall selected")
                    wall = item["object"]
                    
                    for pt, pt_name in [(wall.start, "start"), (wall.end, "end")]:
                        cr.set_source_rgba(1, 1, 0, 1.0)  # Yellow handles
                        cr.arc(pt[0], pt[1], handle_radius, 0, 2 * 3.14159)
                        cr.fill()
                        # Draw a border
                        cr.set_source_rgba(0, 0, 0, 1.0)
                        cr.arc(pt[0], pt[1], handle_radius, 0, 2 * 3.14159)
                        cr.set_line_width(1.0 / self.zoom)
                        cr.stroke()
                    
                    # Set a red color with some opacity.
                    cr.set_source_rgba(1, 0, 0, 1.0) # Opaque red.
                    # Save the original line width.
                    original_line_width = cr.get_line_width()
                    # Set a thicker line width for the selection indicator.
                    # Adjust this value as needed; here we double the default wall width.
                    cr.set_line_width((self.config.DEFAULT_WALL_WIDTH) / self.zoom)
                    # Draw the wall from start to end.
                    cr.move_to(wall.start[0], wall.start[1])
                    cr.line_to(wall.end[0], wall.end[1])
                    cr.stroke()
                    # Restore the original line width.
                    cr.set_line_width(original_line_width)
                elif item["type"] == "vertex":
                    # print("Vertex selected")
                    room, idx = item["object"]
                    pt = room.points[idx]
                    # Use a slightly less transparent red for vertices.
                    cr.set_source_rgba(1, 0, 0, 0.8)
                    radius = 5 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0))
                    cr.arc(pt[0], pt[1], radius, 0, 2 * 3.1416)
                    cr.fill()
                elif item["type"] == "door":
                    # print("Door selected")
                    wall, door, ratio = item["object"]
                    A = wall.start
                    B = wall.end
                    H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
                    dx = B[0] - A[0]
                    dy = B[1] - A[1]
                    length = math.hypot(dx, dy)
                    if length == 0:
                        continue
                    d = (dx / length, dy / length)
                    p = (-d[1], d[0])
                    w = door.width
                    t = self.config.DEFAULT_WALL_WIDTH
                    H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
                    H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
                    P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
                    P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
                    P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
                    P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
                    cr.set_source_rgba(1, 0, 0, 1.0)  # red outline
                    cr.set_line_width((self.config.DEFAULT_WALL_WIDTH) / self.zoom)
                    cr.move_to(*P1)
                    cr.line_to(*P2)
                    cr.line_to(*P3)
                    cr.line_to(*P4)
                    cr.close_path()
                    cr.stroke()

                elif item["type"] == "window":
                    # print("Window selected")
                    wall, window, ratio = item["object"]
                    A = wall.start
                    B = wall.end
                    H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
                    dx = B[0] - A[0]
                    dy = B[1] - A[1]
                    length = math.hypot(dx, dy)
                    if length == 0:
                        continue
                    d = (dx / length, dy / length)
                    p = (-d[1], d[0])
                    w = window.width
                    t = self.config.DEFAULT_WALL_WIDTH
                    H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
                    H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
                    P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
                    P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
                    P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
                    P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
                    cr.set_source_rgba(1, 0, 0, 1.0)
                    cr.set_line_width((self.config.DEFAULT_WALL_WIDTH) / self.zoom)
                    cr.move_to(*P1)
                    cr.line_to(*P2)
                    cr.line_to(*P3)
                    cr.line_to(*P4)
                    cr.close_path()
                    cr.stroke()
                
                elif item["type"] == "polyline":
                    pl = item["object"]
                    cr.set_source_rgba(1, 0, 0, 1.0)               # solid red
                    cr.set_line_width(1.0 / self.zoom)
                    # optional: preserve dash style
                    if pl.style == "dashed":
                        cr.set_dash([4/self.zoom, 4/self.zoom])
                    else:
                        cr.set_dash([])
                    cr.move_to(pl.start[0], pl.start[1])
                    cr.line_to(pl.end[0],   pl.end[1])
                    cr.stroke()
            cr.restore()


        self.draw_live_measurements(cr, pixels_per_inch)
        self.draw_alignment_guide(cr, pixels_per_inch)
        self.draw_snap_indicator(cr, pixels_per_inch)

        cr.restore()  # Return to device coordinates.

        # Draw rulers in device coordinates.
        if self.config.SHOW_RULERS:
            self.draw_rulers(cr, width, height, pixels_per_inch)

    def draw_grid(self, cr):
        if not self.config.SHOW_GRID:
            return
        minor_spacing = 12   # inches (1 ft)
        major_spacing = 96   # inches (8 ft)
        grid_min = -1000
        grid_max = 1000

        cr.set_line_width(1.0 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0)))
        cr.set_source_rgb(0.9, 0.9, 0.9)
        x = math.floor(grid_min / minor_spacing) * minor_spacing
        while x <= grid_max:
            cr.move_to(x, grid_min)
            cr.line_to(x, grid_max)
            x += minor_spacing
        y = math.floor(grid_min / minor_spacing) * minor_spacing
        while y <= grid_max:
            cr.move_to(grid_min, y)
            cr.line_to(grid_max, y)
            y += minor_spacing
        cr.stroke()

        cr.set_source_rgb(0.8, 0.8, 0.8)
        cr.set_line_width(2.0 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0)))
        x = math.floor(grid_min / major_spacing) * major_spacing
        while x <= grid_max:
            cr.move_to(x, grid_min)
            cr.line_to(x, grid_max)
            x += major_spacing
        y = math.floor(grid_min / major_spacing) * major_spacing
        while y <= grid_max:
            cr.move_to(grid_min, y)
            cr.line_to(grid_max, y)
            y += major_spacing
        cr.stroke()

    def draw_live_measurements(self, cr, pixels_per_inch):
        walls_to_label = []
        if self.drawing_wall and self.current_wall:
            walls_to_label.append(self.current_wall)
        
        if hasattr(self, "selected_items"):
            for item in self.selected_items:
                if item.get("type") == "wall":
                    walls_to_label.append(item["object"])

        for wall in walls_to_label:
            start = wall.start
            end = wall.end
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            deg = math.degrees(angle)
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            measurement_str = self.converter.format_measurement(length, use_fraction=False)
            text = f'{measurement_str} @ {deg:.1f}°'
            cr.save()
            cr.translate(mid_x, mid_y)
            cr.rotate(angle)
            offset = 20 / (self.zoom * pixels_per_inch)
            if -90 < deg < 90:
                cr.move_to(0, offset)
            else:
                cr.rotate(math.radians(180))
                cr.move_to(0, offset)
            cr.set_source_rgb(0, 0, 0)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(12 / (self.zoom * pixels_per_inch))
            cr.show_text(text)
            cr.restore()

    def draw_alignment_guide(self, cr, pixels_per_inch):
        if not (self.drawing_wall and self.current_wall and self.alignment_candidate and self.raw_current_end):
            return
        dx = self.raw_current_end[0] - self.alignment_candidate[0]
        dy = self.raw_current_end[1] - self.alignment_candidate[1]
        if math.hypot(dx, dy) < 1:
            return
        cr.save()
        cr.set_line_width(1.0 / (self.zoom * pixels_per_inch))
        dash = 2.0 / (self.zoom * pixels_per_inch)
        cr.set_dash([dash, dash])
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.move_to(self.raw_current_end[0], self.raw_current_end[1])
        cr.line_to(self.alignment_candidate[0], self.alignment_candidate[1])
        cr.stroke()
        cr.restore()

    def draw_snap_indicator(self, cr, pixels_per_inch):
        if self.snap_type == "none" or not self.drawing_wall or not self.current_wall:
            return
        cr.save()
        snap_x, snap_y = self.current_wall.end
        cr.set_line_width(2.0 / (self.zoom * pixels_per_inch))
        cr.set_font_size(12 / (self.zoom * pixels_per_inch))
        cr.select_font_face("Sans", 0, 0)
        if self.snap_type == "endpoint":
            cr.set_source_rgb(1, 0, 0)
            cr.arc(snap_x, snap_y, 10 / (self.zoom * pixels_per_inch), 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Endpoint")
        elif self.snap_type == "midpoint":
            cr.set_source_rgb(0, 0, 1)
            cr.arc(snap_x, snap_y, 10 / (self.zoom * pixels_per_inch), 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Midpoint")
        elif self.snap_type == "axis":
            cr.set_source_rgb(0, 1, 0)
            cr.move_to(snap_x - 20 / (self.zoom * pixels_per_inch), snap_y)
            cr.line_to(snap_x + 20 / (self.zoom * pixels_per_inch), snap_y)
            cr.move_to(snap_x, snap_y - 20 / (self.zoom * pixels_per_inch))
            cr.line_to(snap_x, snap_y + 20 / (self.zoom * pixels_per_inch))
            cr.stroke()
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Axis")
        elif self.snap_type in ["angle", "perpendicular"]:
            cr.set_source_rgb(1, 0, 1)
            cr.move_to(self.current_wall.start[0], self.current_wall.start[1])
            cr.line_to(snap_x, snap_y)
            cr.stroke()
            if self.snap_type == "perpendicular":
                cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
                cr.show_text("Perpendicular")
        elif self.snap_type == "grid":
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.rectangle(snap_x - 10 / (self.zoom * pixels_per_inch), snap_y - 10 / (self.zoom * pixels_per_inch),
                         20 / (self.zoom * pixels_per_inch), 20 / (self.zoom * pixels_per_inch))
            cr.stroke()
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Grid")
        elif self.snap_type == "distance":
            cr.set_source_rgb(1, 0.5, 0)
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Distance")
        elif self.snap_type == "tangent":
            cr.set_source_rgb(0, 1, 1)
            cr.arc(snap_x, snap_y, 10 / (self.zoom * pixels_per_inch), 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / (self.zoom * pixels_per_inch), snap_y)
            cr.show_text("Tangent")
        cr.restore()

    def draw_rulers(self, cr, width, height, pixels_per_inch):
        """
        Draw rulers along the top and left edges (in device coordinates). Instead of recalculating tick positions,
        we reuse the same major grid positions as for the grid lines. Major ticks occur every 96 inches (8 ft)
        in model space. These positions are converted to device coordinates using the same transformation as the grid:
            device = model * T + self.offset
        """
        cr.save()
        cr.identity_matrix()  # Work in device coordinates.

        ruler_thickness = 20  # pixels

        # Draw ruler backgrounds.
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(0, 0, width, ruler_thickness)   # Top ruler.
        cr.rectangle(0, 0, ruler_thickness, height)   # Left ruler.
        cr.fill()

        # Get the visible major grid positions.
        x_positions, y_positions = self.get_major_grid_positions(width, height, pixels_per_inch)

        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)

        # Draw ticks and labels on the top ruler using the same positions as the major grid lines.
        for x in x_positions:
            device_x, _ = self.model_to_device(x, 0, pixels_per_inch)
            if 0 <= device_x <= width:
                tick_length = 10  # pixels.
                cr.move_to(device_x, ruler_thickness)
                cr.line_to(device_x, ruler_thickness - tick_length)
                cr.stroke()
                feet = int(x / 12)
                cr.select_font_face("Sans", 0, 0)
                cr.set_font_size(10)
                cr.move_to(device_x + 2, ruler_thickness - tick_length - 2)
                cr.show_text(f"{feet} ft")
        # Draw ticks and labels on the left ruler using the same positions as the major grid lines.
        for y in y_positions:
            _, device_y = self.model_to_device(0, y, pixels_per_inch)
            if 0 <= device_y <= height:
                tick_length = 10  # pixels.
                cr.move_to(ruler_thickness, device_y)
                cr.line_to(ruler_thickness - tick_length, device_y)
                cr.stroke()
                feet = int(y / 12)
                cr.select_font_face("Sans", 0, 0)
                cr.set_font_size(10)
                cr.move_to(2, device_y - 2)
                cr.show_text(f"{feet} ft")
        cr.restore()

    def draw_texts(self, cr):
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        
        for text in self.texts:
            # Check if selected to draw frame/handles
            is_selected = any(item["type"] == "text" and item["object"] == text for item in self.selected_items)
            
            # Using model space drawing for positioning, but text rendering often needs careful scaling
            # Strategy: Render text at projected device location for sharpness, scaled by zoom
            
            # Calculate device bounds
            device_x, device_y = self.model_to_device(text.x, text.y, pixels_per_inch)
            zoom_transform = self.zoom * pixels_per_inch
            
            cr.save()
            cr.identity_matrix() # Reset to device pixels
            cr.translate(device_x, device_y)
            
            # Apply rotation (convert degrees to radians)
            rotation_radians = math.radians(text.rotation)
            cr.rotate(rotation_radians)
            
            cr.scale(self.zoom, self.zoom) # Scale text with zoom
            
            layout = PangoCairo.create_layout(cr)
            layout.set_text(text.content, -1)
            desc = Pango.FontDescription(f"{text.font_family} {text.font_size}")
            if text.bold:
                desc.set_weight(Pango.Weight.BOLD)
            if text.italic:
                desc.set_style(Pango.Style.ITALIC)
            layout.set_font_description(desc)
            
            attr_list = Pango.AttrList()
            if text.underline:
                attr = Pango.attr_underline_new(Pango.Underline.SINGLE)
                attr_list.insert(attr)
            layout.set_attributes(attr_list)
        
            # Use text color if available, otherwise default to black
            color = getattr(text, 'color', (0.0, 0.0, 0.0))
            cr.set_source_rgb(*color)
            PangoCairo.show_layout(cr, layout)
            
            # Measure layout for selection box
            if is_selected:
                # Get logical extents
                ink_rect, logical_rect = layout.get_extents()
                w = logical_rect.width / Pango.SCALE
                h = logical_rect.height / Pango.SCALE
                
                # Draw selection border
                cr.set_source_rgb(0, 0, 1)
                cr.set_line_width(1.0)
                cr.set_dash([4.0, 2.0])
                cr.rectangle(0, 0, w, h)
                cr.stroke()
                
                # Draw rotation handle (small circle at top-right corner)
                handle_radius = 4.0
                cr.set_source_rgb(0, 0.5, 1)
                cr.set_dash([])
                cr.arc(w, 0, handle_radius, 0, 2 * math.pi)
                cr.fill()
                cr.set_source_rgb(0, 0, 0)
                cr.arc(w, 0, handle_radius, 0, 2 * math.pi)
                cr.set_line_width(1.0)
                cr.stroke()
            
            cr.restore()
    
    def draw_dimensions(self, cr):
        """Draw all dimension objects with extension lines, dimension lines, arrows, and measurement text."""
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        
        # Draw finalized dimensions
        for dimension in self.dimensions:
            self._draw_single_dimension(cr, dimension, pixels_per_inch, is_preview=False)
        
        # Draw dimension preview during creation
        if self.drawing_dimension and self.dimension_start:
            if self.dimension_end:
                # After second click - show preview with current mouse position
                if self.dimension_offset_preview:
                    # Create temporary dimension for preview
                    offset = self._calculate_dimension_offset(
                        self.dimension_start,
                        self.dimension_end,
                        self.dimension_offset_preview
                    )
                    temp_dim = self.Dimension(
                        start=self.dimension_start,
                        end=self.dimension_end,
                        offset=offset,
                        text_size=12.0
                    )
                    self._draw_single_dimension(cr, temp_dim, pixels_per_inch, is_preview=True)
            else:
                # After first click - show line from start to current mouse
                if hasattr(self, "_last_mouse_pos"):
                    cr.save()
                    cr.set_source_rgb(0.5, 0.5, 0.5)
                    cr.set_line_width(1.0 / (self.zoom * pixels_per_inch))
                    cr.set_dash([4.0 / (self.zoom * pixels_per_inch), 4.0 / (self.zoom * pixels_per_inch)])
                    cr.move_to(self.dimension_start[0], self.dimension_start[1])
                    cr.line_to(self._last_mouse_pos[0], self._last_mouse_pos[1])
                    cr.stroke()
                    cr.restore()
    
    def _draw_single_dimension(self, cr, dimension, pixels_per_inch, is_preview=False):
        """Draw a single dimension with all its components."""
        start = dimension.start
        end = dimension.end
        offset = dimension.offset
        
        # Calculate dimension line position (parallel to measured line, offset perpendicularly)
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.hypot(dx, dy)
        
        if length == 0:
            return
        
        # Unit vector along the line
        ux = dx / length
        uy = dy / length
        
        # Perpendicular unit vector (rotate 90 degrees)
        px = -uy
        py = ux
        
        # Dimension line endpoints (offset from measured line)
        dim_start = (start[0] + offset * px, start[1] + offset * py)
        dim_end = (end[0] + offset * px, end[1] + offset * py)
        
        cr.save()
        
        # Check if this dimension is selected
        is_selected = any(
            item.get("type") == "dimension" and item.get("object") is dimension
            for item in self.selected_items
        )
        
        # Set color
        color = getattr(dimension, 'color', (0.0, 0.0, 0.0))
        if is_preview:
            cr.set_source_rgba(color[0], color[1], color[2], 0.5)  # Semi-transparent for preview
        else:
            if is_selected:
                cr.set_source_rgb(0.0, 0.4, 0.8)  # Blue for selected
            else:
                cr.set_source_rgb(*color)
        
        line_width = 1.0 / (self.zoom * pixels_per_inch)
        if is_selected:
            line_width *= 2.5  # Thicker line for selected dimensions
        cr.set_line_width(line_width)
        
        # Set line style
        line_style = getattr(dimension, 'line_style', 'solid')
        if line_style == "dashed":
            cr.set_dash([4.0 / (self.zoom * pixels_per_inch), 4.0 / (self.zoom * pixels_per_inch)])
        else:
            cr.set_dash([])
        
        # Draw extension lines (from measured points to dimension line)
        # Extension lines go slightly beyond the dimension line
        extension_overhang = 2.0  # inches
        
        # Extension line at start
        ext_start_pt = (start[0] + (offset + extension_overhang) * px, start[1] + (offset + extension_overhang) * py)
        cr.move_to(start[0], start[1])
        cr.line_to(ext_start_pt[0], ext_start_pt[1])
        cr.stroke()
        
        # Extension line at end
        ext_end_pt = (end[0] + (offset + extension_overhang) * px, end[1] + (offset + extension_overhang) * py)
        cr.move_to(end[0], end[1])
        cr.line_to(ext_end_pt[0], ext_end_pt[1])
        cr.stroke()
        
        # Draw dimension line
        cr.move_to(dim_start[0], dim_start[1])
        cr.line_to(dim_end[0], dim_end[1])
        cr.stroke()
        
        # Draw arrows if enabled
        show_arrows = getattr(dimension, 'show_arrows', True)
        if show_arrows:
            arrow_len = 3.0  # inches
            arrow_angle = math.radians(20)  # 20 degree arrow angle
            
            # Arrow at start (pointing towards start point)
            arrow_dir_x = -ux
            arrow_dir_y = -uy
            
            # Arrow line 1
            a1x = dim_start[0] + arrow_len * (arrow_dir_x * math.cos(arrow_angle) - arrow_dir_y * math.sin(arrow_angle))
            a1y = dim_start[1] + arrow_len * (arrow_dir_x * math.sin(arrow_angle) + arrow_dir_y * math.cos(arrow_angle))
            cr.move_to(dim_start[0], dim_start[1])
            cr.line_to(a1x, a1y)
            cr.stroke()
            
            # Arrow line 2
            a2x = dim_start[0] + arrow_len * (arrow_dir_x * math.cos(-arrow_angle) - arrow_dir_y * math.sin(-arrow_angle))
            a2y = dim_start[1] + arrow_len * (arrow_dir_x * math.sin(-arrow_angle) + arrow_dir_y * math.cos(-arrow_angle))
            cr.move_to(dim_start[0], dim_start[1])
            cr.line_to(a2x, a2y)
            cr.stroke()
            
            # Arrow at end (pointing towards end point)
            arrow_dir_x = ux
            arrow_dir_y = uy
            
            # Arrow line 1
            a1x = dim_end[0] + arrow_len * (arrow_dir_x * math.cos(arrow_angle) - arrow_dir_y * math.sin(arrow_angle))
            a1y = dim_end[1] + arrow_len * (arrow_dir_x * math.sin(arrow_angle) + arrow_dir_y * math.cos(arrow_angle))
            cr.move_to(dim_end[0], dim_end[1])
            cr.line_to(a1x, a1y)
            cr.stroke()
            
            # Arrow line 2
            a2x = dim_end[0] + arrow_len * (arrow_dir_x * math.cos(-arrow_angle) - arrow_dir_y * math.sin(-arrow_angle))
            a2y = dim_end[1] + arrow_len * (arrow_dir_x * math.sin(-arrow_angle) + arrow_dir_y * math.cos(-arrow_angle))
            cr.move_to(dim_end[0], dim_end[1])
            cr.line_to(a2x, a2y)
            cr.stroke()
        
        # Draw measurement text at midpoint
        mid_x = (dim_start[0] + dim_end[0]) / 2
        mid_y = (dim_start[1] + dim_end[1]) / 2
        
        # Format measurement
        measurement_str = self.converter.format_measurement(length, use_fraction=False)
        
        # Calculate text angle (parallel to dimension line)
        text_angle = math.atan2(dy, dx)
        
        # Flip text if upside down
        if text_angle > math.pi / 2 or text_angle < -math.pi / 2:
            text_angle += math.pi
        
        cr.save()
        cr.translate(mid_x, mid_y)
        cr.rotate(text_angle)
        
        # Set font
        text_size = getattr(dimension, 'text_size', 12.0) / (self.zoom * pixels_per_inch)
        cr.set_font_size(text_size)
        cr.select_font_face("Sans", 0, 0)
        
        # Get text extents for background
        extents = cr.text_extents(measurement_str)
        text_width = extents.width
        text_height = extents.height
        
        # Draw white background for text
        padding = 2.0 / (self.zoom * pixels_per_inch)
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(
            -text_width / 2 - padding,
            -text_height - padding,
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        cr.fill()
        
        # Draw text
        if is_preview:
            cr.set_source_rgba(color[0], color[1], color[2], 0.5)
        else:
            cr.set_source_rgb(*color)
        cr.move_to(-text_width / 2, 0)
        cr.show_text(measurement_str)
        
        cr.restore()
        cr.restore()