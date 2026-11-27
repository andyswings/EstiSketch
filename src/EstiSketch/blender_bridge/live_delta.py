"""Headless helpers that apply a Blender save-triggered delta to an EstiSketch canvas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import blender_sync

DELTA_FILENAME = "delta.esk-delta.zip"


@dataclass
class LiveDeltaResult:
    """Outcome of applying one Blender delta bundle."""

    applied: int = 0
    ignored: int = 0
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """One-line, user-facing summary suitable for the status hint."""
        if self.applied == 0:
            return "Blender: no applicable changes found"
        text = f"Applied {self.applied} change(s) from Blender"
        if self.warnings:
            text += f" ({len(self.warnings)} skipped)"
        return text


class DeltaWatcher:
    """Detect new ``delta.esk-delta.zip`` files written into a sync session folder."""

    def __init__(self, sync_dir: str | Path) -> None:
        self.sync_dir = Path(sync_dir)
        self._last_stamp: tuple[int, int] | None = None

    def poll(self) -> Path | None:
        """Return the delta path if it is new since the last call, else ``None``."""
        path = self.sync_dir / DELTA_FILENAME
        try:
            st = path.stat()
        except OSError:
            return None
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self._last_stamp:
            return None
        self._last_stamp = stamp
        return path


def apply_live_delta(canvas: object, delta_zip: str | Path) -> LiveDeltaResult:
    """Classify and apply ``delta_zip`` to ``canvas`` as ONE undo step, without any prompts."""
    plan = blender_sync.classify_blender_delta(canvas, delta_zip)
    applied, warnings = blender_sync.apply_delta_import_plan(canvas, plan)
    return LiveDeltaResult(applied=applied, ignored=plan.ignored_count, warnings=warnings)
