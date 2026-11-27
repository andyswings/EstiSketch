"""Build a Blender scene from EstiSketch's own 3D assets (no add-ons required).

Imports the ``.glb`` bundle exported by EstiSketch's native 3D mesher + CC0 asset
pack, organizes objects into per-level collections, restores canonical centers for
movable fixtures/assets, sets up sun lighting, and enables live Ctrl+S sync back to
EstiSketch. Optionally delegates to ``estisketch_to_hb5.py`` when the user enables
Home Builder 5 and selects ``auto`` or ``hb5`` mode.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from typing import Literal

VALID_ASSET_SOURCES: tuple[str, ...] = ("estisketch", "auto", "hb5")
BackendChoice = Literal["estisketch", "hb5"]

_KIND_TO_BUCKET: dict[str, str] = {
    "wall": "Walls",
    "footer": "Foundations",
    "rim_band": "Walls",
    "door": "Openings",
    "window": "Openings",
    "opening": "Openings",
    "room": "Rooms",
    "roof": "Roofs",
    "stair": "Stairs",
    "fixture": "Fixtures",
    "custom_asset": "Custom Assets",
}


def normalize_asset_source(value: str | None) -> str:
    """Normalize a configured asset source string to ``estisketch``, ``auto``, or ``hb5``."""
    cleaned = (value or "estisketch").strip().lower()
    if cleaned in VALID_ASSET_SOURCES:
        return cleaned
    return "estisketch"


def resolve_backend_choice(
    asset_source: str,
    hb5_available: bool,
    has_xml: bool,
    has_glb: bool,
) -> BackendChoice:
    """Choose whether Blender builds via ``estisketch`` glTF or optional ``hb5``."""
    mode = normalize_asset_source(asset_source)
    if mode in ("auto", "hb5") and hb5_available and has_xml:
        return "hb5"
    if has_glb:
        return "estisketch"
    if hb5_available and has_xml:
        return "hb5"
    return "estisketch"


def parse_cli_args(argv: list[str]) -> dict[str, str]:
    """Parse Blender script CLI arguments after ``--``."""
    args = argv[argv.index("--") + 1:] if "--" in argv else []

    def _opt(flag: str, default: str = "") -> str:
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1]
        return default

    glb_path = _opt("--glb")
    if not glb_path and args and not args[0].startswith("--"):
        glb_path = args[0]

    return {
        "glb": glb_path,
        "manifest": _opt("--manifest"),
        "xml": _opt("--xml"),
        "sync_dir": _opt("--sync-dir"),
        "custom_assets": _opt("--custom-assets"),
        "asset_source": normalize_asset_source(_opt("--asset-source", "estisketch")),
        "save_blend": _opt("--save-blend"),
    }


def is_hb5_enabled_in_blender() -> bool:
    """Return True when the optional ``home_builder_5`` extension is enabled in Blender."""
    import bpy

    for key in bpy.context.preferences.addons.keys():
        if key == "home_builder_5" or key.endswith(".home_builder_5"):
            return True
    return False


def _load_sibling_module(module_name: str, filename: str) -> object | None:
    path = Path(__file__).resolve().with_name(filename)
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ensure_collection(name: str, parent: object) -> object:
    import bpy

    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        parent.children.link(col)  # type: ignore[attr-defined]
    elif col.name not in [c.name for c in parent.children]:  # type: ignore[attr-defined]
        parent.children.link(col)  # type: ignore[attr-defined]
    return col


def _move_to_collection(obj: object, target_col: object) -> None:
    users = list(getattr(obj, "users_collection", []))
    if target_col not in users:
        target_col.objects.link(obj)  # type: ignore[attr-defined]
    for col in users:
        if col != target_col:
            col.objects.unlink(obj)


def _clear_scene(scene: object) -> None:
    import bpy

    for obj in list(getattr(scene, "objects", [])):
        bpy.data.objects.remove(obj, do_unlink=True)


def _setup_sun(target_col: object, sun_info: dict[str, object]) -> None:
    import bpy

    azimuth_deg = float(sun_info.get("azimuth_deg", 145.0) or 145.0)
    elev_deg = float(sun_info.get("elevation_deg", 48.0) or 48.0)
    light_data = bpy.data.lights.new(name="EstiSketch_Sun", type="SUN")
    light_data.energy = 2.8
    light_obj = bpy.data.objects.new(name="EstiSketch_Sun", object_data=light_data)
    light_obj.rotation_euler = (
        math.radians(max(5.0, 90.0 - elev_deg)),
        0.0,
        math.radians(azimuth_deg),
    )
    target_col.objects.link(light_obj)  # type: ignore[attr-defined]


def _extract_entity_id(obj: object, known_ids: set[str]) -> str:
    raw = str(obj.get("estisketch_id") or "").strip()  # type: ignore[attr-defined]
    if raw:
        return raw
    name = str(getattr(obj, "name", "") or "")
    for eid in sorted(known_ids, key=len, reverse=True):
        if name == eid or name.startswith(f"{eid}_"):
            return eid
    return ""


def _bake_world_transform_into_mesh(obj: object) -> None:
    """Apply ``obj.matrix_world`` directly to mesh vertices and reset transform to identity."""
    from mathutils import Matrix

    mesh = getattr(obj, "data", None)
    if mesh is None or not hasattr(mesh, "transform"):
        return
    mw = obj.matrix_world.copy()  # type: ignore[attr-defined]
    obj.parent = None  # type: ignore[attr-defined]
    mesh.transform(mw)
    mesh.update()
    obj.matrix_world = Matrix.Identity(4)  # type: ignore[attr-defined]


def _recenter_movable_object(
    obj: object,
    loc_m: tuple[float, float, float],
    rot_z_rad: float,
) -> None:
    """Shift mesh vertices to object-local coordinates so ``obj`` sits at ``(loc_m, rot_z_rad)``."""
    from mathutils import Matrix

    mesh = getattr(obj, "data", None)
    if mesh is None or not hasattr(mesh, "transform"):
        return
    lx, ly, lz = loc_m
    inv = Matrix.Rotation(-rot_z_rad, 4, "Z") @ Matrix.Translation((-lx, -ly, -lz))
    mesh.transform(inv)
    mesh.update()
    obj.location = (lx, ly, lz)  # type: ignore[attr-defined]
    obj.rotation_euler = (0.0, 0.0, rot_z_rad)  # type: ignore[attr-defined]


def _join_mesh_objects(objs: list[object]) -> object:
    """Join ``objs`` into a single multi-material mesh object and return it."""
    import bpy

    if len(objs) == 1:
        return objs[0]
    for o in bpy.context.scene.objects:
        o.select_set(False)
    primary = objs[0]
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = primary
    bpy.ops.object.join()
    return primary


def _schedule_viewport_frame() -> None:
    import bpy

    def _frame() -> None:
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with bpy.context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_all()
                        return

    bpy.app.timers.register(_frame, first_interval=0.25)


def build_standalone_in_blender(
    glb_path: str,
    manifest_path: str,
    xml_path: str = "",
    sync_dir: str = "",
    custom_assets_json: str = "",
    asset_source: str = "estisketch",
    save_blend_path: str = "",
) -> dict[str, object]:
    """Load an EstiSketch project into Blender using EstiSketch assets or optional HB5."""
    import bpy

    hb5_ready = is_hb5_enabled_in_blender()
    backend = resolve_backend_choice(
        asset_source=asset_source,
        hb5_available=hb5_ready,
        has_xml=bool(xml_path and os.path.isfile(xml_path)),
        has_glb=bool(glb_path and os.path.isfile(glb_path)),
    )

    if backend == "hb5":
        hb5_mod = _load_sibling_module("estisketch_to_hb5_runner", "estisketch_to_hb5.py")
        if hb5_mod is not None and hasattr(hb5_mod, "build_in_blender"):
            stats = dict(
                hb5_mod.build_in_blender(  # type: ignore[attr-defined]
                    xml_path,
                    save_blend_path=save_blend_path,
                    sync_dir=sync_dir,
                    custom_assets_json=custom_assets_json,
                )
            )
            stats["backend"] = "hb5"
            return stats

    if not glb_path or not os.path.isfile(glb_path):
        raise FileNotFoundError(f"Standalone Blender .glb bundle not found: {glb_path}")

    manifest: dict[str, object] = {}
    if manifest_path and os.path.isfile(manifest_path):
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    raw_center = manifest.get("plan_center_in", [0.0, 0.0])
    cx = float(raw_center[0]) if isinstance(raw_center, list) and len(raw_center) >= 2 else 0.0
    cy = float(raw_center[1]) if isinstance(raw_center, list) and len(raw_center) >= 2 else 0.0
    entities_meta = manifest.get("entities", {})
    if not isinstance(entities_meta, dict):
        entities_meta = {}
    levels_meta = manifest.get("levels", [])
    if not isinstance(levels_meta, list):
        levels_meta = []
    sun_meta = manifest.get("sun", {})
    if not isinstance(sun_meta, dict):
        sun_meta = {}

    scene = bpy.context.scene
    _clear_scene(scene)
    scene["IS_ROOM_SCENE"] = True
    scene.unit_settings.system = "IMPERIAL"
    scene.unit_settings.length_unit = "INCHES"

    root_col = _ensure_collection("EstiSketch Import", scene.collection)
    _setup_sun(root_col, sun_meta)

    bucket_cols: dict[tuple[str, str], object] = {}
    level_cols: dict[str, object] = {}
    for lvl in levels_meta:
        if not isinstance(lvl, dict):
            continue
        lid = str(lvl.get("id") or "")
        lname = str(lvl.get("name") or lid or "Level 1")
        lvl_col = _ensure_collection(f"EstiSketch - {lname}", root_col)
        level_cols[lid] = lvl_col
        for bucket in ("Walls", "Openings", "Rooms", "Roofs", "Stairs", "Fixtures",
                       "Custom Assets", "Foundations"):
            bucket_cols[(lid, bucket)] = _ensure_collection(f"{lname} - {bucket}", lvl_col)

    fallback_col = _ensure_collection("EstiSketch - Scene", root_col)

    before_names = set(bpy.data.objects.keys())
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    imported_objs = [obj for obj in bpy.data.objects if obj.name not in before_names]

    known_ids = set(str(k) for k in entities_meta.keys())
    grouped_meshes: dict[str, list[object]] = {}
    ungrouped_meshes: list[object] = []
    empties_to_delete: list[object] = []

    for obj in imported_objs:
        if str(getattr(obj, "type", "")).upper() != "MESH":
            empties_to_delete.append(obj)
            continue
        _bake_world_transform_into_mesh(obj)
        eid = _extract_entity_id(obj, known_ids)
        if eid:
            grouped_meshes.setdefault(eid, []).append(obj)
        else:
            ungrouped_meshes.append(obj)

    for emp in empties_to_delete:
        if emp.name in bpy.data.objects:
            bpy.data.objects.remove(emp, do_unlink=True)

    built_count = 0
    for eid, mesh_objs in grouped_meshes.items():
        obj = _join_mesh_objects(mesh_objs)
        meta = entities_meta.get(eid, {})
        if not isinstance(meta, dict):
            meta = {}
        kind = str(meta.get("kind") or obj.get("entity_kind") or "entity")
        label = str(meta.get("name") or kind.title())
        lvl_id = str(meta.get("level_id") or obj.get("level_id") or "")
        z_offset_m = float(meta.get("z_offset_m", 0.0) or 0.0)
        is_sync_entity = bool(meta.get("sync_editable", True))

        obj.name = f"{label}_{eid}"
        if is_sync_entity:
            obj["ESTISKETCH_ID"] = eid
            obj["ESTISKETCH_Z_OFFSET_M"] = z_offset_m

        loc_raw = meta.get("loc_m")
        rot_raw = meta.get("rot_z_rad")
        if kind in ("fixture", "custom_asset") and isinstance(loc_raw, list) and len(loc_raw) >= 3:
            loc_m = (float(loc_raw[0]), float(loc_raw[1]), float(loc_raw[2]))
            rot_z = float(rot_raw or 0.0)
            _recenter_movable_object(obj, loc_m, rot_z)

        bucket_name = _KIND_TO_BUCKET.get(kind, "Fixtures")
        target_col = bucket_cols.get((lvl_id, bucket_name), level_cols.get(lvl_id, fallback_col))
        _move_to_collection(obj, target_col)
        built_count += 1

    for obj in ungrouped_meshes:
        _move_to_collection(obj, fallback_col)
        built_count += 1

    bpy.context.view_layer.update()

    if save_blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=save_blend_path)

    live_sync = _load_sibling_module("blender_live_sync", "blender_live_sync.py") if sync_dir else None
    if live_sync is not None and sync_dir:
        live_sync.tag_generated_objects((cx, cy))  # type: ignore[attr-defined]
        live_sync.install_save_handler(sync_dir)  # type: ignore[attr-defined]

    if not bpy.app.background:
        _schedule_viewport_frame()
        if normalize_asset_source(asset_source) == "hb5" and not hb5_ready and live_sync is not None:
            show_fn = getattr(live_sync, "_show_status", None)
            if callable(show_fn):
                show_fn(
                    "EstiSketch: Home Builder 5 add-on not enabled; loaded EstiSketch 3D assets."
                )

    return {
        "backend": "estisketch",
        "hb5_fallback": normalize_asset_source(asset_source) == "hb5" and not hb5_ready,
        "objects": built_count,
        "entities": len(grouped_meshes),
        "levels": len(levels_meta),
    }


if __name__ == "__main__":
    opts = parse_cli_args(sys.argv)
    result = build_standalone_in_blender(
        glb_path=opts["glb"],
        manifest_path=opts["manifest"],
        xml_path=opts["xml"],
        sync_dir=opts["sync_dir"],
        custom_assets_json=opts["custom_assets"],
        asset_source=opts["asset_source"],
        save_blend_path=opts["save_blend"],
    )
    print(f"EstiSketch standalone Blender build complete: {result}")
