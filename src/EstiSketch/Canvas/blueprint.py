"""Blueprint / background-image underlay support for the canvas.

Provides:
- pure geometry helpers (``calibrated_scale`` / ``apply_calibration``) that
  are independent of GTK so they can be unit tested headlessly
- ``CanvasBlueprintMixin``: image loading, rendering, the two-click
  calibration tool and drag-to-move for unlocked underlays.
"""
import math
import os
from typing import Optional

import cairo

from ..components import BackgroundImage

BLUEPRINT_TOOL_MODES = ("calibrate_blueprint", "move_blueprint",
                        "straighten_blueprint")

# Default width (inches) a freshly imported image is fitted to before it is
# calibrated by the user.
DEFAULT_IMPORT_WIDTH_IN = 600.0


# ──────────────────────────────────────────────────────────────────────────
# Pure helpers
# ──────────────────────────────────────────────────────────────────────────

def calibrated_scale(p1, p2, real_inches: float) -> float:
    """Return the factor that makes the model distance ``p1``→``p2`` equal
    ``real_inches``.

    scale = real_inches / current_model_distance
    """
    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if dist <= 1e-9:
        raise ValueError("Calibration points must be distinct.")
    if real_inches <= 0:
        raise ValueError("Real distance must be positive.")
    return real_inches / dist


def apply_calibration(bp: BackgroundImage, p1, p2, real_inches: float) -> float:
    """Rescale ``bp`` so the span ``p1``→``p2`` (model inches) measures
    ``real_inches``. The image is scaled about ``p1`` so the first reference
    point stays put on the plan. Returns the applied factor.
    """
    factor = calibrated_scale(p1, p2, real_inches)
    bp.scale_x *= factor
    bp.scale_y *= factor
    bp.x = p1[0] + (bp.x - p1[0]) * factor
    bp.y = p1[1] + (bp.y - p1[1]) * factor
    return factor


def blueprint_corners(bp: BackgroundImage):
    """Return the four model-space corners of the image (rotation applied)."""
    w = bp.pixel_width * bp.scale_x
    h = bp.pixel_height * bp.scale_y
    ang = math.radians(bp.rotation)
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for lx, ly in ((0, 0), (w, 0), (w, h), (0, h)):
        pts.append((bp.x + lx * ca - ly * sa, bp.y + lx * sa + ly * ca))
    return pts


def point_in_blueprint(bp: BackgroundImage, x: float, y: float) -> bool:
    """True if the model point lies inside the (rotated) image rectangle."""
    ang = math.radians(bp.rotation)
    dx, dy = x - bp.x, y - bp.y
    lx = dx * math.cos(-ang) - dy * math.sin(-ang)
    ly = dx * math.sin(-ang) + dy * math.cos(-ang)
    return (0 <= lx <= bp.pixel_width * bp.scale_x and
            0 <= ly <= bp.pixel_height * bp.scale_y)


def load_surface_from_bytes(data: bytes) -> Optional[cairo.ImageSurface]:
    """Decode encoded image bytes (PNG, JPEG, ...) to a cairo surface."""
    if not data:
        return None
    # Fast path: PNG decodes natively in cairo.
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        import io
        try:
            return cairo.ImageSurface.create_from_png(io.BytesIO(data))
        except Exception:
            pass
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    pixbuf = loader.get_pixbuf()
    if pixbuf is None:
        return None
    w, h = pixbuf.get_width(), pixbuf.get_height()
    channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()
    has_alpha = pixbuf.get_has_alpha()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = surface.get_stride()
    buf = surface.get_data()
    for row in range(h):
        src = row * rowstride
        dst = row * stride
        for col in range(w):
            i = src + col * channels
            r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
            a = pixels[i + 3] if has_alpha else 255
            if a != 255:  # cairo expects premultiplied alpha
                r, g, b = r * a // 255, g * a // 255, b * a // 255
            o = dst + col * 4
            buf[o:o + 4] = bytes((b, g, r, a))  # little-endian BGRA
    surface.mark_dirty()
    return surface


# ──────────────────────────────────────────────────────────────────────────
# Canvas mixin
# ──────────────────────────────────────────────────────────────────────────

class CanvasBlueprintMixin:
    """Blueprint underlay management, rendering and interaction tools."""

    # -- state ------------------------------------------------------------
    def _init_blueprint_state(self):
        self.blueprints = []
        self._blueprint_surfaces = {}
        self.calibrating_blueprint = None
        self.calibration_points = []
        self.calibration_preview = None
        self.active_blueprint = None      # blueprint being moved
        self._blueprint_move_origin = None
        self._blueprint_prev_tool = None
        self._init_straighten_state()

    def reset_blueprints(self):
        self.blueprints = []
        self._blueprint_surfaces = {}
        self.cancel_blueprint_tool()

    def get_blueprint_by_id(self, identifier: str):
        for bp in self.blueprints:
            if bp.identifier == identifier:
                return bp
        return None

    def get_blueprint_surface(self, bp: BackgroundImage):
        """Return (and cache) the decoded surface for ``bp``."""
        surf = self._blueprint_surfaces.get(bp.identifier)
        if surf is None and bp.image_data:
            try:
                surf = load_surface_from_bytes(bp.image_data)
            except Exception as exc:  # corrupt image data
                print(f"Could not decode blueprint {bp.identifier}: {exc}")
                surf = None
            if surf is not None:
                self._blueprint_surfaces[bp.identifier] = surf
                bp.pixel_width = surf.get_width()
                bp.pixel_height = surf.get_height()
        return surf

    def is_blueprint_shown(self, bp: BackgroundImage) -> bool:
        if not bp.visible:
            return False
        if self.show_all_levels or not bp.level_id:
            return True
        return bp.level_id == self.active_level_id

    # -- import -----------------------------------------------------------
    def import_blueprint(self, path: str, start_calibration: bool = True):
        """Load an image file as a new blueprint underlay."""
        with open(path, "rb") as fh:
            data = fh.read()
        bp = BackgroundImage(
            identifier=self.generate_identifier(
                "blueprint", [b.identifier for b in self.blueprints]),
            image_path=path,
            name=os.path.basename(path),
            image_data=data,
            level_id=self.active_level_id,
            opacity=0.5,
            locked=True,
            visible=True,
        )
        surf = self.get_blueprint_surface(bp)
        if surf is None or bp.pixel_width <= 0:
            raise ValueError("Unsupported or unreadable image file.")

        # Fit to a sensible default width and place it in the current view.
        bp.scale_x = bp.scale_y = DEFAULT_IMPORT_WIDTH_IN / bp.pixel_width
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        bp.x, bp.y = self.device_to_model(
            self.ruler_offset + 20, self.ruler_offset + 20, ppi)

        self.blueprints.append(bp)
        self.save_state()
        self.emit('content-changed')
        self.queue_draw()
        if start_calibration:
            self.start_calibration(bp)
        return bp

    def remove_blueprint(self, bp: BackgroundImage):
        if bp in self.blueprints:
            self.blueprints.remove(bp)
            self._blueprint_surfaces.pop(bp.identifier, None)
            if self.calibrating_blueprint is bp or self.active_blueprint is bp:
                self.cancel_blueprint_tool()
            self.save_state()
            self.emit('content-changed')
            self.queue_draw()

    def update_blueprint(self, bp: BackgroundImage, **changes):
        """Set attributes on ``bp``, then record undo and redraw."""
        for key, value in changes.items():
            setattr(bp, key, value)
        self.save_state()
        self.queue_draw()

    # -- rendering --------------------------------------------------------
    def draw_blueprints(self, cr):
        """Paint all visible blueprints (model coordinates)."""
        for bp in self.blueprints:
            if not self.is_blueprint_shown(bp):
                continue
            surf = self.get_blueprint_surface(bp)
            if surf is None:
                continue
            cr.save()
            cr.translate(bp.x, bp.y)
            cr.rotate(math.radians(bp.rotation))
            cr.scale(bp.scale_x, bp.scale_y)
            cr.set_source_surface(surf, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_GOOD)
            cr.paint_with_alpha(max(0.0, min(1.0, bp.opacity)))
            cr.restore()

    def draw_blueprint_overlays(self, cr):
        """Draw frames for movable images and the calibration markers."""
        px = 1.0 / (self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0))
        self.draw_straighten_overlay(cr)
        bp = self.active_blueprint
        if bp is not None and self.tool_mode == "move_blueprint":
            corners = blueprint_corners(bp)
            cr.save()
            cr.set_source_rgba(0.1, 0.5, 1.0, 0.9)
            cr.set_line_width(2 * px)
            cr.set_dash([8 * px, 4 * px])
            cr.move_to(*corners[0])
            for c in corners[1:]:
                cr.line_to(*c)
            cr.close_path()
            cr.stroke()
            cr.restore()

        if self.tool_mode == "calibrate_blueprint" and self.calibration_points:
            pts = list(self.calibration_points)
            if len(pts) == 1 and self.calibration_preview is not None:
                pts.append(self.calibration_preview)
            cr.save()
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.95)
            cr.set_line_width(2 * px)
            if len(pts) == 2:
                cr.move_to(*pts[0])
                cr.line_to(*pts[1])
                cr.stroke()
            for p in pts:
                cr.arc(p[0], p[1], 5 * px, 0, 2 * math.pi)
                cr.fill()
            cr.restore()

    # -- tool state -------------------------------------------------------
    def _remember_tool(self):
        if self.tool_mode not in BLUEPRINT_TOOL_MODES:
            self._blueprint_prev_tool = self.tool_mode

    def cancel_blueprint_tool(self, restore_tool: bool = True):
        """Leave calibration / move mode and restore the previous tool."""
        was_active = self.tool_mode in BLUEPRINT_TOOL_MODES
        self.calibrating_blueprint = None
        self.calibration_points = []
        self.calibration_preview = None
        self.active_blueprint = None
        self._blueprint_move_origin = None
        self.reset_straighten_state()
        if was_active and restore_tool:
            self.set_tool_mode(self._blueprint_prev_tool or "pointer")
        if was_active and hasattr(self, 'emit'):
            self.emit('content-changed')
        self.queue_draw()

    # -- calibration ------------------------------------------------------
    def start_calibration(self, bp: BackgroundImage):
        self._remember_tool()
        self.set_tool_mode("calibrate_blueprint")
        self.calibrating_blueprint = bp
        self.calibration_points = []
        self.calibration_preview = None
        self.update_hint(
            "Calibrate: click the first reference point on the blueprint | Esc to cancel")
        self.queue_draw()

    def _handle_calibration_click(self, n_press, x, y):
        bp = self.calibrating_blueprint
        if bp is None:
            return
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        pt = self.device_to_model(x, y, ppi)
        if len(self.calibration_points) == 0:
            self.calibration_points = [pt]
            self.update_hint(
                "Calibrate: click the second reference point | Esc to cancel")
            self.queue_draw()
            return
        p1 = self.calibration_points[0]
        if math.hypot(pt[0] - p1[0], pt[1] - p1[1]) < 1e-6:
            return  # ignore a double-click on the same spot
        self.calibration_points = [p1, pt]
        self.queue_draw()
        self._ask_calibration_distance(bp, p1, pt)

    def _handle_calibration_motion(self, x, y):
        if self.calibrating_blueprint is None or len(self.calibration_points) != 1:
            return
        ppi = getattr(self.config, "PIXELS_PER_INCH", 2.0)
        self.calibration_preview = self.device_to_model(x, y, ppi)
        self.queue_draw()

    def _ask_calibration_distance(self, bp, p1, p2):
        from ..Dialogs.blueprint_wizard import BlueprintCalibrationDialog
        measured = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        dialog = BlueprintCalibrationDialog(self.get_root(), measured)

        def on_response(dlg, response):
            real = None
            if response == dialog.ok_response:
                real = dlg.get_real_inches()
                if real is None:
                    return  # invalid text: error shown, keep dialog open
            dlg.destroy()
            if real is None:
                # Cancelled / invalid: let the user pick the points again.
                self.calibration_points = []
                self.calibration_preview = None
                self.update_hint(
                    "Calibrate: click the first reference point on the blueprint | Esc to cancel")
                self.queue_draw()
                return
            self.finish_calibration(bp, p1, p2, real)

        dialog.connect("response", on_response)
        dialog.present()

    def finish_calibration(self, bp, p1, p2, real_inches: float):
        apply_calibration(bp, p1, p2, real_inches)
        self.cancel_blueprint_tool()
        self.save_state()
        self.emit('content-changed')
        self.update_hint(
            f"Blueprint calibrated: {bp.scale_x:.4f} in/pixel")
        self.queue_draw()

    # -- move -------------------------------------------------------------
    def start_blueprint_move(self, bp: BackgroundImage) -> bool:
        """Enter drag-to-move mode for an unlocked blueprint."""
        if bp.locked:
            self.update_hint("Unlock the blueprint before moving it.")
            return False
        self._remember_tool()
        self.set_tool_mode("move_blueprint")
        self.active_blueprint = bp
        self.update_hint("Drag to move the blueprint | Esc when done")
        self.queue_draw()
        return True

    def _blueprint_drag_begin(self, start_x, start_y):
        if self.tool_mode == "straighten_blueprint":
            return self._straighten_drag_begin(start_x, start_y)
        bp = self.active_blueprint
        if bp is not None:
            self._blueprint_move_origin = (bp.x, bp.y)

    def _blueprint_drag_update(self, offset_x, offset_y):
        if self.tool_mode == "straighten_blueprint":
            return self._straighten_drag_update(offset_x, offset_y)
        bp = self.active_blueprint
        if bp is None or self._blueprint_move_origin is None:
            return
        T = self.zoom * getattr(self.config, "PIXELS_PER_INCH", 2.0)
        bp.x = self._blueprint_move_origin[0] + offset_x / T
        bp.y = self._blueprint_move_origin[1] + offset_y / T
        self.queue_draw()

    def _blueprint_drag_end(self, offset_x, offset_y):
        if self.tool_mode == "straighten_blueprint":
            return self._straighten_drag_end(offset_x, offset_y)
        if self.active_blueprint is not None and self._blueprint_move_origin is not None:
            self._blueprint_drag_update(offset_x, offset_y)
            self._blueprint_move_origin = None
            self.save_state()
            self.emit('content-changed')
