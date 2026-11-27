"""GTK4 Multi-Style / Multi-Option Floor Plan Generator Dialog."""

from __future__ import annotations

import math
from typing import Callable, Optional

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from ..floor_plan_generator import (  # noqa: E402
    MAX_OPTIONS_PER_STYLE,
    MAX_STYLES,
    MAX_TOTAL_PLANS,
    VALID_BATHROOM_COUNTS,
    FloorPlanRequest,
    GeneratedFloorPlan,
    generate_floor_plans,
    list_styles,
)

_ROOM_TINTS: dict[str, tuple[float, float, float]] = {
    "kitchen": (0.98, 0.94, 0.84),
    "dining": (0.96, 0.91, 0.82),
    "living": (0.91, 0.95, 0.92),
    "bedroom": (0.90, 0.93, 0.98),
    "bathroom": (0.86, 0.95, 0.97),
    "hallway": (0.94, 0.94, 0.93),
    "office": (0.94, 0.91, 0.97),
    "utility": (0.92, 0.92, 0.94),
    "garage": (0.87, 0.88, 0.89),
}


def _plan_bounds(canvas: object, level_id: str) -> tuple[float, float, float, float]:
    """Return ``(min_x, min_y, max_x, max_y)`` in inches across walls and rooms on ``level_id``."""
    layer_to_lvl = {
        getattr(l, "id", ""): getattr(l, "level_id", "")
        for l in getattr(canvas, "layers", []) or []
    }
    xs: list[float] = []
    ys: list[float] = []
    for ws in getattr(canvas, "wall_sets", []) or []:
        for w in ws:
            if layer_to_lvl.get(getattr(w, "layer_id", ""), "") == level_id:
                xs.extend([float(w.start[0]), float(w.end[0])])
                ys.extend([float(w.start[1]), float(w.end[1])])
    for r in getattr(canvas, "rooms", []) or []:
        if layer_to_lvl.get(getattr(r, "layer_id", ""), "") == level_id:
            for px, py in getattr(r, "points", []) or []:
                xs.append(float(px))
                ys.append(float(py))
    if not xs:
        return (0.0, 0.0, 480.0, 360.0)
    return (min(xs), min(ys), max(xs), max(ys))


def _draw_plan_preview(
    _area: Gtk.DrawingArea,
    cr: cairo.Context,
    width: int,
    height: int,
    plan: GeneratedFloorPlan,
    level_index: int,
) -> None:
    """Render a clean architectural 2D preview thumbnail for ``plan``."""
    cr.save()
    try:
        cr.set_source_rgb(0.99, 0.99, 0.99)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        canvas = plan.canvas
        levels = getattr(canvas, "levels", []) or []
        if not levels:
            return
        idx = max(0, min(level_index, len(levels) - 1))
        lvl_id = str(getattr(levels[idx], "id", ""))
        layer_to_lvl = {
            getattr(l, "id", ""): getattr(l, "level_id", "")
            for l in getattr(canvas, "layers", []) or []
        }

        min_x, min_y, max_x, max_y = _plan_bounds(canvas, lvl_id)
        span_x = max(120.0, max_x - min_x)
        span_y = max(120.0, max_y - min_y)
        pad = 14.0
        scale = min((width - 2.0 * pad) / span_x, (height - 2.0 * pad) / span_y)
        ox = (width - span_x * scale) / 2.0 - min_x * scale
        oy = (height - span_y * scale) / 2.0 - min_y * scale

        def to_px(pt: tuple[float, float]) -> tuple[float, float]:
            return (ox + float(pt[0]) * scale, oy + float(pt[1]) * scale)

        # 1. Rooms
        for r in getattr(canvas, "rooms", []) or []:
            if layer_to_lvl.get(getattr(r, "layer_id", ""), "") != lvl_id:
                continue
            pts = getattr(r, "points", []) or []
            if len(pts) < 3:
                continue
            rgb = _ROOM_TINTS.get(getattr(r, "room_type", ""), (0.95, 0.95, 0.95))
            p0 = to_px(pts[0])
            cr.move_to(p0[0], p0[1])
            for pt in pts[1:]:
                p = to_px(pt)
                cr.line_to(p[0], p[1])
            cr.close_path()
            cr.set_source_rgb(*rgb)
            cr.fill()

        # 2. Fixtures
        for fx in getattr(canvas, "fixtures", []) or []:
            if layer_to_lvl.get(getattr(fx, "layer_id", ""), "") != lvl_id:
                continue
            if getattr(fx, "is_upper", False):
                continue
            corners = fx.world_corners(include_overhang=False)
            if len(corners) < 3:
                continue
            c0 = to_px(corners[0])
            cr.move_to(c0[0], c0[1])
            for pt in corners[1:]:
                p = to_px(pt)
                cr.line_to(p[0], p[1])
            cr.close_path()
            cr.set_source_rgba(0.55, 0.60, 0.66, 0.45)
            cr.fill_preserve()
            cr.set_source_rgba(0.32, 0.36, 0.42, 0.75)
            cr.set_line_width(0.8)
            cr.stroke()

        # 3. Stairs
        for st in getattr(canvas, "stairs", []) or []:
            s_lvl = getattr(st, "start_level_id", "") or layer_to_lvl.get(
                getattr(st, "layer_id", ""), ""
            )
            e_lvl = getattr(st, "end_level_id", "") or s_lvl
            if lvl_id not in (s_lvl, e_lvl):
                continue
            sx, sy = to_px(st.start_point)
            cr.set_source_rgb(0.45, 0.35, 0.25)
            cr.arc(sx, sy, max(3.5, 14.0 * scale), 0.0, 2.0 * math.pi)
            cr.stroke()

        # 4. Walls
        seen_walls: set[int] = set()
        for ws in getattr(canvas, "wall_sets", []) or []:
            for w in ws:
                if id(w) in seen_walls:
                    continue
                seen_walls.add(id(w))
                if layer_to_lvl.get(getattr(w, "layer_id", ""), "") != lvl_id:
                    continue
                p0 = to_px(w.start)
                p1 = to_px(w.end)
                cr.set_source_rgb(0.14, 0.16, 0.19)
                cr.set_line_width(max(1.2, float(w.width) * scale))
                cr.set_line_cap(cairo.LINE_CAP_SQUARE)
                cr.move_to(p0[0], p0[1])
                cr.line_to(p1[0], p1[1])
                cr.stroke()

        # 5. Windows & Doors
        for wall, win, ratio in getattr(canvas, "windows", []) or []:
            if layer_to_lvl.get(getattr(win, "layer_id", ""), "") != lvl_id:
                continue
            wx = float(wall.start[0]) + float(ratio) * (float(wall.end[0]) - float(wall.start[0]))
            wy = float(wall.start[1]) + float(ratio) * (float(wall.end[1]) - float(wall.start[1]))
            dx = float(wall.end[0]) - float(wall.start[0])
            dy = float(wall.end[1]) - float(wall.start[1])
            wlen = math.hypot(dx, dy) or 1.0
            ux, uy = dx / wlen, dy / wlen
            hw = float(win.width) * 0.5
            a = to_px((wx - hw * ux, wy - hw * uy))
            b = to_px((wx + hw * ux, wy + hw * uy))
            cr.set_source_rgb(0.28, 0.65, 0.88)
            cr.set_line_width(max(1.8, float(wall.width) * scale * 0.85))
            cr.move_to(a[0], a[1])
            cr.line_to(b[0], b[1])
            cr.stroke()

        for wall, door, ratio in getattr(canvas, "doors", []) or []:
            if layer_to_lvl.get(getattr(door, "layer_id", ""), "") != lvl_id:
                continue
            dx = float(wall.end[0]) - float(wall.start[0])
            dy = float(wall.end[1]) - float(wall.start[1])
            wlen = math.hypot(dx, dy) or 1.0
            ux, uy = dx / wlen, dy / wlen
            cx = float(wall.start[0]) + float(ratio) * dx
            cy = float(wall.start[1]) + float(ratio) * dy
            hw = float(door.width) * 0.5
            a = to_px((cx - hw * ux, cy - hw * uy))
            b = to_px((cx + hw * ux, cy + hw * uy))
            cr.set_source_rgb(0.99, 0.99, 0.99)
            cr.set_line_width(max(1.5, float(wall.width) * scale + 0.5))
            cr.move_to(a[0], a[1])
            cr.line_to(b[0], b[1])
            cr.stroke()
            cr.set_source_rgb(0.75, 0.35, 0.12)
            cr.set_line_width(1.2)
            cr.move_to(a[0], a[1])
            cr.line_to(b[0], b[1])
            cr.stroke()

        # 6. Room Names
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(max(6.5, min(9.5, 22.0 * scale)))
        for r in getattr(canvas, "rooms", []) or []:
            if layer_to_lvl.get(getattr(r, "layer_id", ""), "") != lvl_id:
                continue
            pts = getattr(r, "points", []) or []
            if len(pts) < 3:
                continue
            rcx = sum(p[0] for p in pts) / len(pts)
            rcy = sum(p[1] for p in pts) / len(pts)
            px, py = to_px((rcx, rcy))
            label = getattr(r, "name", "") or ""
            if not label:
                continue
            ext = cr.text_extents(label)
            cr.set_source_rgba(0.12, 0.14, 0.18, 0.85)
            cr.move_to(px - ext.width / 2.0, py + ext.height / 2.0)
            cr.show_text(label)
    finally:
        cr.restore()


class FloorPlanGeneratorDialog(Gtk.Window):
    """Interactive multi-style, multi-option floor plan generator window."""

    def __init__(
        self,
        parent: Optional[Gtk.Window],
        on_apply_plan: Callable[[GeneratedFloorPlan, bool], None],
    ) -> None:
        super().__init__(
            title="Auto-Populate Floor Plan Generator",
            transient_for=parent,
            modal=True,
        )
        self.on_apply_plan = on_apply_plan
        self._plans: list[GeneratedFloorPlan] = []
        self._selected_plan: Optional[GeneratedFloorPlan] = None
        self._preview_level_index: int = 0
        self._style_checks: dict[str, Gtk.CheckButton] = {}
        self._preview_areas: list[Gtk.DrawingArea] = []
        self._seed: int = 42
        self._refresh_source_id: Optional[int] = None
        self._text_refresh_source_id: Optional[int] = None
        self._initializing: bool = True

        self.set_default_size(1120, 740)
        self.connect("close-request", self._on_close_request)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_margin_top(12)
        outer.set_margin_bottom(12)
        outer.set_margin_start(12)
        outer.set_margin_end(12)
        self.set_child(outer)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_position(340)
        outer.append(paned)

        # Left Controls Panel
        controls_scroll = Gtk.ScrolledWindow()
        controls_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        controls_box.set_margin_end(12)
        controls_scroll.set_child(controls_box)
        paned.set_start_child(controls_scroll)

        prog_lbl = Gtk.Label()
        prog_lbl.set_markup("<b>Home Program</b>")
        prog_lbl.set_xalign(0.0)
        controls_box.append(prog_lbl)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        controls_box.append(grid)

        row = 0
        grid.attach(self._lbl("Bedrooms"), 0, row, 1, 1)
        self.bed_spin = Gtk.SpinButton.new_with_range(1, 5, 1)
        self.bed_spin.set_value(3)
        grid.attach(self.bed_spin, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Bathrooms"), 0, row, 1, 1)
        self.bath_combo = Gtk.ComboBoxText()
        for b in VALID_BATHROOM_COUNTS:
            self.bath_combo.append(f"{b:.1f}", f"{b:g} Bath")
        self.bath_combo.set_active_id("2.0")
        grid.attach(self.bath_combo, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Levels (Stories)"), 0, row, 1, 1)
        self.level_combo = Gtk.ComboBoxText()
        self.level_combo.append("1", "1 Story")
        self.level_combo.append("2", "2 Stories")
        self.level_combo.set_active_id("1")
        grid.attach(self.level_combo, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Garage Size"), 0, row, 1, 1)
        self.garage_combo = Gtk.ComboBoxText()
        self.garage_combo.append("0", "No Garage")
        self.garage_combo.append("1", "1-Car Garage")
        self.garage_combo.append("2", "2-Car Garage")
        self.garage_combo.append("3", "3-Car Garage")
        self.garage_combo.set_active_id("2")
        grid.attach(self.garage_combo, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Layout Concept"), 0, row, 1, 1)
        self.layout_concept_combo = Gtk.ComboBoxText()
        self.layout_concept_combo.append("style_default", "Style Default")
        self.layout_concept_combo.append("open", "Open Floor Plan")
        self.layout_concept_combo.append("traditional", "Traditional (Divided)")
        self.layout_concept_combo.set_active_id("style_default")
        grid.attach(self.layout_concept_combo, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Min Sq Ft"), 0, row, 1, 1)
        self.min_sqft_spin = Gtk.SpinButton.new_with_range(700, 4500, 100)
        self.min_sqft_spin.set_value(1400)
        grid.attach(self.min_sqft_spin, 1, row, 1, 1)
        row += 1

        grid.attach(self._lbl("Max Sq Ft"), 0, row, 1, 1)
        self.max_sqft_spin = Gtk.SpinButton.new_with_range(800, 5000, 100)
        self.max_sqft_spin.set_value(2000)
        grid.attach(self.max_sqft_spin, 1, row, 1, 1)
        row += 1

        self.min_sqft_spin.connect("value-changed", self._sync_sqft_bounds)
        self.max_sqft_spin.connect("value-changed", self._sync_sqft_bounds)
        self.min_sqft_spin.connect("changed", self._on_sqft_text_changed)
        self.max_sqft_spin.connect("changed", self._on_sqft_text_changed)
        self.bed_spin.connect("value-changed", lambda _s: self._schedule_refresh())
        self.bath_combo.connect("changed", lambda _c: self._schedule_refresh())
        self.level_combo.connect("changed", lambda _c: self._schedule_refresh())
        self.garage_combo.connect("changed", lambda _c: self._schedule_refresh())
        self.layout_concept_combo.connect("changed", lambda _c: self._schedule_refresh())

        # Optional Rooms
        self.dining_check = Gtk.CheckButton(label="Include Formal Dining Room")
        self.dining_check.set_active(True)
        self.dining_check.connect("toggled", lambda _b: self._schedule_refresh())
        controls_box.append(self.dining_check)

        self.office_check = Gtk.CheckButton(label="Include Home Office / Study")
        self.office_check.set_active(False)
        self.office_check.connect("toggled", lambda _b: self._schedule_refresh())
        controls_box.append(self.office_check)

        self.laundry_check = Gtk.CheckButton(label="Include Laundry Room")
        self.laundry_check.set_active(True)
        self.laundry_check.connect("toggled", lambda _b: self._schedule_refresh())
        controls_box.append(self.laundry_check)

        controls_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Styles & Options Caps
        self.style_header_lbl = Gtk.Label()
        self.style_header_lbl.set_xalign(0.0)
        controls_box.append(self.style_header_lbl)

        for idx, style in enumerate(list_styles()):
            chk = Gtk.CheckButton(label=f"{style.name} — {style.roof_pitch_rise}/12 {style.roof_type.title()}")
            chk.set_tooltip_text(style.description)
            chk.set_active(idx < 2)
            chk.connect("toggled", self._on_style_toggled, style.key)
            self._style_checks[style.key] = chk
            controls_box.append(chk)

        opt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        opt_row.append(self._lbl(f"Options / Style (1–{MAX_OPTIONS_PER_STYLE})"))
        self.options_spin = Gtk.SpinButton.new_with_range(1, MAX_OPTIONS_PER_STYLE, 1)
        self.options_spin.set_value(2)
        self.options_spin.connect("value-changed", self._on_options_changed)
        opt_row.append(self.options_spin)
        controls_box.append(opt_row)

        self.total_cap_lbl = Gtk.Label()
        self.total_cap_lbl.set_xalign(0.0)
        self.total_cap_lbl.add_css_class("dim-label")
        controls_box.append(self.total_cap_lbl)

        self.range_note_lbl = Gtk.Label(label="")
        self.range_note_lbl.set_xalign(0.0)
        self.range_note_lbl.set_wrap(True)
        self.range_note_lbl.set_visible(False)
        controls_box.append(self.range_note_lbl)

        gen_btn = Gtk.Button(label="Generate New Plans")
        gen_btn.add_css_class("suggested-action")
        gen_btn.connect("clicked", lambda _b: self.refresh_new_plans())
        controls_box.append(gen_btn)

        # Right Preview Panel
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_box.set_margin_start(12)
        paned.set_end_child(right_box)

        preview_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.results_lbl = Gtk.Label(label="")
        self.results_lbl.set_xalign(0.0)
        self.results_lbl.set_hexpand(True)
        preview_hdr.append(self.results_lbl)

        self.refresh_btn = Gtk.Button()
        refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        refresh_box.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        refresh_box.append(Gtk.Label(label="Refresh / New Plans"))
        self.refresh_btn.set_child(refresh_box)
        self.refresh_btn.set_tooltip_text("Generate a fresh set of floor plan layouts")
        self.refresh_btn.connect("clicked", lambda _b: self.refresh_new_plans())
        preview_hdr.append(self.refresh_btn)

        self.level_toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.level_toggle_box.add_css_class("linked")
        self.lvl1_btn = Gtk.ToggleButton(label="Level 1")
        self.lvl1_btn.set_active(True)
        self.lvl2_btn = Gtk.ToggleButton(label="Level 2")
        self.lvl2_btn.set_group(self.lvl1_btn)
        self.lvl1_btn.connect("toggled", lambda b: self._set_preview_level(0) if b.get_active() else None)
        self.lvl2_btn.connect("toggled", lambda b: self._set_preview_level(1) if b.get_active() else None)
        self.level_toggle_box.append(self.lvl1_btn)
        self.level_toggle_box.append(self.lvl2_btn)
        preview_hdr.append(self.level_toggle_box)
        right_box.append(preview_hdr)

        cards_scroll = Gtk.ScrolledWindow()
        cards_scroll.set_vexpand(True)
        cards_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(2)
        self.flowbox.set_min_children_per_line(1)
        self.flowbox.set_row_spacing(12)
        self.flowbox.set_column_spacing(12)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.connect("selected-children-changed", self._on_card_selected)
        cards_scroll.set_child(self.flowbox)
        right_box.append(cards_scroll)

        # Bottom Action Row
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.selected_lbl = Gtk.Label(label="Select a floor plan option above.")
        self.selected_lbl.set_xalign(0.0)
        self.selected_lbl.set_hexpand(True)
        bottom.append(self.selected_lbl)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _b: self.close())
        self.load_btn = Gtk.Button(label="Load Into Editor")
        self.load_btn.connect("clicked", lambda _b: self._apply_selected(save_as=False))
        self.save_new_btn = Gtk.Button(label="Load & Save As New Project...")
        self.save_new_btn.add_css_class("suggested-action")
        self.save_new_btn.connect("clicked", lambda _b: self._apply_selected(save_as=True))

        bottom.append(cancel_btn)
        bottom.append(self.load_btn)
        bottom.append(self.save_new_btn)
        outer.append(bottom)

        self._update_cap_labels()
        self._initializing = False
        self._regenerate()

    @staticmethod
    def _lbl(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_xalign(0.0)
        return lbl

    def _cancel_pending_refresh(self) -> None:
        if self._refresh_source_id is not None:
            GLib.source_remove(self._refresh_source_id)
            self._refresh_source_id = None
        if self._text_refresh_source_id is not None:
            GLib.source_remove(self._text_refresh_source_id)
            self._text_refresh_source_id = None

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        self._cancel_pending_refresh()
        return False

    def _commit_pending_sqft_edits(self) -> None:
        """Apply cleanly typed numeric text in sq ft spinbuttons before reading values."""
        for spin, lo_bound, hi_bound in (
            (self.min_sqft_spin, 700, 4500),
            (self.max_sqft_spin, 800, 5000),
        ):
            raw = spin.get_text().strip()
            try:
                parsed = int(round(float(raw)))
            except ValueError:
                continue
            if lo_bound <= parsed <= hi_bound:
                spin.update()

    def _on_sqft_text_changed(self, spin: Gtk.SpinButton) -> None:
        """Schedule a debounced spinbutton commit when the user types an in-range integer."""
        if self._initializing:
            return
        raw = spin.get_text().strip()
        try:
            parsed = int(round(float(raw)))
        except ValueError:
            return
        lo_bound, hi_bound = spin.get_range()
        if parsed < int(lo_bound) or parsed > int(hi_bound):
            return
        if self._text_refresh_source_id is not None:
            GLib.source_remove(self._text_refresh_source_id)
        self._text_refresh_source_id = GLib.timeout_add(
            400, self._commit_sqft_text_and_refresh, spin
        )

    def _commit_sqft_text_and_refresh(self, spin: Gtk.SpinButton) -> bool:
        self._text_refresh_source_id = None
        spin.update()
        self._schedule_refresh()
        return False

    def _schedule_refresh(self) -> None:
        """Debounce option changes so controls auto-refresh plans smoothly."""
        if self._initializing:
            return
        self._cancel_pending_refresh()
        self._refresh_source_id = GLib.timeout_add(120, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> bool:
        self._refresh_source_id = None
        self._regenerate()
        return False

    def refresh_new_plans(self) -> None:
        """Advance the layout seed and immediately generate a new batch of floor plans."""
        self._cancel_pending_refresh()
        self._commit_pending_sqft_edits()
        self._seed += 1
        self._regenerate()

    def _sync_sqft_bounds(self, spin: Gtk.SpinButton) -> None:
        lo = int(self.min_sqft_spin.get_value())
        hi = int(self.max_sqft_spin.get_value())
        if lo > hi:
            if spin is self.max_sqft_spin:
                self.min_sqft_spin.set_value(hi)
            else:
                self.max_sqft_spin.set_value(lo)
            return
        self._schedule_refresh()

    def _selected_styles(self) -> list[str]:
        return [k for k, chk in self._style_checks.items() if chk.get_active()]

    def _on_style_toggled(self, btn: Gtk.CheckButton, _key: str) -> None:
        selected = self._selected_styles()
        if not selected:
            btn.set_active(True)
            return
        if len(selected) > MAX_STYLES:
            btn.set_active(False)
            return
        self._update_cap_labels()
        self._schedule_refresh()

    def _on_options_changed(self, _spin: Gtk.SpinButton) -> None:
        self._update_cap_labels()
        self._schedule_refresh()

    def _update_cap_labels(self) -> None:
        selected = self._selected_styles()
        n_styles = len(selected)
        opts = int(self.options_spin.get_value())
        total = min(MAX_TOTAL_PLANS, n_styles * opts)
        self.style_header_lbl.set_markup(
            f"<b>Architectural Styles ({n_styles}/{MAX_STYLES} max)</b>"
        )
        self.total_cap_lbl.set_text(
            f"Will generate {total} option(s) (system cap: {MAX_TOTAL_PLANS} max)."
        )

    def _set_preview_level(self, idx: int) -> None:
        self._preview_level_index = idx
        for area in self._preview_areas:
            area.queue_draw()

    def _build_request(self) -> FloorPlanRequest:
        return FloorPlanRequest(
            bedrooms=int(self.bed_spin.get_value()),
            bathrooms=float(self.bath_combo.get_active_id() or "2.0"),
            levels=int(self.level_combo.get_active_id() or "1"),
            garage_cars=int(self.garage_combo.get_active_id() or "2"),
            min_sqft=int(self.min_sqft_spin.get_value()),
            max_sqft=int(self.max_sqft_spin.get_value()),
            include_office=self.office_check.get_active(),
            include_dining=self.dining_check.get_active(),
            include_laundry=self.laundry_check.get_active(),
            open_floor_plan=self.layout_concept_combo.get_active_id() or "style_default",
            styles=tuple(self._selected_styles()),
            options_per_style=int(self.options_spin.get_value()),
            seed=self._seed,
        )

    def _regenerate(self) -> None:
        self._commit_pending_sqft_edits()
        req = self._build_request()
        norm_req = req.normalized()
        self._plans = generate_floor_plans(req)
        self._preview_areas.clear()
        self._preview_level_index = 0
        self.lvl1_btn.set_active(True)
        self.level_toggle_box.set_visible(norm_req.levels > 1)

        min_actual = min((p.living_sqft for p in self._plans), default=0.0)
        if min_actual > norm_req.max_sqft + 15.0:
            self.range_note_lbl.set_markup(
                f"<span foreground='#b45309'>Note: Selected rooms require at least "
                f"~{min_actual:,.0f} sq ft (above Max {norm_req.max_sqft:,.0f} sq ft).</span>"
            )
            self.range_note_lbl.set_visible(True)
        else:
            self.range_note_lbl.set_visible(False)

        child = self.flowbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.flowbox.remove(child)
            child = nxt

        for plan in self._plans:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.set_margin_top(6)
            card.set_margin_bottom(6)
            card.set_margin_start(6)
            card.set_margin_end(6)

            area = Gtk.DrawingArea()
            area.set_content_width(330)
            area.set_content_height(215)
            area.set_draw_func(
                lambda a, cr, w, h, p=plan: _draw_plan_preview(
                    a, cr, w, h, p, self._preview_level_index
                )
            )
            self._preview_areas.append(area)
            card.append(area)

            title = Gtk.Label()
            title.set_markup(f"<b>{plan.style_name} — {plan.variant_name}</b>")
            title.set_xalign(0.0)
            card.append(title)

            meta = Gtk.Label(label=plan.summary)
            meta.set_xalign(0.0)
            card.append(meta)

            roof_lbl = Gtk.Label(label=f"Roof: {plan.roof_summary}")
            roof_lbl.set_xalign(0.0)
            roof_lbl.add_css_class("dim-label")
            card.append(roof_lbl)

            status = Gtk.Label()
            if not plan.layout_violations:
                status.set_markup("<span foreground='#2ec27e'>✓ Layout checks passed</span>")
            else:
                status.set_markup(
                    f"<span foreground='#e01b24'>⚠ {len(plan.layout_violations)} layout note(s)</span>"
                )
            status.set_xalign(0.0)
            card.append(status)

            self.flowbox.append(card)

        self.results_lbl.set_markup(f"<b>Generated {len(self._plans)} Floor Plan Option(s)</b>")
        first_child = self.flowbox.get_child_at_index(0)
        if first_child is not None:
            self.flowbox.select_child(first_child)

    def _on_card_selected(self, _flowbox: Gtk.FlowBox) -> None:
        sel = self.flowbox.get_selected_children()
        if not sel:
            self._selected_plan = None
            self.selected_lbl.set_text("Select a floor plan option above.")
            self.load_btn.set_sensitive(False)
            self.save_new_btn.set_sensitive(False)
            return
        idx = sel[0].get_index()
        if 0 <= idx < len(self._plans):
            self._selected_plan = self._plans[idx]
            self.selected_lbl.set_text(
                f"Selected: {self._selected_plan.style_name} — "
                f"{self._selected_plan.variant_name} ({self._selected_plan.living_sqft:,.0f} sq ft)"
            )
            self.load_btn.set_sensitive(True)
            self.save_new_btn.set_sensitive(True)

    def _apply_selected(self, save_as: bool) -> None:
        if self._selected_plan is None:
            return
        plan = self._selected_plan
        self.close()
        self.on_apply_plan(plan, save_as)


def show_floor_plan_generator_dialog(
    parent: Optional[Gtk.Window],
    on_apply_plan: Callable[[GeneratedFloorPlan, bool], None],
) -> FloorPlanGeneratorDialog:
    """Create and present the Multi-Style / Multi-Option Floor Plan Generator dialog."""
    dlg = FloorPlanGeneratorDialog(parent, on_apply_plan)
    dlg.present()
    return dlg
