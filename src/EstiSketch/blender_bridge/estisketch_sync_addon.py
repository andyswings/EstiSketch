"""MIT-licensed Blender companion add-on (`estisketch_sync`) for Two-Tier glTF delta round-trips.

Install or run inside Blender 3.6+/4.x to export parametric moves, sculpted visual overrides,
and custom modeled meshes back into EstiSketch via `.esk-delta.zip` bundles while skipping
cameras, lights, empties, and `ESTISKETCH_IGNORE` helper objects.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

bl_info = {
    "name": "EstiSketch Two-Tier Sync",
    "author": "EstiSketch Contributors",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > EstiSketch Sync",
    "description": "Export parametric deltas and custom/edited .glb meshes to EstiSketch",
    "license": "MIT",
    "category": "Import-Export",
}

_IGNORED_TYPES = frozenset({"CAMERA", "LIGHT", "EMPTY", "SPEAKER", "LIGHT_PROBE"})


def _object_mesh_hash(obj: object) -> str:
    """Deterministic hash of local mesh vertex coordinates in millimeters."""
    mesh = getattr(obj, "data", None)
    verts = getattr(mesh, "vertices", None)
    if not verts:
        return ""
    h = hashlib.sha256()
    for v in verts:
        co = getattr(v, "co", (0.0, 0.0, 0.0))
        q = (round(float(co[0]) * 1000.0), round(float(co[1]) * 1000.0), round(float(co[2]) * 1000.0))
        h.update(f"{q[0]},{q[1]},{q[2]};".encode("ascii"))
    return h.hexdigest()[:16]


def export_delta_bundle_from_blender(output_zip: str | Path) -> Path:
    """Export current Blender scene delta into ``output_zip`` (`.esk-delta.zip`)."""
    import bpy

    out_path = Path(output_zip)
    entries: list[dict[str, object]] = []
    glb_blobs: dict[str, bytes] = {}
    tmp_dir = out_path.parent
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for obj in getattr(bpy.context.scene, "objects", []):
        obj_type = str(getattr(obj, "type", "MESH")).upper()
        name = str(getattr(obj, "name", "Object"))
        if obj_type in _IGNORED_TYPES or "ESTISKETCH_IGNORE" in name:
            continue
        est_id = ""
        if hasattr(obj, "get"):
            est_id = str(obj.get("estisketch_id") or obj.get("ESTISKETCH_ID") or "")
        loc = getattr(obj, "location", (0.0, 0.0, 0.0))
        rot = getattr(obj, "rotation_euler", (0.0, 0.0, 0.0))
        scale = getattr(obj, "scale", (1.0, 1.0, 1.0))

        entry: dict[str, object] = {
            "name": name,
            "blender_type": obj_type,
            "estisketch_id": est_id,
            "loc_m": [float(loc[0]), float(loc[1]), float(loc[2])],
            "rot_z_rad": float(rot[2]),
            "scale": [float(scale[0]), float(scale[1]), float(scale[2])],
            "mesh_hash": _object_mesh_hash(obj),
        }

        if not est_id or bool(obj.get("estisketch_mesh_modified", False)):
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            safe_stem = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name)
            rel = f"assets/{safe_stem}.glb"
            tmp_glb = tmp_dir / f".tmp_{safe_stem}.glb"
            bpy.ops.export_scene.gltf(
                filepath=str(tmp_glb),
                export_format="GLB",
                use_selection=True,
                export_extras=True,
            )
            if tmp_glb.is_file():
                glb_blobs[rel] = tmp_glb.read_bytes()
                tmp_glb.unlink()
                entry["glb"] = rel
                entry["mesh_modified"] = True
        entries.append(entry)

    manifest = {"schema_version": 1, "objects": entries}
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("delta_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        for rel, blob in glb_blobs.items():
            zf.writestr(rel, blob)
    return out_path


try:
    import bpy

    class ESTISKETCH_OT_export_delta(bpy.types.Operator):
        """Export modified & custom objects back to EstiSketch."""

        bl_idname = "estisketch.export_delta"
        bl_label = "Export EstiSketch Delta (.esk-delta.zip)"
        __annotations__ = {
            "filepath": bpy.props.StringProperty(
                subtype="FILE_PATH", default="changes.esk-delta.zip"
            )
        }

        def invoke(self, context, event):
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

        def execute(self, context):
            out = export_delta_bundle_from_blender(self.filepath)
            self.report({"INFO"}, f"Exported EstiSketch delta to {out}")
            return {"FINISHED"}

    class ESTISKETCH_PT_sync_panel(bpy.types.Panel):
        """Sidebar panel inside Blender 3D Viewport."""

        bl_label = "EstiSketch Sync"
        bl_idname = "ESTISKETCH_PT_sync_panel"
        bl_space_type = "VIEW_3D"
        bl_region_type = "UI"
        bl_category = "EstiSketch"

        def draw(self, context):
            layout = self.layout
            layout.operator("estisketch.export_delta", icon="EXPORT")

    def register():
        bpy.utils.register_class(ESTISKETCH_OT_export_delta)
        bpy.utils.register_class(ESTISKETCH_PT_sync_panel)

    def unregister():
        bpy.utils.unregister_class(ESTISKETCH_PT_sync_panel)
        bpy.utils.unregister_class(ESTISKETCH_OT_export_delta)
except ImportError:
    pass
