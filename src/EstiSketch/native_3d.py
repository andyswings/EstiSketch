"""Optional Python wrapper around the native Rust ``EstiSketch._native_3d`` extension.

The main EstiSketch 2D application and headless test suite continue to operate if
the compiled Rust extension is unavailable in a checkout; availability can be
queried via :func:`is_native_3d_available`.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from .scene_ir import SceneDeltaIR, SceneIR


@dataclass(frozen=True)
class PickHit:
    """Closest raycast intersection returned by the Rust 3D BVH picker.

    Attributes:
        entity_id: Source ``SceneIR`` entity identifier.
        entity_kind: Entity category (``"wall"``, ``"opening"``, ``"room"``, ``"roof"``,
            ``"stair"``, ``"fixture"``).
        sub_part: Hit mesh sub-part (``"LeftFace"``, ``"RightFace"``, ``"RoofDeck"``, etc.).
        world_pos_m: Intersection point ``(x, y, z)`` in **meters** (Z-up).
        normal: Unit surface normal facing back toward the camera ray in **meters**.
        distance_m: Distance along ray from origin in **meters**.
    """

    entity_id: str
    entity_kind: str
    sub_part: str
    world_pos_m: tuple[float, float, float]
    normal: tuple[float, float, float]
    distance_m: float


def _as_vec3(value: object, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"PickHit.{field_name} must be a 3-element sequence")
    coords: list[float] = []
    for elem in value:
        if not isinstance(elem, (int, float)):
            raise ValueError(f"PickHit.{field_name} entries must be numeric")
        coords.append(float(elem))
    return (coords[0], coords[1], coords[2])


def parse_pick_hit(raw_json: str | None) -> PickHit | None:
    """Parse a JSON ``PickHit`` string from ``_native_3d`` into :class:`PickHit`."""
    if not raw_json:
        return None
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object for PickHit")
    entity_id = parsed.get("entity_id")
    entity_kind = parsed.get("entity_kind")
    sub_part = parsed.get("sub_part")
    distance_m = parsed.get("distance_m")
    if not isinstance(entity_id, str) or not isinstance(entity_kind, str):
        raise ValueError("Malformed PickHit fields from native 3D picker")
    if not isinstance(sub_part, str) or not isinstance(distance_m, (int, float)):
        raise ValueError("Malformed PickHit fields from native 3D picker")
    return PickHit(
        entity_id=entity_id,
        entity_kind=entity_kind,
        sub_part=sub_part,
        world_pos_m=_as_vec3(parsed.get("world_pos_m"), "world_pos_m"),
        normal=_as_vec3(parsed.get("normal"), "normal"),
        distance_m=float(distance_m),
    )


class NativeSceneSessionProtocol(Protocol):
    """Typed interface exposed by ``_native_3d.NativeSceneSession``."""

    def load_scene(self, scene_json: str) -> str:
        """Load a full SceneIR v1 JSON document and return JSON summary."""
        ...

    def upsert_entities(self, delta_json: str) -> str:
        """Apply a SceneDeltaIR JSON patch and return JSON summary."""
        ...

    def remove_entities(self, ids: list[str]) -> str:
        """Remove entities by ID and return JSON summary."""
        ...

    def summary_json(self) -> str:
        """Return current loaded scene summary as JSON."""
        ...

    def entity_count(self) -> int:
        """Return number of loaded scene entities."""
        ...

    def set_asset_root(self, asset_root: str) -> int:
        """Load ``manifest.json`` and register `.glb` asset directory, returning entry count."""
        ...

    def mesh_stats_json(self) -> str:
        """Return compiled 3D mesh statistics JSON."""
        ...

    def export_glb(self, output_path: str) -> int:
        """Export current compiled 3D scene to `.glb` and return bytes written."""
        ...

    def init_gl(self) -> None:
        """Initialize OpenGL 3.3 Core resources inside active GL context."""
        ...

    def destroy_gl(self) -> None:
        """Release all GPU buffers, textures, and shaders cleanly."""
        ...

    def resize_gl(self, width: int, height: int) -> None:
        """Update framebuffer viewport size in physical pixels."""
        ...

    def render_gl(self) -> None:
        """Render shadow, sky, opaque PBR, and transparent passes."""
        ...

    def set_camera_mode(self, mode: str) -> None:
        """Switch between ``orbit`` and ``walkthrough`` camera modes."""
        ...

    def orbit_drag(self, dx: float, dy: float) -> None:
        """Rotate orbit camera or walkthrough head by pointer delta in pixels."""
        ...

    def pan_drag(self, dx: float, dy: float) -> None:
        """Pan camera parallel to view plane by pointer delta in pixels."""
        ...

    def zoom_scroll(self, delta: float) -> None:
        """Zoom camera by scroll wheel delta."""
        ...

    def walk_move(self, forward: float, right: float, up: float) -> None:
        """Translate camera eye/target incrementally in meters."""
        ...

    def set_camera_preset(self, preset: str) -> None:
        """Apply standard view preset (``iso``, ``top``, ``front``, ``back``, ``left``, ``right``)."""
        ...

    def fit_scene(self) -> None:
        """Fit orbit camera smoothly around the current scene bounding box."""
        ...

    def jump_to_room(self, x_m: float, y_m: float, floor_z_m: float) -> None:
        """Enter walkthrough mode at eye height (`1.676 m`) above `(x_m, y_m, floor_z_m)`."""
        ...

    def set_render_style(self, style: str) -> None:
        """Set visual style (``textured``, ``clay``, ``sketch``, ``xray``)."""
        ...

    def set_time_of_day(self, hour: float) -> None:
        """Set sun daylight hour (`6.0` to `20.0`)."""
        ...

    def set_dollhouse_level(self, level_id: str | None) -> None:
        """Slice display up to the specified level ID (or ``None`` for all levels)."""
        ...

    def set_auto_hide_roofs(self, enabled: bool) -> None:
        """Toggle hiding roofs and top ceilings when viewing from above."""
        ...

    def screen_ray(
        self, ndc_x: float, ndc_y: float
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Unproject OpenGL NDC coordinates ``(ndc_x, ndc_y)`` into ``(origin_m, dir_m)``."""
        ...

    def pick_screen(self, ndc_x: float, ndc_y: float) -> str | None:
        """Raycast from NDC screen coordinates and return JSON ``PickHit`` or ``None``."""
        ...

    def pick_ray(
        self,
        origin: tuple[float, float, float],
        direction: tuple[float, float, float],
    ) -> str | None:
        """Raycast in world **meters** and return JSON ``PickHit`` or ``None``."""
        ...

    def set_selected_entities(self, entity_ids: list[str]) -> None:
        """Highlight selected entity IDs in the OpenGL shader pass."""
        ...

    def set_hovered_entity(
        self,
        entity_id: str | None,
        sub_part: str | None,
        sub_part_only: bool,
    ) -> None:
        """Highlight hovered entity or sub-part in the OpenGL shader pass."""
        ...

    def set_transform_preview(
        self,
        entity_id: str,
        pivot_m: tuple[float, float, float],
        delta_pos_m: tuple[float, float, float],
        delta_rot_z_rad: float,
    ) -> None:
        """Apply zero-rebuild GPU model matrix offset for smooth interactive drags."""
        ...

    def clear_transform_preview(self) -> None:
        """Clear any active GPU transform preview matrix override."""
        ...


class _NativeModuleProtocol(Protocol):
    NATIVE_3D_VERSION: str
    SCHEMA_VERSION: int

    def echo_scene_ir(self, scene_json: str) -> str:
        ...

    def summarize_scene_ir(self, scene_json: str) -> str:
        ...

    def scene_mesh_stats(self, scene_json: str) -> str:
        ...

    def export_scene_glb(self, scene_json: str, output_path: str) -> int:
        ...

    def NativeSceneSession(self) -> NativeSceneSessionProtocol:
        ...


_NATIVE_MOD: _NativeModuleProtocol | None = None
_LOAD_ERROR: str | None = None

try:
    _imported = importlib.import_module("._native_3d", package=__package__ or "EstiSketch")
    _NATIVE_MOD = cast(_NativeModuleProtocol, _imported)
except (ImportError, OSError) as exc:
    _LOAD_ERROR = str(exc)


def _require_native() -> _NativeModuleProtocol:
    if _NATIVE_MOD is None:
        detail = _LOAD_ERROR or "compiled extension not installed"
        raise RuntimeError(f"EstiSketch._native_3d is not available: {detail}")
    return _NATIVE_MOD


def is_native_3d_available() -> bool:
    """Return ``True`` when the compiled Rust ``_native_3d`` extension loaded cleanly."""
    return _NATIVE_MOD is not None


def native_3d_load_error() -> str | None:
    """Return the import error string if ``_native_3d`` failed to load, else ``None``."""
    return _LOAD_ERROR


def native_3d_version() -> str | None:
    """Return compiled native module version string, or ``None`` if unavailable."""
    if _NATIVE_MOD is None:
        return None
    return _NATIVE_MOD.NATIVE_3D_VERSION


def native_schema_version() -> int | None:
    """Return supported SceneIR schema version reported by Rust, or ``None``."""
    if _NATIVE_MOD is None:
        return None
    return _NATIVE_MOD.SCHEMA_VERSION


def echo_scene_ir(scene: SceneIR | str) -> dict[str, object]:
    """Round-trip a ``SceneIR`` or JSON payload through Rust Serde validation."""
    mod = _require_native()
    payload = scene if isinstance(scene, str) else scene.to_json()
    raw = mod.echo_scene_ir(payload)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object from _native_3d.echo_scene_ir")
    return cast(dict[str, object], parsed)


def summarize_scene_ir(scene: SceneIR | str) -> dict[str, object]:
    """Load a ``SceneIR`` in Rust and return its parsed entity count summary."""
    mod = _require_native()
    payload = scene if isinstance(scene, str) else scene.to_json()
    raw = mod.summarize_scene_ir(payload)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object from _native_3d.summarize_scene_ir")
    return cast(dict[str, object], parsed)


def scene_mesh_stats(scene: SceneIR | str) -> dict[str, object]:
    """Build 3D scene meshes in Rust headlessly and return vertex/triangle/bounds stats."""
    mod = _require_native()
    payload = scene if isinstance(scene, str) else scene.to_json()
    raw = mod.scene_mesh_stats(payload)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object from _native_3d.scene_mesh_stats")
    return cast(dict[str, object], parsed)


def export_scene_glb(scene: SceneIR | str, output_path: str | Path) -> int:
    """Export ``scene`` directly to a binary glTF 2.0 ``.glb`` file via Rust."""
    mod = _require_native()
    payload = scene if isinstance(scene, str) else scene.to_json()
    return mod.export_scene_glb(payload, str(output_path))


ASSETS_3D_DIR: Path = Path(__file__).resolve().parent / "assets_3d"


def create_native_session() -> NativeSceneSessionProtocol:
    """Create a stateful Rust :class:`NativeSceneSession` and register bundled assets."""
    session = _require_native().NativeSceneSession()
    if ASSETS_3D_DIR.is_dir():
        session.set_asset_root(str(ASSETS_3D_DIR))
    return session


def serialize_delta_for_native(delta: SceneDeltaIR) -> str:
    """Serialize a :class:`SceneDeltaIR` to JSON for ``NativeSceneSession.upsert_entities``."""
    return delta.to_json()
