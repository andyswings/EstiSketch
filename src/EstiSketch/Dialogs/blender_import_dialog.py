"""GTK4 Import Review Dialog for Two-Tier Blender delta imports."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..blender_bridge.blender_sync import DeltaImportPlan  # noqa: E402


class BlenderImportReviewDialog(Gtk.Dialog):
    """Modal review checklist summarizing Tier 1, Tier 2A, and Tier 2B Blender deltas."""

    def __init__(
        self,
        parent: Gtk.Window | None,
        plan: DeltaImportPlan,
        on_apply: Callable[[set[int]], None],
    ) -> None:
        super().__init__(title="Review Blender Sync Delta", transient_for=parent, modal=True)
        self.set_default_size(520, 380)
        self._plan = plan
        self._on_apply = on_apply
        self._checks: list[tuple[int, Gtk.CheckButton]] = []

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Apply Selected", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)

        box = self.get_content_area()
        box.set_spacing(10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(14)
        box.set_margin_end(14)

        t1 = sum(1 for it in plan.items if it.tier == "parametric")
        t2a = sum(1 for it in plan.items if it.tier == "override_3d")
        t2b = sum(1 for it in plan.items if it.tier == "custom_asset")
        summary = (
            f"{t1} parametric update(s), {t2a} 3D visual override(s), "
            f"{t2b} new custom asset(s) — {plan.ignored_count} helper(s) ignored"
        )
        hdr = Gtk.Label(label=summary)
        hdr.set_xalign(0.0)
        hdr.set_wrap(True)
        box.append(hdr)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for idx, item in enumerate(plan.items):
            chk = Gtk.CheckButton(label=f"[{item.tier}] {item.summary}")
            chk.set_active(item.accepted)
            self._checks.append((idx, chk))
            list_box.append(chk)
        scroll.set_child(list_box)
        box.append(scroll)

        self.connect("response", self._on_response)

    def _on_response(self, _dlg: Gtk.Dialog, response: int) -> None:
        if response == Gtk.ResponseType.OK:
            accepted = {idx for idx, chk in self._checks if chk.get_active()}
            self._on_apply(accepted)
        self.destroy()
