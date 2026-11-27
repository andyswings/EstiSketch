"""Launch Blender with Home Builder 5 populated from an EstiSketch project."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from .. import esk_archive, project_io


def get_bridge_script_path() -> str:
    """Return the absolute path to ``estisketch_to_hb5.py``."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "estisketch_to_hb5.py")


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


def open_in_blender_session(
    canvas: object,
    window_width: int,
    window_height: int,
    blender_path: str = "",
    project_filepath: str = "",
) -> Tuple[bool, str, str]:
    """Open the project in Blender and enable automatic "save to send back" syncing.

    Returns:
        ``(ok, message, sync_dir)``; ``sync_dir`` is empty when launching failed.  EstiSketch
        should watch ``sync_dir`` for ``delta.esk-delta.zip`` (written when the user saves in
        Blender).
    """
    blender_exe = find_blender_executable(blender_path)
    if not blender_exe:
        return (
            False,
            "Could not find a Blender executable. Install Blender 5.1+ with the "
            "Home Builder 5 extension enabled, or set 'Blender Executable' in Settings.",
            "",
        )

    script_path = get_bridge_script_path()
    if not os.path.isfile(script_path):
        return (False, f"Bridge script not found: {script_path}", "")

    sync_dir = new_sync_session_dir()
    if project_filepath:
        stem = os.path.splitext(os.path.basename(project_filepath))[0] or "project"
    else:
        stem = "unsaved_project"
    xml_out = os.path.join(sync_dir, f"{stem}.xml")
    project_io.save_project(canvas, window_width, window_height, xml_out)
    assets_json = write_custom_assets_manifest(canvas, sync_dir)

    cmd = [
        blender_exe,
        "--python",
        script_path,
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
    return (
        True,
        "Opened in Blender. Press Ctrl+S in Blender to send your changes back to EstiSketch.",
        sync_dir,
    )


def open_in_blender(
    canvas: object,
    window_width: int,
    window_height: int,
    blender_path: str = "",
    project_filepath: str = "",
) -> Tuple[bool, str]:
    """Open the project in Blender (see :func:`open_in_blender_session`)."""
    ok, msg, _sync_dir = open_in_blender_session(
        canvas, window_width, window_height, blender_path, project_filepath
    )
    return (ok, msg)
