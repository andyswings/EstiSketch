"""Portable ``.esk`` ZIP project archive reader, writer, and asset materializer.

Archive layout::

    project.esk (ZIP)
    ├── manifest.json          # format="esk", version=1, app_version, created_utc
    ├── project.xml            # canonical EstiSketch XML (all 2D, takeoff, and objects)
    ├── views.json             # saved 3D camera, render style, sun hour, SSAO, dollhouse
    ├── overrides_3d.json      # per-entity 3D visual override metadata (rel paths, hashes)
    ├── blueprints/bp_<id>.png # raw underlay image bytes (replaces inline base64 in .esk)
    ├── assets/<id>.glb        # custom imported & Blender-sculpted binary glTF meshes
    ├── sync/blender_state.json# baseline mesh hashes & ESTISKETCH_ID mapping
    └── preview.png            # optional viewport thumbnail

All file paths inside archives are validated against directory traversal.
This module has zero GTK/Cairo dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Callable, cast
import xml.etree.ElementTree as ET
import zipfile

from .version import __version__

ESK_FORMAT_VERSION = 1
_ZIP_MAGIC = b"PK\x03\x04"


def is_esk_archive(filepath: str | Path) -> bool:
    """Return True if ``filepath`` exists and begins with the ZIP magic header ``PK\\x03\\x04``."""
    p = Path(filepath)
    if not p.is_file():
        return False
    try:
        with p.open("rb") as fh:
            return fh.read(4) == _ZIP_MAGIC
    except OSError:
        return False


def _sanitize_archive_relpath(rel_path: str) -> str:
    """Validate and normalize an internal archive POSIX path (blocking ``..`` or roots)."""
    cleaned = rel_path.replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/"):
        raise ValueError(f"Unsafe archive member path '{rel_path}'")
    posix = PurePosixPath(cleaned)
    if ".." in posix.parts:
        raise ValueError(f"Directory traversal in archive member '{rel_path}'")
    return str(posix)


def _guess_image_ext(image_data: bytes, orig_path: str) -> str:
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    ext = Path(orig_path).suffix.lower() if orig_path else ""
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        return ext
    return ".png"


def _asset_cache_dir(canvas: object) -> Path:
    existing = getattr(canvas, "_esk_asset_cache_dir", None)
    if isinstance(existing, (str, Path)) and str(existing):
        cache_dir = Path(existing)
    else:
        cache_dir = Path(tempfile.mkdtemp(prefix="estisketch_esk_assets_"))
        setattr(canvas, "_esk_asset_cache_dir", str(cache_dir))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def materialize_project_assets(canvas: object) -> Path:
    """Write embedded `.glb` payloads on ``canvas`` to a clean local cache directory.

    Returns:
        Path to the temporary asset cache root containing ``assets/*.glb``.
    """
    cache_dir = _asset_cache_dir(canvas)
    for item in getattr(canvas, "custom_assets", []) or []:
        rel = str(getattr(item, "glb_rel_path", "") or "").strip()
        raw = getattr(item, "glb_bytes", None)
        if not rel:
            ident = str(getattr(item, "identifier", "asset"))
            rel = f"assets/{ident}.glb"
            setattr(item, "glb_rel_path", rel)
        safe_rel = _sanitize_archive_relpath(rel)
        dest = cache_dir / safe_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(raw, (bytes, bytearray)) and raw:
            dest.write_bytes(bytes(raw))
            setattr(item, "resolved_glb_path", str(dest))
        elif dest.is_file():
            setattr(item, "resolved_glb_path", str(dest))

    overrides = getattr(canvas, "overrides_3d", None)
    if isinstance(overrides, dict):
        for ent_id, meta in overrides.items():
            if not isinstance(meta, dict):
                continue
            rel = str(meta.get("glb_rel_path") or f"assets/override_{ent_id}.glb")
            raw = meta.get("glb_bytes")
            safe_rel = _sanitize_archive_relpath(rel)
            dest = cache_dir / safe_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(raw, (bytes, bytearray)) and raw:
                dest.write_bytes(bytes(raw))
                meta["glb_rel_path"] = safe_rel
                meta["resolved_glb_path"] = str(dest)
            elif dest.is_file():
                meta["resolved_glb_path"] = str(dest)

    return cache_dir


def _json_overrides_metadata(canvas: object) -> dict[str, dict[str, object]]:
    """Return JSON-serializable ``overrides_3d.json`` dict (excluding raw binary bytes)."""
    raw_map = getattr(canvas, "overrides_3d", None)
    if not isinstance(raw_map, dict):
        return {}
    cleaned: dict[str, dict[str, object]] = {}
    for ent_id, entry in raw_map.items():
        if not isinstance(entry, dict):
            continue
        cleaned[str(ent_id)] = {
            str(k): v for k, v in entry.items() if k not in ("glb_bytes", "resolved_glb_path")
        }
    return cleaned


def save_esk_project(
    canvas: object,
    window_width: int,
    window_height: int,
    filepath: str | Path,
    preview_png: bytes | None = None,
) -> None:
    """Serialize ``canvas`` state, blueprints, 3D views, overrides, and `.glb` assets into ``.esk``."""
    from . import project_io

    dest_path = Path(filepath)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

    root, blueprint_files, asset_files = project_io.build_project_xml_tree(
        canvas,
        window_width,
        window_height,
        embed_blueprints_inline=False,
    )
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    manifest = {
        "format": "esk",
        "version": ESK_FORMAT_VERSION,
        "app_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "project_sha256": hashlib.sha256(xml_bytes).hexdigest(),
    }
    views_obj = getattr(canvas, "views_3d", None)
    views_payload = views_obj if isinstance(views_obj, dict) else {}
    overrides_payload = _json_overrides_metadata(canvas)
    sync_obj = getattr(canvas, "blender_sync_state", None)
    sync_payload = sync_obj if isinstance(sync_obj, dict) else {}

    # Collect Tier 2A override `.glb` blobs alongside custom asset `.glb` files
    raw_overrides = getattr(canvas, "overrides_3d", None)
    if isinstance(raw_overrides, dict):
        for ent_id, meta in raw_overrides.items():
            if not isinstance(meta, dict):
                continue
            rel = str(meta.get("glb_rel_path") or f"assets/override_{ent_id}.glb")
            blob = meta.get("glb_bytes")
            if isinstance(blob, (bytes, bytearray)) and blob:
                asset_files[_sanitize_archive_relpath(rel)] = bytes(blob)
            else:
                res_p = meta.get("resolved_glb_path")
                if isinstance(res_p, str) and Path(res_p).is_file():
                    asset_files[_sanitize_archive_relpath(rel)] = Path(res_p).read_bytes()

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        zf.writestr("project.xml", xml_bytes)
        zf.writestr("views.json", json.dumps(views_payload, indent=2, sort_keys=True))
        zf.writestr("overrides_3d.json", json.dumps(overrides_payload, indent=2, sort_keys=True))
        zf.writestr("sync/blender_state.json", json.dumps(sync_payload, indent=2, sort_keys=True))
        for rel, data in sorted(blueprint_files.items()):
            zf.writestr(_sanitize_archive_relpath(rel), data)
        for rel, data in sorted(asset_files.items()):
            zf.writestr(_sanitize_archive_relpath(rel), data)
        if preview_png:
            zf.writestr("preview.png", preview_png)

    tmp_path.replace(dest_path)


def open_esk_project(canvas: object, filepath: str | Path) -> tuple[int, int]:
    """Load an EstiSketch ``.esk`` ZIP archive into ``canvas`` and return window ``(w, h)``."""
    from . import project_io

    src_path = Path(filepath)
    with zipfile.ZipFile(src_path, "r") as zf:
        names = set(zf.namelist())
        if "project.xml" not in names:
            raise ValueError(f"Archive '{src_path}' is missing required project.xml")
        for member in names:
            _sanitize_archive_relpath(member)

        xml_bytes = zf.read("project.xml")
        root = ET.fromstring(xml_bytes)

        def _read_member(rel_path: str) -> bytes | None:
            safe = _sanitize_archive_relpath(rel_path)
            if safe in names:
                return zf.read(safe)
            return None

        win_w, win_h = project_io.load_project_xml_root(
            canvas, root, archive_reader=cast(Callable[[str], bytes | None], _read_member)
        )

        # Restore 3D views metadata
        if "views.json" in names:
            loaded_views = json.loads(zf.read("views.json").decode("utf-8"))
            if isinstance(loaded_views, dict):
                setattr(canvas, "views_3d", loaded_views)

        # Restore Tier 2A 3D overrides & embedded GLB bytes
        restored_overrides: dict[str, dict[str, object]] = {}
        if "overrides_3d.json" in names:
            raw_ov = json.loads(zf.read("overrides_3d.json").decode("utf-8"))
            if isinstance(raw_ov, dict):
                for ent_id, meta in raw_ov.items():
                    if not isinstance(meta, dict):
                        continue
                    item_dict: dict[str, object] = {str(k): v for k, v in meta.items()}
                    rel = str(item_dict.get("glb_rel_path") or f"assets/override_{ent_id}.glb")
                    blob = _read_member(rel)
                    if blob is not None:
                        item_dict["glb_bytes"] = blob
                    restored_overrides[str(ent_id)] = item_dict
        setattr(canvas, "overrides_3d", restored_overrides)

        # Restore Blender baseline sync state
        if "sync/blender_state.json" in names:
            loaded_sync = json.loads(zf.read("sync/blender_state.json").decode("utf-8"))
            if isinstance(loaded_sync, dict):
                setattr(canvas, "blender_sync_state", loaded_sync)

    materialize_project_assets(canvas)
    return (win_w, win_h)


def blueprint_archive_relpath(identifier: str, image_data: bytes, image_path: str) -> str:
    """Return canonical archive relative path ``blueprints/bp_<id>.<ext>``."""
    safe_id = (identifier or "bp").replace("/", "_").replace("\\", "_")
    ext = _guess_image_ext(image_data, image_path)
    return f"blueprints/{safe_id}{ext}"
