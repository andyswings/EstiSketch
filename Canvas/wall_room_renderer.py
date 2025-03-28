

def draw_walls(self, cr):
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