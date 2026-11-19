"""Phase 8: Interactive Material Takeoff Dialog backed by TakeoffEngine."""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # type: ignore

from ..TakeoffEngine import (
    ALL_DEFAULTS,
    AssumptionSet,
    LineItem,
    ReferenceTakeoff,
    compare_to_reference,
    export_takeoff_csv,
    export_takeoff_json,
    run_takeoff,
)
from ..TakeoffEngine.line_item import NONE


def _ensure_takeoff_state(canvas: Any) -> Dict[str, Any]:
    state = getattr(canvas, "takeoff_state", None)
    if not isinstance(state, dict):
        state = {}
        canvas.takeoff_state = state
    state.setdefault("assumptions", {})
    state.setdefault("overrides", {})
    state.setdefault("custom_items", [])
    state.setdefault("reference", None)
    return state


def _custom_line_items(state: Dict[str, Any]) -> List[LineItem]:
    items: List[LineItem] = []
    for idx, rec in enumerate(state.get("custom_items", [])):
        item_id = rec.get("id") or f"custom_{idx}"
        qty = float(rec.get("qty", 0.0))
        items.append(
            LineItem(
                id=item_id,
                description=str(rec.get("description", "Custom item")),
                category=str(rec.get("category", "Custom")),
                unit=str(rec.get("unit", "ea")),
                formula=lambda m, a, q=qty: q,
                explanation=str(rec.get("explanation", "Manual custom line item")),
                rounding=NONE,
            )
        )
    return items


def _fmt_num(val: float) -> str:
    if abs(val - round(val)) < 1e-6:
        return f"{int(round(val))}"
    return f"{val:.2f}"


class TakeoffController:
    """Testable controller for the Takeoff Dialog state & actions."""

    def __init__(self, canvas: Any):
        self.canvas = canvas
        self.state = _ensure_takeoff_state(canvas)
        self.result = None
        self.checks: List[Any] = []
        self.measurements: Dict[str, Any] = {}
        self.recompute()

    def build_assumptions(self) -> AssumptionSet:
        defaults = dict(ALL_DEFAULTS)
        cfg = getattr(self.canvas, "config", None)
        if getattr(cfg, "TAKEOFF_CEILING_TYPE", "vaulted") == "flat":
            defaults["ceiling_vaulted"] = 0.0
            defaults["include_gable_walls_in_interior"] = 0.0
        a = AssumptionSet(defaults)
        for k, v in self.state.get("assumptions", {}).items():
            if k in ALL_DEFAULTS:
                try:
                    a.set_project(k, float(v))
                except (TypeError, ValueError):
                    pass
        return a

    def get_ceiling_type(self) -> str:
        return "vaulted" if self.build_assumptions().get("ceiling_vaulted") >= 0.5 else "flat"

    def set_ceiling_type(self, ceiling_type: str) -> None:
        is_vaulted = 1.0 if ceiling_type == "vaulted" else 0.0
        self.state["assumptions"]["ceiling_vaulted"] = is_vaulted
        self.state["assumptions"]["include_gable_walls_in_interior"] = is_vaulted
        self.recompute()

    def recompute(self) -> None:
        a = self.build_assumptions()
        extra = _custom_line_items(self.state)
        self.result, self.checks, self.measurements = run_takeoff(
            self.canvas,
            assumptions=a,
            overrides=self.state.get("overrides", {}),
            extra_items=extra,
        )

    def set_override(self, item_id: str, value: float) -> None:
        lr = self.result.by_id(item_id)
        self.state["overrides"][item_id] = {
            "value": float(value),
            "computed_at_override": float(lr.computed),
        }
        self.recompute()

    def keep_override(self, item_id: str) -> None:
        if item_id in self.state["overrides"]:
            lr = self.result.by_id(item_id)
            self.state["overrides"][item_id]["computed_at_override"] = float(lr.computed)
            self.recompute()

    def clear_override(self, item_id: str) -> None:
        self.state["overrides"].pop(item_id, None)
        self.recompute()

    def set_assumption(self, key: str, value: float) -> None:
        self.state["assumptions"][key] = float(value)
        self.recompute()

    def reset_assumption(self, key: str) -> None:
        self.state["assumptions"].pop(key, None)
        self.recompute()

    def add_custom_item(self, description: str, category: str, qty: float, unit: str = "ea") -> str:
        idx = len(self.state["custom_items"]) + 1
        item_id = f"custom_{idx}"
        existing = {rec.get("id") for rec in self.state["custom_items"]}
        while item_id in existing:
            idx += 1
            item_id = f"custom_{idx}"
        self.state["custom_items"].append({
            "id": item_id,
            "description": description.strip() or "Custom item",
            "category": category.strip() or "Custom",
            "qty": float(qty),
            "unit": unit.strip() or "ea",
        })
        self.recompute()
        return item_id

    def remove_custom_item(self, item_id: str) -> None:
        self.state["custom_items"] = [
            rec for rec in self.state["custom_items"] if rec.get("id") != item_id
        ]
        self.state["overrides"].pop(item_id, None)
        self.recompute()

    def save_reference(self, name: str = "project_reference", export_path: Optional[str] = None) -> ReferenceTakeoff:
        ref = ReferenceTakeoff(
            name=name,
            values={r.item.id: r.final for r in self.result.results},
            assumptions=dict(self.state.get("assumptions", {})),
            computed_at_save={r.item.id: r.computed for r in self.result.results},
        )
        self.state["reference"] = json.loads(ref.to_json())
        if export_path:
            ref.save(export_path)
        return ref

    def get_reference(self) -> Optional[ReferenceTakeoff]:
        raw = self.state.get("reference")
        if not isinstance(raw, dict) or not raw.get("values"):
            return None
        return ReferenceTakeoff(
            name=str(raw.get("name", "reference")),
            values={k: float(v) for k, v in raw.get("values", {}).items()},
            assumptions={k: float(v) for k, v in raw.get("assumptions", {}).items()},
            computed_at_save={k: float(v) for k, v in raw.get("computed_at_save", {}).items()},
        )


def create_takeoff_dialog(parent: Optional[Gtk.Window], canvas: Any) -> Gtk.Window:
    """Create the interactive Material Takeoff window backed by TakeoffEngine."""
    ctrl = TakeoffController(canvas)

    win = Gtk.Window(title="Material Takeoff Engine", transient_for=parent, modal=False)
    win.set_default_size(980, 680)
    win._controller = ctrl  # type: ignore[attr-defined]

    root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    root_box.set_margin_start(12)
    root_box.set_margin_end(12)
    root_box.set_margin_top(12)
    root_box.set_margin_bottom(12)
    win.set_child(root_box)

    notebook = Gtk.Notebook()
    notebook.set_hexpand(True)
    notebook.set_vexpand(True)
    root_box.append(notebook)

    # ── TAB 1: TAKEOFF TABLE ──────────────────────────────────────────
    tab1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    tab1.set_margin_start(8)
    tab1.set_margin_end(8)
    tab1.set_margin_top(8)
    tab1.set_margin_bottom(8)

    filter_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    filter_bar.append(Gtk.Label(label="Trade:"))
    cat_model = Gtk.StringList.new(["All Trades"])
    cat_dropdown = Gtk.DropDown(model=cat_model)
    filter_bar.append(cat_dropdown)

    filter_bar.append(Gtk.Label(label="Ceiling:"))
    ceiling_model = Gtk.StringList.new(["Vaulted", "Flat"])
    ceiling_dropdown = Gtk.DropDown(model=ceiling_model)
    ceiling_dropdown.set_selected(0 if ctrl.get_ceiling_type() == "vaulted" else 1)
    filter_bar.append(ceiling_dropdown)

    search_entry = Gtk.SearchEntry()
    search_entry.set_placeholder_text("Filter line items...")
    search_entry.set_hexpand(True)
    filter_bar.append(search_entry)

    btn_recalc = Gtk.Button(label="Recalculate")
    filter_bar.append(btn_recalc)

    btn_add_custom = Gtk.Button(label="+ Add Custom Item")
    filter_bar.append(btn_add_custom)
    tab1.append(filter_bar)

    # Column header
    hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    hdr.set_margin_start(6)
    hdr.set_margin_end(6)
    for text, width, hexp in [
        ("Description (hover for formula)", 340, True),
        ("Computed", 110, False),
        ("Final / Override", 130, False),
        ("Status", 200, False),
    ]:
        lbl = Gtk.Label(xalign=0.0)
        lbl.set_markup(f"<b>{html.escape(text)}</b>")
        lbl.set_size_request(width, -1)
        lbl.set_hexpand(hexp)
        hdr.append(lbl)
    tab1.append(hdr)
    tab1.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)
    scroll1 = Gtk.ScrolledWindow()
    scroll1.set_vexpand(True)
    scroll1.set_hexpand(True)
    scroll1.set_child(list_box)
    tab1.append(scroll1)

    status_bar = Gtk.Label(xalign=0.0)
    tab1.append(status_bar)

    # Bottom export / reference bar
    action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_export_csv = Gtk.Button(label="Export CSV")
    btn_export_json = Gtk.Button(label="Export JSON")
    btn_save_ref = Gtk.Button(label="Save as Reference Takeoff")
    action_bar.append(btn_export_csv)
    action_bar.append(btn_export_json)
    action_bar.append(btn_save_ref)
    tab1.append(action_bar)

    # ── TAB 2: ASSUMPTIONS ────────────────────────────────────────────
    tab2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    tab2.set_margin_start(8)
    tab2.set_margin_end(8)
    tab2.set_margin_top(8)
    tab2.set_margin_bottom(8)

    assump_search = Gtk.SearchEntry()
    assump_search.set_placeholder_text("Filter assumptions (e.g. stud, paint, rebar, roof)...")
    tab2.append(assump_search)

    assump_list = Gtk.ListBox()
    assump_list.set_selection_mode(Gtk.SelectionMode.NONE)
    scroll2 = Gtk.ScrolledWindow()
    scroll2.set_vexpand(True)
    scroll2.set_hexpand(True)
    scroll2.set_child(assump_list)
    tab2.append(scroll2)

    # ── TAB 3: CHECKS & REFERENCE VARIANCE ────────────────────────────
    tab3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    tab3.set_margin_start(8)
    tab3.set_margin_end(8)
    tab3.set_margin_top(8)
    tab3.set_margin_bottom(8)

    checks_hdr = Gtk.Label(xalign=0.0)
    checks_hdr.set_markup("<b>Sanity Checks</b>")
    tab3.append(checks_hdr)

    checks_list = Gtk.ListBox()
    checks_list.set_selection_mode(Gtk.SelectionMode.NONE)
    scroll3a = Gtk.ScrolledWindow()
    scroll3a.set_min_content_height(150)
    scroll3a.set_vexpand(False)
    scroll3a.set_child(checks_list)
    tab3.append(scroll3a)

    var_hdr = Gtk.Label(xalign=0.0)
    var_hdr.set_markup("<b>Reference Takeoff Variance</b>")
    tab3.append(var_hdr)

    var_list = Gtk.ListBox()
    var_list.set_selection_mode(Gtk.SelectionMode.NONE)
    scroll3b = Gtk.ScrolledWindow()
    scroll3b.set_vexpand(True)
    scroll3b.set_child(var_list)
    tab3.append(scroll3b)

    checks_tab_label = Gtk.Label(label="Checks & Reference")
    notebook.append_page(tab1, Gtk.Label(label="Takeoff Table"))
    notebook.append_page(tab2, Gtk.Label(label="Assumptions"))
    notebook.append_page(tab3, checks_tab_label)

    # Close button at bottom
    bottom_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    bottom_row.set_halign(Gtk.Align.END)
    btn_close = Gtk.Button(label="Close")
    btn_close.connect("clicked", lambda _b: win.destroy())
    bottom_row.append(btn_close)
    root_box.append(bottom_row)

    # ── REFRESH HELPERS ───────────────────────────────────────────────
    def _clear_listbox(lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            lb.remove(child)
            child = nxt

    def _populate_categories() -> None:
        cats = ["All Trades"] + list(ctrl.result.by_category().keys())
        current_idx = cat_dropdown.get_selected()
        current_name = cat_model.get_string(current_idx) if current_idx < cat_model.get_n_items() else "All Trades"
        cat_model.splice(0, cat_model.get_n_items(), cats)
        if current_name in cats:
            cat_dropdown.set_selected(cats.index(current_name))
        else:
            cat_dropdown.set_selected(0)

    def _refresh_table() -> None:
        _clear_listbox(list_box)
        sel_idx = cat_dropdown.get_selected()
        sel_cat = cat_model.get_string(sel_idx) if sel_idx < cat_model.get_n_items() else "All Trades"
        query = search_entry.get_text().strip().lower()
        custom_ids = {rec.get("id") for rec in ctrl.state.get("custom_items", [])}

        shown = 0
        for cat, rows in ctrl.result.by_category().items():
            if sel_cat != "All Trades" and cat != sel_cat:
                continue
            filtered = [
                r for r in rows
                if not query or query in r.item.description.lower() or query in r.item.id.lower()
            ]
            if not filtered:
                continue

            cat_lbl = Gtk.Label(xalign=0.0)
            cat_lbl.set_markup(f"<b>{html.escape(cat)}</b>")
            cat_lbl.set_margin_top(6)
            cat_lbl.set_margin_bottom(2)
            cat_lbl.set_margin_start(4)
            list_box.append(cat_lbl)

            for r in filtered:
                shown += 1
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row_box.set_margin_start(6)
                row_box.set_margin_end(6)
                row_box.set_margin_top(2)
                row_box.set_margin_bottom(2)

                desc_lbl = Gtk.Label(label=r.item.description, xalign=0.0)
                desc_lbl.set_size_request(340, -1)
                desc_lbl.set_hexpand(True)
                if r.item.explanation:
                    desc_lbl.set_tooltip_text(f"{r.item.id}\n{r.item.explanation}")
                row_box.append(desc_lbl)

                comp_lbl = Gtk.Label(label=f"{_fmt_num(r.computed)} {r.item.unit}", xalign=0.0)
                comp_lbl.set_size_request(110, -1)
                row_box.append(comp_lbl)

                entry = Gtk.Entry()
                entry.set_text(_fmt_num(r.final))
                entry.set_size_request(130, -1)

                def _on_commit(ent, item_id=r.item.id, comp_val=r.computed):
                    txt = ent.get_text().strip()
                    if not txt:
                        ctrl.clear_override(item_id)
                        _refresh_all()
                        return
                    try:
                        val = float(txt)
                    except ValueError:
                        ent.set_text(_fmt_num(comp_val))
                        return
                    if abs(val - comp_val) < 1e-6:
                        ctrl.clear_override(item_id)
                    else:
                        ctrl.set_override(item_id, val)
                    _refresh_all()

                entry.connect("activate", _on_commit)
                row_box.append(entry)

                status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                status_box.set_size_request(200, -1)
                if r.error:
                    st = Gtk.Label(xalign=0.0)
                    st.set_markup(f"<span foreground='red'>Error: {html.escape(r.error)}</span>")
                    status_box.append(st)
                elif r.stale:
                    st = Gtk.Label(xalign=0.0)
                    st.set_markup(f"<span foreground='orange'><b>STALE</b> (was {_fmt_num(r.old_computed or 0)})</span>")
                    status_box.append(st)
                    b_keep = Gtk.Button(label="Keep")
                    b_keep.connect("clicked", lambda _b, iid=r.item.id: (ctrl.keep_override(iid), _refresh_all()))
                    b_rst = Gtk.Button(label="Reset")
                    b_rst.connect("clicked", lambda _b, iid=r.item.id: (ctrl.clear_override(iid), _refresh_all()))
                    status_box.append(b_keep)
                    status_box.append(b_rst)
                elif r.override is not None:
                    st = Gtk.Label(xalign=0.0)
                    st.set_markup("<span foreground='#2563eb'><b>Override</b></span>")
                    status_box.append(st)
                    b_rst = Gtk.Button(label="Reset")
                    b_rst.connect("clicked", lambda _b, iid=r.item.id: (ctrl.clear_override(iid), _refresh_all()))
                    status_box.append(b_rst)
                else:
                    st = Gtk.Label(label="Auto", xalign=0.0)
                    status_box.append(st)

                if r.item.id in custom_ids:
                    b_del = Gtk.Button(label="Delete")
                    b_del.connect("clicked", lambda _b, iid=r.item.id: (ctrl.remove_custom_item(iid), _refresh_all()))
                    status_box.append(b_del)

                row_box.append(status_box)
                list_box.append(row_box)

        n_over = len(ctrl.state.get("overrides", {}))
        n_stale = sum(1 for r in ctrl.result.results if r.stale)
        status_bar.set_text(
            f"Showing {shown} of {len(ctrl.result.results)} line items | "
            f"{n_over} override(s) | {n_stale} stale | {len(ctrl.checks)} check(s)"
        )

    _BOOL_KEYS = {
        "ceiling_vaulted",
        "include_gable_walls_in_interior",
        "deduct_openings",
        "use_interior_dimensions",
        "thickened_count_full_depth",
    }
    _CHOICE_KEYS = {
        "roof_framing_method": ["Trusses", "Stick-framed", "Auto"],
    }
    _syncing_ui = [False]

    def _refresh_assumptions() -> None:
        _clear_listbox(assump_list)
        q = assump_search.get_text().strip().lower()
        proj = ctrl.state.get("assumptions", {})
        resolved_defaults = ctrl.build_assumptions().global_defaults
        for key in sorted(ALL_DEFAULTS.keys()):
            if q and q not in key.lower():
                continue
            default_val = resolved_defaults.get(key, ALL_DEFAULTS[key])
            cur_val = float(proj.get(key, default_val))
            is_mod = key in proj

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(6)
            row.set_margin_end(6)
            row.set_margin_top(2)
            row.set_margin_bottom(2)

            k_lbl = Gtk.Label(xalign=0.0)
            k_lbl.set_markup(f"<b>{html.escape(key)}</b>" if is_mod else html.escape(key))
            k_lbl.set_size_request(300, -1)
            k_lbl.set_hexpand(True)
            row.append(k_lbl)

            if key in _BOOL_KEYS:
                d_txt = "On" if default_val >= 0.5 else "Off"
                d_lbl = Gtk.Label(label=f"default: {d_txt}", xalign=0.0)
                d_lbl.set_size_request(130, -1)
                row.append(d_lbl)

                sw = Gtk.Switch()
                sw.set_active(cur_val >= 0.5)
                sw.set_halign(Gtk.Align.START)

                def _on_sw(widget, _pspec, k=key, dv=default_val):
                    val = 1.0 if widget.get_active() else 0.0
                    if abs(val - dv) < 1e-9:
                        ctrl.reset_assumption(k)
                    else:
                        ctrl.set_assumption(k, val)
                    _refresh_all()

                sw.connect("notify::active", _on_sw)
                row.append(sw)
            elif key in _CHOICE_KEYS:
                choices = _CHOICE_KEYS[key]
                d_lbl = Gtk.Label(label=f"default: {choices[int(default_val)]}", xalign=0.0)
                d_lbl.set_size_request(130, -1)
                row.append(d_lbl)

                dd = Gtk.DropDown(model=Gtk.StringList.new(choices))
                dd.set_selected(max(0, min(len(choices) - 1, int(round(cur_val)))))

                def _on_choice(widget, _pspec, k=key, dv=default_val):
                    val = float(widget.get_selected())
                    if abs(val - dv) < 1e-9:
                        ctrl.reset_assumption(k)
                    else:
                        ctrl.set_assumption(k, val)
                    _refresh_all()

                dd.connect("notify::selected", _on_choice)
                row.append(dd)
            else:
                d_lbl = Gtk.Label(label=f"default: {_fmt_num(default_val)}", xalign=0.0)
                d_lbl.set_size_request(130, -1)
                row.append(d_lbl)

                ent = Gtk.Entry()
                ent.set_text(_fmt_num(cur_val))
                ent.set_size_request(120, -1)

                def _on_a_commit(e, k=key, dv=default_val):
                    try:
                        val = float(e.get_text().strip())
                    except ValueError:
                        e.set_text(_fmt_num(dv))
                        return
                    if abs(val - dv) < 1e-9:
                        ctrl.reset_assumption(k)
                    else:
                        ctrl.set_assumption(k, val)
                    _refresh_all()

                ent.connect("activate", _on_a_commit)
                row.append(ent)

            if is_mod:
                b_rst = Gtk.Button(label="Reset")
                b_rst.connect("clicked", lambda _b, k=key: (ctrl.reset_assumption(k), _refresh_all()))
                row.append(b_rst)

            assump_list.append(row)

    def _refresh_checks_and_ref() -> None:
        _clear_listbox(checks_list)
        if not ctrl.checks:
            ok = Gtk.Label(label="All sanity checks passed.", xalign=0.0)
            ok.set_margin_start(6)
            checks_list.append(ok)
        else:
            for ch in ctrl.checks:
                lbl = Gtk.Label(xalign=0.0)
                lbl.set_wrap(True)
                color = "red" if ch.severity == "error" else "orange"
                lbl.set_markup(
                    f"<span foreground='{color}'><b>[{html.escape(ch.severity.upper())}]</b></span> "
                    f"<b>{html.escape(ch.name)}:</b> {html.escape(ch.message)}"
                )
                lbl.set_margin_start(6)
                lbl.set_margin_top(2)
                checks_list.append(lbl)

        checks_tab_label.set_text(
            f"Checks ({len(ctrl.checks)}) & Reference" if ctrl.checks else "Checks & Reference"
        )

        _clear_listbox(var_list)
        ref = ctrl.get_reference()
        if ref is None:
            empty = Gtk.Label(
                label="No reference takeoff saved for this project yet. Use 'Save as Reference Takeoff' on Tab 1.",
                xalign=0.0,
            )
            empty.set_margin_start(6)
            var_list.append(empty)
            return

        variances = compare_to_reference(ctrl.result, ref)
        for vp in variances:
            if abs(vp.diff) < 1e-6:
                continue
            lbl = Gtk.Label(
                label=f"{vp.item_id}: engine={_fmt_num(vp.engine)}, ref={_fmt_num(vp.reference)}, "
                      f"diff={vp.diff:+.2f} ({vp.pct:+.1f}%)",
                xalign=0.0,
            )
            lbl.set_margin_start(6)
            var_list.append(lbl)
        if var_list.get_first_child() is None:
            lbl = Gtk.Label(label=f"All {len(variances)} lines match reference '{ref.name}' (0% variance).", xalign=0.0)
            lbl.set_margin_start(6)
            var_list.append(lbl)

    def _refresh_all() -> None:
        _syncing_ui[0] = True
        try:
            ceiling_dropdown.set_selected(0 if ctrl.get_ceiling_type() == "vaulted" else 1)
        finally:
            _syncing_ui[0] = False
        _populate_categories()
        _refresh_table()
        _refresh_assumptions()
        _refresh_checks_and_ref()

    # ── SIGNALS ───────────────────────────────────────────────────────
    def _on_ceiling_changed(_dd, _pspec):
        if _syncing_ui[0]:
            return
        ctrl.set_ceiling_type("vaulted" if ceiling_dropdown.get_selected() == 0 else "flat")
        _refresh_all()

    ceiling_dropdown.connect("notify::selected", _on_ceiling_changed)
    cat_dropdown.connect("notify::selected", lambda _d, _p: _refresh_table())
    search_entry.connect("search-changed", lambda _e: _refresh_table())
    assump_search.connect("search-changed", lambda _e: _refresh_assumptions())
    btn_recalc.connect("clicked", lambda _b: (ctrl.recompute(), _refresh_all()))

    def _on_add_custom(_btn):
        dlg = Gtk.Window(title="Add Custom Line Item", transient_for=win, modal=True)
        dlg.set_default_size(360, 220)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        dlg.set_child(box)

        e_desc = Gtk.Entry(placeholder_text="Description (e.g. Simpson hurricane ties)")
        e_cat = Gtk.Entry(text="Custom", placeholder_text="Category")
        e_qty = Gtk.Entry(text="1", placeholder_text="Quantity")
        e_unit = Gtk.Entry(text="ea", placeholder_text="Unit")
        for w in (e_desc, e_cat, e_qty, e_unit):
            box.append(w)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btns.set_halign(Gtk.Align.END)
        b_cancel = Gtk.Button(label="Cancel")
        b_ok = Gtk.Button(label="Add")
        b_cancel.connect("clicked", lambda _b: dlg.destroy())

        def _commit(_b):
            try:
                q = float(e_qty.get_text().strip() or "0")
            except ValueError:
                q = 0.0
            ctrl.add_custom_item(e_desc.get_text(), e_cat.get_text(), q, e_unit.get_text())
            _refresh_all()
            dlg.destroy()

        b_ok.connect("clicked", _commit)
        btns.append(b_cancel)
        btns.append(b_ok)
        box.append(btns)
        dlg.present()

    btn_add_custom.connect("clicked", _on_add_custom)

    def _choose_save_path(title: str, default_name: str, callback) -> None:
        fd = Gtk.FileDialog(title=title)
        fd.set_initial_name(default_name)

        def _done(dialog, res):
            try:
                gfile = dialog.save_finish(res)
            except Exception:
                return
            if gfile and gfile.get_path():
                callback(gfile.get_path())

        fd.save(win, None, _done)

    btn_export_csv.connect(
        "clicked",
        lambda _b: _choose_save_path(
            "Export Takeoff CSV",
            "takeoff.csv",
            lambda p: (export_takeoff_csv(ctrl.result, p), status_bar.set_text(f"Exported CSV to {os.path.basename(p)}")),
        ),
    )
    btn_export_json.connect(
        "clicked",
        lambda _b: _choose_save_path(
            "Export Takeoff JSON",
            "takeoff.json",
            lambda p: (export_takeoff_json(ctrl.result, ctrl.checks, p), status_bar.set_text(f"Exported JSON to {os.path.basename(p)}")),
        ),
    )

    def _on_save_ref(_b):
        ctrl.save_reference("project_reference")
        _refresh_checks_and_ref()
        status_bar.set_text("Saved reference takeoff to project (save project XML to persist).")

    btn_save_ref.connect("clicked", _on_save_ref)

    _refresh_all()
    return win
