

def draw_walls(self, cr):
    cr.set_line_join(0) # 0 = miter join.
    cr.set_line_cap(0) # 0 = butt cap.
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
        current_width_user = -1.0
        current_opacity = -1.0
        
        for i, wall in enumerate(wall_set):
            if not is_visible(wall):
                if path_active:
                    cr.stroke()
                    path_active = False
                continue
            
            width_user = wall.width / self.zoom
            opacity = get_opacity(wall)
            
            should_start_new = True
            if path_active:
                # Check connectivity and property matching
                prev_wall = wall_set[i-1]
                connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and 
                             abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
                if (connected and 
                    abs(width_user - current_width_user) < 1e-6 and
                    abs(opacity - current_opacity) < 1e-6):
                    should_start_new = False
            
            if should_start_new:
                if path_active:
                    cr.stroke()
                
                current_width_user = width_user
                current_opacity = opacity
                cr.set_line_width(current_width_user)
                cr.set_source_rgba(0, 0, 0, current_opacity)
                cr.move_to(wall.start[0], wall.start[1])
                cr.line_to(wall.end[0], wall.end[1])
                path_active = True
            else:
                cr.line_to(wall.end[0], wall.end[1])
        
        if path_active:
            cr.stroke()

    # Draw active drawing chain
    active_chain = []
    if self.walls:
        active_chain.extend(self.walls)
    if self.current_wall:
        active_chain.append(self.current_wall)
    
    if active_chain:
        path_active = False
        current_width_user = -1.0
        current_opacity = -1.0
        
        for i, wall in enumerate(active_chain):
            if not is_visible(wall):
                if path_active:
                    cr.stroke()
                    path_active = False
                continue

            width_user = wall.width / self.zoom
            opacity = get_opacity(wall)
            
            should_start_new = True
            if path_active:
                prev_wall = active_chain[i-1]
                connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and 
                             abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
                if (connected and 
                    abs(width_user - current_width_user) < 1e-6 and
                    abs(opacity - current_opacity) < 1e-6):
                    should_start_new = False
            
            if should_start_new:
                if path_active:
                    cr.stroke()
                current_width_user = width_user
                current_opacity = opacity
                cr.set_line_width(current_width_user)
                cr.set_source_rgba(0, 0, 0, current_opacity)
                cr.move_to(wall.start[0], wall.start[1])
                cr.line_to(wall.end[0], wall.end[1])
                path_active = True
            else:
                cr.line_to(wall.end[0], wall.end[1])
        
        if path_active:
            cr.stroke()


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
        # For preview we might stick to full opacity or use active layer opacity
        active_opacity = 1.0
        if hasattr(self, 'active_layer_id') and hasattr(self, 'get_layer_by_id'):
             active_layer = self.get_layer_by_id(self.active_layer_id)
             if active_layer:
                 active_opacity = active_layer.opacity
                 
        cr.save()
        cr.set_source_rgba(0, 0, 1, active_opacity)
        cr.set_line_width(2.0 / zoom_transform)
        cr.move_to(self.current_room_points[0][0], self.current_room_points[0][1])
        for pt in self.current_room_points[1:]:
            cr.line_to(pt[0], pt[1])
        if self.current_room_preview:
            cr.line_to(self.current_room_preview[0], self.current_room_preview[1])
        cr.stroke()
        cr.restore()