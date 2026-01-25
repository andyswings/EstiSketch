#!/bin/bash
set -e

# Ensure flatpak-builder is installed
if ! command -v flatpak-builder &> /dev/null; then
    echo "Error: flatpak-builder is not installed."
    echo "Please install it using: sudo apt install flatpak-builder"
    exit 1
fi

# Install dependencies
flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo
echo "Installing GNOME Runtime (this may take a while)..."
flatpak install -y --user flathub org.gnome.Platform//45 org.gnome.Sdk//45

echo "Resizing icon..."
python3 packaging/resize_icon.py src/EstiSketch/Icons/estisketch.png packaging/estisketch_128.png 128

echo "Resizing icon..."
python3 packaging/resize_icon.py src/EstiSketch/Icons/estisketch.png packaging/estisketch_128.png 128

echo "Building Flatpak..."
flatpak-builder --user --install --force-clean build_flatpak packaging/com.estisketch.EstiSketch.yml

echo "Build complete."
echo "You can run the app with: flatpak run com.estisketch.EstiSketch"
