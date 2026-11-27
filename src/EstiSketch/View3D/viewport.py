"""GTK4 ``Gtk.GLArea`` 3D viewport backed by the Rust ``EstiSketch._native_3d`` engine."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import native_3d  # noqa: E402
from ..scene_ir import (  # noqa: E402
    SceneIR,
    build_scene_ir_from_canvas,
    diff_scene_ir,
)


class Viewport3DWidget(Gtk.Overlay):
    """Embedded live OpenGL 3.3 3D viewport with camera, style, and dollhouse HUD."""

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
        self._last_ir: SceneIR | None = None
        self._dirty: bool = True
        self._sync_source_id: int | None = None
        self._gl_error: str | None = None
        self._drag_last_x: float = 0.0
        self._drag_last_y: float = 0.0
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
        self._gl_area.add_controller(drag)

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

    def _build_hud_bar(self) -> None:
        hud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hud.set_halign(Gtk.Align.CENTER)
        hud.set_valign(Gtk.Align.START)
        hud.set_margin_top(8)
        hud.set_margin_start(8)
        hud.set_margin_end(8)
        hud.add_css_class("toolbar")

        self._orbit_btn = Gtk.ToggleButton(label="Orbit")
        self._orbit_btn.set_active(True)
        self._orbit_btn.set_tooltip_text("Orbit / Dollhouse navigation")
        self._orbit_btn.connect("toggled", self._on_mode_toggled)
        hud.append(self._orbit_btn)

        self._walk_btn = Gtk.ToggleButton(label="Walk")
        self._walk_btn.set_group(self._orbit_btn)
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

        sun_lbl = Gtk.Label(label="Sun:")
        hud.append(sun_lbl)
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

    def _on_drag_begin(self, _gesture: Gtk.GestureDrag, _x: float, _y: float) -> None:
        self._gl_area.grab_focus()
        self._drag_last_x = 0.0
        self._drag_last_y = 0.0

    def _on_drag_update(
        self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        dx = offset_x - self._drag_last_x
        dy = offset_y - self._drag_last_y
        self._drag_last_x = offset_x
        self._drag_last_y = offset_y

        session = self._session
        if session is None:
            return
        btn = gesture.get_current_button()
        state = gesture.get_current_event_state()
        is_shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if btn == 3 or (btn == 2 and is_shift):
            session.pan_drag(dx, dy)
        else:
            session.orbit_drag(dx, dy)
        self._gl_area.queue_render()

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
        step = 0.45 if (state & Gdk.ModifierType.SHIFT_MASK) else 0.18
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

    def _on_mode_toggled(self, _btn: Gtk.ToggleButton) -> None:
        session = self._session
        if session is None:
            return
        mode = "walkthrough" if self._walk_btn.get_active() else "orbit"
        session.set_camera_mode(mode)
        self._gl_area.queue_render()

    def _on_view_preset_changed(
        self, combo: Gtk.DropDown, _pspec: object
    ) -> None:
        if self._updating_dropdowns or self._session is None:
            return
        presets = ["iso", "top", "front", "back", "left", "right"]
        idx = int(combo.get_selected())
        if 0 <= idx < len(presets):
            self._orbit_btn.set_active(True)
            self._session.set_camera_preset(presets[idx])
            self._gl_area.queue_render()

    def _on_fit_clicked(self, _btn: Gtk.Button) -> None:
        if self._session is None:
            return
        self._orbit_btn.set_active(True)
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
