"""Canvas mixin for interactive fixture placement, cabinet runs, and kitchen/vanity layouts."""
import math
from types import SimpleNamespace
from typing import List, Optional, Tuple

from ..Resources.tool_hints import TOOL_HINTS
from ..components import Fixture
from ..fixtures_catalog import (
    generate_kitchen_or_vanity_layout,
    get_fixture_spec,
    pack_cabinet_run,
    resolve_fixture_surface,
    snap_fixture_to_walls,
    snap_layout_to_walls,
    snap_point_to_wall_face,
)


class CanvasFixtureMixin:
    def _init_fixture_state(self) -> None:
        self.active_fixture_type = "base_cabinet"
        self.active_fixture_rotation = 0.0
        self.fixture_ghost = None
        self.pending_layout_config = None
        self.layout_ghost_fixtures = []
        self.cabinet_run_start = None
        self.cabinet_run_preview = None
        self.cabinet_run_include_uppers = True
        self.cabinet_run_material = "quartz"
        self.cabinet_run_side = 1.0
        self._cabinet_run_start_normal = None
        self._cabinet_run_manual_side = False
        self.dragging_fixture = None
        self.dragging_fixtures = None
        self.rotating_fixture = None

    def _reset_fixture_interaction_state(self) -> None:
        self.fixture_ghost = None
        self.layout_ghost_fixtures = []
        self.cabinet_run_start = None
        self.cabinet_run_preview = None
        self._cabinet_run_start_normal = None
        self._cabinet_run_manual_side = False
        self.dragging_fixture = None
        self.dragging_fixtures = None
        self.rotating_fixture = None

    def _get_visible_walls(self) -> List[object]:
        walls: List[object] = []
        for ws in getattr(self, "wall_sets", []):
            for w in ws:
                if not hasattr(self, "is_object_on_visible_layer") or self.is_object_on_visible_layer(w):
                    walls.append(w)
        for w in getattr(self, "walls", []):
            if w not in walls and (
                not hasattr(self, "is_object_on_visible_layer") or self.is_object_on_visible_layer(w)
            ):
                walls.append(w)

        # Also include visible room boundary edges when not already backed by structural walls
        for room in getattr(self, "rooms", []):
            if hasattr(self, "is_object_on_visible_layer") and not self.is_object_on_visible_layer(room):
                continue
            pts = getattr(room, "points", []) or []
            n_pts = len(pts)
            if n_pts < 3:
                continue
            for i in range(n_pts):
                p1, p2 = pts[i], pts[(i + 1) % n_pts]
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 6.0:
                    continue
                mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
                covered = False
                for w in walls:
                    if hasattr(w, "start") and hasattr(w, "end"):
                        x1, y1 = w.start
                        x2, y2 = w.end
                        dx, dy = x2 - x1, y2 - y1
                        lsq = dx * dx + dy * dy
                        if lsq > 1e-6:
                            t = max(0.0, min(1.0, ((mx - x1) * dx + (my - y1) * dy) / lsq))
                            if math.hypot(mx - (x1 + t * dx), my - (y1 + t * dy)) <= 6.0:
                                covered = True
                                break
                if not covered:
                    walls.append(
                        SimpleNamespace(
                            start=p1,
                            end=p2,
                            width=0.0,
                            is_curved=False,
                            symbolic=False,
                        )
                    )
        return walls

    def _build_fixture_preview(self, model_x: float, model_y: float) -> Fixture:
        sym = getattr(self, "active_fixture_type", "base_cabinet") or "base_cabinet"
        spec = get_fixture_spec(sym)
        w = float(spec["width"])
        d = float(spec["depth"])
        cur_rot = float(getattr(self, "active_fixture_rotation", 0.0) or 0.0)

        snap_enabled = bool(getattr(getattr(self, "snap_manager", None), "snap_enabled", True))
        if snap_enabled:
            sx, sy, rot, _ = snap_fixture_to_walls(
                model_x,
                model_y,
                w,
                d,
                self._get_visible_walls(),
                snap_dist=24.0,
                current_rotation=cur_rot,
                symbol_type=sym,
            )
        else:
            sx, sy, rot = model_x, model_y, cur_rot

        fix = Fixture(
            symbol_type=sym,
            x=sx,
            y=sy,
            rotation=rot,
            layer_id=getattr(self, "active_layer_id", ""),
        )
        resolve_fixture_surface(fix, getattr(self, "rooms", []))
        return fix

    def _build_layout_preview(self, model_x: float, model_y: float) -> List[Fixture]:
        cfg = getattr(self, "pending_layout_config", None) or {}
        layout_type = cfg.get("layout_type", "one_wall")
        run_a = float(cfg.get("run_a", 120.0))
        run_b = float(cfg.get("run_b", 108.0))
        include_uppers = bool(cfg.get("include_uppers", True))
        include_appliances = bool(cfg.get("include_appliances", True))
        material = cfg.get("countertop_material", "quartz") or "quartz"
        rot = float(cfg.get("rotation_deg", getattr(self, "active_fixture_rotation", 0.0)) or 0.0)
        origin = (model_x, model_y)

        snap_enabled = bool(getattr(getattr(self, "snap_manager", None), "snap_enabled", True))
        if snap_enabled:
            origin, rot, _snapped = snap_layout_to_walls(
                layout_type,
                origin,
                rot,
                self._get_visible_walls(),
                snap_dist=24.0,
            )

        items = generate_kitchen_or_vanity_layout(
            layout_type=layout_type,
            origin=origin,
            rotation_deg=rot,
            run_a=run_a,
            run_b=run_b,
            include_uppers=include_uppers,
            include_appliances=include_appliances,
            countertop_material=material,
            layer_id=getattr(self, "active_layer_id", ""),
        )
        rooms = getattr(self, "rooms", [])
        for it in items:
            resolve_fixture_surface(it, rooms)
        return items

    def rotate_active_fixture_preview(self, step_deg: float = 90.0) -> None:
        self.active_fixture_rotation = (float(getattr(self, "active_fixture_rotation", 0.0)) + step_deg) % 360.0
        if getattr(self, "pending_layout_config", None) is not None:
            self.pending_layout_config["rotation_deg"] = self.active_fixture_rotation
        pos = getattr(self, "_last_mouse_pos", None)
        if pos is not None:
            mx, my = pos
            if getattr(self, "tool_mode", None) == "add_fixture":
                self.fixture_ghost = self._build_fixture_preview(mx, my)
            elif getattr(self, "tool_mode", None) == "add_kitchen_layout":
                self.layout_ghost_fixtures = self._build_layout_preview(mx, my)
        self.queue_draw()

    def get_fixture_rotation_handle_device(self, fix) -> Optional[Tuple[float, float]]:
        if not fix or not hasattr(fix, "world_corners"):
            return None
        corners = fix.world_corners(include_overhang=True)
        front_mid = ((corners[2][0] + corners[3][0]) / 2.0, (corners[2][1] + corners[3][1]) / 2.0)
        rad = math.radians(fix.rotation)
        hx = front_mid[0] - math.sin(rad) * (12.0 / self.zoom)
        hy = front_mid[1] + math.cos(rad) * (12.0 / self.zoom)
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        T = self.zoom * pixels_per_inch
        return (hx * T + self.offset_x, hy * T + self.offset_y)

    def _handle_fixture_click(self, n_press: int, x: float, y: float) -> None:
        if n_press != 1:
            return
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        fix = self._build_fixture_preview(mx, my)
        fix.identifier = self.generate_identifier("fixture", self.existing_ids)
        self.existing_ids.append(fix.identifier)
        if not hasattr(self, "fixtures"):
            self.fixtures = []
        self.fixtures.append(fix)
        self.selected_items = [{"type": "fixture", "object": fix}]
        self.save_state()
        self.emit("selection-changed", self.selected_items)
        self.emit("content-changed")
        self.queue_draw()

    def _handle_fixture_motion(self, x: float, y: float) -> None:
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        self.fixture_ghost = self._build_fixture_preview(mx, my)
        self.queue_draw()

    def _handle_kitchen_layout_click(self, n_press: int, x: float, y: float) -> None:
        if n_press != 1:
            return
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        items = self._build_layout_preview(mx, my)
        if not items:
            return
        if not hasattr(self, "fixtures"):
            self.fixtures = []
        for it in items:
            it.identifier = self.generate_identifier("fixture", self.existing_ids)
            self.existing_ids.append(it.identifier)
            self.fixtures.append(it)
        self.selected_items = [{"type": "fixture", "object": it} for it in items]
        self.save_state()
        self.emit("selection-changed", self.selected_items)
        self.emit("content-changed")
        self.queue_draw()

    def _handle_kitchen_layout_motion(self, x: float, y: float) -> None:
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        self.layout_ghost_fixtures = self._build_layout_preview(mx, my)
        self.queue_draw()

    def _snap_run_endpoint_with_normal(self, mx: float, my: float) -> Tuple[float, float, Optional[Tuple[float, float]]]:
        snap_enabled = bool(getattr(getattr(self, "snap_manager", None), "snap_enabled", True))
        if snap_enabled:
            fx, fy, out_n = snap_point_to_wall_face(mx, my, self._get_visible_walls(), snap_dist=18.0)
            if out_n is not None:
                return (fx, fy, out_n)
        if hasattr(self, "_compute_room_snap"):
            (sx, sy), _, _ = self._compute_room_snap(mx, my)
            return (sx, sy, None)
        return (mx, my, None)

    def _snap_run_endpoint(self, mx: float, my: float) -> Tuple[float, float]:
        sx, sy, _ = self._snap_run_endpoint_with_normal(mx, my)
        return (sx, sy)

    def _compute_run_side(self, start: Tuple[float, float], end: Tuple[float, float], end_normal: Optional[Tuple[float, float]]) -> float:
        if getattr(self, "_cabinet_run_manual_side", False):
            return float(getattr(self, "cabinet_run_side", 1.0) or 1.0)
        wn = getattr(self, "_cabinet_run_start_normal", None) or end_normal
        if wn is not None:
            dx, dy = end[0] - start[0], end[1] - start[1]
            rlen = math.hypot(dx, dy)
            if rlen >= 1e-4:
                ux, uy = dx / rlen, dy / rlen
                return 1.0 if ((-uy) * wn[0] + ux * wn[1]) >= 0.0 else -1.0
        return float(getattr(self, "cabinet_run_side", 1.0) or 1.0)

    def _handle_cabinet_run_click(self, n_press: int, x: float, y: float) -> None:
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        sx, sy, out_n = self._snap_run_endpoint_with_normal(mx, my)

        if getattr(self, "cabinet_run_start", None) is None:
            self.cabinet_run_start = (sx, sy)
            self.cabinet_run_preview = (sx, sy)
            self._cabinet_run_start_normal = out_n
            self._cabinet_run_manual_side = False
            if "draw_cabinet_run_active" in TOOL_HINTS:
                self.update_hint(TOOL_HINTS["draw_cabinet_run_active"])
            self.queue_draw()
            return

        start = self.cabinet_run_start
        end = (sx, sy)
        # Keep orthogonal snap if nearly H or V
        if abs(end[0] - start[0]) > 4.0 and abs(end[1] - start[1]) < 4.0:
            end = (end[0], start[1])
        elif abs(end[1] - start[1]) > 4.0 and abs(end[0] - start[0]) < 4.0:
            end = (start[0], end[1])

        eff_side = self._compute_run_side(start, end, out_n)
        self.cabinet_run_side = eff_side

        items = pack_cabinet_run(
            start,
            end,
            include_uppers=bool(getattr(self, "cabinet_run_include_uppers", True)),
            countertop_material=getattr(self, "cabinet_run_material", "quartz") or "quartz",
            layer_id=getattr(self, "active_layer_id", ""),
            side=eff_side,
            existing_ids=self.existing_ids,
        )
        self.cabinet_run_start = None
        self.cabinet_run_preview = None
        self._cabinet_run_start_normal = None
        self._cabinet_run_manual_side = False
        if "draw_cabinet_run" in TOOL_HINTS:
            self.update_hint(TOOL_HINTS["draw_cabinet_run"])
        if items:
            if not hasattr(self, "fixtures"):
                self.fixtures = []
            rooms = getattr(self, "rooms", [])
            for it in items:
                resolve_fixture_surface(it, rooms)
                self.fixtures.append(it)
            self.selected_items = [{"type": "fixture", "object": it} for it in items]
            self.save_state()
            self.emit("selection-changed", self.selected_items)
            self.emit("content-changed")
        self.queue_draw()

    def _handle_cabinet_run_motion(self, x: float, y: float) -> None:
        if getattr(self, "cabinet_run_start", None) is None:
            return
        pixels_per_inch = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        mx, my = self.device_to_model(x, y, pixels_per_inch)
        sx, sy, out_n = self._snap_run_endpoint_with_normal(mx, my)
        start = self.cabinet_run_start
        if abs(sx - start[0]) > 4.0 and abs(sy - start[1]) < 4.0:
            sy = start[1]
        elif abs(sy - start[1]) > 4.0 and abs(sx - start[0]) < 4.0:
            sx = start[0]
        self.cabinet_run_preview = (sx, sy)
        self.cabinet_run_side = self._compute_run_side(start, (sx, sy), out_n)
        self.queue_draw()
