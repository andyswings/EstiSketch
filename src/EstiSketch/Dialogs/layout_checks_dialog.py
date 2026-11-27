"""Architectural layout checks window displaying categorized design issues."""

from __future__ import annotations

from typing import Callable, Optional

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..geometry.design_checks import LayoutIssue, validate_project_layout_detailed  # noqa: E402


def _select_object_by_id(canvas: object, object_id: str) -> None:
    """Find and select ``object_id`` on ``canvas`` when present."""
    if not object_id:
        return
    for wset in getattr(canvas, "wall_sets", []) or []:
        for wall in wset:
            if getattr(wall, "identifier", "") == object_id:
                canvas.selected_items = [{"type": "wall", "object": wall}]  # type: ignore[attr-defined]
                return
    for wall, door, ratio in getattr(canvas, "doors", []) or []:
        if getattr(door, "identifier", "") == object_id:
            canvas.selected_items = [{"type": "door", "object": (wall, door, ratio)}]  # type: ignore[attr-defined]
            return
    for wall, win, ratio in getattr(canvas, "windows", []) or []:
        if getattr(win, "identifier", "") == object_id:
            canvas.selected_items = [{"type": "window", "object": (wall, win, ratio)}]  # type: ignore[attr-defined]
            return
    for attr, sel_type in (
        ("fixtures", "fixture"),
        ("rooms", "room"),
        ("stairs", "stair"),
    ):
        for obj in getattr(canvas, attr, []) or []:
            if getattr(obj, "identifier", "") == object_id:
                canvas.selected_items = [{"type": sel_type, "object": obj}]  # type: ignore[attr-defined]
                return


def _pan_canvas_to(canvas: object, pt: tuple[float, float]) -> None:
    """Center the 2D canvas viewport on ``pt`` in model inches."""
    if not hasattr(canvas, "get_width") or not hasattr(canvas, "get_height"):
        return
    width = float(canvas.get_width() or 0)  # type: ignore[attr-defined]
    height = float(canvas.get_height() or 0)  # type: ignore[attr-defined]
    zoom = float(getattr(canvas, "zoom", 1.0) or 1.0)
    ppi = float(getattr(getattr(canvas, "config", None), "PIXELS_PER_INCH", 2.0) or 2.0)
    scale = zoom * ppi
    if width <= 0.0 or height <= 0.0 or scale <= 0.0:
        return
    canvas.offset_x = (width / 2.0) / scale - float(pt[0])  # type: ignore[attr-defined]
    canvas.offset_y = (height / 2.0) / scale - float(pt[1])  # type: ignore[attr-defined]


class LayoutChecksDialog(Gtk.Window):
    """Non-modal window listing architectural layout checks with click-to-focus."""

    def __init__(
        self,
        parent: Optional[Gtk.Window],
        canvas: object,
        on_navigate: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(
            title="Architectural Layout Checks",
            transient_for=parent,
            modal=False,
        )
        self.canvas = canvas
        self.on_navigate = on_navigate
        self._issues: list[LayoutIssue] = []
        self._visible_issues: list[LayoutIssue] = []

        self.set_default_size(700, 520)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        self.set_child(root)

        # Summary + Category filter row
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.summary_label = Gtk.Label(label="")
        self.summary_label.set_xalign(0.0)
        self.summary_label.set_hexpand(True)
        top_bar.append(self.summary_label)

        filter_lbl = Gtk.Label(label="Category:")
        top_bar.append(filter_lbl)

        self._categories: list[str] = ["All"]
        self._cat_model = Gtk.StringList.new(self._categories)
        self.category_dropdown = Gtk.DropDown(model=self._cat_model)
        self.category_dropdown.connect("notify::selected", self._on_filter_changed)
        top_bar.append(self.category_dropdown)
        root.append(top_bar)

        # Scrollable issue list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.set_child(self.listbox)
        root.append(scrolled)

        hint_lbl = Gtk.Label(
            label="Double-click or press Enter on an issue to focus that level and location."
        )
        hint_lbl.set_xalign(0.0)
        hint_lbl.add_css_class("dim-label")
        root.append(hint_lbl)

        # Bottom action buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_row.set_halign(Gtk.Align.END)
        recheck_btn = Gtk.Button(label="Re-check")
        recheck_btn.connect("clicked", lambda _b: self.refresh())
        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _b: self.close())
        btn_row.append(recheck_btn)
        btn_row.append(close_btn)
        root.append(btn_row)

        self.refresh()

    def refresh(self) -> None:
        """Re-run ``validate_project_layout_detailed`` and populate the UI list."""
        self._issues = validate_project_layout_detailed(self.canvas)
        cats = ["All"] + sorted({issue.category for issue in self._issues})
        if cats != self._categories:
            self._categories = cats
            self._cat_model = Gtk.StringList.new(cats)
            self.category_dropdown.set_model(self._cat_model)
            self.category_dropdown.set_selected(0)

        if not self._issues:
            self.summary_label.set_markup(
                "<b>All checks passed</b> — 0 layout issues found."
            )
        else:
            self.summary_label.set_markup(
                f"<b>{len(self._issues)} layout issue(s) found</b>"
            )
        self._populate_rows()

    def _selected_category(self) -> str:
        idx = int(self.category_dropdown.get_selected())
        if 0 <= idx < len(self._categories):
            return self._categories[idx]
        return "All"

    def _on_filter_changed(self, _dropdown: Gtk.DropDown, _pspec: object) -> None:
        self._populate_rows()

    def _populate_rows(self) -> None:
        child = self.listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt

        cat = self._selected_category()
        self._visible_issues = [
            issue for issue in self._issues if cat == "All" or issue.category == cat
        ]

        if not self._visible_issues:
            empty_row = Gtk.ListBoxRow()
            empty_row.set_selectable(False)
            lbl = Gtk.Label(label="No issues in this category.")
            lbl.set_margin_top(16)
            lbl.set_margin_bottom(16)
            empty_row.set_child(lbl)
            self.listbox.append(empty_row)
            return

        for issue in self._visible_issues:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(8)
            box.set_margin_end(8)

            badge = Gtk.Label(label=f"[{issue.category}]")
            badge.set_xalign(0.0)
            badge.set_valign(Gtk.Align.START)
            badge.add_css_class("error" if issue.severity == "error" else "dim-label")
            box.append(badge)

            msg_lbl = Gtk.Label(label=issue.message)
            msg_lbl.set_xalign(0.0)
            msg_lbl.set_wrap(True)
            msg_lbl.set_hexpand(True)
            box.append(msg_lbl)

            row.set_child(box)
            self.listbox.append(row)

    def _on_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        idx = row.get_index()
        if idx < 0 or idx >= len(self._visible_issues):
            return
        issue = self._visible_issues[idx]

        if issue.level_id and hasattr(self.canvas, "set_active_level"):
            self.canvas.set_active_level(issue.level_id)  # type: ignore[attr-defined]
        _select_object_by_id(self.canvas, issue.object_id)
        if issue.location_in is not None:
            _pan_canvas_to(self.canvas, issue.location_in)
        if hasattr(self.canvas, "emit"):
            self.canvas.emit("selection-changed", getattr(self.canvas, "selected_items", []))  # type: ignore[attr-defined]
        if hasattr(self.canvas, "queue_draw"):
            self.canvas.queue_draw()  # type: ignore[attr-defined]
        if self.on_navigate is not None:
            self.on_navigate()


def show_layout_checks_dialog(
    parent: Optional[Gtk.Window],
    canvas: object,
    on_navigate: Optional[Callable[[], None]] = None,
) -> LayoutChecksDialog:
    """Create and present the non-modal architectural layout checks window."""
    dlg = LayoutChecksDialog(parent, canvas, on_navigate=on_navigate)
    dlg.present()
    return dlg
