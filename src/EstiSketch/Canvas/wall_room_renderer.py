
def draw_walls(self, cr):
    cr.set_line_join(0)  # 0 = miter join.
    cr.set_line_cap(0)  # 0 = butt cap.
    cr.set_miter_limit(10.0)

    # Helper to check visibility
    def is_visible(obj):
        if hasattr(self, 'is_object_on_visible_layer'):
            return self.is_object_on_visible_layer(obj)
        return True

    def get_opacity(obj):
        if hasattr(self, 'get_object_opacity'):
            return self.get_object_opacity(obj)
        return 1.0

    # Draw wall sets (connected components)
    for wall_set in self.wall_sets:
        if not wall_set:
            continue

        # Process the wall set
        path_active = False
        path_start_point = None
        current_width_user = -1.0
        current_opacity = -1.0

        for i, wall in enumerate(wall_set):
            # Skip symbolic walls - they only render footers, not the wall itself
            if getattr(wall, 'symbolic', False):
                if path_active:
                    cur_pt = cr.get_current_point()
                    if path_start_point and \
                       abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
                       abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                        cr.close_path()
                    cr.stroke()
                    path_active = False
                continue

            if not is_visible(wall):
                if path_active:
                    cur_pt = cr.get_current_point()
                    if path_start_point and \
                       abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
                       abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                        cr.close_path()
                    cr.stroke()
                    path_active = False
                continue

            width_user = wall.width
            opacity = get_opacity(wall)

            should_start_new = True
            if path_active:
                # Check connectivity and property matching
                prev_wall = wall_set[i - 1]
                connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and
                             abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
                if (connected and
                    abs(width_user - current_width_user) < 1e-6 and
                        abs(opacity - current_opacity) < 1e-6):
                    should_start_new = False

            if should_start_new:
                if path_active:
                    cur_pt = cr.get_current_point()
                    if path_start_point and \
                       abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
                       abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                        cr.close_path()
                    cr.stroke()

                current_width_user = width_user
                current_opacity = opacity
                cr.set_line_width(current_width_user)
                cr.set_source_rgba(0, 0, 0, current_opacity)
                cr.move_to(wall.start[0], wall.start[1])
                path_start_point = wall.start
                
                # Draw first wall segment (could be straight or curved)
                if wall.is_curved and wall.arc_center and wall.arc_radius:
                    # Draw curved wall as an arc
                    import math
                    cx, cy = wall.arc_center
                    radius = wall.arc_radius
                    
                    # Calculate angles for start and end points
                    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
                    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
                    
                    # Determine arc direction
                    angle_diff = end_angle - start_angle
                    # Normalize to -2π to 2π range
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    # Draw the arc
                    if angle_diff < 0:
                        cr.arc_negative(cx, cy, radius, start_angle, end_angle)
                    else:
                        cr.arc(cx, cy, radius, start_angle, end_angle)
                else:
                    # Draw straight wall
                    cr.line_to(wall.end[0], wall.end[1])
                    
                path_active = True
            else:
                # Draw wall segment (straight or curved)
                if wall.is_curved and wall.arc_center and wall.arc_radius:
                    # Draw curved wall as an arc
                    import math
                    cx, cy = wall.arc_center
                    radius = wall.arc_radius
                    
                    # Calculate angles for start and end points
                    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
                    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
                    
                    # Determine arc direction
                    angle_diff = end_angle - start_angle
                    # Normalize to -2π to 2π range
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    # Draw the arc with proper width
                    if angle_diff < 0:
                        cr.arc_negative(cx, cy, radius, start_angle, end_angle)
                    else:
                        cr.arc(cx, cy, radius, start_angle, end_angle)
                else:
                    # Draw straight wall  
                    cr.line_to(wall.end[0], wall.end[1])

        if path_active:
            cur_pt = cr.get_current_point()
            if path_start_point and \
               abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
               abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                cr.close_path()
            cr.stroke()

    # Draw active drawing chain
    active_chain = []
    if self.walls:
        active_chain.extend(self.walls)
    if self.current_wall:
        active_chain.append(self.current_wall)

    if active_chain:
        path_active = False
        path_start_point = None
        current_width_user = -1.0
        current_opacity = -1.0

        for i, wall in enumerate(active_chain):
            if not is_visible(wall):
                if path_active:
                    cur_pt = cr.get_current_point()
                    if path_start_point and \
                       abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
                       abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                        cr.close_path()
                    cr.stroke()
                    path_active = False
                continue

            width_user = wall.width
            opacity = get_opacity(wall)

            should_start_new = True
            if path_active:
                prev_wall = active_chain[i - 1]
                connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and
                             abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
                if (connected and
                    abs(width_user - current_width_user) < 1e-6 and
                        abs(opacity - current_opacity) < 1e-6):
                    should_start_new = False

            if should_start_new:
                if path_active:
                    cur_pt = cr.get_current_point()
                    if path_start_point and \
                       abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
                       abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                        cr.close_path()
                    cr.stroke()
                current_width_user = width_user
                current_opacity = opacity
                cr.set_line_width(current_width_user)
                cr.set_source_rgba(0, 0, 0, current_opacity)
                cr.move_to(wall.start[0], wall.start[1])
                path_start_point = wall.start
                
                # Draw first wall segment (could be straight or curved)
                if wall.is_curved and wall.arc_center and wall.arc_radius:
                    import math
                    cx, cy = wall.arc_center
                    radius = wall.arc_radius
                    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
                    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
                    
                    angle_diff = end_angle - start_angle
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    if angle_diff < 0:
                        cr.arc_negative(cx, cy, radius, start_angle, end_angle)
                    else:
                        cr.arc(cx, cy, radius, start_angle, end_angle)
                else:
                    cr.line_to(wall.end[0], wall.end[1])
                    
                path_active = True
            else:
                # Draw wall segment (straight or curved)
                if wall.is_curved and wall.arc_center and wall.arc_radius:
                    # Draw curved wall as an arc
                    import math
                    cx, cy = wall.arc_center
                    radius = wall.arc_radius
                    
                    # Calculate angles for start and end points
                    start_angle = math.atan2(wall.start[1] - cy, wall.start[0] - cx)
                    end_angle = math.atan2(wall.end[1] - cy, wall.end[0] - cx)
                    
                    # Determine arc direction
                    angle_diff = end_angle - start_angle
                    # Normalize to -2π to 2π range
                    while angle_diff > math.pi:
                        angle_diff -= 2 * math.pi
                    while angle_diff < -math.pi:
                        angle_diff += 2 * math.pi
                    
                    # Draw the arc with proper width
                    if angle_diff < 0:
                        cr.arc_negative(cx, cy, radius, start_angle, end_angle)
                    else:
                        cr.arc(cx, cy, radius, start_angle, end_angle)
                else:
                    # Draw straight wall
                    cr.line_to(wall.end[0], wall.end[1])

        if path_active:
            cur_pt = cr.get_current_point()
            if path_start_point and \
               abs(cur_pt[0] - path_start_point[0]) < 1e-4 and \
               abs(cur_pt[1] - path_start_point[1]) < 1e-4:
                cr.close_path()
            cr.stroke()

    # Draw curved wall preview if in curve mode
    if (hasattr(self, 'wall_curve_mode') and self.wall_curve_mode and 
        hasattr(self, 'wall_curve_point') and self.wall_curve_point and 
        hasattr(self, 'walls') and self.walls):
        
        last_wall = self.walls[-1]
        bulge_point = self.wall_curve_point
        
        # Calculate arc from 3 points
        geom = self.get_circle_from_3_points(
            last_wall.start, last_wall.end, bulge_point
        )
        
        if geom:
            import math
            (cx, cy), radius = geom
            
            # Draw preview arc in blue
            cr.save()
            cr.set_source_rgba(0, 0, 1, 0.6)  # Blue preview
            cr.set_line_width(self.config.DEFAULT_WALL_WIDTH)
            
            start_angle = math.atan2(last_wall.start[1] - cy, last_wall.start[0] - cx)
            end_angle = math.atan2(last_wall.end[1] - cy, last_wall.end[0] - cx)
            mid_angle = math.atan2(bulge_point[1] - cy, bulge_point[0] - cx)
            
            # Determine direction using the middle point
            a_mid_rel = (mid_angle - start_angle) % (2 * math.pi)
            a_end_rel = (end_angle - start_angle) % (2 * math.pi)
            
            cr.new_path()
            if a_mid_rel < a_end_rel:
                cr.arc(cx, cy, radius, start_angle, end_angle)
            else:
                cr.arc_negative(cx, cy, radius, start_angle, end_angle)
            cr.stroke()
            
            # Draw radius label near cursor (bulge point)
            if hasattr(self, 'converter'):
                pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
                radius_str = self.converter.format_measurement(radius, use_fraction=False)
                
                # Position label near the bulge point (cursor), offset slightly
                offset = 10 / (self.zoom * pixels_per_inch)
                label_x = bulge_point[0] + offset
                label_y = bulge_point[1] - offset
                
                cr.set_source_rgba(0, 0, 1, 0.8)
                cr.select_font_face("Sans", 0, 1)  # Bold
                cr.set_font_size(14 / (self.zoom * pixels_per_inch))
                
                text = f"R: {radius_str}"
                extents = cr.text_extents(text)
                
                # Draw background rectangle for better visibility
                padding = 2 / (self.zoom * pixels_per_inch)
                cr.set_source_rgba(1, 1, 1, 0.9)  # White background
                cr.rectangle(
                    label_x - padding,
                    label_y - extents.height - padding,
                    extents.width + 2 * padding,
                    extents.height + 2 * padding
                )
                cr.fill()
                
                # Draw text
                cr.set_source_rgba(0, 0, 1, 1.0)  # Blue text
                cr.move_to(label_x, label_y)
                cr.show_text(text)
            
            cr.restore()

    draw_sloped_wall_indicators(self, cr)


def draw_sloped_wall_indicators(self, cr):
    """Draw slope direction arrows and height labels for sloped/variable height walls."""
    import math

    pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
    zoom_transform = self.zoom * pixels_per_inch

    all_walls = []
    for wall_set in getattr(self, 'wall_sets', []):
        all_walls.extend(wall_set)
    all_walls.extend(getattr(self, 'walls', []))

    for wall in all_walls:
        if not getattr(wall, 'is_sloped', False):
            continue

        start_h = float(wall.height)
        end_h = float(getattr(wall, 'height_at_end', start_h))
        if abs(start_h - end_h) < 0.01:
            continue

        p_start = wall.start
        p_end = wall.end
        dx = p_end[0] - p_start[0]
        dy = p_end[1] - p_start[1]
        length = math.hypot(dx, dy)
        if length < 1e-4:
            continue

        # Unit vector along wall
        ux = dx / length
        uy = dy / length

        # Center point
        mid_x = (p_start[0] + p_end[0]) / 2.0
        mid_y = (p_start[1] + p_end[1]) / 2.0

        # Normal vector for offsetting label
        nx = -uy
        ny = ux

        cr.save()

        # Format label text
        if hasattr(self, 'converter'):
            s_str = self.converter.format_measurement(start_h, use_fraction=False)
            e_str = self.converter.format_measurement(end_h, use_fraction=False)
        else:
            s_str = f"{start_h:.0f}\""
            e_str = f"{end_h:.0f}\""

        label_text = f"{s_str} ↗ {e_str}"

        # Uphill direction vector
        if end_h > start_h:
            dir_x, dir_y = ux, uy
        else:
            dir_x, dir_y = -ux, -uy

        # Draw slope arrow along centerline
        arrow_len = min(24.0, length * 0.3)
        a_start_x = mid_x - dir_x * (arrow_len / 2.0)
        a_start_y = mid_y - dir_y * (arrow_len / 2.0)
        a_end_x = mid_x + dir_x * (arrow_len / 2.0)
        a_end_y = mid_y + dir_y * (arrow_len / 2.0)

        cr.set_source_rgba(0.1, 0.4, 0.8, 0.9)
        cr.set_line_width(2.0 / zoom_transform)

        cr.move_to(a_start_x, a_start_y)
        cr.line_to(a_end_x, a_end_y)
        cr.stroke()

        # Arrowhead
        head_size = 6.0 / zoom_transform
        angle = math.atan2(dir_y, dir_x)
        left_head_x = a_end_x - head_size * math.cos(angle - math.pi / 6)
        left_head_y = a_end_y - head_size * math.sin(angle - math.pi / 6)
        right_head_x = a_end_x - head_size * math.cos(angle + math.pi / 6)
        right_head_y = a_end_y - head_size * math.sin(angle + math.pi / 6)

        cr.move_to(a_end_x, a_end_y)
        cr.line_to(left_head_x, left_head_y)
        cr.line_to(right_head_x, right_head_y)
        cr.close_path()
        cr.fill()

        # Draw text label parallel to wall, slightly offset from wall centerline
        offset_dist = (wall.width / 2.0 + 8.0)
        text_x = mid_x + nx * offset_dist
        text_y = mid_y + ny * offset_dist

        # Compute wall alignment angle (keep right-side up)
        wall_angle = math.atan2(dy, dx)
        if wall_angle > math.pi / 2 or wall_angle < -math.pi / 2:
            wall_angle += math.pi

        cr.save()
        cr.translate(text_x, text_y)
        cr.rotate(wall_angle)

        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(11.0 / zoom_transform)
        extents = cr.text_extents(label_text)

        pad = 3.0 / zoom_transform
        rect_x = -extents.width / 2.0 - pad
        rect_y = -extents.height / 2.0 - pad
        rect_w = extents.width + 2 * pad
        rect_h = extents.height + 2 * pad

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
        cr.rectangle(rect_x, rect_y, rect_w, rect_h)
        cr.fill()

        cr.set_source_rgba(0.1, 0.4, 0.8, 1.0)
        cr.move_to(-extents.width / 2.0, extents.height / 2.0)
        cr.show_text(label_text)
        cr.restore()

        cr.restore()


def draw_rooms(self, cr, zoom_transform):
    cr.set_line_width(1.0 / zoom_transform)

    def is_visible(obj):
        if hasattr(self, 'is_object_on_visible_layer'):
            return self.is_object_on_visible_layer(obj)
        return True

    def get_opacity(obj):
        if hasattr(self, 'get_object_opacity'):
            return self.get_object_opacity(obj)
        return 1.0

    for room in self.rooms:
        if not is_visible(room):
            continue

        opacity = get_opacity(room)

        if room.points:
            cr.save()
            cr.move_to(room.points[0][0], room.points[0][1])
            for pt in room.points[1:]:
                cr.line_to(pt[0], pt[1])
            cr.close_path()

            # Check if this is a slab - use different fill style
            if getattr(room, 'is_slab', False):
                # Gray fill for concrete slab
                cr.set_source_rgba(0.85, 0.85, 0.85, opacity)
            else:
                # Light blue fill for regular rooms
                cr.set_source_rgba(0.9, 0.9, 1, opacity)
            cr.fill_preserve()

            cr.set_source_rgba(0, 0, 0, opacity)
            cr.stroke()
            
            # Draw hatching pattern for slabs
            if getattr(room, 'is_slab', False) and room.points:
                cr.save()
                # Create clipping path from room polygon
                cr.move_to(room.points[0][0], room.points[0][1])
                for pt in room.points[1:]:
                    cr.line_to(pt[0], pt[1])
                cr.close_path()
                cr.clip()
                
                # Calculate bounding box
                min_x = min(p[0] for p in room.points)
                max_x = max(p[0] for p in room.points)
                min_y = min(p[1] for p in room.points)
                max_y = max(p[1] for p in room.points)
                
                # Draw diagonal hatching lines
                cr.set_source_rgba(0.6, 0.6, 0.6, opacity * 0.5)
                cr.set_line_width(0.5 / zoom_transform)
                spacing = 12  # inches between hatch lines
                
                # Diagonal lines from bottom-left to top-right
                start_offset = int(min_x + min_y - max_y - spacing)
                end_offset = int(max_x + max_y - min_y + spacing)
                for offset in range(start_offset, end_offset, int(spacing)):
                    cr.move_to(offset, min_y - spacing)
                    cr.line_to(offset + (max_y - min_y) + 2 * spacing, max_y + spacing)
                cr.stroke()
                cr.restore()
            
            cr.restore()

    if self.tool_mode == "draw_rooms" and self.current_room_points:
        active_opacity = 1.0
        if hasattr(
                self,
                'active_layer_id') and hasattr(
                self,
                'get_layer_by_id'):
            active_layer = self.get_layer_by_id(self.active_layer_id)
            if active_layer:
                active_opacity = active_layer.opacity

        cr.save()
        cr.set_source_rgba(0, 0, 1, active_opacity)
        cr.set_line_width(2.0 / zoom_transform)
        cr.move_to(
            self.current_room_points[0][0],
            self.current_room_points[0][1])
        for pt in self.current_room_points[1:]:
            cr.line_to(pt[0], pt[1])
        if self.current_room_preview:
            cr.line_to(
                self.current_room_preview[0],
                self.current_room_preview[1])
        cr.stroke()
        cr.restore()


def draw_footers(self, cr):
    import math

    if not self.wall_sets:
        return

    # Helper: Normalize vector
    def normalize(v):
        l = math.hypot(v[0], v[1])
        if l == 0: return (0, 0)
        return (v[0] / l, v[1] / l)

    # Helper: Line intersection: P1 + t*V1 = P2 + u*V2
    def intersect(p1, v1, p2, v2):
        # cross product 2d
        det = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(det) < 1e-9:
            return None # Parallel
        
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        
        u = (dx * v1[1] - dy * v1[0]) / det
        # t = (dx * v2[1] - dy * v2[0]) / det # not needed unless checking bounds
        
        # Intersection point
        return (p2[0] + u * v2[0], p2[1] + u * v2[1])

    # 1. Build adjacency graph for walls with footers
    adjacency = {} # (x, y) -> list of walls
    
    footer_walls = []
    for wall_set in self.wall_sets:
        for wall in wall_set:
            if getattr(wall, 'footer', False):
                footer_walls.append(wall)
                # Register endpoints
                # Rounding to handle float precision issues
                s = (round(wall.start[0], 4), round(wall.start[1], 4))
                e = (round(wall.end[0], 4), round(wall.end[1], 4))
                
                if s not in adjacency: adjacency[s] = []
                adjacency[s].append(wall)
                if e not in adjacency: adjacency[e] = []
                adjacency[e].append(wall)

    # Setup drawing style
    pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
    zoom_transform = self.zoom * pixels_per_inch
    
    cr.save()
    # Earthy brown
    cr.set_source_rgba(0.5, 0.4, 0.3, 0.8)
    cr.set_line_width(2.0 / zoom_transform) # consistent thin line
    
    # Dashed line
    dash_len = 6.0 / zoom_transform
    cr.set_dash([dash_len, dash_len * 0.5])

    for wall in footer_walls:
        # Calculate wall direction and normal
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        length = math.hypot(dx, dy)
        if length < 1e-6: continue
        
        dir_v = (dx / length, dy / length)
        # Normal vector (Left side relative to wall direction)
        
        perp_L = (dir_v[1], -dir_v[0]) 
        perp_R = (-dir_v[1], dir_v[0])

        w_l = wall.footer_left_offset
        w_r = wall.footer_right_offset
        
        # Base Points
        p_start = wall.start
        p_end = wall.end
        
        # Start corners default (just offset)
        start_L = (p_start[0] + perp_L[0] * w_l, p_start[1] + perp_L[1] * w_l)
        start_R = (p_start[0] + perp_R[0] * w_r, p_start[1] + perp_R[1] * w_r)
        
        # End corners default
        end_L = (p_end[0] + perp_L[0] * w_l, p_end[1] + perp_L[1] * w_l)
        end_R = (p_end[0] + perp_R[0] * w_r, p_end[1] + perp_R[1] * w_r)
        
        # --- Handle Start Junction ---
        s_key = (round(wall.start[0], 4), round(wall.start[1], 4))
        neighbors = [w for w in adjacency.get(s_key, []) if w is not wall]
        
        if not neighbors:
             # Free End: Extend backwards
             ext = max(w_l, w_r)
             start_L = (start_L[0] - dir_v[0] * ext, start_L[1] - dir_v[1] * ext)
             start_R = (start_R[0] - dir_v[0] * ext, start_R[1] - dir_v[1] * ext)
        else:
            other = neighbors[0]
            
            o_dx = other.end[0] - other.start[0]
            o_dy = other.end[1] - other.start[1]
            o_len = math.hypot(o_dx, o_dy)
            o_dir = (o_dx/o_len, o_dy/o_len) if o_len > 0 else (0,0)
            o_perp_L = (o_dir[1], -o_dir[0])
            o_perp_R = (-o_dir[1], o_dir[0])
            o_wl = other.footer_left_offset
            o_wr = other.footer_right_offset

            # Connectivity Check
            s_key_val = (round(wall.start[0], 4), round(wall.start[1], 4))
            other_at_start = (s_key_val == (round(other.start[0], 4), round(other.start[1], 4)))
            start_connection = (round(other.end[0], 4) == round(wall.start[0], 4))
            
            if start_connection:
                # Other -> Wall
                o_p_start = (other.start[0] + o_perp_L[0] * o_wl, other.start[1] + o_perp_L[1] * o_wl)
                pt_L = intersect(start_L, dir_v, o_p_start, o_dir)
                if pt_L: start_L = pt_L
                
                o_p_start_R = (other.start[0] + o_perp_R[0] * o_wr, other.start[1] + o_perp_R[1] * o_wr)
                pt_R = intersect(start_R, dir_v, o_p_start_R, o_dir)
                if pt_R: start_R = pt_R
                
            elif other_at_start:
                 # Start->Start
                 # Flip logic: Match Left with Other.Right
                 o_p_start_R = (other.start[0] + o_perp_R[0] * o_wr, other.start[1] + o_perp_R[1] * o_wr)
                 pt_L = intersect(start_L, dir_v, o_p_start_R, o_dir)
                 if pt_L: start_L = pt_L

                 o_p_start_L = (other.start[0] + o_perp_L[0] * o_wl, other.start[1] + o_perp_L[1] * o_wl)
                 pt_R = intersect(start_R, dir_v, o_p_start_L, o_dir)
                 if pt_R: start_R = pt_R
            else:
                 # End->Start but not matched? (Float issue?). Already covered by start_connection check.
                 # Fallback
                 ext = max(w_l, w_r)
                 start_L = (start_L[0] - dir_v[0] * ext, start_L[1] - dir_v[1] * ext)
                 start_R = (start_R[0] - dir_v[0] * ext, start_R[1] - dir_v[1] * ext)

        # --- Handle End Junction ---
        e_key = (round(wall.end[0], 4), round(wall.end[1], 4))
        neighbors_e = [w for w in adjacency.get(e_key, []) if w is not wall]
        
        if not neighbors_e:
              ext = max(w_l, w_r)
              end_L = (end_L[0] + dir_v[0] * ext, end_L[1] + dir_v[1] * ext)
              end_R = (end_R[0] + dir_v[0] * ext, end_R[1] + dir_v[1] * ext)
        else:
             other = neighbors_e[0]
             
             o_dx = other.end[0] - other.start[0]
             o_dy = other.end[1] - other.start[1]
             o_len = math.hypot(o_dx, o_dy)
             o_dir = (o_dx/o_len, o_dy/o_len) if o_len > 0 else (0,0)
             o_perp_L = (o_dir[1], -o_dir[0])
             o_perp_R = (-o_dir[1], o_dir[0])
             o_wl = other.footer_left_offset
             o_wr = other.footer_right_offset

             end_connection = (round(wall.end[0], 4) == round(other.start[0], 4))
             
             if end_connection:
                 # Match Left with Left
                 o_p_start_L = (other.start[0] + o_perp_L[0] * o_wl, other.start[1] + o_perp_L[1] * o_wl)
                 pt_L = intersect(end_L, dir_v, o_p_start_L, o_dir)
                 if pt_L: end_L = pt_L
                 
                 o_p_start_R = (other.start[0] + o_perp_R[0] * o_wr, other.start[1] + o_perp_R[1] * o_wr)
                 pt_R = intersect(end_R, dir_v, o_p_start_R, o_dir)
                 if pt_R: end_R = pt_R
             else:
                 flip_other = (round(wall.end[0], 4) == round(other.end[0], 4))
                 if flip_other:
                     # Match Left with Other.Right
                     o_p_end_R = (other.end[0] + o_perp_R[0] * o_wr, other.end[1] + o_perp_R[1] * o_wr)
                     pt_L = intersect(end_L, dir_v, o_p_end_R, o_dir)
                     if pt_L: end_L = pt_L
                     
                     o_p_end_L = (other.end[0] + o_perp_L[0] * o_wl, other.end[1] + o_perp_L[1] * o_wl)
                     pt_R = intersect(end_R, dir_v, o_p_end_L, o_dir)
                     if pt_R: end_R = pt_R
                 else:
                     ext = max(w_l, w_r)
                     end_L = (end_L[0] + dir_v[0] * ext, end_L[1] + dir_v[1] * ext)
                     end_R = (end_R[0] + dir_v[0] * ext, end_R[1] + dir_v[1] * ext)


        # Draw Polygon
        # Draw outlines (skipping shared edges)
        c1 = start_L
        c2 = end_L
        c3 = end_R
        c4 = start_R
        
        cr.move_to(c1[0], c1[1])
        cr.line_to(c2[0], c2[1])
        
        if not neighbors_e:
            cr.line_to(c3[0], c3[1])
        else:
            cr.move_to(c3[0], c3[1])
            
        cr.line_to(c4[0], c4[1])
        
        if not neighbors:
            cr.line_to(c1[0], c1[1])
            
        cr.stroke()
        
    cr.restore()
