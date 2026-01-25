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

        # Update hint for the new tool mode
        from ..Resources.tool_hints import TOOL_HINTS
        hint_key = mode if mode else "pointer"
        # Special case for circle/arc variants if needed, or just use base mode
        if hint_key in TOOL_HINTS:
            self.update_hint(TOOL_HINTS[hint_key])
        elif not mode:
             self.update_hint(TOOL_HINTS["pointer"])
