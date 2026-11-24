#!/bin/bash
set -e

# Build script for creating EstiSketch Fat AppImage using PyInstaller

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_pyinstaller"
APPDIR="$BUILD_DIR/EstiSketch.AppDir"
DIST_DIR="$PROJECT_ROOT/dist"

VERSION="$(python3 -c "import ast, pathlib, re; t = (pathlib.Path('$PROJECT_ROOT') / 'src/EstiSketch/version.py').read_text(); m = re.search(r'^__version__\s*=\s*(.+)$', t, re.M); print(ast.literal_eval(m.group(1)))")"
OUTPUT_APPIMAGE="$DIST_DIR/EstiSketch-${VERSION}-x86_64.AppImage"

echo "Building EstiSketch ${VERSION} Fat AppImage with PyInstaller..."
echo "This will bundle Python + GTK4 + all dependencies"
echo ""

# Clean previous PyInstaller build artifacts (preserve other artifacts in dist/)
rm -rf "$BUILD_DIR" "$PROJECT_ROOT/build" "$DIST_DIR/estisketch"
mkdir -p "$APPDIR" "$DIST_DIR"

echo "Step 1/4: Running PyInstaller..."
cd "$PROJECT_ROOT"
pyinstaller --clean --noconfirm "$SCRIPT_DIR/estisketch.spec"

echo "Step 2/4: Copying PyInstaller output to AppDir..."
# PyInstaller creates dist/estisketch/ directory with executable and _internal/
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST_DIR/estisketch" "$APPDIR/usr/bin/"

# Create proper directory structure
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/128x128/apps"

# Copy desktop file and icon
cp "$SCRIPT_DIR/estisketch.desktop" "$APPDIR/usr/share/applications/"
cp "$SCRIPT_DIR/estisketch_128.png" "$APPDIR/usr/share/icons/hicolor/128x128/apps/estisketch.png"

# Create symlinks for AppImage (required by AppImage spec)
ln -s usr/share/applications/estisketch.desktop "$APPDIR/estisketch.desktop"
ln -s usr/share/icons/hicolor/128x128/apps/estisketch.png "$APPDIR/estisketch.png"

echo "Step 3/4: Creating AppRun launcher..."
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"

# Set up library paths
export LD_LIBRARY_PATH="$HERE/usr/lib:$LD_LIBRARY_PATH"

# Set up data directories
export XDG_DATA_DIRS="$HERE/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Run the PyInstaller executable
if [ -f "$HERE/usr/bin/estisketch/estisketch" ]; then
    exec "$HERE/usr/bin/estisketch/estisketch" "$@"
elif [ -f "$HERE/usr/estisketch" ]; then
    exec "$HERE/usr/estisketch" "$@"
else
    echo "Error: Could not find estisketch executable"
    exit 1
fi
EOF
chmod +x "$APPDIR/AppRun"

echo "Step 4/4: Building AppImage..."
# Download appimagetool if not present
APPIMAGETOOL="$BUILD_DIR/appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q -O "$APPIMAGETOOL" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# Build AppImage (extract-and-run works in containers/CI without FUSE)
cd "$BUILD_DIR"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT_APPIMAGE"

echo ""
echo "✓ Fat AppImage created successfully!"
echo "Location: $OUTPUT_APPIMAGE"
SIZE=$(du -h "$OUTPUT_APPIMAGE" | cut -f1)
echo "Size: $SIZE"
echo ""
echo "To run: $OUTPUT_APPIMAGE"
echo ""
echo "This AppImage includes Python and all dependencies!"
