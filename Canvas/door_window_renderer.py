import math

def draw_doors(self, cr, pixels_per_inch):
    # Draw doors
    cr.save()
    zoom_transform = self.zoom * pixels_per_inch

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
            cr.set_line_width(1.0 / zoom_transform)
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
            cr.set_dash([4.0 / zoom_transform, 4.0 / zoom_transform])
            cr.stroke()
            cr.set_dash([])
        
        # TODO Come up with a good recognizable symbol for garage doors. Make it distinct from other doors.
        if door.door_type == "garage":
            print("Garage door")
        
        if door.door_type == "double":
            # Hinge positions for double doors
            hinge1 = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])
            hinge2 = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])
            
            # Calculate open leaf positions (90-degree swing from wall)
            w_half = w / 2  # Half width for each leaf
            if door.swing == "left":
                # Both leaves swing toward the normal (outward)
                F1 = (hinge1[0] + w_half * n[0], hinge1[1] + w_half * n[1])  # Left leaf
                F2 = (hinge2[0] + w_half * n[0], hinge2[1] + w_half * n[1])  # Right leaf
            else:
                # Both leaves swing opposite the normal (inward)
                F1 = (hinge1[0] - w_half * n[0], hinge1[1] - w_half * n[1])  # Left leaf
                F2 = (hinge2[0] - w_half * n[0], hinge2[1] - w_half * n[1])  # Right leaf
            
            # Draw door leaves
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*hinge1)
            cr.line_to(*F1)
            cr.stroke()
            cr.move_to(*hinge2)
            cr.line_to(*F2)
            cr.stroke()
            
            # Draw swing arcs for both leaves
            angle_closed = math.atan2(d[1], d[0])  # Along wall
            if door.swing == "left":
                # Both leaves swing toward normal (counter-clockwise from wall)
                angle_open = angle_closed - math.pi/2  # 90 degrees counter-clockwise
                # Draw left leaf arc (from closed to open)
                cr.move_to(*hinge1)
                cr.arc_negative(hinge1[0], hinge1[1], w_half, angle_closed, angle_open)
                cr.set_dash([4.0 / zoom_transform, 4.0 / zoom_transform])
                cr.stroke()
                # Draw right leaf arc (from closed on opposite side to open)
                cr.move_to(*hinge2)
                cr.arc(hinge2[0], hinge2[1], w_half, angle_closed + math.pi, angle_open)
                cr.stroke()
            else:
                # Both leaves swing opposite normal (clockwise from wall)
                angle_open = angle_closed + math.pi/2  # 90 degrees clockwise
                # Draw left leaf arc (from closed to open)
                cr.move_to(*hinge1)
                cr.arc(hinge1[0], hinge1[1], w_half, angle_closed, angle_open)
                cr.set_dash([4.0 / zoom_transform, 4.0 / zoom_transform])
                cr.stroke()
                # Draw right leaf arc (from closed on opposite side to open)
                cr.move_to(*hinge2)
                cr.arc_negative(hinge2[0], hinge2[1], w_half, angle_closed + math.pi, angle_open)
                cr.stroke()
            
            cr.set_dash([])  # Reset dash pattern
        
        if door.door_type == "frame":
            print("Door frame")
        
        #TODO Draw sliding doors differently so they don't look the same as sliding windows. I don't like the way they look with the current code.
        if door.door_type == "sliding":
            print("Sliding door")
            offset = w / 4  # Offset for the sliding panels
            panel1_start = (H_start[0] + offset * d[0], H_start[1] + offset * d[1])
            panel1_end = (H_end[0] + offset * d[0], H_end[1] + offset * d[1])
            panel2_start = (H_start[0] - offset * d[0], H_start[1] - offset * d[1])
            panel2_end = (H_end[0] - offset * d[0], H_end[1] - offset * d[1])
            
            
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / zoom_transform)
            cr.set_dash([6.0 / zoom_transform, 3.0 / zoom_transform])  # Dashed pattern
            cr.move_to(*panel1_start)
            cr.line_to(*panel1_end)
            cr.stroke()
            cr.move_to(*panel2_start)
            cr.line_to(*panel2_end)
            cr.stroke()
            cr.set_dash([])  # Reset dash pattern
        
        # TODO Fix the drawing of pocket doors. They currently look like fixed windows.
        if door.door_type == "pocket":
            print("Pocket door")
            # Draw pocket door outline
            T = self.zoom * pixels_per_inch
            pocket_start = (H_start[0] + (w / 2) * d[0], H_start[1] + (w / 2) * d[1])
            pocket_end = (H_end[0] - (w / 2) * d[0], H_end[1] - (w / 2) * d[1])
            
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*H_start)
            cr.line_to(*pocket_start)
            cr.stroke()
            cr.move_to(*H_end)
            cr.line_to(*pocket_end)
            cr.stroke()
        
        if door.door_type == "bi-fold":
            # Draw bi-fold door panels
            w_half = w / 2  # Each leaf is half the total width
            
            # Hinge points
            hinge_start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left hinge
            hinge_end = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])      # Right hinge
            
            # Calculate center of door opening
            center_x = (H_start[0] + H_end[0]) / 2 + (t / 2) * n[0]
            center_y = (H_start[1] + H_end[1]) / 2 + (t / 2) * n[1]
            
            # Angles for 60-degree folds (converted to radians)
            angle_60 = math.pi / 3  # 60 degrees
            
            # Left leaf: from hinge_start at 60 degrees toward center
            angle_closed = math.atan2(d[1], d[0])  # Along wall
            angle_left1 = angle_closed - angle_60  # 60 degrees counter-clockwise from wall
            left1_end = (hinge_start[0] + w_half * math.cos(angle_left1),
                        hinge_start[1] + w_half * math.sin(angle_left1))
            
            # Left leaf second segment: from left1_end at 60 degrees back toward center
            direction_to_center = angle_closed + math.pi + angle_60
            angle_left2 = direction_to_center + angle_60 * 3  
            left2_end = (left1_end[0] + w_half * math.cos(angle_left2),
                        left1_end[1] + w_half * math.sin(angle_left2))
            
            # Draw folded panels
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / zoom_transform)
            
            # Left leaf: hinge_start -> left1_end -> left2_end
            cr.move_to(*hinge_start)
            cr.line_to(*left1_end)
            cr.line_to(*left2_end)
            cr.stroke()
        
        if door.door_type == "double bi-fold":
            # Draw bi-fold door panels
            w_quarter = w / 4  # Each leaf is a quarter the total width
            
            # Hinge points
            hinge_start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left hinge
            hinge_end = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])      # Right hinge
            
            # Calculate center of door opening
            center_x = (H_start[0] + H_end[0]) / 2 + (t / 2) * n[0]
            center_y = (H_start[1] + H_end[1]) / 2 + (t / 2) * n[1]
            
            # Angles for 60-degree folds (converted to radians)
            angle_60 = math.pi / 3  # 60 degrees
            
            # Left leaf: from hinge_start at 60 degrees toward center
            angle_closed = math.atan2(d[1], d[0])  # Along wall
            angle_left1 = angle_closed - angle_60  # 60 degrees counter-clockwise from wall
            left1_end = (hinge_start[0] + w_quarter * math.cos(angle_left1),
                        hinge_start[1] + w_quarter * math.sin(angle_left1))
            
            # Left leaf second segment: from left1_end at 60 degrees back toward center
            direction_to_center = angle_closed + math.pi + angle_60
            angle_left2 = direction_to_center + angle_60 * 3  
            left2_end = (left1_end[0] + w_quarter * math.cos(angle_left2),
                        left1_end[1] + w_quarter * math.sin(angle_left2))
            
            # Right leaf: from hinge_end at 60 degrees toward center
            angle_right1 = angle_closed + math.pi + angle_60  # 60 degrees clockwise from opposite wall
            right1_end = (hinge_end[0] + w_quarter * math.cos(angle_right1),
                        hinge_end[1] + w_quarter * math.sin(angle_right1))
            
            # Right leaf second segment: from right1_end at 60 degrees back toward center
            direction_to_center = math.atan2(center_y - right1_end[1], center_x + right1_end[0])
            angle_right2 = direction_to_center - angle_60 * 4 # 60 degrees counter-clockwise from center direction
            right2_end = (right1_end[0] + w_quarter * math.cos(angle_right2),
                        right1_end[1] + w_quarter * math.sin(angle_right2))
            
            # Draw folded panels
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / zoom_transform)
            
            # Left leaf: hinge_start -> left1_end -> left2_end
            cr.move_to(*hinge_start)
            cr.line_to(*left1_end)
            cr.line_to(*left2_end)
            cr.stroke()
            
            # Right leaf: hinge_end -> right1_end -> right2_end
            cr.move_to(*hinge_end)
            cr.line_to(*right1_end)
            cr.line_to(*right2_end)
            cr.stroke()

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
        font_size = 12 / zoom_transform  # Adjust for zoom and DPI
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
    zoom_transform = self.zoom * pixels_per_inch
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
        
        if window.window_type == "sliding":
            print("Sliding window")
            # Draw two lines parallel to the wall for sliding panels
            offset = w / 4 # Offset for the sliding panels
            line1_start = (H_start[0] + offset * d[0], H_start[1] + offset * d[1]) # Bottom line
            line1_end = (H_end[0] + offset * d[0], H_end[1] + offset * d[1])
            line2_start = (H_start[0] - offset * d[0], H_start[1] - offset * d[1]) # Top line
            line2_end = (H_end[0] - offset * d[0], H_end[1] - offset * d[1])
            
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / zoom_transform)  # Thin line adjusted for zoom
            cr.move_to(*line1_start)
            cr.line_to(*line1_end)
            cr.stroke()
            cr.move_to(*line2_start)
            cr.line_to(*line2_end)
            cr.stroke()
        
        if window.window_type == "double-hung":
            print("Double hung window")
            # Draw two horizontal lines for double-hung window sashes
            sash_offset = w / 4  # Offset for the sashes
            sash1_start = (H_start[0] + sash_offset * d[0], H_start[1] + sash_offset * d[1])
            sash1_end = (H_end[0] + sash_offset * d[0], H_end[1] + sash_offset * d[1])
            sash2_start = (H_start[0] - sash_offset * d[0], H_start[1] - sash_offset * d[1])
            sash2_end = (H_end[0] - sash_offset * d[0], H_end[1] - sash_offset * d[1])
            
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / zoom_transform)  # Thin line adjusted for zoom
            cr.move_to(*sash1_start)
            cr.line_to(*sash1_end)
            cr.stroke()
            cr.move_to(*sash2_start)
            cr.line_to(*sash2_end)
            cr.stroke()

        if window.window_type == "fixed":
            print("Fixed window")
            # Draw a single rectangle outline for fixed window
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*P1)
            cr.line_to(*P2)
            cr.line_to(*P3)
            cr.line_to(*P4)
            cr.close_path()
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
        font_size = 12 / zoom_transform  # Adjust for zoom and DPI
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(font_size)
        extents = cr.text_extents(text)
        x_text = -extents.width / 2  # Center horizontally
        y_text = -font_size * -1.5   # Offset above
        cr.move_to(x_text, y_text)
        cr.set_source_rgb(0, 0, 0)  # Black text
        cr.show_text(text)
        cr.restore()