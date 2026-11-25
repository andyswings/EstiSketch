"""Launch Blender with Home Builder 5 populated from an EstiSketch project."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

from .. import project_io


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


def open_in_blender(
    canvas,
    window_width: int,
    window_height: int,
    blender_path: str = "",
    project_filepath: str = "",
) -> Tuple[bool, str]:
    """Export the active canvas to a temporary XML file and open it in Blender."""
    blender_exe = find_blender_executable(blender_path)
    if not blender_exe:
        return (
            False,
            "Could not find a Blender executable. Install Blender 5.1+ with the "
            "Home Builder 5 extension enabled, or set 'Blender Executable' in Settings.",
        )

    script_path = get_bridge_script_path()
    if not os.path.isfile(script_path):
        return (False, f"Bridge script not found: {script_path}")

    bridge_dir = os.path.join(tempfile.gettempdir(), "estisketch_blender_bridge")
    os.makedirs(bridge_dir, exist_ok=True)
    if project_filepath:
        stem = os.path.splitext(os.path.basename(project_filepath))[0] or "project"
    else:
        stem = "unsaved_project"
    xml_out = os.path.join(bridge_dir, f"{stem}.xml")

    project_io.save_project(canvas, int(window_width), int(window_height), xml_out)

    cmd = [blender_exe, "--python", script_path, "--", xml_out]
    popen_kwargs = {}
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True
    else:
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)

    subprocess.Popen(cmd, **popen_kwargs)
    return (True, f"Launched Blender ({blender_exe}) with {xml_out}")
