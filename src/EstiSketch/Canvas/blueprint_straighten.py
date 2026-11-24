"""Interactive "Straighten" tool for blueprint underlays.

Lets the user drag four corner handles onto the real corners of the plan
sheet (fixes photos taken at an angle) and four edge-midpoint handles to
bend the edges (fixes curved paper). Applying bakes the correction into a
new straightened image. See :mod:`EstiSketch.geometry.image_warp`.
"""
import io
import math

import cairo
import numpy as np

from ..geometry import image_warp as iw

HANDLE_HIT_PX = 22


def surface_to_rgba(surf: cairo.ImageSurface) -> np.ndarray:
    """Copy a cairo ARGB32 surface into an (H, W, 4) uint8 array."""
    surf.flush()
    w, h, stride = surf.get_width(), surf.get_height(), surf.get_stride()
    arr = np.ndarray((h, stride // 4, 4), np.uint8, buffer=surf.get_data())
    return arr[:, :w].copy()


def rgba_to_surface(arr: np.ndarray) -> cairo.ImageSurface:
    h, w = arr.shape[:2]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    dst = np.ndarray((h, surf.get_stride() // 4, 4), np.uint8,
                     buffer=surf.get_data())
    dst[:, :w] = arr
    surf.mark_dirty()
    return surf


def default_corners(width: int, height: int, inset: float = 0.1):
    ix, iy = width * inset, height * inset
    return [[ix, iy], [width - ix, iy], [width - ix, height - iy], [ix, height - iy]]


def straighten_surface(surf: cairo.ImageSurface, corners, offsets):
    """Return ``(new_surface, shrink)`` with the correction applied."""
    out_w, out_h, shrink = iw.output_size(corners)
    out = iw.warp_image(surface_to_rgba(surf), corners, offsets, out_w, out_h)
    return rgba_to_surface(out), shrink


class CanvasBlueprintStraightenMixin:
    """Straighten tool state, overlay drawing and interaction."""

    def _init_straighten_state(self):
        self.straighten_bp = None
        self.straighten_corners = []
        self.straighten_offsets = []
        self._straighten_drag = None   # ("corner"|"edge", index)
        self._straighten_drag_start = (0.0, 0.0)

    # -- coordinate helpers ------------------------------------------------
    @staticmethod
    def _bp_img_to_model(bp, px, py):
        a = math.radians(bp.rotation)
        lx, ly = px * bp.scale_x, py * bp.scale_y
        return (bp.x + lx * math.cos(a) - ly * math.sin(a),
                bp.y + lx * math.sin(a) + ly * math.cos(a))

    @staticmethod
    def _bp_model_to_img(bp, mx, my):
        a = math.radians(bp.rotation)
        dx, dy = mx - bp.x, my - bp.y
        lx = dx * math.cos(a) + dy * math.sin(a)
        ly = -dx * math.sin(a) + dy * math.cos(a)
        return lx / bp.scale_x, ly / bp.scale_y

    def _straighten_handles(self):
        """Handle positions in image pixels: 4 corners then 4 edge handles."""
        corners = [(float(c[0]), float(c[1])) for c in self.straighten_corners]
        anchors = iw.edge_anchors(corners)
        edges = [(ax + dx, ay + dy) for (ax, ay), (dx, dy)
                 in zip(anchors, self.straighten_offsets)]
        return corners, edges

    # -- lifecycle -----------------------------------------------------------
    def start_straighten(self, bp) -> bool:
        surf = self.get_blueprint_surface(bp)
        if surf is None:
            return False
        self._remember_tool()
        self.set_tool_mode("straighten_blueprint")
        self.straighten_bp = bp
        self.straighten_corners = default_corners(bp.pixel_width, bp.pixel_height)
        self.straighten_offsets = [[0.0, 0.0] for _ in range(4)]
        self._straighten_drag = None
        self.update_hint(
            "Straighten: drag the corner handles onto the plan's corners, drag the "
            "edge handles to bend curved edges | Enter to apply | Esc to cancel")
        if hasattr(self, 'emit'):
            self.emit('content-changed')
        self.queue_draw()
        return True

    def reset_straighten_state(self):
        self.straighten_bp = None
        self.straighten_corners = []
        self.straighten_offsets = []
        self._straighten_drag = None

    def apply_straighten(self):
        bp = self.straighten_bp
        if bp is None:
            return
        corners = [tuple(c) for c in self.straighten_corners]
        offsets = [tuple(o) for o in self.straighten_offsets]
        try:
            surf = self.get_blueprint_surface(bp)
            new_surf, shrink = straighten_surface(surf, corners, offsets)
        except ValueError as exc:
            self.update_hint(f"Cannot straighten: {exc}")
            return
        buf = io.BytesIO()
        new_surf.write_to_png(buf)

        # The straightened image's top-left pixel is the TL handle; same
        # pixel density as before (unless it was capped), so scale carries over.
        new_x, new_y = self._bp_img_to_model(bp, *corners[0])
        bp.image_data = buf.getvalue()
        self._blueprint_surfaces[bp.identifier] = new_surf
        bp.pixel_width, bp.pixel_height = new_surf.get_width(), new_surf.get_height()
        bp.scale_x /= shrink
        bp.scale_y /= shrink
        bp.x, bp.y = new_x, new_y

        self.cancel_blueprint_tool()
        self.save_state()
        self.emit('content-changed')
        self.update_hint(
            "Blueprint straightened. Re-run Calibrate to set the exact scale.")
        self.queue_draw()

    # -- interaction ---------------------------------------------------------
    def _straighten_drag_begin(self, start_x, start_y):
        bp = self.straighten_bp
        if bp is None:
            return
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        self._straighten_drag_start = (start_x, start_y)
        corners, edges = self._straighten_handles()
        best, best_d = None, HANDLE_HIT_PX
        for kind, pts in (("corner", corners), ("edge", edges)):
            for i, (px, py) in enumerate(pts):
                mx, my = self._bp_img_to_model(bp, px, py)
                dx, dy = self.model_to_device(mx, my, ppi)
                d = math.hypot(dx - start_x, dy - start_y)
                if d <= best_d:
                    best, best_d = (kind, i), d
        self._straighten_drag = best

    def _straighten_drag_update(self, offset_x, offset_y):
        bp = self.straighten_bp
        if bp is None or self._straighten_drag is None:
            return
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        sx, sy = self._straighten_drag_start
        mx, my = self.device_to_model(sx + offset_x, sy + offset_y, ppi)
        px, py = self._bp_model_to_img(bp, mx, my)
        kind, i = self._straighten_drag
        if kind == "corner":
            self.straighten_corners[i] = [px, py]
        else:
            corners = [(float(c[0]), float(c[1])) for c in self.straighten_corners]
            ax, ay = iw.edge_anchors(corners)[i]
            self.straighten_offsets[i] = [px - ax, py - ay]
        self.queue_draw()

    def _straighten_drag_end(self, offset_x, offset_y):
        self._straighten_drag_update(offset_x, offset_y)
        self._straighten_drag = None

    # -- drawing -------------------------------------------------------------
    def draw_straighten_overlay(self, cr):
        bp = self.straighten_bp
        if bp is None or self.tool_mode != "straighten_blueprint":
            return
        px_len = 1.0 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0))
        corners = [tuple(c) for c in self.straighten_corners]
        offsets = [tuple(o) for o in self.straighten_offsets]
        t = np.linspace(0.0, 1.0, 33)

        def to_model(xs, ys):
            return [self._bp_img_to_model(bp, float(x), float(y))
                    for x, y in zip(xs, ys)]

        def polyline(pts):
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)

        cr.save()
        # Preview grid showing where straight lines will end up
        cr.set_source_rgba(0.1, 0.8, 0.2, 0.55)
        cr.set_line_width(1 * px_len)
        for f in (0.25, 0.5, 0.75):
            polyline(to_model(*iw.source_point(corners, offsets, t, np.full_like(t, f))))
            cr.stroke()
            polyline(to_model(*iw.source_point(corners, offsets, np.full_like(t, f), t)))
            cr.stroke()

        # Outline of the region that will be kept
        cr.set_source_rgba(1.0, 0.3, 0.0, 0.95)
        cr.set_line_width(2 * px_len)
        for u, v in ((t, np.zeros_like(t)), (np.ones_like(t), t),
                     (t[::-1], np.ones_like(t)), (np.zeros_like(t), t[::-1])):
            polyline(to_model(*iw.source_point(corners, offsets, u, v)))
            cr.stroke()

        # Handles
        c_pts, e_pts = self._straighten_handles()
        for pts, rgb in ((c_pts, (1.0, 0.9, 0.0)), (e_pts, (0.0, 0.8, 1.0))):
            for (ix, iy) in pts:
                mx, my = self._bp_img_to_model(bp, ix, iy)
                cr.set_source_rgba(*rgb, 1.0)
                cr.arc(mx, my, 7 * px_len, 0, 2 * math.pi)
                cr.fill_preserve()
                cr.set_source_rgba(0, 0, 0, 1)
                cr.set_line_width(1 * px_len)
                cr.stroke()
        cr.restore()
