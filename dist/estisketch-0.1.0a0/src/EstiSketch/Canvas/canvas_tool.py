class CanvasToolMixin:
    def set_tool_mode(self, mode):
        self.tool_mode = mode
        self.current_wall = None
        self.drawing_wall = False
        self.snap_type = "none"
        self.alignment_candidate = None
        self.raw_current_end = None
        self.current_room_points = []
        self.current_room_preview = None
        self.queue_draw()
