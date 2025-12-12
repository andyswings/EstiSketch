import math

def draw_doors(self, cr, pixels_per_inch):
    # Draw doors
    cr.save()
    zoom_transform = self.zoom * pixels_per_inch

    for door_item in self.doors:
        wall, door, ratio = door_item
        A = wall.start
        B = wall.end
        H = (A[0] + ratio * (B[0] - A[0]), A[1] + ratio * (B[1] - A[1])) # Center of door opening
        
        # Wall direction and perpendicular
        dx = B[0] - A[0]
        dy = B[1] - A[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        d = (dx / length, dy / length)
        p = (-d[1], d[0]) # Perpendicular vector to wall direction
        
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

            if door.orientation == "inswing":
                current_normal = p
                offset_vector = (t / 2 * p[0], t / 2 * p[1])
            else:  # "inswing"
                current_normal = (-p[0], -p[1])
                offset_vector = (t / 2 * current_normal[0], t / 2 * current_normal[1])

            if (door.orientation == "inswing" and door.swing == "left") or \
            (door.orientation == "outswing" and door.swing == "right"):
                hinge_base = H_start
            else:
                hinge_base = H_end
            
            if door.orientation == "inswing":
                if door.swing == "left":
                    hinge_wall_direction = d
                else:  # "right"
                    hinge_wall_direction = (-d[0], -d[1])
            else:  # "inswing"
                if door.swing == "left":
                    hinge_wall_direction = (-d[0], -d[1])
                else:  # "right"
                    hinge_wall_direction = d

            hinge = (hinge_base[0] + offset_vector[0], hinge_base[1] + offset_vector[1])

            F = (hinge[0] + w * current_normal[0], hinge[1] + w * current_normal[1])

            # Draw the door leaf line
            cr.set_source_rgb(0, 0, 0) # Black color
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*hinge)
            cr.line_to(*F)
            cr.stroke()

            # Draw the swing arc
            angle_closed = math.atan2(hinge_wall_direction[1], hinge_wall_direction[0])
            # Calculate the angle towards which the door opens (based on current_normal)
            angle_open_direction = math.atan2(current_normal[1], current_normal[0])

            # Calculate the angle difference to determine sweep direction (CW/CCW)
            delta_angle = angle_open_direction - angle_closed
            # Normalize angle difference to the range (-pi, pi]
            while delta_angle <= -math.pi: delta_angle += 2 * math.pi
            while delta_angle > math.pi: delta_angle -= 2 * math.pi

            # Determine the 90-degree sweep angle, preserving the sign for direction
            sweep_angle = math.copysign(math.pi / 2.0, delta_angle)
            angle_open = angle_closed + sweep_angle

            # Set up dashed line style for the arc
            cr.new_path()
            cr.set_dash([4.0 / zoom_transform, 4.0 / zoom_transform])

            # Draw the arc using the correct direction (CW/CCW)
            if sweep_angle > 0: # Positive sweep -> CCW
                cr.arc(hinge[0], hinge[1], w, angle_closed, angle_open)
            else: # Negative sweep -> CW
                cr.arc_negative(hinge[0], hinge[1], w, angle_closed, angle_open)

            cr.stroke() # Render the dashed arc
            cr.set_dash([]) # Reset dash pattern
        
        if door.door_type == "double":
            # Double doors always treated as "left" swing since they open both ways
            # Override n to always use left swing direction
            n_override = (-p[0], -p[1])  # Same as left swing
            
            # Hinge positions for double doors
            hinge1 = (H_start[0] + (t / 2) * n_override[0], H_start[1] + (t / 2) * n_override[1])  # Left hinge
            hinge2 = (H_end[0] + (t / 2) * n_override[0], H_end[1] + (t / 2) * n_override[1])      # Right hinge
            
            # Calculate open leaf positions (90-degree swing from wall)
            w_half = w / 2  # Half width for each leaf
            
            # Determine swing direction based on orientation
            if door.orientation == "outswing":
                swing_normal = n_override
            else:  # "inswing"
                swing_normal = (-n_override[0], -n_override[1])
            
            # Leaf positions based on swing direction
            F1 = (hinge1[0] + w_half * swing_normal[0], hinge1[1] + w_half * swing_normal[1])  # Left leaf
            F2 = (hinge2[0] + w_half * swing_normal[0], hinge2[1] + w_half * swing_normal[1])  # Right leaf
            
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
            angle_closed = math.atan2(d[1], d[0])  # Along wall direction
            
            # Reset the path to avoid connecting lines from leaves to arcs
            cr.new_path()
            
            cr.set_dash([4.0 / zoom_transform, 4.0 / zoom_transform])
            
            if door.orientation == "outswing":
                # Left leaf: 90 degrees counter-clockwise from closed to open (toward n)
                angle_open_left = angle_closed - math.pi / 2
                cr.arc_negative(hinge1[0], hinge1[1], w_half, angle_closed, angle_open_left)
                cr.stroke()
                # Right leaf: 90 degrees clockwise from opposite side to open (toward n)
                angle_open_right = angle_closed - math.pi / 2
                cr.new_path()  # Reset path to avoid connecting arcs
                cr.arc(hinge2[0], hinge2[1], w_half, angle_closed + math.pi, angle_open_right)
                cr.stroke()
            else:  # "outswing"
                # Left leaf: 90 degrees clockwise from closed to open (toward -n)
                angle_open_left = angle_closed + math.pi / 2
                cr.arc(hinge1[0], hinge1[1], w_half, angle_closed, angle_open_left)
                cr.stroke()
                # Right leaf: 90 degrees counter-clockwise from opposite side to open (toward -n)
                angle_open_right = angle_closed + math.pi / 2
                cr.new_path()
                cr.arc_negative(hinge2[0], hinge2[1], w_half, angle_closed + math.pi, angle_open_right)
                cr.stroke()
            
            cr.set_dash([])  # Reset dash pattern
        
        if door.door_type == "frame":
            # Door frame symbol needs nothing special, just draw the opening
            pass
        
        if door.door_type == "sliding":
            T = self.zoom * pixels_per_inch
            
            # Wall endpoints with thickness offset
            wall_start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left edge (outside)
            wall_end = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])      # Right edge (outside)
            wall_inside_start = (H_start[0] - (t / 2) * n[0], H_start[1] - (t / 2) * n[1])  # Left inside
            wall_inside_end = (H_end[0] - (t / 2) * n[0], H_end[1] - (t / 2) * n[1])      # Right inside
            
            # Middle of the wall (centerline between outside and inside edges)
            wall_mid_start = (H_start[0], H_start[1])  # Midpoint at start
            wall_mid_end = (H_end[0], H_end[1])        # Midpoint at end
            
            # Door leaf thickness (one-quarter of wall thickness)
            leaf_thickness = t / 4
            half_thickness = leaf_thickness / 2
            
            # Door leaf width (half of door opening width, assuming they overlap slightly when closed)
            leaf_width = w / 2
            
            # Offset from centerline for each leaf
            offset = half_thickness * 2.1  # Slight separation from centerline for clarity
            
            # Left leaf: Touches left side of opening, offset above centerline
            left_leaf_start = wall_mid_start  # Starts at left edge of opening
            left_leaf_end = (wall_mid_start[0] + leaf_width * d[0], wall_mid_start[1] + leaf_width * d[1])  # Ends halfway across
            left_top_start = (left_leaf_start[0] + offset * n[0], left_leaf_start[1] + offset * n[1])  # Top edge
            left_top_end = (left_leaf_end[0] + offset * n[0], left_leaf_end[1] + offset * n[1])
            left_bottom_start = (left_leaf_start[0] + (offset - leaf_thickness) * n[0], left_leaf_start[1] + (offset - leaf_thickness) * n[1])  # Bottom edge
            left_bottom_end = (left_leaf_end[0] + (offset - leaf_thickness) * n[0], left_leaf_end[1] + (offset - leaf_thickness) * n[1])
            
            # Right leaf: Positioned to show right side open, offset below centerline
            right_leaf_start = (wall_mid_end[0] - leaf_width * d[0], wall_mid_end[1] - leaf_width * d[1])  # Starts halfway, ends at right edge
            right_leaf_end = wall_mid_end  # Ends at right edge of opening
            right_top_start = (right_leaf_start[0] - offset * n[0], right_leaf_start[1] - offset * n[1])  # Top edge
            right_top_end = (right_leaf_end[0] - offset * n[0], right_leaf_end[1] - offset * n[1])
            right_bottom_start = (right_leaf_start[0] - (offset - leaf_thickness) * n[0], right_leaf_start[1] - (offset - leaf_thickness) * n[1])  # Bottom edge
            right_bottom_end = (right_leaf_end[0] - (offset - leaf_thickness) * n[0], right_leaf_end[1] - (offset - leaf_thickness) * n[1])
            
            # Set drawing properties
            cr.set_line_width(1.0 / T)
            
            # Draw solid black outline of door opening
            cr.set_source_rgb(0, 0, 0)  # Black
            cr.move_to(*wall_start)
            cr.line_to(*wall_end)  # Top (outside wall)
            cr.line_to(*wall_inside_end)  # Right side
            cr.line_to(*wall_inside_start)  # Bottom (inside wall)
            cr.line_to(*wall_start)  # Left side
            cr.stroke()
            
            # Draw left leaf (black outline, white fill)
            cr.set_source_rgb(1, 1, 1)  # White fill
            cr.move_to(*left_top_start)
            cr.line_to(*left_top_end)
            cr.line_to(*left_bottom_end)
            cr.line_to(*left_bottom_start)
            cr.close_path()
            cr.fill()
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.move_to(*left_top_start)
            cr.line_to(*left_top_end)
            cr.line_to(*left_bottom_end)
            cr.line_to(*left_bottom_start)
            cr.close_path()
            cr.stroke()
            
            # Draw right leaf (black outline, white fill)
            cr.set_source_rgb(1, 1, 1)  # White fill
            cr.move_to(*right_top_start)
            cr.line_to(*right_top_end)
            cr.line_to(*right_bottom_end)
            cr.line_to(*right_bottom_start)
            cr.close_path()
            cr.fill()
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.move_to(*right_top_start)
            cr.line_to(*right_top_end)
            cr.line_to(*right_bottom_end)
            cr.line_to(*right_bottom_start)
            cr.close_path()
            cr.stroke()
        
        if door.door_type == "pocket":
            # Draw pocket door symbol
            T = self.zoom * pixels_per_inch
            
            # Wall endpoints with thickness offset
            wall_start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left edge (outside)
            wall_end = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])      # Right edge (outside)
            wall_inside_start = (H_start[0] - (t / 2) * n[0], H_start[1] - (t / 2) * n[1])  # Left inside
            wall_inside_end = (H_end[0] - (t / 2) * n[0], H_end[1] - (t / 2) * n[1])      # Right inside
            
            # Door leaf width (one-third of door opening width)
            door_width = w
            # Door leaf thickness (one-third of wall thickness)
            door_thickness = t / 3
            
            # Middle of the wall (centerline between outside and inside edges)
            wall_mid_start = (H_start[0], H_start[1])  # Midpoint at start
            wall_mid_end = (H_end[0], H_end[1])        # Midpoint at end
            
            # Door leaf position (centered in wall thickness, partially protruding into opening)
            if door.swing == "left":
                # Slides left: most of door in left wall, protruding slightly into opening
                door_start = (wall_mid_start[0] - (door_width * 3 / 4) * d[0], wall_mid_start[1] - (door_width * 3 / 4) * d[1])  # 2/3 into wall
                door_end = (wall_mid_start[0] + (door_width / 4) * d[0], wall_mid_start[1] + (door_width / 4) * d[1])  # 1/3 in opening
            else:  # "right"
                # Slides right: most of door in right wall, protruding slightly into opening
                door_start = (wall_mid_end[0] - (door_width / 4) * d[0], wall_mid_end[1] - (door_width / 4) * d[1])  # 1/3 in opening
                door_end = (wall_mid_end[0] + (door_width * 3 / 4) * d[0], wall_mid_end[1] + (door_width * 3 / 4) * d[1])  # 2/3 into wall
            
            # Calculate door leaf rectangle corners (centered in wall thickness)
            # Normal vector n is perpendicular to door direction d, so use it for thickness offset
            half_thickness = door_thickness / 2
            door_top_start = (door_start[0] + half_thickness * n[0], door_start[1] + half_thickness * n[1])  # Top left
            door_top_end = (door_end[0] + half_thickness * n[0], door_end[1] + half_thickness * n[1])      # Top right
            door_bottom_start = (door_start[0] - half_thickness * n[0], door_start[1] - half_thickness * n[1])  # Bottom left
            door_bottom_end = (door_end[0] - half_thickness * n[0], door_end[1] - half_thickness * n[1])      # Bottom right
            
            # Set drawing properties
            cr.set_line_width(1.0 / T)
            
            # Draw solid black outline of door opening
            cr.set_source_rgb(0, 0, 0)  # Black
            cr.move_to(*wall_start)
            cr.line_to(*wall_end)  # Top (outside wall)
            cr.line_to(*wall_inside_end)  # Right side
            cr.line_to(*wall_inside_start)  # Bottom (inside wall)
            cr.line_to(*wall_start)  # Left side
            cr.stroke()
            
            # Draw door leaf as a rectangle (black outline, white fill)
            # Fill with white first
            cr.set_source_rgb(1, 1, 1)  # White
            cr.move_to(*door_top_start)
            cr.line_to(*door_top_end)
            cr.line_to(*door_bottom_end)
            cr.line_to(*door_bottom_start)
            cr.close_path()
            cr.fill()
            
            # Draw black outline
            cr.set_source_rgb(0, 0, 0)  # Black
            cr.move_to(*door_top_start)
            cr.line_to(*door_top_end)
            cr.line_to(*door_bottom_end)
            cr.line_to(*door_bottom_start)
            cr.close_path()
            cr.stroke()
    
        if door.door_type == "bi-fold":
            if door.orientation == "outswing":
                current_normal = p
                offset_vector = (p[0], p[1])
            else:  # "inswing"
                current_normal = (-p[0], -p[1])
                offset_vector = (current_normal[0], current_normal[1])

            if (door.orientation == "outswing" and door.swing == "left") or \
            (door.orientation == "inswing" and door.swing == "right"):
                hinge_base = H_start
            else:
                hinge_base = H_end
            
            if door.orientation == "outswing":
                if door.swing == "left":
                    hinge_wall_direction = d
                else:  # "right"
                    hinge_wall_direction = (-d[0], -d[1])
            else:  # "inswing"
                if door.swing == "left":
                    hinge_wall_direction = (-d[0], -d[1])
                else:  # "right"
                    hinge_wall_direction = d

            hinge = (hinge_base[0] + offset_vector[0], hinge_base[1] + offset_vector[1])

            F = (hinge[0] + w * current_normal[0], hinge[1] + w * current_normal[1])
            
            # Each panel is half the total door width.
            w_half = w / 2

            # Compute the door center (already defined as H)
            # and then compute the base angle from the pivot to H.
            base_angle = math.atan2(H[1] - hinge[1], H[0] - hinge[0])
            angle_60 = math.pi / 3  # 60° in radians

            # For the door leaf panels, adjust the base angle by 60°:
            # For a left-swing door, subtract 60°; for a right-swing door, add 60°.
            if door.swing == "left":
                angle1 = base_angle - angle_60  # first panel rotates -60° from the inward direction
                angle2 = angle1 + 2 * angle_60    # second panel folds +120° relative to the first
            else:
                angle1 = base_angle + angle_60  # first panel rotates +60° from the inward direction
                angle2 = angle1 - 2 * angle_60    # second panel folds -120° relative to the first

            # Compute endpoints for the panels relative to the pivot.
            end1 = (hinge[0] + w_half * math.cos(angle1),
                    hinge[1] + w_half * math.sin(angle1))
            end2 = (end1[0] + w_half * math.cos(angle2),
                    end1[1] + w_half * math.sin(angle2))

            # Draw the door leaf.
            cr.set_source_rgb(0, 0, 0)           # Black lines.
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*hinge)
            cr.line_to(*end1)
            cr.line_to(*end2)
            cr.stroke()

            
        if door.door_type == "double bi-fold":
            
            if door.orientation == "outswing":
                n = (-p[0], -p[1])
            else:  # "inswing"
                n = (p[0], p[1])
            
            # Each panel is one-quarter of the total width
            w_quarter = w / 4  

            # Hinge points for the left and right sides (using the overridden n)
            hinge_start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left hinge
            hinge_end   = (H_end[0]   + (t / 2) * n[0], H_end[1]   + (t / 2) * n[1])  # Right hinge

            # Define the basic angles
            angle_60 = math.pi / 3             # 60° in radians
            angle_closed = math.atan2(d[1], d[0])  # Door closed is along the wall direction

            # Set drawing properties
            cr.set_source_rgb(0, 0, 0)           # Black lines
            cr.set_line_width(1.0 / zoom_transform)

            # --- Left Leaf Geometry ---
            # For "outswing": left leaf rotates -60° from the closed angle.
            # For "inswing": mimic the right inswing by rotating +60°.
            if door.orientation == "outswing":
                angle_left1 = angle_closed - angle_60          # 60° counter-clockwise from closed position
                angle_left2 = angle_left1 + 2 * angle_60           # Second panel folds 120° clockwise
            else:  # "inswing"
                angle_left1 = angle_closed + angle_60           # 60° clockwise from closed position
                angle_left2 = angle_left1 - 2 * angle_60           # Second panel folds 120° counter-clockwise

            left1_end = (hinge_start[0] + w_quarter * math.cos(angle_left1),
                        hinge_start[1] + w_quarter * math.sin(angle_left1))
            left2_end = (left1_end[0] + w_quarter * math.cos(angle_left2),
                        left1_end[1] + w_quarter * math.sin(angle_left2))

            # --- Right Leaf Geometry ---
            # For "outswing": mirror the left leaf by starting with a π offset and adding 60°.
            # For "inswing": use the right inswing geometry: π offset then subtract 60°.
            if door.orientation == "outswing":
                angle_right1 = angle_closed + math.pi + angle_60   # π offset then add 60°
                angle_right2 = angle_right1 - 2 * angle_60            # Second panel folds 120° counter-clockwise
            else:  # "inswing"
                angle_right1 = angle_closed + math.pi - angle_60   # π offset then subtract 60°
                angle_right2 = angle_right1 + 2 * angle_60            # Second panel folds 120° clockwise

            right1_end = (hinge_end[0] + w_quarter * math.cos(angle_right1),
                        hinge_end[1] + w_quarter * math.sin(angle_right1))
            right2_end = (right1_end[0] + w_quarter * math.cos(angle_right2),
                        right1_end[1] + w_quarter * math.sin(angle_right2))

            # Draw the left leaf: hinge_start -> left1_end -> left2_end
            cr.move_to(*hinge_start)
            cr.line_to(*left1_end)
            cr.line_to(*left2_end)
            cr.stroke()

            # Draw the right leaf: hinge_end -> right1_end -> right2_end
            cr.move_to(*hinge_end)
            cr.line_to(*right1_end)
            cr.line_to(*right2_end)
            cr.stroke()

        
        if door.door_type == "garage":
            # Draw garage door symbol
            T = self.zoom * pixels_per_inch
            
            # Door endpoints with thickness offset (outside of wall)
            start = (H_start[0] + (t / 2) * n[0], H_start[1] + (t / 2) * n[1])  # Left edge
            end = (H_end[0] + (t / 2) * n[0], H_end[1] + (t / 2) * n[1])      # Right edge
            
            # Inside wall endpoints (opposite side of wall thickness)
            inside_start = (H_start[0] - (t / 2) * n[0], H_start[1] - (t / 2) * n[1])  # Left inside
            inside_end = (H_end[0] - (t / 2) * n[0], H_end[1] - (t / 2) * n[1])      # Right inside
            
            depth = door.height  # Extend inward by the door's height
            
            # Endpoints of the inner dashed rectangle (extending inside the garage)
            inner_left = (inside_start[0] - depth * n[0], inside_start[1] - depth * n[1])
            inner_right = (inside_end[0] - depth * n[0], inside_end[1] - depth * n[1])
            
            # Set drawing properties
            cr.set_source_rgb(0, 0, 0)  # Black lines
            cr.set_line_width(1.0 / T)
            
            # Draw outer box (solid lines)
            cr.move_to(*start)
            cr.line_to(*end)  # Top (outside wall)
            cr.line_to(*inside_end)  # Right side
            cr.line_to(*inside_start)  # Bottom (inside wall)
            cr.line_to(*start)  # Left side
            cr.stroke()
            
            # Draw inner dashed line on inside of wall
            cr.set_dash([4.0 / T, 4.0 / T])  # Dashed pattern
            cr.move_to(*inside_start)
            cr.line_to(*inside_end)
            cr.stroke()
            
            # Draw dashed rectangle extending inside
            cr.move_to(*inside_start)
            cr.line_to(*inner_left)  # Left side inward
            cr.line_to(*inner_right)  # Bottom inside
            cr.line_to(*inside_end)  # Right side inward
            cr.stroke()
            
            cr.set_dash([])  # Reset dash pattern

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
            
            # Wall endpoints with thickness offset
            wall_start = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])  # Left edge (outside)
            wall_end = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])      # Right edge (outside)
            wall_inside_start = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])  # Left inside
            wall_inside_end = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])      # Right inside
            
            # Middle of the wall (centerline between outside and inside edges)
            wall_mid_start = (H_start[0], H_start[1])  # Midpoint at start
            wall_mid_end = (H_end[0], H_end[1])        # Midpoint at end
            
            # Window pane thickness (one-quarter of wall thickness)
            pane_thickness = t / 8
            half_thickness = pane_thickness / 2
            
            # Window pane width (half of door opening width, assuming they overlap slightly when closed)
            pane_width = w / 2
            
            # Offset from centerline for each pane
            offset = half_thickness * 2.1  # Slight separation from centerline for clarity
            
            # Left pane: Touches left side of opening, offset above centerline
            left_pane_start = wall_mid_start  # Starts at left edge of opening
            left_pane_end = (wall_mid_start[0] + pane_width * d[0], wall_mid_start[1] + pane_width * d[1])  # Ends halfway across
            left_top_start = (left_pane_start[0] + offset * p[0], left_pane_start[1] + offset * p[1])  # Top edge
            left_top_end = (left_pane_end[0] + offset * p[0], left_pane_end[1] + offset * p[1])
            left_bottom_start = (left_pane_start[0] + (offset - pane_thickness) * p[0], left_pane_start[1] + (offset - pane_thickness) * p[1])  # Bottom edge
            left_bottom_end = (left_pane_end[0] + (offset - pane_thickness) * p[0], left_pane_end[1] + (offset - pane_thickness) * p[1])
            
            # Right pane: Positioned to show right side open, offset below centerline
            right_pane_start = (wall_mid_end[0] - pane_width * d[0], wall_mid_end[1] - pane_width * d[1])  # Starts halfway, ends at right edge
            right_pane_end = wall_mid_end  # Ends at right edge of opening
            right_top_start = (right_pane_start[0] - offset * p[0], right_pane_start[1] - offset * p[1])  # Top edge
            right_top_end = (right_pane_end[0] - offset * p[0], right_pane_end[1] - offset * p[1])
            right_bottom_start = (right_pane_start[0] - (offset - pane_thickness) * p[0], right_pane_start[1] - (offset - pane_thickness) * p[1])  # Bottom edge
            right_bottom_end = (right_pane_end[0] - (offset - pane_thickness) * p[0], right_pane_end[1] - (offset - pane_thickness) * p[1])
            
            # Set drawing properties
            cr.set_line_width(1.0 / zoom_transform)
            
            # Draw solid black outline of window opening
            cr.set_source_rgb(0, 0, 0)  # Black
            cr.move_to(*wall_start)
            cr.line_to(*wall_end)  # Top (outside wall)
            cr.line_to(*wall_inside_end)  # Right side
            cr.line_to(*wall_inside_start)  # Bottom (inside wall)
            cr.line_to(*wall_start)  # Left side
            cr.stroke()
            
            # Draw left pane (black outline, white fill)
            cr.set_source_rgb(1, 1, 1)  # White fill
            cr.move_to(*left_top_start)
            cr.line_to(*left_top_end)
            cr.line_to(*left_bottom_end)
            cr.line_to(*left_bottom_start)
            cr.close_path()
            cr.fill()
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.move_to(*left_top_start)
            cr.line_to(*left_top_end)
            cr.line_to(*left_bottom_end)
            cr.line_to(*left_bottom_start)
            cr.close_path()
            cr.stroke()
            
            # Draw right pane (black outline, white fill)
            cr.set_source_rgb(1, 1, 1)  # White fill
            cr.move_to(*right_top_start)
            cr.line_to(*right_top_end)
            cr.line_to(*right_bottom_end)
            cr.line_to(*right_bottom_start)
            cr.close_path()
            cr.fill()
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.move_to(*right_top_start)
            cr.line_to(*right_top_end)
            cr.line_to(*right_bottom_end)
            cr.line_to(*right_bottom_start)
            cr.close_path()
            cr.stroke()
        
        if window.window_type == "double-hung":
            # Wall endpoints with thickness offset
            wall_start = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])  # Left edge (outside)
            wall_end = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])      # Right edge (outside)
            wall_inside_start = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])  # Left inside
            wall_inside_end = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])      # Right inside
            
            # Middle of the wall (centerline between outside and inside edges)
            wall_mid_start = (H_start[0], H_start[1])  # Midpoint at start
            wall_mid_end = (H_end[0], H_end[1])        # Midpoint at end
            
            # Draw a single rectangle outline for fixed window
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*P1)
            cr.line_to(*P2)
            cr.line_to(*P3)
            cr.line_to(*P4)
            cr.close_path()
            cr.stroke()
            
            # Draw solid black line for window pane
            cr.move_to(*wall_mid_start)
            cr.line_to(*wall_mid_end)
            cr.stroke()
            
            # Compute a unit vector along the window's width (from H_start to H_end)
            dx = H_end[0] - H_start[0]
            dy = H_end[1] - H_start[1]
            length = math.sqrt(dx*dx + dy*dy)
            v = (dx / length, dy / length)
            
            # Define the extension distance (in the same units as your drawing)
            extension = 1.0  # one inch
            
            # Compute the base of the extension rectangle:
            # Extend the window's outside edge by one inch on each side
            rect_left_start = (wall_start[0] - extension * v[0], wall_start[1] - extension * v[1])
            rect_right_start = (wall_end[0] + extension * v[0], wall_end[1] + extension * v[1])
            
            # Now, push that line outward by one inch (using the outward vector p)
            rect_left_outer = (rect_left_start[0] + extension * p[0], rect_left_start[1] + extension * p[1])
            rect_right_outer = (rect_right_start[0] + extension * p[0], rect_right_start[1] + extension * p[1])
            
            # Draw the extension rectangle outline
            cr.set_source_rgb(0, 0, 0)  # Black outline (or choose a different color/style if desired)
            cr.move_to(*rect_left_start)
            cr.line_to(*rect_right_start)
            cr.line_to(*rect_right_outer)
            cr.line_to(*rect_left_outer)
            cr.close_path()
            cr.stroke()

        if window.window_type == "fixed":
            # Wall endpoints with thickness offset
            wall_start = (H_start[0] + (t / 2) * p[0], H_start[1] + (t / 2) * p[1])  # Left edge (outside)
            wall_end = (H_end[0] + (t / 2) * p[0], H_end[1] + (t / 2) * p[1])      # Right edge (outside)
            wall_inside_start = (H_start[0] - (t / 2) * p[0], H_start[1] - (t / 2) * p[1])  # Left inside
            wall_inside_end = (H_end[0] - (t / 2) * p[0], H_end[1] - (t / 2) * p[1])      # Right inside
            
            # Middle of the wall (centerline between outside and inside edges)
            wall_mid_start = (H_start[0], H_start[1])  # Midpoint at start
            wall_mid_end = (H_end[0], H_end[1])        # Midpoint at end
            
            # Draw a single rectangle outline for fixed window
            cr.set_source_rgb(0, 0, 0)  # Black outline
            cr.set_line_width(1.0 / zoom_transform)
            cr.move_to(*P1)
            cr.line_to(*P2)
            cr.line_to(*P3)
            cr.line_to(*P4)
            cr.close_path()
            cr.stroke()
            
            # Draw solid black line for window pane
            cr.move_to(*wall_mid_start)
            cr.line_to(*wall_mid_end)
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