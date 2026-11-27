"""Launch Blender populated from an EstiSketch project (standalone assets or optional HB5)."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from .. import esk_archive, native_3d, project_io
from ..scene_ir import build_scene_ir_from_canvas
from ..scene_ir.parsed import INCH_TO_M
from .estisketch_to_blender import normalize_asset_source


def get_bridge_script_path() -> str:
    """Return the absolute path to ``estisketch_to_hb5.py``."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "estisketch_to_hb5.py")


def get_standalone_bridge_script_path() -> str:
    """Return the absolute path to ``estisketch_to_blender.py``."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "estisketch_to_blender.py")


def is_hb5_installed() -> bool:
    """Return ``True`` when the optional Home Builder 5 Blender add-on directory exists."""
    patterns = [
        os.path.expanduser("~/.config/blender/*/extensions/*/home_builder_5"),
        os.path.expanduser("~/.config/blender/*/scripts/addons/home_builder_5"),
        os.path.expanduser(
            "~/Library/Application Support/Blender/*/extensions/*/home_builder_5"
        ),
        os.path.expanduser(
            "~/Library/Application Support/Blender/*/scripts/addons/home_builder_5"
        ),
    ]
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            patterns.extend([
                os.path.join(
                    appdata, "Blender Foundation", "Blender", "*", "extensions", "*",
                    "home_builder_5",
                ),
                os.path.join(
                    appdata, "Blender Foundation", "Blender", "*", "scripts", "addons",
                    "home_builder_5",
                ),
            ])
    return any(glob.glob(p) for p in patterns)


def find_blender_executable(configured_path: str = "") -> Optional[str]:
    """Locate a Blender executable from user config, PATH, or standard install paths."""
    candidate = (configured_path or "").strip()
    if candidate:
        expanded = os.path.expanduser(candidate)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    which_blender = shutil.which("blender")
    if which_blender:
        return which_blender

    candidates = [
        "/snap/bin/blender",
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/Applications/Blender.app/Contents/MacOS/Blender",
    ]
    if sys.platform == "win32":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.extend(
            sorted(
                glob.glob(os.path.join(prog_files, "Blender Foundation", "Blender *", "blender.exe")),
                reverse=True,
            )
        )

    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def write_custom_assets_manifest(canvas: object, sync_dir: str) -> str:
    """Copy custom ``.glb`` assets into ``sync_dir`` and write ``custom_assets.json``.

    Positions are EstiSketch inches / degrees; the Blender side converts to meters.

    Returns:
        Absolute path of the JSON manifest (an empty list when there are no assets).
    """
    assets = list(getattr(canvas, "custom_assets", []) or [])
    manifest: list[dict[str, object]] = []
    if assets:
        cache_dir = esk_archive.materialize_project_assets(canvas)
        out_dir = os.path.join(sync_dir, "assets")
        os.makedirs(out_dir, exist_ok=True)
        elevations = {
            str(getattr(lvl, "id", "")): float(getattr(lvl, "elevation", 0.0))
            for lvl in getattr(canvas, "levels", []) or []
        }
        for item in assets:
            rel = str(getattr(item, "glb_rel_path", "") or "")
            src = os.path.join(str(cache_dir), rel)
            if not rel or not os.path.isfile(src):
                continue
            ident = str(getattr(item, "identifier", ""))
            dst = os.path.join(out_dir, f"{ident}.glb")
            shutil.copyfile(src, dst)
            manifest.append(
                {
                    "identifier": ident,
                    "name": str(getattr(item, "name", "") or "Custom Asset"),
                    "glb": dst,
                    "x": float(item.x),  # type: ignore[attr-defined]
                    "y": float(item.y),  # type: ignore[attr-defined]
                    "z": float(item.z),  # type: ignore[attr-defined]
                    "rotation": float(item.rotation),  # type: ignore[attr-defined]
                    "scale": [float(v) for v in item.scale],  # type: ignore[attr-defined]
                    "level_elevation_in": elevations.get(str(getattr(item, "level_id", "")), 0.0),
                }
            )
    path = os.path.join(sync_dir, "custom_assets.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return path


def new_sync_session_dir() -> str:
    """Create and return a fresh per-launch sync folder in the system temp directory."""
    base = os.path.join(tempfile.gettempdir(), "estisketch_blender_bridge")
    os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix="session_", dir=base)


def export_standalone_blender_bundle(canvas: object, sync_dir: str) -> Tuple[str, str]:
    """Export ``project.glb`` and ``scene_manifest.json`` using EstiSketch's own 3D assets.

    Returns:
        ``(glb_path, manifest_path)`` written inside ``sync_dir``.
    """
    scene = build_scene_ir_from_canvas(canvas)
    esk_archive.materialize_project_assets(canvas)

    glb_path = os.path.join(sync_dir, "project.glb")
    session = native_3d.create_native_session()
    session.load_scene(scene.to_json())
    session.export_glb(glb_path)

    level_elev_by_id = {lvl.id: float(lvl.elevation_m) for lvl in scene.levels}
    entities: dict[str, dict[str, object]] = {}

    for w in scene.walls:
        entities[w.id] = {
            "kind": "wall",
            "name": "Wall",
            "level_id": w.level_id,
            "z_offset_m": level_elev_by_id.get(w.level_id, 0.0),
            "sync_editable": True,
        }
    wall_level_by_id = {w.id: w.level_id for w in scene.walls}
    for op in scene.openings:
        lvl_id = wall_level_by_id.get(op.host_wall_id, "")
        entities[op.id] = {
            "kind": op.kind,
            "name": op.kind.title(),
            "level_id": lvl_id,
            "z_offset_m": level_elev_by_id.get(lvl_id, 0.0),
            "sync_editable": True,
        }
    for rm in scene.rooms:
        entities[rm.id] = {
            "kind": "room",
            "name": rm.name or "Room",
            "level_id": rm.level_id,
            "z_offset_m": level_elev_by_id.get(rm.level_id, 0.0),
            "sync_editable": True,
        }
    for rf in scene.roofs:
        entities[rf.id] = {
            "kind": "roof",
            "name": "Roof",
            "level_id": rf.level_id,
            "z_offset_m": level_elev_by_id.get(rf.level_id, 0.0),
            "sync_editable": True,
        }
    for st in scene.stairs:
        entities[st.id] = {
            "kind": "stair",
            "name": f"Stair_{st.stair_type}",
            "level_id": st.level_id,
            "z_offset_m": level_elev_by_id.get(st.level_id, 0.0),
            "sync_editable": True,
        }
    for ft in scene.footers:
        entities[ft.id] = {
            "kind": "footer",
            "name": "Footer",
            "level_id": ft.level_id,
            "z_offset_m": 0.0,
            "sync_editable": False,
        }
    for rb in scene.rim_bands:
        entities[rb.id] = {
            "kind": "rim_band",
            "name": "RimBand",
            "level_id": rb.level_id,
            "z_offset_m": 0.0,
            "sync_editable": False,
        }
    for fx in scene.fixtures:
        entities[fx.id] = {
            "kind": "fixture",
            "name": fx.symbol_type,
            "level_id": fx.level_id,
            "loc_m": list(fx.loc_m),
            "rot_z_rad": float(fx.rot_z_rad),
            "z_offset_m": level_elev_by_id.get(fx.level_id, 0.0),
            "sync_editable": True,
        }
    ca_level_by_id: dict[str, str] = {}
    for ca_src in getattr(canvas, "custom_assets", []) or []:
        cid = str(getattr(ca_src, "identifier", "") or "")
        if cid:
            ca_level_by_id[cid] = str(getattr(ca_src, "level_id", "") or "")
    for ca in scene.custom_assets:
        entities[ca.id] = {
            "kind": "custom_asset",
            "name": "CustomAsset",
            "level_id": ca_level_by_id.get(ca.id, ""),
            "loc_m": list(ca.loc_m),
            "rot_z_rad": float(ca.rot_z_rad),
            "z_offset_m": 0.0,
            "sync_editable": True,
        }

    manifest = {
        "schema_version": 1,
        "plan_center_in": list(scene.plan_center_in),
        "inch_to_m": INCH_TO_M,
        "sun": {
            "north_angle_deg": float(scene.sun.north_angle_deg),
            "azimuth_deg": float(scene.sun.azimuth_deg),
            "elevation_deg": float(scene.sun.elevation_deg),
        },
        "levels": [
            {
                "id": lvl.id,
                "name": lvl.name,
                "elevation_m": float(lvl.elevation_m),
            }
            for lvl in scene.levels
        ],
        "entities": entities,
    }
    manifest_path = os.path.join(sync_dir, "scene_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return (glb_path, manifest_path)


def open_in_blender_session(
    canvas: object,
    window_width: int,
    window_height: int,
    blender_path: str = "",
    project_filepath: str = "",
    asset_source: str = "estisketch",
) -> Tuple[bool, str, str]:
    """Open the project in Blender and enable automatic "save to send back" syncing.

    By default (``asset_source="estisketch"``) exports EstiSketch's own procedural and
    bundled ``.glb`` assets so no third-party Blender add-on is required. When
    ``asset_source`` is ``"auto"`` or ``"hb5"`` and Home Builder 5 is installed/enabled
    in Blender, it optionally delegates to ``estisketch_to_hb5.py``.

    Returns:
        ``(ok, message, sync_dir)``; ``sync_dir`` is empty when launching failed.
    """
    blender_exe = find_blender_executable(blender_path)
    if not blender_exe:
        return (
            False,
            "Could not find a Blender executable. Install Blender 4.0+ or set "
            "'Blender Executable' in Settings.",
            "",
        )

    mode = normalize_asset_source(asset_source)
    has_native = native_3d.is_native_3d_available()
    standalone_script = get_standalone_bridge_script_path()
    hb5_script = get_bridge_script_path()

    if not has_native and not os.path.isfile(hb5_script):
        return (False, "Neither native 3D glTF export nor Home Builder 5 bridge is available.", "")

    sync_dir = new_sync_session_dir()
    if project_filepath:
        stem = os.path.splitext(os.path.basename(project_filepath))[0] or "project"
    else:
        stem = "unsaved_project"

    xml_out = ""
    assets_json = ""
    if mode in ("auto", "hb5") or not has_native:
        xml_out = os.path.join(sync_dir, f"{stem}.xml")
        project_io.save_project(canvas, window_width, window_height, xml_out)
        assets_json = write_custom_assets_manifest(canvas, sync_dir)

    if has_native and os.path.isfile(standalone_script):
        glb_path, manifest_path = export_standalone_blender_bundle(canvas, sync_dir)
        cmd = [
            blender_exe,
            "--python",
            standalone_script,
            "--",
            "--glb",
            glb_path,
            "--manifest",
            manifest_path,
            "--sync-dir",
            sync_dir,
            "--asset-source",
            mode,
        ]
        if xml_out:
            cmd.extend(["--xml", xml_out])
        if assets_json:
            cmd.extend(["--custom-assets", assets_json])
    else:
        if not os.path.isfile(hb5_script):
            return (False, f"Bridge script not found: {hb5_script}", "")
        cmd = [
            blender_exe,
            "--python",
            hb5_script,
            "--",
            xml_out,
            "--sync-dir",
            sync_dir,
            "--custom-assets",
            assets_json,
        ]

    popen_kwargs: dict[str, object] = {}
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)

    subprocess.Popen(cmd, **popen_kwargs)  # type: ignore[call-overload]
    if mode == "estisketch":
        status_msg = (
            "Opened in Blender using EstiSketch 3D assets. "
            "Press Ctrl+S in Blender to send your changes back."
        )
    elif mode == "auto":
        status_msg = (
            "Opened in Blender (Auto: Home Builder 5 if enabled, else EstiSketch assets). "
            "Press Ctrl+S in Blender to send your changes back."
        )
    else:
        status_msg = (
            "Opened in Blender (Home Builder 5 if enabled, fallback to EstiSketch assets). "
            "Press Ctrl+S in Blender to send your changes back."
        )
    return (True, status_msg, sync_dir)


def open_in_blender(
    canvas: object,
    window_width: int,
    window_height: int,
    blender_path: str = "",
    project_filepath: str = "",
    asset_source: str = "estisketch",
) -> Tuple[bool, str]:
    """Open the project in Blender (see :func:`open_in_blender_session`)."""
    ok, msg, _sync_dir = open_in_blender_session(
        canvas,
        window_width,
        window_height,
        blender_path,
        project_filepath,
        asset_source=asset_source,
    )
    return (ok, msg)
