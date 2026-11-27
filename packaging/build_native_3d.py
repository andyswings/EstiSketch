"""Build and install the native Rust PyO3 extension ``EstiSketch._native_3d``.

Invokes ``cargo build --release -p estisketch_3d_py`` and copies the resulting
``abi3`` shared library into ``src/EstiSketch/`` as ``_native_3d.abi3.so`` on
POSIX (or ``_native_3d.pyd`` on Windows). Safe to run directly in local dev
environments and CI workflows without requiring ``maturin``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUST_MANIFEST = REPO_ROOT / "rust" / "Cargo.toml"
PACKAGE_DIR = REPO_ROOT / "src" / "EstiSketch"


def _candidate_artifacts(target_dir: Path, profile: str) -> tuple[list[Path], Path]:
    profile_dir = target_dir / profile
    if sys.platform == "win32":
        return (
            [profile_dir / "_native_3d.dll", profile_dir / "lib_native_3d.dll"],
            PACKAGE_DIR / "_native_3d.pyd",
        )
    if sys.platform == "darwin":
        return (
            [profile_dir / "lib_native_3d.dylib"],
            PACKAGE_DIR / "_native_3d.abi3.so",
        )
    return (
        [profile_dir / "lib_native_3d.so"],
        PACKAGE_DIR / "_native_3d.abi3.so",
    )


def build_native_extension(debug: bool = False) -> Path:
    """Compile ``estisketch_3d_py`` and install the binary module into ``src/EstiSketch``."""
    profile = "debug" if debug else "release"
    cmd = ["cargo", "build", "--manifest-path", str(RUST_MANIFEST), "-p", "estisketch_3d_py"]
    if not debug:
        cmd.append("--release")

    env = os.environ.copy()
    env.setdefault("PYO3_PYTHON", sys.executable)
    env.setdefault("PYO3_USE_ABI3_FORWARD_COMPATIBILITY", "1")

    subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, check=True)

    target_dir = Path(env.get("CARGO_TARGET_DIR", str(REPO_ROOT / "rust" / "target")))
    candidates, dest_path = _candidate_artifacts(target_dir, profile)
    src_path = next((p for p in candidates if p.is_file()), None)
    if src_path is None:
        searched = ", ".join(str(p) for p in candidates)
        raise FileNotFoundError(f"Built _native_3d artifact not found (checked: {searched})")

    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_path)
    return dest_path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for building and staging ``EstiSketch._native_3d``."""
    parser = argparse.ArgumentParser(description="Build EstiSketch Rust _native_3d extension")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build with cargo debug profile instead of --release",
    )
    args = parser.parse_args(argv)
    out = build_native_extension(debug=bool(args.debug))
    print(f"Installed native 3D module -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
