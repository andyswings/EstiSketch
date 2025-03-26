import math
from gi.repository import cairo

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

    def on_draw(self, widget, cr, width, height):
        # Clear background (device coordinates)
        cr.identity_matrix()
        cr.set_source_rgb(1, 1, 1)
        cr.paint()

        # Save state and set up transformation for model coordinates.
        cr.save()
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        T = self.zoom * pixels_per_inch
        # Transformation: device = model * T + self.offset
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(T, T)

        # Draw grid, walls, rooms, etc. in model coordinates.
        self.draw_grid(cr)

        cr.set_source_rgb(0, 0, 0) # Black lines.
        cr.set_line_width(self.config.DEFAULT_WALL_WIDTH) # Set wall width.
        cr.set_line_join(0) # 0 = miter join.
        cr.set_line_cap(0) # 0 = butt cap.
        cr.set_miter_limit(10.0)
        for wall_set in self.wall_sets:
            if not wall_set:
                continue
            cr.move_to(wall_set[0].start[0], wall_set[0].start[1])
            for wall in wall_set:
                cr.line_to(wall.end[0], wall.end[1])
            if len(wall_set) > 2 and wall_set[-1].end == wall_set[0].start:
                cr.close_path()
            cr.stroke()

        if self.walls:
            cr.move_to(self.walls[0].start[0], self.walls[0].start[1])
            for wall in self.walls:
                cr.line_to(wall.end[0], wall.end[1])
            if self.current_wall:
                cr.line_to(self.current_wall.end[0], self.current_wall.end[1])
            if not self.drawing_wall and len(self.walls) > 2 and self.walls[-1].end == self.walls[0].start:
                cr.close_path()
            cr.stroke()
        elif self.current_wall:
            cr.move_to(self.current_wall.start[0], self.current_wall.start[1])
            cr.line_to(self.current_wall.end[0], self.current_wall.end[1])
            cr.stroke()

        cr.set_source_rgb(0.9, 0.9, 1)  # light blue fill.
        cr.set_line_width(1.0 / T)
        for room in self.rooms:
            if room.points:
                cr.save()
                cr.move_to(room.points[0][0], room.points[0][1])
                for pt in room.points[1:]:
                    cr.line_to(pt[0], pt[1])
                cr.close_path()
                cr.fill_preserve()
                cr.set_source_rgb(0, 0, 0)
                cr.stroke()
                cr.restore()

        if self.tool_mode == "draw_rooms" and self.current_room_points:
            cr.save()
            cr.set_source_rgb(0, 0, 1)
            cr.set_line_width(2.0 / T)
            cr.move_to(self.current_room_points[0][0], self.current_room_points[0][1])
            for pt in self.current_room_points[1:]:
                cr.line_to(pt[0], pt[1])
            if self.current_room_preview:
                cr.line_to(self.current_room_preview[0], self.current_room_preview[1])
            cr.stroke()
            cr.restore()
        
        # Draw doors
        cr.save()
        T = self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0)
        wall_thickness = self.config.DEFAULT_WALL_WIDTH  # full wall thickness in inches

        for door_item in self.doors:
            wall, door, ratio = door_item
            A = wall.start
            B = wall.end
            H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
            
            # Wall direction and perpendicular
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            d = (dx / length, dy / length)
            p = (-d[1], d[0])
            
            # Leaf direction based on swing
            if door.swing == "left":
                n = (-p[0], -p[1])  # -p
            else:  # "right"
                n = (p[0], p[1])    # p
            
            w = door.width
            t = self.config.DEFAULT_WALL_WIDTH
            
            # Opening endpoints
            H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
            H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
            
            # Opening rectangle
            P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
            P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
            P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
            P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
            
            cr.set_source_rgb(1, 1, 1)  # White fill for opening
            cr.move_to(*P1)
            cr.line_to(*P2)
            cr.line_to(*P3)
            cr.line_to(*P4)
            cr.close_path()
            cr.fill()
            
            # Hinge position
            if door.swing == "left":
                hinge = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Bottom-left corner
            else:
                hinge = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])     # Top-right corner
            
            # Draw leaf in open position
            F = (hinge[0] + w * n[0], hinge[1] + w * n[1])
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(1.0 / T)
            cr.move_to(*hinge)
            cr.line_to(*F)
            cr.stroke()
            
            # Draw swing arc from closed to open
            angle_closed = math.atan2(d[1], d[0])  # Along wall
            angle_open = math.atan2(n[1], n[0])    # Along leaf
            if door.swing == "left":
                cr.arc_negative(hinge[0], hinge[1], w, angle_closed, angle_open)
            else:
                cr.arc(hinge[0], hinge[1], w, angle_closed, angle_open)
            cr.set_dash([4.0 / T, 4.0 / T])
            cr.stroke()
            cr.set_dash([])

            # Compute label text (e.g., "3'0\" x 6'8\"")
            width_str = self.inches_to_feet_inches(door.width)
            height_str = self.inches_to_feet_inches(door.height)
            text = f"{width_str} x {height_str}"

            # Compute label position (offset from wall center H, opposite the swing direction n)
            margin = 6.0  # Offset in inches
            t = 4.0       # Wall thickness in inches, example value
            label_pos = (H[0] - (t / 2 + margin) * n[0], H[1] - (t / 2 + margin) * n[1])

            # Compute the wall's angle
            theta = math.atan2(d[1], d[0])

            # Adjust theta to avoid upside-down text
            theta_adjusted = theta % (2 * math.pi)
            if theta_adjusted > math.pi / 2 and theta_adjusted < 3 * math.pi / 2:
                theta_text = theta + math.pi
            else:
                theta_text = theta

            # Save the Cairo context
            cr.save()

            # Translate to label position
            cr.translate(label_pos[0], label_pos[1])

            # Rotate to the adjusted angle
            cr.rotate(theta_text)

            # Set font properties
            font_size = 12 / (self.zoom * pixels_per_inch)  # Adjust for zoom and DPI
            cr.select_font_face("Sans", 0, 0)  # Family, slant, weight
            cr.set_font_size(font_size)

            # Center the text horizontally
            extents = cr.text_extents(text)
            x = -extents.width / 2  # Center along the wall
            y = -font_size * -1.5    # Offset "above" in rotated coordinates

            # Move to position and draw
            cr.move_to(x, y)
            cr.set_source_rgb(0, 0, 0)  # Black text
            cr.show_text(text)

            # Restore the context
            cr.restore()
        cr.restore()
        
        # Draw windows
        for window_item in self.windows:
            wall, window, ratio = window_item
            A = wall.start
            B = wall.end
            H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1]))
            
            # Calculate wall direction and perpendicular
            dx = B[0] - A[0]
            dy = B[1] - A[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            d = (dx / length, dy / length)  # Unit vector along wall
            p = (-d[1], d[0])  # Perpendicular vector
            
            w = window.width
            t = self.config.DEFAULT_WALL_WIDTH
            
            # Window opening endpoints along the wall
            H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1])
            H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1])
            
            # Opening rectangle corners
            P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])
            P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])
            P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])
            P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])
            
            # Draw the opening as a white rectangle
            cr.set_source_rgb(1, 1, 1)  # White fill
            cr.move_to(*P1)
            cr.line_to(*P2)
            cr.line_to(*P3)
            cr.line_to(*P4)
            cr.close_path()
            cr.fill()
            
            if window.window_type == "sliding":
                # Draw two lines parallel to the wall for sliding panels
                T = self.zoom * pixels_per_inch
                offset = w / 4
                line1_start = (H_start[0] + offset * d[0], H_start[1] + offset * d[1])
                line1_end = (H_end[0] + offset * d[0], H_end[1] + offset * d[1])
                line2_start = (H_start[0] - offset * d[0], H_start[1] - offset * d[1])
                line2_end = (H_end[0] - offset * d[0], H_end[1] - offset * d[1])
                
                cr.set_source_rgb(0, 0, 0)  # Black lines
                cr.set_line_width(1.0 / T)  # Thin line adjusted for zoom
                cr.move_to(*line1_start)
                cr.line_to(*line1_end)
                cr.stroke()
                cr.move_to(*line2_start)
                cr.line_to(*line2_end)
                cr.stroke()
            
            # Draw label with window dimensions
            width_str = self.inches_to_feet_inches(window.width)
            height_str = self.inches_to_feet_inches(window.height)
            text = f"{width_str} x {height_str}"
            margin = 6.0  # Offset in inches
            label_pos = (H[0] + (t / 2 + margin) * p[0], H[1] + (t / 2 + margin) * p[1])
            
            cr.save()
            cr.translate(label_pos[0], label_pos[1])
            theta = math.atan2(d[1], d[0])
            theta_adjusted = theta % (2 * math.pi)
            if theta_adjusted > math.pi / 2 and theta_adjusted < 3 * math.pi / 2:
                theta_text = theta + math.pi  # Flip if upside down
            else:
                theta_text = theta
            cr.rotate(theta_text)
            font_size = 12 / (self.zoom * pixels_per_inch)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(font_size)
            extents = cr.text_extents(text)
            x_text = -extents.width / 2  # Center horizontally
            y_text = -font_size * -1.5   # Offset above
            cr.move_to(x_text, y_text)
            cr.set_source_rgb(0, 0, 0)  # Black text
            cr.show_text(text)
            cr.restore()
        
        # Draw live selection rectangle if box selecting is active.
        if self.tool_mode == "pointer" and self.box_selecting:
            cr.save()
            # Set a dashed line style.
            pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
            T = self.zoom * pixels_per_inch
            dash_length = 4 / T  # adjust dash length based on zoom
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
            # We’re still in model coordinates here.
            for item in self.selected_items:
                if item["type"] == "wall":
                    wall = item["object"]
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
                    room, idx = item["object"]
                    pt = room.points[idx]
                    # Use a slightly less transparent red for vertices.
                    cr.set_source_rgba(1, 0, 0, 0.8)
                    radius = 5 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0))
                    cr.arc(pt[0], pt[1], radius, 0, 2 * 3.1416)
                    cr.fill()
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
        if self.drawing_wall and self.current_wall:
            start = self.current_wall.start
            end = self.current_wall.end
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            length = math.hypot(dx, dy)
            angle = math.atan2(dy, dx)
            deg = math.degrees(angle)
            mid_x = (start[0] + end[0]) / 2
            mid_y = (start[1] + end[1]) / 2
            measurement_str = self.converter.format_measurement(self, length, use_fraction=False)
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
        T = self.zoom * pixels_per_inch

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