"""Two-Tier Blender Sync protocol: glTF export, delta classification, and atomic apply.

Implements Section 8.2 of ``docs/native_3d_architecture.md`` without requiring ``bpy`` or
``gi`` so all delta classification, boilerplate filtering, Tier 2A visual overrides, Tier 2B
custom 3D assets, and single-snapshot Undo invariants run under headless ``pytest``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path, PurePosixPath
import tempfile
from typing import Literal, cast
import zipfile

from .. import native_3d
from ..View3D.editor import (
    _hex_to_rgb,
    commit_canvas_mutation,
    is_object_editable,
    resolve_canvas_object,
    world_m_to_canvas_in,
)
from ..components import CustomAsset
from ..esk_archive import materialize_project_assets
from ..scene_ir import build_scene_ir_from_canvas
from ..scene_ir.parsed import INCH_TO_M

TierKind = Literal["parametric", "override_3d", "custom_asset"]

IGNORED_BLENDER_TYPES: frozenset[str] = frozenset(
    {"CAMERA", "LIGHT", "EMPTY", "SPEAKER", "LIGHT_PROBE"}
)
DEFAULT_UNANCHORED_NAMES: frozenset[str] = frozenset(
    {"Cube", "Camera", "Light", "Sun", "Suzanne"}
)

_BOOTSTRAP_SCRIPT = '''"""EstiSketch -> Blender glTF sync bootstrap script (MIT)."""
import json
from pathlib import Path
import bpy

sync_dir = Path(__file__).resolve().parent
glb_path = sync_dir / "project.glb"
manifest_path = sync_dir / "sync_manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(glb_path))

scene = bpy.context.scene
scene.render.engine = "CYCLES" if hasattr(bpy.types, "CyclesRenderSettings") else "BLENDER_EEVEE"

sun_info = manifest.get("sun", {})
sun_data = bpy.data.lights.new(name="EstiSketch_Sun", type="SUN")
sun_data.energy = 3.2
sun_obj = bpy.data.objects.new(name="EstiSketch_Sun", object_data=sun_data)
scene.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (0.78, 0.22, float(sun_info.get("azimuth_deg", 145.0)) * 0.01745329)

cam_data = bpy.data.cameras.new(name="EstiSketch_Camera")
cam_obj = bpy.data.objects.new(name="EstiSketch_Camera", object_data=cam_data)
scene.collection.objects.link(cam_obj)
cam_obj.location = (12.0, -12.0, 9.0)
cam_obj.rotation_euler = (1.02, 0.0, 0.78)
scene.camera = cam_obj
'''


@dataclass(frozen=True)
class SyncBundleResult:
    """Files written by :func:`export_gltf_sync_bundle` for Blender import."""

    output_dir: Path
    glb_path: Path
    manifest_path: Path
    bootstrap_path: Path
    entity_count: int


@dataclass
class DeltaItem:
    """Single classified object delta parsed from a Blender ``.esk-delta.zip`` bundle."""

    tier: TierKind
    entity_id: str
    entity_kind: str
    name: str
    summary: str
    payload: dict[str, object] = field(default_factory=dict)
    glb_bytes: bytes | None = None
    accepted: bool = True


@dataclass
class DeltaImportPlan:
    """Reviewable import plan returned by :func:`classify_blender_delta`."""

    items: list[DeltaItem]
    ignored_count: int
    ignored_reasons: list[str]
    plan_center_in: tuple[float, float]


def export_gltf_sync_bundle(
    canvas: object, output_dir: str | Path
) -> SyncBundleResult:
    """Export ``project.glb``, ``sync_manifest.json``, and ``blender_bootstrap.py``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    scene = build_scene_ir_from_canvas(canvas)

    glb_path = out / "project.glb"
    native_3d.export_scene_glb(scene, glb_path)

    entities: dict[str, dict[str, object]] = {}
    for w in scene.walls:
        entities[w.id] = {"kind": "wall", "level_id": w.level_id}
    for fx in scene.fixtures:
        entities[fx.id] = {
            "kind": "fixture",
            "level_id": fx.level_id,
            "loc_m": list(fx.loc_m),
            "rot_z_rad": fx.rot_z_rad,
        }
    for ca in scene.custom_assets:
        entities[ca.id] = {
            "kind": "custom_asset",
            "loc_m": list(ca.loc_m),
            "rot_z_rad": ca.rot_z_rad,
        }

    sync_state = {
        "schema_version": 1,
        "plan_center_in": list(scene.plan_center_in),
        "sun": {
            "north_angle_deg": scene.sun.north_angle_deg,
            "azimuth_deg": scene.sun.azimuth_deg,
            "elevation_deg": scene.sun.elevation_deg,
        },
        "entities": entities,
    }
    manifest_path = out / "sync_manifest.json"
    manifest_path.write_text(json.dumps(sync_state, indent=2, sort_keys=True), encoding="utf-8")

    bootstrap_path = out / "blender_bootstrap.py"
    bootstrap_path.write_text(_BOOTSTRAP_SCRIPT, encoding="utf-8")

    setattr(canvas, "blender_sync_state", sync_state)
    return SyncBundleResult(
        output_dir=out,
        glb_path=glb_path,
        manifest_path=manifest_path,
        bootstrap_path=bootstrap_path,
        entity_count=len(entities),
    )


def _safe_zip_member(rel_path: str) -> str:
    cleaned = rel_path.replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/"):
        raise ValueError(f"Unsafe zip path '{rel_path}'")
    posix = PurePosixPath(cleaned)
    if ".." in posix.parts:
        raise ValueError(f"Unsafe zip traversal path '{rel_path}'")
    return str(posix)


def _float_tuple3(raw: object, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        out: list[float] = []
        for elem in raw[:3]:
            if isinstance(elem, (int, float)):
                out.append(float(elem))
        if len(out) == 3:
            return (out[0], out[1], out[2])
    return default


def _inspect_glb_bytes_for_hull(glb_bytes: bytes) -> tuple[list[tuple[float, float]], str]:
    """Compute 2D footprint in **inches** + mesh hash from raw ``.glb`` bytes via Rust."""
    if not native_3d.is_native_3d_available():
        return ([(-18.0, -18.0), (18.0, -18.0), (18.0, 18.0), (-18.0, 18.0)], "")
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        tmp.write_bytes(glb_bytes)
        info = native_3d.inspect_3d_asset(tmp)
        hull_in = [(x / INCH_TO_M, -y / INCH_TO_M) for (x, y) in info.silhouette_2d_m]
        return (hull_in, info.mesh_hash)
    finally:
        if tmp.exists():
            tmp.unlink()


def classify_blender_delta(canvas: object, delta_zip_path: str | Path) -> DeltaImportPlan:
    """Parse ``.esk-delta.zip`` from Blender and classify entries into Tier 1 / 2A / 2B."""
    src = Path(delta_zip_path)
    sync_state = getattr(canvas, "blender_sync_state", None)
    base_center = (0.0, 0.0)
    baseline_hashes: dict[str, str] = {}
    if isinstance(sync_state, dict):
        raw_pc = sync_state.get("plan_center_in")
        if isinstance(raw_pc, (list, tuple)) and len(raw_pc) >= 2:
            if isinstance(raw_pc[0], (int, float)) and isinstance(raw_pc[1], (int, float)):
                base_center = (float(raw_pc[0]), float(raw_pc[1]))
        raw_hashes = sync_state.get("mesh_hashes")
        if isinstance(raw_hashes, dict):
            baseline_hashes = {str(k): str(v) for k, v in raw_hashes.items()}

    items: list[DeltaItem] = []
    ignored_reasons: list[str] = []

    with zipfile.ZipFile(src, "r") as zf:
        names = set(zf.namelist())
        if "delta_manifest.json" not in names:
            raise ValueError(f"'{src}' is missing required delta_manifest.json")
        manifest = json.loads(zf.read("delta_manifest.json").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("delta_manifest.json must contain a JSON object")

        raw_pc_m = manifest.get("plan_center_in")
        if isinstance(raw_pc_m, (list, tuple)) and len(raw_pc_m) >= 2:
            if isinstance(raw_pc_m[0], (int, float)) and isinstance(raw_pc_m[1], (int, float)):
                base_center = (float(raw_pc_m[0]), float(raw_pc_m[1]))

        raw_objects = manifest.get("objects")
        obj_list = raw_objects if isinstance(raw_objects, list) else []
        for entry in obj_list:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "Object")
            b_type = str(entry.get("blender_type") or "MESH").upper()
            ent_id = str(entry.get("estisketch_id") or "").strip()

            if entry.get("ignore") or "ESTISKETCH_IGNORE" in name:
                ignored_reasons.append(f"{name}: marked ESTISKETCH_IGNORE")
                continue
            if b_type in IGNORED_BLENDER_TYPES:
                ignored_reasons.append(f"{name}: ignored {b_type}")
                continue
            if not ent_id and name in DEFAULT_UNANCHORED_NAMES:
                ignored_reasons.append(f"{name}: un-anchored default primitive")
                continue

            glb_rel = str(entry.get("glb") or "").strip()
            glb_bytes: bytes | None = None
            if glb_rel:
                safe_rel = _safe_zip_member(glb_rel)
                if safe_rel in names:
                    glb_bytes = zf.read(safe_rel)

            resolved = resolve_canvas_object(canvas, ent_id) if ent_id else None
            if resolved is None and ent_id:
                for ca in getattr(canvas, "custom_assets", []) or []:
                    if getattr(ca, "identifier", "") == ent_id:
                        resolved = ("custom_asset", ca, ca)
                        break

            if resolved is not None:
                sel_type, _, primary = resolved
                new_hash = str(entry.get("mesh_hash") or "")
                old_hash = baseline_hashes.get(ent_id, "")
                mesh_modified = bool(entry.get("mesh_modified", False))
                if not mesh_modified and new_hash and old_hash and new_hash != old_hash:
                    mesh_modified = True

                if mesh_modified and glb_bytes is not None:
                    items.append(
                        DeltaItem(
                            tier="override_3d",
                            entity_id=ent_id,
                            entity_kind=sel_type,
                            name=name,
                            summary=f"Visual 3D override for {sel_type} ({name})",
                            payload={
                                "mesh_hash": new_hash,
                                "glb_rel": glb_rel or f"assets/override_{ent_id}.glb",
                            },
                            glb_bytes=glb_bytes,
                        )
                    )
                else:
                    items.append(
                        DeltaItem(
                            tier="parametric",
                            entity_id=ent_id,
                            entity_kind=sel_type,
                            name=name,
                            summary=f"Parametric update to {sel_type} ({getattr(primary, 'custom_name', '') or name})",
                            payload={str(k): v for k, v in entry.items()},
                        )
                    )
                continue

            # Tier 2B: new user-created mesh in Blender without ESTISKETCH_ID
            if glb_bytes is None:
                ignored_reasons.append(f"{name}: new object missing .glb payload")
                continue
            hull_in, mesh_hash = _inspect_glb_bytes_for_hull(glb_bytes)
            payload = {str(k): v for k, v in entry.items()}
            payload["silhouette_2d"] = hull_in
            payload["mesh_hash"] = mesh_hash or str(entry.get("mesh_hash") or "")
            assigned_id = ent_id or str(entry.get("new_estisketch_id") or "")
            items.append(
                DeltaItem(
                    tier="custom_asset",
                    entity_id=assigned_id,
                    entity_kind="custom_asset",
                    name=name,
                    summary=f"New custom 3D asset '{name}' ({len(hull_in)}-pt 2D footprint)",
                    payload=payload,
                    glb_bytes=glb_bytes,
                )
            )

    return DeltaImportPlan(
        items=items,
        ignored_count=len(ignored_reasons),
        ignored_reasons=ignored_reasons,
        plan_center_in=base_center,
    )


def apply_delta_import_plan(
    canvas: object,
    plan: DeltaImportPlan,
    accepted_indices: set[int] | None = None,
) -> tuple[int, list[str]]:
    """Apply checked :class:`DeltaImportPlan` items to ``canvas`` in ONE atomic Undo snapshot."""
    warnings: list[str] = []
    applied = 0

    for idx, item in enumerate(plan.items):
        if accepted_indices is not None and idx not in accepted_indices:
            continue
        if not item.accepted and accepted_indices is None:
            continue

        if item.tier == "custom_asset":
            if item.glb_bytes is None:
                warnings.append(f"Skipped {item.name}: missing .glb binary")
                continue
            loc_m = _float_tuple3(item.payload.get("loc_m"), (0.0, 0.0, 0.0))
            x_in, y_in, z_in = world_m_to_canvas_in(loc_m, plan.plan_center_in)
            rot_rad = float(cast(float, item.payload.get("rot_z_rad", 0.0)))
            scale = _float_tuple3(item.payload.get("scale"), (1.0, 1.0, 1.0))
            raw_hull = item.payload.get("silhouette_2d")
            hull: list[tuple[float, float]] = []
            if isinstance(raw_hull, list):
                for pt in raw_hull:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        hull.append((float(pt[0]), float(pt[1])))
            ca = CustomAsset(
                identifier=item.entity_id or "",
                name=item.name,
                x=x_in,
                y=y_in,
                z=max(0.0, z_in),
                rotation=-math.degrees(rot_rad) % 360.0,
                scale=scale,
                silhouette_2d=hull,
                glb_bytes=item.glb_bytes,
                layer_id=str(getattr(canvas, "active_layer_id", "") or ""),
            )
            ca.glb_rel_path = f"assets/{ca.identifier}.glb"
            lst = getattr(canvas, "custom_assets", None)
            if isinstance(lst, list):
                lst.append(ca)
            else:
                setattr(canvas, "custom_assets", [ca])
            applied += 1
            continue

        # Locate existing object for Tier 1 / Tier 2A
        resolved = resolve_canvas_object(canvas, item.entity_id)
        if resolved is None:
            for ca in getattr(canvas, "custom_assets", []) or []:
                if getattr(ca, "identifier", "") == item.entity_id:
                    resolved = ("custom_asset", ca, ca)
                    break
        if resolved is None:
            warnings.append(f"Missing target object '{item.entity_id}' for {item.name}")
            continue

        sel_type, _sel_obj, primary = resolved
        if not is_object_editable(canvas, primary):
            warnings.append(f"Locked target '{item.name}' skipped")
            continue

        if item.tier == "override_3d":
            if item.glb_bytes is None:
                warnings.append(f"Skipped override {item.name}: missing .glb binary")
                continue
            ov_map = getattr(canvas, "overrides_3d", None)
            if not isinstance(ov_map, dict):
                ov_map = {}
                setattr(canvas, "overrides_3d", ov_map)
            rel = f"assets/override_{item.entity_id}.glb"
            ov_map[item.entity_id] = {
                "entity_kind": sel_type,
                "name": item.name,
                "glb_rel_path": rel,
                "mesh_hash": str(item.payload.get("mesh_hash") or ""),
                "glb_bytes": item.glb_bytes,
            }
            setattr(primary, "custom_3d_override", rel)
            applied += 1
            continue

        # Tier 1 parametric delta application
        if _apply_parametric_delta(primary, sel_type, item.payload, plan.plan_center_in):
            applied += 1

    if applied > 0:
        materialize_project_assets(canvas)
        commit_canvas_mutation(canvas)

    return (applied, warnings)


def _apply_parametric_delta(
    obj: object,
    kind: str,
    payload: dict[str, object],
    plan_center_in: tuple[float, float],
) -> bool:
    changed = False
    loc_raw = payload.get("loc_m")
    if isinstance(loc_raw, (list, tuple)) and len(loc_raw) >= 3:
        loc_m = _float_tuple3(loc_raw, (0.0, 0.0, 0.0))
        x_in, y_in, z_in = world_m_to_canvas_in(loc_m, plan_center_in)
        if kind in ("fixture", "custom_asset"):
            setattr(obj, "x", x_in)
            setattr(obj, "y", y_in)
            if kind == "custom_asset":
                setattr(obj, "z", max(0.0, z_in))
            changed = True

    rot_raw = payload.get("rot_z_rad")
    if isinstance(rot_raw, (int, float)) and kind in ("fixture", "custom_asset"):
        setattr(obj, "rotation", (-math.degrees(float(rot_raw))) % 360.0)
        changed = True

    color_raw = payload.get("base_color_hex")
    if isinstance(color_raw, str) and color_raw.startswith("#"):
        rgb = _hex_to_rgb(color_raw)
        if kind == "fixture":
            setattr(obj, "fill_color", rgb)
            changed = True
        elif kind == "wall":
            setattr(obj, "left_color", rgb)
            setattr(obj, "right_color", rgb)
            changed = True

    height_m = payload.get("height_m")
    if isinstance(height_m, (int, float)) and kind == "wall":
        h_in = max(12.0, min(480.0, float(height_m) / INCH_TO_M))
        setattr(obj, "height", h_in)
        setattr(obj, "height_at_end", h_in)
        changed = True

    pitch_raw = payload.get("pitch_rise")
    if isinstance(pitch_raw, (int, float)) and kind == "roof":
        setattr(obj, "pitch_rise", max(1.0, min(18.0, float(pitch_raw))))
        changed = True

    return changed


def reset_object_to_parametric(canvas: object, entity_id: str) -> bool:
    """Clear any Tier 2A Blender 3D visual override on ``entity_id`` and commit one undo."""
    ov_map = getattr(canvas, "overrides_3d", None)
    had_override = isinstance(ov_map, dict) and entity_id in ov_map
    if isinstance(ov_map, dict):
        ov_map.pop(entity_id, None)

    resolved = resolve_canvas_object(canvas, entity_id)
    if resolved is not None:
        _, _, primary = resolved
        if getattr(primary, "custom_3d_override", ""):
            setattr(primary, "custom_3d_override", "")
            had_override = True

    if had_override:
        commit_canvas_mutation(canvas)
    return had_override
