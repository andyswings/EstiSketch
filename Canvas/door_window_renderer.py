import math

def draw_doors(self, cr, pixels_per_inch):
    # Draw doors
    cr.save()
    T = self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0)

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
        
        if door.door_type == "single":
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


def draw_windows(self, cr, pixels_per_inch):
    # Draw windows
    for window_item in self.windows: # window_item = (wall, window, ratio)
        wall, window, ratio = window_item # wall is a Wall object, window is a Window object, ratio is a float
        A = wall.start # wall.start and wall.end are tuples (x, y)
        B = wall.end
        H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1])) # H is the center of the window opening
        
        # Calculate wall direction and perpendicular
        dx = B[0] - A[0]
        dy = B[1] - A[1]
        length = math.hypot(dx, dy) # Length of the wall segment
        if length == 0: # Avoid division by zero if wall segment is degenerate
            continue
        d = (dx / length, dy / length)  # Unit vector along wall
        p = (-d[1], d[0])  # Perpendicular vector
        
        w = window.width 
        t = self.config.DEFAULT_WALL_WIDTH 
        
        # Window opening endpoints along the wall
        H_start = (H[0] - (w / 2) * d[0], H[1] - (w / 2) * d[1]) 
        H_end = (H[0] + (w / 2) * d[0], H[1] + (w / 2) * d[1]) 
        
        # Opening rectangle corners
        P1 = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1]) # Bottom-left corner
        P2 = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1]) # Bottom-right corner
        P3 = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1]) # Top-right corner
        P4 = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1]) # Top-left corner
        
        # Draw the opening as a white rectangle
        cr.set_source_rgb(1, 1, 1)  # White fill
        cr.move_to(*P1)
        cr.line_to(*P2)
        cr.line_to(*P3)
        cr.line_to(*P4)
        cr.close_path()
        cr.fill() 
        
        #TODO Add other types of windows. (Double-hung, Fixed)
        if window.window_type == "sliding":
            # Draw two lines parallel to the wall for sliding panels
            T = self.zoom * pixels_per_inch 
            offset = w / 4 # Offset for the sliding panels
            line1_start = (H_start[0] + offset * d[0], H_start[1] + offset * d[1]) # Bottom line
            line1_end = (H_end[0] + offset * d[0], H_end[1] + offset * d[1])
            line2_start = (H_start[0] - offset * d[0], H_start[1] - offset * d[1]) # Top line
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
        theta = math.atan2(d[1], d[0]) # Angle of the wall
        # Adjust theta to avoid upside-down text
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