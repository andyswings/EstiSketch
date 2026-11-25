#!/usr/bin/env python3
import ast
import re
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
BUILD_DIR = PROJECT_ROOT / "build_deb"
DIST_DIR = PROJECT_ROOT / "dist"
SRC_DIR = PROJECT_ROOT / "src"


def read_app_version() -> str:
    """Read ``__version__`` from ``src/EstiSketch/version.py`` without importing GTK."""
    version_file = SRC_DIR / "EstiSketch" / "version.py"
    text = version_file.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*(.+)$', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find __version__ in {version_file}")
    return str(ast.literal_eval(match.group(1).strip()))


def to_debian_version(version: str) -> str:
    """Convert PEP/SemVer pre-release tags (-alpha, -beta, -rc) to Debian tilde notation."""
    return re.sub(r"-(alpha|beta|rc)", r"~\1", version)


# Configuration
APP_NAME = "estisketch"
RAW_VERSION = read_app_version()
VERSION = to_debian_version(RAW_VERSION)
ARCH = "all"
AUTHOR = "Andrew Sharon"
EMAIL = "andrewsharon@gmx.com"
DESCRIPTION = "A lightweight 2-D floor-plan sketcher and building estimator"
DEPENDENCIES = [
    "python3",
    "python3-gi",
    "python3-gi-cairo",
    "gir1.2-gtk-4.0",
    "python3-cairo",
    "python3-numpy",
]
RECOMMENDS = [
    "python3-reportlab",
]


def clean():
    """Reset the temporary Debian staging directory while keeping existing dist artifacts."""
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def create_structure():
    """Create the Debian package directory hierarchy."""
    (BUILD_DIR / "DEBIAN").mkdir(parents=True)
    (BUILD_DIR / "usr/bin").mkdir(parents=True)
    (BUILD_DIR / "usr/lib/python3/dist-packages").mkdir(parents=True)
    (BUILD_DIR / "usr/share/applications").mkdir(parents=True)
    (BUILD_DIR / "usr/share/icons/hicolor/128x128/apps").mkdir(parents=True)


def copy_files():
    """Copy Python package sources, desktop entry, and application icon into staging."""
    print("Copying source files...")
    dest_pkg = BUILD_DIR / "usr/lib/python3/dist-packages/EstiSketch"
    shutil.copytree(SRC_DIR / "EstiSketch", dest_pkg)

    for p in dest_pkg.rglob("__pycache__"):
        shutil.rmtree(p)

    print("Copying resources...")
    desktop_dest = BUILD_DIR / "usr/share/applications/estisketch.desktop"
    shutil.copy(
        PROJECT_ROOT / "packaging" / "estisketch.desktop",
        desktop_dest,
    )
    desktop_dest.chmod(0o644)

    icon_candidates = [
        PROJECT_ROOT / "packaging" / "estisketch_128.png",
        SRC_DIR / "EstiSketch/Icons/estisketch.png",
    ]
    icon_src = next((p for p in icon_candidates if p.exists()), None)
    if icon_src is None:
        icons = list((SRC_DIR / "EstiSketch/Icons").glob("*.png"))
        if icons:
            icon_src = icons[0]
            print(f"Using fallback icon: {icon_src}")

    if icon_src is not None and icon_src.exists():
        icon_dest = BUILD_DIR / "usr/share/icons/hicolor/128x128/apps/estisketch.png"
        shutil.copy(icon_src, icon_dest)
        icon_dest.chmod(0o644)
    else:
        print("Warning: No PNG icon found for Debian package.")


def create_executable():
    """Create the /usr/bin/estisketch launcher script."""
    print("Creating executable wrapper...")
    bin_path = BUILD_DIR / "usr/bin/estisketch"
    with open(bin_path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n")
        f.write('exec python3 -m EstiSketch.main "$@"\n')
    bin_path.chmod(0o755)


def create_control():
    """Write the DEBIAN/control metadata file."""
    print("Creating control file...")
    control_content = f"""Package: {APP_NAME}
Version: {VERSION}
Section: graphics
Priority: optional
Architecture: {ARCH}
Depends: {", ".join(DEPENDENCIES)}
Recommends: {", ".join(RECOMMENDS)}
Maintainer: {AUTHOR} <{EMAIL}>
Description: {DESCRIPTION}
 EstiSketch is a tool for creating 2D floor plans and material takeoffs.
"""
    control_path = BUILD_DIR / "DEBIAN/control"
    with open(control_path, "w", encoding="utf-8") as f:
        f.write(control_content)
    control_path.chmod(0o644)


def create_maintainer_scripts():
    """Create postinst and postrm scripts to refresh desktop and icon caches."""
    print("Creating maintainer scripts...")
    cache_refresh_script = """#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
"""
    for script_name in ("postinst", "postrm"):
        script_path = BUILD_DIR / "DEBIAN" / script_name
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(cache_refresh_script)
        script_path.chmod(0o755)


def build_deb():
    """Build the .deb archive into dist/."""
    print("Building .deb package...")
    pkg_name = f"{APP_NAME}_{VERSION}_{ARCH}.deb"
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "--build", str(BUILD_DIR), str(DIST_DIR / pkg_name)],
        check=True,
    )
    print(f"Package created: {DIST_DIR / pkg_name}")


def main():
    clean()
    create_structure()
    copy_files()
    create_executable()
    create_control()
    create_maintainer_scripts()
    build_deb()


if __name__ == "__main__":
    main()
