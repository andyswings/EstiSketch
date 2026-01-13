

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
        # Process the wall set
        path_active = False
        path_start_point = None
        current_width_user = -1.0
        current_opacity = -1.0

        for i, wall in enumerate(wall_set):
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

            cr.set_source_rgba(0.9, 0.9, 1, opacity)
            cr.fill_preserve()

            cr.set_source_rgba(0, 0, 0, opacity)
            cr.stroke()
            cr.restore()

    if self.tool_mode == "draw_rooms" and self.current_room_points:
        # Current drawing room is temporary, we assume it's visible (active layer opacity?)
        # For preview we might stick to full opacity or use active layer
        # opacity
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
