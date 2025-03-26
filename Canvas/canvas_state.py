import copy

class CanvasStateMixin:
    def save_state(self):
        state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.config.UNDO_REDO_LIMIT:
            self.undo_stack.pop(0)
        print(f"save_state: {len(state['wall_sets'])} wall sets, {len(state['walls'])} walls, {len(state['rooms'])} rooms")

    def restore_state(self, state):
        self.wall_sets = copy.deepcopy(state["wall_sets"])
        self.walls = copy.deepcopy(state["walls"])
        self.current_wall = copy.deepcopy(state["current_wall"]) if state["current_wall"] else None
        self.drawing_wall = state["drawing_wall"]
        self.rooms = copy.deepcopy(state["rooms"])
        self.current_room_points = copy.deepcopy(state["current_room_points"])
        self.snap_type = "none"
        self.queue_draw()
        print(f"restore_state: {len(self.wall_sets)} wall sets, {len(self.walls)} walls, {len(self.rooms)} rooms")

    def undo(self):
        if not self.undo_stack:
            print("Nothing to undo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.redo_stack.append(current_state)
        state = self.undo_stack.pop()
        self.restore_state(state)

    def redo(self):
        if not self.redo_stack:
            print("Nothing to redo.")
            return
        current_state = {
            "wall_sets": copy.deepcopy(self.wall_sets),
            "walls": copy.deepcopy(self.walls),
            "current_wall": copy.deepcopy(self.current_wall) if self.current_wall else None,
            "drawing_wall": self.drawing_wall,
            "rooms": copy.deepcopy(self.rooms),
            "current_room_points": copy.deepcopy(self.current_room_points)
        }
        self.undo_stack.append(current_state)
        state = self.redo_stack.pop()
        self.restore_state(state)
