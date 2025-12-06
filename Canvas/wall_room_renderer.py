

def draw_walls(self, cr):
    cr.set_source_rgb(0, 0, 0) # Black lines.
    cr.set_line_join(0) # 0 = miter join.
    cr.set_line_cap(0) # 0 = butt cap.
    cr.set_miter_limit(10.0)
    # Draw wall sets (connected components)
    for wall_set in self.wall_sets:
        if not wall_set:
            continue
        
        # We need to act like a single path for mitering to work on connected segments.
        # Assumptions: 
        # 1. Walls in a set are ordered (verified in canvas_events.py).
        # 2. We only bundle them into one stroke if they share the same width.
        
        # Start the first path
        current_width_user = wall_set[0].width / self.zoom
        cr.set_line_width(current_width_user)
        cr.move_to(wall_set[0].start[0], wall_set[0].start[1])
        cr.line_to(wall_set[0].end[0], wall_set[0].end[1])
        
        for i in range(1, len(wall_set)):
            wall = wall_set[i]
            prev_wall = wall_set[i-1]
            
            # Check if connected
            # We use a small epsilon for float comparison, though exact match is likely.
            connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and 
                         abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
            
            width_user = wall.width / self.zoom
            
            if connected and abs(width_user - current_width_user) < 1e-6:
                # Continue the path
                cr.line_to(wall.end[0], wall.end[1])
            else:
                # Stroke what we have and start new
                cr.stroke()
                
                # Setup next
                current_width_user = width_user
                cr.set_line_width(current_width_user)
                cr.move_to(wall.start[0], wall.start[1])
                cr.line_to(wall.end[0], wall.end[1])
        
        # Stroke the final sequence
        # Check if closed loop
        if len(wall_set) > 1 and abs(wall_set[-1].end[0] - wall_set[0].start[0]) < 1e-6 and abs(wall_set[-1].end[1] - wall_set[0].start[1]) < 1e-6:
             cr.close_path()
        cr.stroke()

    # Draw loose walls (temp/preview list usually empty or separate; just in case)
    # Draw active drawing chain (self.walls + current_wall)
    # We combine them temporarily to allow the rubber-band segment to miter with the last fixated segment.
    active_chain = []
    if self.walls:
        active_chain.extend(self.walls)
    if self.current_wall:
        active_chain.append(self.current_wall)
    
    if active_chain:
        # Same logic as above for the active chain
        current_width_user = active_chain[0].width / self.zoom
        cr.set_line_width(current_width_user)
        cr.move_to(active_chain[0].start[0], active_chain[0].start[1])
        cr.line_to(active_chain[0].end[0], active_chain[0].end[1])
        
        for i in range(1, len(active_chain)):
            wall = active_chain[i]
            prev_wall = active_chain[i-1]
            
            connected = (abs(prev_wall.end[0] - wall.start[0]) < 1e-6 and 
                         abs(prev_wall.end[1] - wall.start[1]) < 1e-6)
            
            width_user = wall.width / self.zoom
            
            if connected and abs(width_user - current_width_user) < 1e-6:
                cr.line_to(wall.end[0], wall.end[1])
            else:
                cr.stroke()
                current_width_user = width_user
                cr.set_line_width(current_width_user)
                cr.move_to(wall.start[0], wall.start[1])
                cr.line_to(wall.end[0], wall.end[1])
        
        cr.stroke()


def draw_rooms(self, cr, zoom_transform):
    cr.set_source_rgb(0.9, 0.9, 1)  # light blue fill.
    cr.set_line_width(1.0 / zoom_transform)
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
        cr.set_line_width(2.0 / zoom_transform)
        cr.move_to(self.current_room_points[0][0], self.current_room_points[0][1])
        for pt in self.current_room_points[1:]:
            cr.line_to(pt[0], pt[1])
        if self.current_room_preview:
            cr.line_to(self.current_room_preview[0], self.current_room_preview[1])
        cr.stroke()
        cr.restore()