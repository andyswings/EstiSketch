#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Configuration
APP_NAME = "estisketch"
VERSION = "0.3.0"
ARCH = "all"
AUTHOR = "Andrew"
EMAIL = "andrew@example.com" # Placeholder, update if known
DESCRIPTION = "A lightweight 2-D floor-plan sketcher"
DEPENDENCIES = [
    "python3",
    "python3-gi",
    "gir1.2-gtk-4.0",
    "python3-cairo"
]

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
BUILD_DIR = PROJECT_ROOT / "build_deb"
DIST_DIR = PROJECT_ROOT / "dist"
SRC_DIR = PROJECT_ROOT / "src"

def clean():
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if not DIST_DIR.exists():
        DIST_DIR.mkdir(parents=True)

def create_structure():
    # standard debian package structure
    # /DEBIAN/control
    # /usr/bin/estisketch
    # /usr/lib/python3/dist-packages/EstiSketch
    # /usr/share/applications/estisketch.desktop
    # /usr/share/icons/hicolor/scalable/apps/estisketch.svg (if svg)
    
    (BUILD_DIR / "DEBIAN").mkdir(parents=True)
    (BUILD_DIR / "usr/bin").mkdir(parents=True)
    (BUILD_DIR / "usr/lib/python3/dist-packages").mkdir(parents=True)
    (BUILD_DIR / "usr/share/applications").mkdir(parents=True)
    (BUILD_DIR / "usr/share/icons/hicolor/128x128/apps").mkdir(parents=True)

def copy_files():
    print("Copying source files...")
    # Copy source code
    # We want src/EstiSketch -> /usr/lib/python3/dist-packages/EstiSketch
    dest_pkg = BUILD_DIR / "usr/lib/python3/dist-packages/EstiSketch"
    shutil.copytree(SRC_DIR / "EstiSketch", dest_pkg)
    
    # Clean up __pycache__
    for p in dest_pkg.rglob("__pycache__"):
        shutil.rmtree(p)

    print("Copying resources...")
    # Desktop file
    shutil.copy( PROJECT_ROOT / "packaging" / "estisketch.desktop", 
                 BUILD_DIR / "usr/share/applications/estisketch.desktop")
    
    # Icon - Finding the best icon
    # Assuming there is an icon in src/EstiSketch/Icons
    icon_src = SRC_DIR / "EstiSketch/Icons/estisketch.png" 
    # Fallback or specific check?
    if not icon_src.exists():
        print(f"Warning: Icon not found at {icon_src}")
        # Try to find any png
        icons = list((SRC_DIR / "EstiSketch/Icons").glob("*.png"))
        if icons:
            icon_src = icons[0]
            print(f"Using {icon_src} instead.")
    
    if icon_src.exists():
        shutil.copy(icon_src, BUILD_DIR / "usr/share/icons/hicolor/128x128/apps/estisketch.png")

def create_executable():
    print("Creating executable wrapper...")
    # Create /usr/bin/estisketch script
    bin_path = BUILD_DIR / "usr/bin/estisketch"
    with open(bin_path, "w") as f:
        f.write("#!/bin/sh\n")
        f.write("exec python3 -m EstiSketch.main \"$@\"\n")
    
    bin_path.chmod(0o755)

def create_control():
    print("Creating control file...")
    control_content = f"""Package: {APP_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: {ARCH}
Depends: {", ".join(DEPENDENCIES)}
Maintainer: {AUTHOR} <{EMAIL}>
Description: {DESCRIPTION}
 EstiSketch is a tool for creating 2D floor plans.
"""
    with open(BUILD_DIR / "DEBIAN/control", "w") as f:
        f.write(control_content)

def build_deb():
    print("Building .deb package...")
    pkg_name = f"{APP_NAME}_{VERSION}_{ARCH}.deb"
    subprocess.run(["dpkg-deb", "--build", str(BUILD_DIR), str(DIST_DIR / pkg_name)], check=True)
    print(f"Package created: {DIST_DIR / pkg_name}")

def main():
    clean()
    create_structure()
    copy_files()
    create_executable()
    create_control()
    build_deb()

if __name__ == "__main__":
    main()
