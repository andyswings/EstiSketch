import copy

class CanvasStateMixin:
    def save_state(self):
        state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points),
            "polylines": copy.deepcopy(self.polylines),
            "polyline_sets": copy.deepcopy(self.polyline_sets),
            "doors": copy.deepcopy(self.doors),
            "windows": copy.deepcopy(self.windows),
            "texts": copy.deepcopy(self.texts),
            "dimensions": copy.deepcopy(self.dimensions)
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.config.UNDO_REDO_LIMIT:
            self.undo_stack.pop(0)
        import traceback
        stack = traceback.extract_stack()
        caller = stack[-2]
        print(f"save_state called from {caller.filename}:{caller.lineno} in {caller.name}")
        print(f"save_state: {len(state['wall_sets'])} wall sets, {len(state['walls'])} walls, {len(state['rooms'])} rooms")

    def restore_state(self, state):
        self.wall_sets = copy.deepcopy(state["wall_sets"])
        self.walls = copy.deepcopy(state["walls"])
        self.current_wall = copy.deepcopy(state["current_wall"]) if state["current_wall"] else None
        self.drawing_wall = state["drawing_wall"]
        self.rooms = copy.deepcopy(state["rooms"])
        self.current_room_points = copy.deepcopy(state["current_room_points"])
        self.polylines = copy.deepcopy(state.get("polylines", []))
        self.polyline_sets = copy.deepcopy(state.get("polyline_sets", []))
        self.doors = copy.deepcopy(state.get("doors", []))
        self.windows = copy.deepcopy(state.get("windows", []))
        self.texts = copy.deepcopy(state.get("texts", []))
        self.dimensions = copy.deepcopy(state.get("dimensions", []))
        self.snap_type = "none"
        self.queue_draw()
        print(f"restore_state: {len(self.wall_sets)} wall sets, {len(self.walls)} walls, {len(self.rooms)} rooms")

    def undo(self):
        # We need at least 2 states: current state (to save) and previous state (to restore)
        if len(self.undo_stack) < 2:
            print("Nothing to undo.")
            return

        # 1. Pop the current state (which represents the canvas NOW)
        current_state = self.undo_stack.pop()
        
        # 2. Move it to the redo stack so we can go back
        self.redo_stack.append(current_state)
        
        # 3. Peek at the *new* top of the undo stack (the PREVIOUS state)
        previous_state = self.undo_stack[-1]
        
        # 4. Restore that previous state
        self.restore_state(previous_state)

    def redo(self):
        if not self.redo_stack:
            print("Nothing to redo.")
            return

        # 1. Pop the next state from the redo stack
        next_state = self.redo_stack.pop()
        
        # 2. Push it back onto the undo stack (it becomes the current state)
        self.undo_stack.append(next_state)
        
        # 3. Restore it
        self.restore_state(next_state)
