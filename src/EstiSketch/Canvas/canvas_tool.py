class CanvasToolMixin:
    def set_tool_mode(self, mode):
        self.tool_mode = mode
        self.opening_ghost = None  # clear door/window ghost on tool change
        self.current_wall = None
        self.drawing_wall = False
        self.snap_type = "none"
        self.alignment_candidate = None
        self.raw_current_end = None
        self.current_room_points = []
        self.current_room_preview = None
        self.drawing_roof_line = False
        self.roof_line_start = None
        self.roof_line_preview = None
        self.editing_roof_line = None
        self.editing_roof_line_handle = None
        self.dragging_roof_lines = None

        # Reset dimension tool state
        self.drawing_dimension = False
        self.dimension_start = None
        self.dimension_end = None
        self.dimension_offset_preview = None

        # Reset dimension chain tool state
        self.drawing_dimension_chain = False
        self.dimension_chain_points = []
        self.dimension_chain_offset = None

        # Reset leader callout tool state
        self.drawing_leader = False
        self.leader_tip = None
        self.leader_elbow = None

        # Clear selection when activating creation tools
        creation_tools = (
            "add_dimension_chain", "add_dimension", "add_leader",
            "draw_walls", "draw_rooms", "add_polyline", "add_doors",
            "add_windows", "add_circle", "add_arc", "add_stair", "add_roof_line"
        )
        if mode in creation_tools and getattr(self, "selected_items", None):
            self.selected_items = []
            self.emit('selection-changed', self.selected_items)

        self.queue_draw()

        # Update hint for the new tool mode
        from ..Resources.tool_hints import TOOL_HINTS
        hint_key = mode if mode else "pointer"
        # Special case for circle/arc variants if needed, or just use base mode
        if hint_key in TOOL_HINTS:
            self.update_hint(TOOL_HINTS[hint_key])
        elif not mode:
             self.update_hint(TOOL_HINTS["pointer"])
