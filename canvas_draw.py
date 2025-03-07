import math
from gi.repository import cairo

class CanvasDrawMixin:
    def on_draw(self, widget, cr, width, height):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.save()
        cr.translate(self.offset_x, self.offset_y)
        cr.scale(self.zoom, self.zoom)
        self.draw_grid(cr, width, height)

        # Draw walls
        base_feet_per_pixel = 60.0 / width
        wall_thickness_feet = self.config.DEFAULT_WALL_WIDTH / 12
        wall_pixel_width = wall_thickness_feet / base_feet_per_pixel
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(max(wall_pixel_width * self.zoom, 1.0))
        cr.set_line_join(0)
        cr.set_line_cap(0)
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

        # Draw finalized rooms
        cr.set_source_rgb(0.9, 0.9, 1)  # Light blue fill for rooms
        cr.set_line_width(1.0 / self.zoom)  # Thinner line for room outlines
        for room in self.rooms:
            if room.points:
                cr.save()
                cr.move_to(room.points[0][0], room.points[0][1])
                for pt in room.points[1:]:
                    cr.line_to(pt[0], pt[1])
                cr.close_path()
                cr.fill_preserve()
                cr.set_source_rgb(0, 0, 0)  # Black outline
                cr.stroke()
                cr.restore()

        # Draw room in-progress (manual)
        if self.tool_mode == "draw_rooms" and self.current_room_points:
            cr.save()
            cr.set_source_rgb(0, 0, 1)  # Blue for in-progress room
            cr.set_line_width(2.0 / self.zoom)
            cr.move_to(self.current_room_points[0][0], self.current_room_points[0][1])
            for pt in self.current_room_points[1:]:
                cr.line_to(pt[0], pt[1])
            if self.current_room_preview:
                cr.line_to(self.current_room_preview[0], self.current_room_preview[1])
            cr.stroke()
            cr.restore()
        
        if hasattr(self, "selected_items"):
            for item in self.selected_items:
                if item["type"] == "wall":
                    wall = item["object"]
                    cr.save()
                    cr.set_source_rgb(1, 0, 0)  # red highlight for wall segments
                    cr.set_line_width(3.0 / self.zoom)
                    cr.move_to(wall.start[0], wall.start[1])
                    cr.line_to(wall.end[0], wall.end[1])
                    cr.stroke()
                    cr.restore()
                elif item["type"] == "vertex":
                    room, index = item["object"]
                    pt = room.points[index]
                    cr.save()
                    cr.set_source_rgb(0, 1, 0)  # green highlight for room vertices
                    cr.arc(pt[0], pt[1], 5 / self.zoom, 0, 2 * math.pi)
                    cr.fill()
                    cr.restore()
        
        if hasattr(self, "box_selecting") and self.box_selecting:
            cr.save()
            # Use a dashed line and semi-transparent fill:
            cr.set_source_rgba(0, 0, 1, 0.3)  # blue fill with some transparency
            x1 = min(self.box_select_start[0], self.box_select_end[0])
            y1 = min(self.box_select_start[1], self.box_select_end[1])
            x2 = max(self.box_select_start[0], self.box_select_end[0])
            y2 = max(self.box_select_start[1], self.box_select_end[1])
            cr.rectangle(x1, y1, x2 - x1, y2 - y1)
            cr.set_line_width(2.0 / self.zoom)
            cr.set_dash([4.0 / self.zoom, 4.0 / self.zoom])
            cr.stroke_preserve()
            cr.set_source_rgba(0, 0, 1, 0.1)
            cr.fill()
            cr.restore()


        self.draw_alignment_guide(cr)
        self.draw_snap_indicator(cr)

        cr.restore()
        if self.config.SHOW_RULERS:
            self.draw_rulers(cr, width, height)

    def draw_alignment_guide(self, cr):
        if not (self.drawing_wall and self.current_wall and self.alignment_candidate and self.raw_current_end):
            return
        dx = self.raw_current_end[0] - self.alignment_candidate[0]
        dy = self.raw_current_end[1] - self.alignment_candidate[1]
        if math.sqrt(dx**2 + dy**2) < 1:
            return
        cr.save()
        cr.set_line_width(1.0 / self.zoom)
        cr.set_dash([2.0 / self.zoom, 2.0 / self.zoom])
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.move_to(self.raw_current_end[0], self.raw_current_end[1])
        cr.line_to(self.alignment_candidate[0], self.alignment_candidate[1])
        cr.stroke()
        cr.restore()

    def draw_snap_indicator(self, cr):
        if self.snap_type == "none" or not self.drawing_wall or not self.current_wall:
            return
        cr.save()
        snap_x, snap_y = self.current_wall.end
        cr.set_line_width(2.0 / self.zoom)
        cr.set_font_size(12 / self.zoom)
        cr.select_font_face("Sans")
        if self.snap_type == "endpoint":
            cr.set_source_rgb(1, 0, 0)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Endpoint")
        elif self.snap_type == "midpoint":
            cr.set_source_rgb(0, 0, 1)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Midpoint")
        elif self.snap_type == "axis":
            cr.set_source_rgb(0, 1, 0)
            cr.move_to(snap_x - 20 / self.zoom, snap_y)
            cr.line_to(snap_x + 20 / self.zoom, snap_y)
            cr.move_to(snap_x, snap_y - 20 / self.zoom)
            cr.line_to(snap_x, snap_y + 20 / self.zoom)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Axis")
        elif self.snap_type in ["angle", "perpendicular"]:
            cr.set_source_rgb(1, 0, 1)
            cr.move_to(self.current_wall.start[0], self.current_wall.start[1])
            cr.line_to(snap_x, snap_y)
            cr.stroke()
            if self.snap_type == "perpendicular":
                cr.move_to(snap_x + 15 / self.zoom, snap_y)
                cr.show_text("Perpendicular")
        elif self.snap_type == "grid":
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.rectangle(snap_x - 10 / self.zoom, snap_y - 10 / self.zoom, 20 / self.zoom, 20 / self.zoom)
            cr.stroke()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Grid")
        elif self.snap_type == "distance":
            cr.set_source_rgb(1, 0.5, 0)
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Distance")
        elif self.snap_type == "tangent":
            cr.set_source_rgb(0, 1, 1)
            cr.arc(snap_x, snap_y, 10 / self.zoom, 0, 2 * math.pi)
            cr.fill()
            cr.move_to(snap_x + 15 / self.zoom, snap_y)
            cr.show_text("Tangent")
        cr.restore()

    def draw_rulers(self, cr, width, height):
        ruler_size = 20
        base_feet_per_pixel = 60.0 / width
        major_spacing = 8 / base_feet_per_pixel * self.zoom
        minor_spacing = major_spacing / 8
        grid_left_pixel = -self.offset_x / self.zoom
        grid_top_pixel = -self.offset_y / self.zoom
        left_feet = grid_left_pixel * base_feet_per_pixel
        top_feet = grid_top_pixel * base_feet_per_pixel
        first_grid_x_feet = math.floor(left_feet / 8) * 8
        first_grid_y_feet = math.floor(top_feet / 8) * 8
        first_major_x_pixel = (first_grid_x_feet / base_feet_per_pixel * self.zoom + self.offset_x)
        first_major_y_pixel = (first_grid_y_feet / base_feet_per_pixel * self.zoom + self.offset_y)
        while first_major_x_pixel > 20:
            first_major_x_pixel -= major_spacing
            first_grid_x_feet -= 8
        while first_major_x_pixel < 20 - major_spacing:
            first_major_x_pixel += major_spacing
            first_grid_x_feet += 8
        while first_major_y_pixel > 20:
            first_major_y_pixel -= major_spacing
            first_grid_y_feet -= 8
        while first_major_y_pixel < 20 - major_spacing:
            first_major_y_pixel += major_spacing
            first_grid_y_feet += 8
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.rectangle(20, 0, width, ruler_size)
        cr.rectangle(0, 20, ruler_size, height)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(1)
        for x in range(int(first_major_x_pixel), width + int(major_spacing), int(major_spacing)):
            if x >= 20 and x <= width:
                cr.move_to(x, ruler_size - 10)
                cr.line_to(x, ruler_size)
                cr.stroke()
                feet = round((x - first_major_x_pixel) / major_spacing) * 8 + first_grid_x_feet
                cr.move_to(x + 2, ruler_size - 7)
                cr.show_text(f"{feet} ft")
            for i in range(1, 8):
                minor_x = x + i * minor_spacing
                if minor_x >= 20 and minor_x <= width:
                    cr.move_to(minor_x, ruler_size - 5)
                    cr.line_to(minor_x, ruler_size)
                    cr.stroke()
        for y in range(int(first_major_y_pixel), height + int(major_spacing), int(major_spacing)):
            if y >= 20 and y <= height:
                cr.move_to(ruler_size - 10, y)
                cr.line_to(ruler_size, y)
                cr.stroke()
                feet = round((y - first_major_y_pixel) / major_spacing) * 8 + first_grid_y_feet
                cr.move_to(2, y + 10)
                cr.show_text(f"{feet} ft")
            for i in range(1, 8):
                minor_y = y + i * minor_spacing
                if minor_y >= 20 and minor_y <= height:
                    cr.move_to(ruler_size - 5, minor_y)
                    cr.line_to(ruler_size, minor_y)
                    cr.stroke()

    def draw_grid(self, cr, width, height):
        if not self.config.SHOW_GRID:
            return
        base_feet_per_pixel = 60.0 / width
        major_grid_spacing = 8
        minor_grid_spacing = 1
        left_pixel = -self.offset_x / self.zoom
        right_pixel = (width - self.offset_x) / self.zoom
        top_pixel = -self.offset_y / self.zoom
        bottom_pixel = (height - self.offset_y) / self.zoom
        left_feet = left_pixel * base_feet_per_pixel
        right_feet = right_pixel * base_feet_per_pixel
        top_feet = top_pixel * base_feet_per_pixel
        bottom_feet = bottom_pixel * base_feet_per_pixel
        buffer_feet = 8
        left_feet -= buffer_feet
        right_feet += buffer_feet
        top_feet -= buffer_feet
        bottom_feet += buffer_feet
        cr.set_line_width(1 / self.zoom)
        cr.set_source_rgb(0.8, 0.8, 0.8)
        first_major_x = math.floor(left_feet / 8) * 8
        for feet in range(int(first_major_x), int(right_feet) + 1, 8):
            x = feet / base_feet_per_pixel
            cr.move_to(x, top_pixel)
            cr.line_to(x, bottom_pixel)
        first_major_y = math.floor(top_feet / 8) * 8
        for feet in range(int(first_major_y), int(bottom_feet) + 1, 8):
            y = feet / base_feet_per_pixel
            cr.move_to(left_pixel, y)
            cr.line_to(right_pixel, y)
        cr.stroke()
        cr.set_source_rgb(0.9, 0.9, 0.9)
        first_minor_x = math.floor(left_feet)
        for feet in range(int(first_minor_x), int(right_feet) + 1):
            if feet % 8 != 0:
                x = feet / base_feet_per_pixel
                cr.move_to(x, top_pixel)
                cr.line_to(x, bottom_pixel)
        first_minor_y = math.floor(top_feet)
        for feet in range(int(first_minor_y), int(bottom_feet) + 1):
            if feet % 8 != 0:
                y = feet / base_feet_per_pixel
                cr.move_to(left_pixel, y)
                cr.line_to(right_pixel, y)
        cr.stroke()
