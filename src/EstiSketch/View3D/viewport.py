"""GTK4 ``Gtk.GLArea`` 3D viewport backed by the Rust ``EstiSketch._native_3d`` engine."""

from __future__ import annotations

from collections.abc import Callable
import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import native_3d  # noqa: E402
from ..Canvas.floor_patterns import FLOOR_PATTERNS  # noqa: E402
from ..components import WALL_FINISH_OPTIONS  # noqa: E402
from ..scene_ir import (  # noqa: E402
    SceneIR,
    build_scene_ir_from_canvas,
    diff_scene_ir,
)
from .editor import (  # noqa: E402
    ROOF_MATERIAL_OPTIONS,
    EditActionResult,
    Editor3DController,
    ndc_from_widget_xy,
    select_from_hit,
    selected_entity_ids_from_canvas,
)

_SWATCH_PALETTE: tuple[str, ...] = (
    "#FFFFFF",
    "#EAE6DF",
    "#D7CEC2",
    "#B8C4CC",
    "#A8B5A2",
    "#C87D55",
    "#7D848B",
    "#3A424D",
)
_FLOOR_PATTERN_IDS: tuple[str, ...] = tuple(pid for pid, _label in FLOOR_PATTERNS)
_FLOOR_PATTERN_LABELS: list[str] = [label for _pid, label in FLOOR_PATTERNS]


class Viewport3DWidget(Gtk.Overlay):
    """Embedded live OpenGL 3.3 3D viewport with camera, editing tools, and Paint Brush."""

    def __init__(
        self,
        canvas: object,
        on_export_glb: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the 3D overlay widget bound to an EstiSketch 2D ``canvas``.

        Args:
            canvas: Source ``CanvasArea`` instance read via ``build_scene_ir_from_canvas``.
            on_export_glb: Optional callback invoked when the user clicks ``Export .glb``.
        """
        super().__init__()
        self._canvas = canvas
        self._on_export_glb = on_export_glb
        self._session: native_3d.NativeSceneSessionProtocol | None = None
        self._editor = Editor3DController()
        self._last_ir: SceneIR | None = None
        self._dirty: bool = True
        self._sync_source_id: int | None = None
        self._syncing_from_3d: bool = False
        self._gl_error: str | None = None

        self._drag_last_x: float = 0.0
        self._drag_last_y: float = 0.0
        self._drag_start_x: float = 0.0
        self._drag_start_y: float = 0.0
        self._drag_max_px: float = 0.0
        self._drag_button: int = 0
        self._drag_editing: bool = False
        self._last_hover_key: tuple[str, str, bool] | None = None

        self._updating_dropdowns: bool = False
        self._level_ids: list[str] = []
        self._room_centers: list[tuple[float, float, float]] = []

        self.set_hexpand(True)
        self.set_vexpand(True)

        self._gl_area = Gtk.GLArea()
        self._gl_area.set_required_version(3, 3)
        self._gl_area.set_has_depth_buffer(True)
        self._gl_area.set_auto_render(False)
        self._gl_area.set_hexpand(True)
        self._gl_area.set_vexpand(True)
        self._gl_area.set_focusable(True)
        self._gl_area.connect("realize", self._on_gl_realize)
        self._gl_area.connect("resize", self._on_gl_resize)
        self._gl_area.connect("render", self._on_gl_render)
        self._gl_area.connect("unrealize", self._on_gl_unrealize)
        self.set_child(self._gl_area)

        self._attach_input_controllers()
        self._build_fallback_banner()
        self._build_hud_bar()
        self._build_status_pill()

        if not native_3d.is_native_3d_available():
            detail = native_3d.native_3d_load_error() or "module not compiled"
            self._show_fallback(
                f"Native 3D extension (_native_3d) is unavailable:\n{detail}\n\n"
                "Run `python3 packaging/build_native_3d.py` to enable live 3D rendering."
            )

    def _attach_input_controllers(self) -> None:
        drag = Gtk.GestureDrag()
        drag.set_button(0)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self._gl_area.add_controller(drag)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_pointer_motion)
        motion.connect("leave", self._on_pointer_leave)
        self._gl_area.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self._on_scroll)
        self._gl_area.add_controller(scroll)

        key_ctrl = Gtk.EventControllerKey.new()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self._gl_area.add_controller(key_ctrl)

    def _build_fallback_banner(self) -> None:
        self._fallback_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._fallback_box.set_halign(Gtk.Align.CENTER)
        self._fallback_box.set_valign(Gtk.Align.CENTER)
        self._fallback_box.set_visible(False)

        self._fallback_label = Gtk.Label()
        self._fallback_label.set_justify(Gtk.Justification.CENTER)
        self._fallback_label.set_wrap(True)
        self._fallback_box.append(self._fallback_label)
        self.add_overlay(self._fallback_box)

    def _show_fallback(self, message: str) -> None:
        self._gl_error = message
        self._fallback_label.set_text(message)
        self._fallback_box.set_visible(True)

    def _build_status_pill(self) -> None:
        pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        pill.set_halign(Gtk.Align.CENTER)
        pill.set_valign(Gtk.Align.END)
        pill.set_margin_bottom(12)
        pill.add_css_class("osd")
        pill.set_can_target(False)
        pill.set_visible(False)

        self._status_label = Gtk.Label()
        self._status_label.set_margin_start(10)
        self._status_label.set_margin_end(10)
        self._status_label.set_margin_top(4)
        self._status_label.set_margin_bottom(4)
        pill.append(self._status_label)
        self._status_pill = pill
        self.add_overlay(pill)

    def _set_hud_message(self, message: str) -> None:
        text = message.strip()
        if not text:
            self._status_pill.set_visible(False)
            return
        self._status_label.set_text(text)
        self._status_pill.set_visible(True)

    def _build_hud_bar(self) -> None:
        hud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hud.set_halign(Gtk.Align.CENTER)
        hud.set_valign(Gtk.Align.START)
        hud.set_margin_top(8)
        hud.set_margin_start(8)
        hud.set_margin_end(8)
        hud.add_css_class("toolbar")

        self._select_btn = Gtk.ToggleButton(label="Select")
        self._select_btn.set_active(True)
        self._select_btn.set_tooltip_text(
            "Select & Edit 3D objects (V) — Right-drag orbits camera"
        )
        self._select_btn.connect("toggled", self._on_mode_toggled)
        hud.append(self._select_btn)

        self._orbit_btn = Gtk.ToggleButton(label="Orbit")
        self._orbit_btn.set_group(self._select_btn)
        self._orbit_btn.set_tooltip_text("Orbit / Dollhouse navigation (O)")
        self._orbit_btn.connect("toggled", self._on_mode_toggled)
        hud.append(self._orbit_btn)

        self._paint_btn = Gtk.ToggleButton(label="Paint")
        self._paint_btn.set_group(self._select_btn)
        self._paint_btn.set_tooltip_text(
            "Paint Material Brush (B) — Shift+Click: Room walls | Alt+Click: Eyedropper"
        )
        self._paint_btn.connect("toggled", self._on_mode_toggled)
        hud.append(self._paint_btn)

        self._brush_btn = Gtk.MenuButton(label="Brush")
        self._brush_btn.set_tooltip_text("Configure active 3D Paint Brush finishes & colors")
        self._brush_btn.set_popover(self._build_brush_popover())
        hud.append(self._brush_btn)

        self._walk_btn = Gtk.ToggleButton(label="Walk")
        self._walk_btn.set_group(self._select_btn)
        self._walk_btn.set_tooltip_text("First-person Walkthrough (WASD + Drag look)")
        self._walk_btn.connect("toggled", self._on_mode_toggled)
        hud.append(self._walk_btn)

        views = ["Iso", "Top", "Front", "Back", "Left", "Right"]
        self._view_combo = Gtk.DropDown(model=Gtk.StringList.new(views))
        self._view_combo.set_tooltip_text("Camera Preset")
        self._view_combo.connect("notify::selected", self._on_view_preset_changed)
        hud.append(self._view_combo)

        fit_btn = Gtk.Button(label="Fit")
        fit_btn.set_tooltip_text("Frame entire building")
        fit_btn.connect("clicked", self._on_fit_clicked)
        hud.append(fit_btn)

        self._room_combo = Gtk.DropDown(model=Gtk.StringList.new(["Jump to Room..."]))
        self._room_combo.set_tooltip_text("Enter room in Walkthrough mode")
        self._room_combo.connect("notify::selected", self._on_room_jump_changed)
        hud.append(self._room_combo)

        self._level_combo = Gtk.DropDown(model=Gtk.StringList.new(["All Levels"]))
        self._level_combo.set_tooltip_text("Dollhouse level slicer")
        self._level_combo.connect("notify::selected", self._on_level_changed)
        hud.append(self._level_combo)

        self._auto_hide_btn = Gtk.ToggleButton(label="Hide Roofs")
        self._auto_hide_btn.set_active(True)
        self._auto_hide_btn.set_tooltip_text("Auto-hide roofs & ceilings when looking down")
        self._auto_hide_btn.connect("toggled", self._on_auto_hide_toggled)
        hud.append(self._auto_hide_btn)

        styles = ["Textured", "Clay", "Sketch", "X-Ray"]
        self._style_combo = Gtk.DropDown(model=Gtk.StringList.new(styles))
        self._style_combo.set_tooltip_text("3D Visual Style")
        self._style_combo.connect("notify::selected", self._on_style_changed)
        hud.append(self._style_combo)

        hud.append(Gtk.Label(label="Sun:"))
        self._sun_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 6.0, 20.0, 0.25)
        self._sun_scale.set_value(13.5)
        self._sun_scale.set_size_request(90, -1)
        self._sun_scale.set_draw_value(False)
        self._sun_scale.set_tooltip_text("Time of day (06:00 - 20:00)")
        self._sun_scale.connect("value-changed", self._on_sun_changed)
        hud.append(self._sun_scale)

        export_btn = Gtk.Button(label="Export .glb")
        export_btn.set_tooltip_text("Export current 3D scene to glTF 2.0 Binary (.glb)")
        export_btn.connect("clicked", lambda _btn: self._trigger_export_glb())
        hud.append(export_btn)

        self._hud_bar = hud
        self.add_overlay(hud)

    def _build_brush_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        box.append(self._labeled_row("Wall Finish:", self._make_wall_finish_combo()))

        swatch_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        swatch_row.append(Gtk.Label(label="Wall Color:"))
        for hex_col in _SWATCH_PALETTE:
            btn = Gtk.Button(label=hex_col[-2:])
            btn.set_tooltip_text(f"Set wall color {hex_col}")
            btn.connect("clicked", self._make_wall_color_cb(hex_col))
            swatch_row.append(btn)
        self._wall_color_entry = Gtk.Entry()
        self._wall_color_entry.set_width_chars(8)
        self._wall_color_entry.set_text(self._editor.brush.wall_color)
        self._wall_color_entry.connect("activate", self._on_wall_color_entry)
        swatch_row.append(self._wall_color_entry)
        box.append(swatch_row)

        box.append(self._labeled_row("Floor Pattern:", self._make_floor_combo()))
        box.append(self._labeled_row("Roof Material:", self._make_roof_combo()))

        fx_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fx_row.append(Gtk.Label(label="Cabinet/Top:"))
        for label, fx_col, ct_col in (
            ("Oak", "#C99F6D", "#EAE6DF"),
            ("White", "#F4F2EE", "#D4CFC7"),
            ("Slate", "#4A5562", "#3A424D"),
            ("Sage", "#8CA08E", "#E5E2DC"),
        ):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", self._make_fixture_preset_cb(fx_col, ct_col))
            fx_row.append(btn)
        box.append(fx_row)

        hint = Gtk.Label(
            label="Click: paint surface  |  Shift+Click: room walls  |  Alt+Click: sample"
        )
        hint.add_css_class("dim-label")
        box.append(hint)
        pop.set_child(box)
        self._sync_brush_widgets()
        return pop

    def _labeled_row(self, text: str, widget: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl = Gtk.Label(label=text)
        lbl.set_xalign(0.0)
        lbl.set_size_request(100, -1)
        row.append(lbl)
        row.append(widget)
        return row

    def _make_wall_finish_combo(self) -> Gtk.DropDown:
        self._brush_wall_combo = Gtk.DropDown(
            model=Gtk.StringList.new(list(WALL_FINISH_OPTIONS))
        )
        self._brush_wall_combo.connect("notify::selected", self._on_brush_wall_changed)
        return self._brush_wall_combo

    def _make_floor_combo(self) -> Gtk.DropDown:
        self._brush_floor_combo = Gtk.DropDown(model=Gtk.StringList.new(_FLOOR_PATTERN_LABELS))
        self._brush_floor_combo.connect("notify::selected", self._on_brush_floor_changed)
        return self._brush_floor_combo

    def _make_roof_combo(self) -> Gtk.DropDown:
        self._brush_roof_combo = Gtk.DropDown(
            model=Gtk.StringList.new(list(ROOF_MATERIAL_OPTIONS))
        )
        self._brush_roof_combo.connect("notify::selected", self._on_brush_roof_changed)
        return self._brush_roof_combo

    def _make_wall_color_cb(self, hex_col: str) -> Callable[[Gtk.Button], None]:
        def _cb(_btn: Gtk.Button) -> None:
            self._editor.brush.wall_color = hex_col
            self._wall_color_entry.set_text(hex_col)
            self._paint_btn.set_active(True)
            self._set_hud_message(f"Brush wall: {self._editor.brush.wall_finish} ({hex_col})")

        return _cb

    def _make_fixture_preset_cb(
        self, fx_col: str, ct_col: str
    ) -> Callable[[Gtk.Button], None]:
        def _cb(_btn: Gtk.Button) -> None:
            self._editor.brush.fixture_color = fx_col
            self._editor.brush.countertop_color = ct_col
            self._paint_btn.set_active(True)
            self._set_hud_message(f"Brush cabinet {fx_col} / top {ct_col}")

        return _cb

    def _on_wall_color_entry(self, entry: Gtk.Entry) -> None:
        val = entry.get_text().strip()
        if val.startswith("#") and len(val) in (4, 7):
            self._editor.brush.wall_color = val
            self._set_hud_message(f"Brush wall color: {val}")

    def _on_brush_wall_changed(self, combo: Gtk.DropDown, _pspec: object) -> None:
        if self._updating_dropdowns:
            return
        idx = int(combo.get_selected())
        if 0 <= idx < len(WALL_FINISH_OPTIONS):
            self._editor.brush.wall_finish = WALL_FINISH_OPTIONS[idx]

    def _on_brush_floor_changed(self, combo: Gtk.DropDown, _pspec: object) -> None:
        if self._updating_dropdowns:
            return
        idx = int(combo.get_selected())
        if 0 <= idx < len(_FLOOR_PATTERN_IDS):
            self._editor.brush.floor_pattern = _FLOOR_PATTERN_IDS[idx]

    def _on_brush_roof_changed(self, combo: Gtk.DropDown, _pspec: object) -> None:
        if self._updating_dropdowns:
            return
        idx = int(combo.get_selected())
        if 0 <= idx < len(ROOF_MATERIAL_OPTIONS):
            self._editor.brush.roof_material = ROOF_MATERIAL_OPTIONS[idx]

    def _sync_brush_widgets(self) -> None:
        self._updating_dropdowns = True
        try:
            brush = self._editor.brush
            if brush.wall_finish in WALL_FINISH_OPTIONS:
                self._brush_wall_combo.set_selected(
                    WALL_FINISH_OPTIONS.index(brush.wall_finish)
                )
            self._wall_color_entry.set_text(brush.wall_color)
            if brush.floor_pattern in _FLOOR_PATTERN_IDS:
                self._brush_floor_combo.set_selected(
                    _FLOOR_PATTERN_IDS.index(brush.floor_pattern)
                )
            if brush.roof_material in ROOF_MATERIAL_OPTIONS:
                self._brush_roof_combo.set_selected(
                    ROOF_MATERIAL_OPTIONS.index(brush.roof_material)
                )
        finally:
            self._updating_dropdowns = False

    def _trigger_export_glb(self) -> None:
        if self._on_export_glb is not None:
            self._on_export_glb()

    def _ensure_session(self) -> native_3d.NativeSceneSessionProtocol | None:
        if not native_3d.is_native_3d_available():
            return None
        if self._session is None:
            self._session = native_3d.create_native_session()
        return self._session

    def mark_dirty(self) -> None:
        """Schedule a lazy sync from the 2D canvas whenever the 3D view is visible."""
        if self._syncing_from_3d or self._editor.active_drag is not None:
            return
        self._dirty = True
        if not self.get_visible():
            return
        if self._sync_source_id is None:
            self._sync_source_id = GLib.idle_add(self._on_idle_sync)

    def _on_idle_sync(self) -> bool:
        self._sync_source_id = None
        if self.get_visible() and self._dirty:
            self.sync_from_canvas()
        return False

    def sync_selection_from_canvas(self) -> None:
        """Synchronize 2D ``canvas.selected_items`` highlight to the 3D renderer."""
        session = self._session
        if session is None:
            return
        ids = selected_entity_ids_from_canvas(self._canvas)
        session.set_selected_entities(ids)
        if self._gl_error is None:
            self._gl_area.queue_render()

    def sync_from_canvas(self) -> None:
        """Rebuild ``SceneIR`` from canvas, push incremental delta to Rust, and redraw."""
        curr = build_scene_ir_from_canvas(self._canvas)
        prev = self._last_ir
        self._last_ir = curr
        self._dirty = False
        self._refresh_hud_lists(curr)

        session = self._ensure_session()
        if session is None:
            return
        if prev is None:
            session.load_scene(curr.to_json())
        else:
            delta = diff_scene_ir(prev, curr)
            session.upsert_entities(delta.to_json())
        session.set_selected_entities(selected_entity_ids_from_canvas(self._canvas))
        if self._gl_error is None:
            self._gl_area.queue_render()

    def _refresh_hud_lists(self, scene: SceneIR) -> None:
        self._updating_dropdowns = True
        try:
            level_names = ["All Levels"] + [lvl.name for lvl in scene.levels]
            self._level_ids = [""] + [lvl.id for lvl in scene.levels]
            self._level_combo.set_model(Gtk.StringList.new(level_names))

            level_z = {lvl.id: lvl.elevation_m for lvl in scene.levels}
            room_labels = ["Jump to Room..."]
            room_centers: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
            for r in scene.rooms:
                if not r.outer_m:
                    continue
                cx = sum(pt[0] for pt in r.outer_m) / len(r.outer_m)
                cy = sum(pt[1] for pt in r.outer_m) / len(r.outer_m)
                fz = level_z.get(r.level_id, r.z_top_m)
                room_labels.append(r.name or r.id)
                room_centers.append((cx, cy, fz))
            self._room_centers = room_centers
            self._room_combo.set_model(Gtk.StringList.new(room_labels))
        finally:
            self._updating_dropdowns = False

    def _on_gl_realize(self, area: Gtk.GLArea) -> None:
        area.make_current()
        err = area.get_error()
        if err is not None:
            self._show_fallback(f"OpenGL 3.3 context unavailable: {err}")
            return
        session = self._ensure_session()
        if session is None:
            return
        try:
            if self._last_ir is None or self._dirty:
                curr = build_scene_ir_from_canvas(self._canvas)
                self._last_ir = curr
                self._dirty = False
                self._refresh_hud_lists(curr)
                session.load_scene(curr.to_json())
                session.set_selected_entities(selected_entity_ids_from_canvas(self._canvas))
            scale = max(1, area.get_scale_factor())
            w = max(1, area.get_width() * scale)
            h = max(1, area.get_height() * scale)
            session.resize_gl(w, h)
            session.init_gl()
            self._fallback_box.set_visible(False)
            self._gl_error = None
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_fallback(f"Failed to initialize 3D viewport: {exc}")

    def _on_gl_resize(self, _area: Gtk.GLArea, width: int, height: int) -> None:
        session = self._session
        if session is not None and width > 0 and height > 0:
            session.resize_gl(width, height)

    def _on_gl_render(self, _area: Gtk.GLArea, _context: Gdk.GLContext) -> bool:
        if self._gl_error is not None:
            return False
        session = self._session
        if session is None:
            return False
        try:
            session.render_gl()
            return True
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_fallback(f"3D render error: {exc}")
            return False

    def _on_gl_unrealize(self, area: Gtk.GLArea) -> None:
        session = self._session
        if session is None:
            return
        area.make_current()
        if area.get_error() is None:
            session.destroy_gl()

    def _pick_at_widget_xy(
        self, x: float, y: float
    ) -> tuple[native_3d.PickHit | None, tuple[float, float, float], tuple[float, float, float]]:
        session = self._session
        if session is None:
            return (None, (0.0, 0.0, 0.0), (0.0, 0.0, -1.0))
        ndc_x, ndc_y = ndc_from_widget_xy(
            x, y, float(self._gl_area.get_width()), float(self._gl_area.get_height())
        )
        origin, direction = session.screen_ray(ndc_x, ndc_y)
        raw_hit = session.pick_screen(ndc_x, ndc_y)
        return (native_3d.parse_pick_hit(raw_hit), origin, direction)

    def _apply_action_result(self, result: EditActionResult) -> None:
        session = self._session
        if result.hud_message:
            self._set_hud_message(result.hud_message)
        if result.brush_sampled:
            self._sync_brush_widgets()
        if session is None:
            return
        if result.selected_ids is not None:
            session.set_selected_entities(result.selected_ids)
        if result.clear_preview:
            session.clear_transform_preview()
        elif result.preview_transform is not None:
            ent_id, pivot_m, delta_m, drot_rad = result.preview_transform
            session.set_transform_preview(ent_id, pivot_m, delta_m, drot_rad)
        if result.needs_mesh_sync:
            self._syncing_from_3d = True
            try:
                self.sync_from_canvas()
            finally:
                self._syncing_from_3d = False
            return
        if result.needs_render and self._gl_error is None:
            self._gl_area.queue_render()

    def _on_pointer_motion(
        self, _ctrl: Gtk.EventControllerMotion, x: float, y: float
    ) -> None:
        session = self._session
        if session is None or self._drag_button != 0 or self._walk_btn.get_active():
            return
        hit, _orig, _dir = self._pick_at_widget_xy(x, y)
        if hit is None:
            hover_key: tuple[str, str, bool] | None = None
        else:
            hover_key = (hit.entity_id, hit.sub_part, self._editor.tool == "paint")
        if hover_key != self._last_hover_key:
            self._last_hover_key = hover_key
            if hover_key is None:
                session.set_hovered_entity(None, None, False)
            else:
                session.set_hovered_entity(hover_key[0], hover_key[1], hover_key[2])
            if self._gl_error is None:
                self._gl_area.queue_render()

    def _on_pointer_leave(self, _ctrl: Gtk.EventControllerMotion) -> None:
        if self._last_hover_key is not None and self._session is not None:
            self._last_hover_key = None
            self._session.set_hovered_entity(None, None, False)
            if self._gl_error is None:
                self._gl_area.queue_render()

    def _on_drag_begin(self, gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        self._gl_area.grab_focus()
        self._drag_last_x = 0.0
        self._drag_last_y = 0.0
        self._drag_start_x = x
        self._drag_start_y = y
        self._drag_max_px = 0.0
        self._drag_button = int(gesture.get_current_button())
        self._drag_editing = False

        if self._drag_button != 1 or self._walk_btn.get_active():
            return
        if self._last_ir is None or self._session is None:
            return
        if self._editor.tool != "select":
            return

        state = gesture.get_current_event_state()
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        hit, origin, direction = self._pick_at_widget_xy(x, y)
        res = self._editor.begin_drag(
            self._canvas,
            hit,
            origin,
            direction,
            self._last_ir.plan_center_in,
            shift=shift,
            alt=alt,
        )
        self._drag_editing = res.handled
        self._apply_action_result(res)

    def _on_drag_update(
        self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        dx = offset_x - self._drag_last_x
        dy = offset_y - self._drag_last_y
        self._drag_last_x = offset_x
        self._drag_last_y = offset_y
        self._drag_max_px = max(self._drag_max_px, math.hypot(offset_x, offset_y))

        session = self._session
        if session is None:
            return

        state = gesture.get_current_event_state()
        is_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if self._drag_editing and self._last_ir is not None:
            ndc_x, ndc_y = ndc_from_widget_xy(
                self._drag_start_x + offset_x,
                self._drag_start_y + offset_y,
                float(self._gl_area.get_width()),
                float(self._gl_area.get_height()),
            )
            origin, direction = session.screen_ray(ndc_x, ndc_y)
            res = self._editor.update_drag(
                self._canvas,
                origin,
                direction,
                self._last_ir.plan_center_in,
                shift=is_shift,
            )
            self._apply_action_result(res)
            return

        if self._drag_button == 3 or (self._drag_button == 2 and is_shift):
            session.pan_drag(dx, dy)
        elif self._drag_button in (1, 2):
            session.orbit_drag(dx, dy)
        self._gl_area.queue_render()

    def _on_drag_end(
        self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        self._drag_max_px = max(self._drag_max_px, math.hypot(offset_x, offset_y))
        btn = self._drag_button
        self._drag_button = 0

        if self._drag_editing:
            self._drag_editing = False
            self._syncing_from_3d = True
            try:
                res = self._editor.end_drag(self._canvas)
            finally:
                self._syncing_from_3d = False
            self._apply_action_result(res)
            return

        if btn == 1 and not self._walk_btn.get_active() and self._drag_max_px < 5.0:
            state = gesture.get_current_event_state()
            shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
            alt = bool(state & Gdk.ModifierType.ALT_MASK)
            hit, _origin, _dir = self._pick_at_widget_xy(
                self._drag_start_x + offset_x,
                self._drag_start_y + offset_y,
            )
            self._syncing_from_3d = True
            try:
                res = self._editor.handle_click(self._canvas, hit, shift=shift, alt=alt)
            finally:
                self._syncing_from_3d = False
            if res.commit_undo:
                res.needs_mesh_sync = True
            self._apply_action_result(res)

    def _on_scroll(
        self, _ctrl: Gtk.EventControllerScroll, _dx: float, dy: float
    ) -> bool:
        session = self._session
        if session is None:
            return False
        session.zoom_scroll(-dy)
        self._gl_area.queue_render()
        return True

    def _on_key_pressed(
        self,
        _ctrl: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        session = self._session
        if session is None:
            return False
        is_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        is_alt = bool(state & Gdk.ModifierType.ALT_MASK)

        if keyval == Gdk.KEY_Escape:
            if self._editor.active_drag is not None:
                self._drag_editing = False
                res = self._editor.cancel_drag(self._canvas)
                self._apply_action_result(res)
                return True
            ids = select_from_hit(self._canvas, None, extend=False)
            session.set_selected_entities(ids)
            self._set_hud_message("")
            self._gl_area.queue_render()
            return True

        if not self._walk_btn.get_active():
            if keyval in (Gdk.KEY_v, Gdk.KEY_V):
                self._select_btn.set_active(True)
                return True
            if keyval in (Gdk.KEY_o, Gdk.KEY_O):
                self._orbit_btn.set_active(True)
                return True
            if keyval in (Gdk.KEY_b, Gdk.KEY_B):
                self._paint_btn.set_active(True)
                return True
            if keyval in (Gdk.KEY_r, Gdk.KEY_R):
                step = 1.0 if is_alt else (-15.0 if is_shift else 15.0)
                self._syncing_from_3d = True
                try:
                    res = self._editor.rotate_selected_fixture(self._canvas, step)
                finally:
                    self._syncing_from_3d = False
                if res.handled or res.hud_message:
                    self._apply_action_result(res)
                    return True

        step = 0.45 if is_shift else 0.18
        moved = False
        if keyval in (Gdk.KEY_w, Gdk.KEY_W, Gdk.KEY_Up):
            session.walk_move(step, 0.0, 0.0)
            moved = True
        elif keyval in (Gdk.KEY_s, Gdk.KEY_S, Gdk.KEY_Down):
            session.walk_move(-step, 0.0, 0.0)
            moved = True
        elif keyval in (Gdk.KEY_a, Gdk.KEY_A, Gdk.KEY_Left):
            session.walk_move(0.0, -step, 0.0)
            moved = True
        elif keyval in (Gdk.KEY_d, Gdk.KEY_D, Gdk.KEY_Right):
            session.walk_move(0.0, step, 0.0)
            moved = True
        elif keyval in (Gdk.KEY_e, Gdk.KEY_E):
            session.walk_move(0.0, 0.0, step * 0.7)
            moved = True
        elif keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            session.walk_move(0.0, 0.0, -step * 0.7)
            moved = True
        if moved:
            self._gl_area.queue_render()
        return moved

    def _on_mode_toggled(self, btn: Gtk.ToggleButton) -> None:
        if not btn.get_active():
            return
        if self._walk_btn.get_active():
            cam_mode = "walkthrough"
            self._editor.set_tool("orbit")
            self._set_hud_message("Walkthrough: WASD move, Drag look")
        elif self._paint_btn.get_active():
            cam_mode = "orbit"
            self._editor.set_tool("paint")
            self._set_hud_message(
                f"Paint: {self._editor.brush.wall_finish} (Shift: Room | Alt: Sample)"
            )
        elif self._orbit_btn.get_active():
            cam_mode = "orbit"
            self._editor.set_tool("orbit")
            self._set_hud_message("Orbit mode: Left-drag orbits")
        else:
            cam_mode = "orbit"
            self._editor.set_tool("select")
            self._set_hud_message("Select / Edit mode (Right-drag orbits)")

        session = self._session
        if session is not None:
            session.set_camera_mode(cam_mode)
            self._gl_area.queue_render()

    def _on_view_preset_changed(
        self, combo: Gtk.DropDown, _pspec: object
    ) -> None:
        if self._updating_dropdowns or self._session is None:
            return
        presets = ["iso", "top", "front", "back", "left", "right"]
        idx = int(combo.get_selected())
        if 0 <= idx < len(presets):
            if self._walk_btn.get_active():
                self._select_btn.set_active(True)
            self._session.set_camera_preset(presets[idx])
            self._gl_area.queue_render()

    def _on_fit_clicked(self, _btn: Gtk.Button) -> None:
        if self._session is None:
            return
        if self._walk_btn.get_active():
            self._select_btn.set_active(True)
        self._session.fit_scene()
        self._gl_area.queue_render()

    def _on_room_jump_changed(
        self, combo: Gtk.DropDown, _pspec: object
    ) -> None:
        if self._updating_dropdowns or self._session is None:
            return
        idx = int(combo.get_selected())
        if 1 <= idx < len(self._room_centers):
            cx, cy, fz = self._room_centers[idx]
            self._walk_btn.set_active(True)
            self._session.jump_to_room(cx, cy, fz)
            self._gl_area.queue_render()

    def _on_level_changed(
        self, combo: Gtk.DropDown, _pspec: object
    ) -> None:
        if self._updating_dropdowns or self._session is None:
            return
        idx = int(combo.get_selected())
        if 0 <= idx < len(self._level_ids):
            lvl_id = self._level_ids[idx] or None
            self._session.set_dollhouse_level(lvl_id)
            self._gl_area.queue_render()

    def _on_auto_hide_toggled(self, btn: Gtk.ToggleButton) -> None:
        if self._session is not None:
            self._session.set_auto_hide_roofs(btn.get_active())
            self._gl_area.queue_render()

    def _on_style_changed(
        self, combo: Gtk.DropDown, _pspec: object
    ) -> None:
        if self._updating_dropdowns or self._session is None:
            return
        styles = ["textured", "clay", "sketch", "xray"]
        idx = int(combo.get_selected())
        if 0 <= idx < len(styles):
            self._session.set_render_style(styles[idx])
            self._gl_area.queue_render()

    def _on_sun_changed(self, scale: Gtk.Scale) -> None:
        if self._session is not None:
            self._session.set_time_of_day(float(scale.get_value()))
            self._gl_area.queue_render()

    def export_glb_to_path(self, output_path: str) -> int:
        """Compile current scene and export a `.glb` binary to ``output_path``."""
        curr = build_scene_ir_from_canvas(self._canvas)
        self._last_ir = curr
        self._dirty = False
        session = self._ensure_session()
        if session is not None:
            session.load_scene(curr.to_json())
            return session.export_glb(output_path)
        return native_3d.export_scene_glb(curr, output_path)
