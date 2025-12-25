

class CanvasRoomMixin:
    def _handle_room_click(self, n_press: int, x: float, y: float) -> None:
        """
        Handle click events for drawing rooms on the canvas.

        This method is called when the user clicks while the room drawing tool is active.
        On a single click, it adds a snapped and aligned point to the current room outline.
        On a double click, it finalizes the room by closing the polygon and creating a new room object,
        or attempts to create a room from a closed wall set if the click is inside one.

        Args:
            n_press (int): The number of presses (1 for single click, 2 for double click).
            x (float): The x-coordinate of the click in widget coordinates.
            y (float): The y-coordinate of the click in widget coordinates.

        Returns:
            None
        """
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        canvas_x, canvas_y = self.device_to_model(x, y, pixels_per_inch)
        # raw_point = (canvas_x, canvas_y)
        base_x = self.current_room_points[-1][0] if self.current_room_points else canvas_x
        base_y = self.current_room_points[-1][1] if self.current_room_points else canvas_y
        candidate_points = self._get_candidate_points()
        candidate_points.extend(self.current_room_points)
        
        (snapped_x, snapped_y), _ = self.snap_manager.snap_point(
            canvas_x, canvas_y, base_x, base_y,
            self.walls, self.rooms,
            current_wall=None, last_wall=None,
            in_progress_points=candidate_points,
            canvas_width=self.get_allocation().width or self.config.WINDOW_WIDTH,
            zoom=self.zoom
        )
        aligned_x, aligned_y, _ = self._apply_alignment_snapping(canvas_x, canvas_y)
        snapped_x, snapped_y = aligned_x, aligned_y

        if n_press == 1:
            # Removed save_state here - only save when room is complete
            self.current_room_points.append((snapped_x, snapped_y))
            self.queue_draw()
        elif n_press == 2:
            # Only save when finalizing the room
            room_created = False
            if self.current_room_points and len(self.current_room_points) >= 3:
                # Room stores only unique vertices - rendering uses close_path() to close polygon
                new_room = self.Room(self.current_room_points, layer_id=self.active_layer_id)
                self.rooms.append(new_room)
                self.current_room_points = []
                self.current_room_preview = None
                room_created = True
            for wall_set in self.wall_sets:
                if len(wall_set) < 3:
                    continue
                if self._is_closed_polygon(wall_set):
                    poly = [w.start for w in wall_set]
                    if self._point_in_polygon((snapped_x, snapped_y), poly):
                        new_room = self.Room(poly, layer_id=self.active_layer_id)
                        self.rooms.append(new_room)
                        # Reset room drawing state after creating room from closed loop
                        self.current_room_points = []
                        self.current_room_preview = None
                        room_created = True
                        break
            if room_created:
                self.save_state()
            self.queue_draw()
            
    def finalize_room(self):
        # Only finalize if there are enough points to form a room
        if self.current_room_points and len(self.current_room_points) >= 3:
            # Room stores only unique vertices - rendering uses close_path() to close polygon
            new_room = self.Room(self.current_room_points, layer_id=self.active_layer_id)
            self.rooms.append(new_room)
            print(f"Finalized room with points: {self.current_room_points}")
        # Clear the temporary room points and preview
        self.current_room_points = []
        self.current_room_preview = None
        self.queue_draw()