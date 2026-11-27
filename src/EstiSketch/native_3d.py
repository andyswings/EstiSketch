"""Optional Python wrapper around the native Rust ``EstiSketch._native_3d`` extension.

The main EstiSketch 2D application and headless test suite continue to operate if
the compiled Rust extension is unavailable in a checkout; availability can be
queried via :func:`is_native_3d_available`.
"""

from __future__ import annotations

import importlib
import json
from typing import Protocol, cast

from .scene_ir import SceneDeltaIR, SceneIR


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


class _NativeModuleProtocol(Protocol):
    NATIVE_3D_VERSION: str
    SCHEMA_VERSION: int

    def echo_scene_ir(self, scene_json: str) -> str:
        ...

    def summarize_scene_ir(self, scene_json: str) -> str:
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


def create_native_session() -> NativeSceneSessionProtocol:
    """Create a stateful Rust :class:`NativeSceneSession` for incremental updates."""
    return _require_native().NativeSceneSession()


def serialize_delta_for_native(delta: SceneDeltaIR) -> str:
    """Serialize a :class:`SceneDeltaIR` to JSON for ``NativeSceneSession.upsert_entities``."""
    return delta.to_json()
