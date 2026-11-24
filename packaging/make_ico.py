#!/usr/bin/env python3
"""Convert a PNG image into a Windows Vista+ PNG-encoded .ico file (stdlib only)."""

import struct
import sys
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_to_ico(png_path: Path, ico_path: Path) -> None:
    """Wrap a PNG image in a single-entry Windows ICO container."""
    png_data = png_path.read_bytes()
    if len(png_data) < 24 or png_data[:8] != PNG_SIGNATURE or png_data[12:16] != b"IHDR":
        raise ValueError(f"{png_path} is not a valid PNG file")

    width, height = struct.unpack(">II", png_data[16:24])
    if width > 256 or height > 256 or width == 0 or height == 0:
        raise ValueError(f"ICO PNG dimensions must be 1..256, got {width}x{height}")

    ico_w = 0 if width == 256 else width
    ico_h = 0 if height == 256 else height

    # ICONDIR: reserved (2B), type=1 for icon (2B), count=1 (2B)
    icondir = struct.pack("<HHH", 0, 1, 1)
    # ICONDIRENTRY: width, height, color_count, reserved, planes, bit_count, bytes_in_res, image_offset
    header_size = 6 + 16
    entry = struct.pack("<BBBBHHII", ico_w, ico_h, 0, 0, 1, 32, len(png_data), header_size)

    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(icondir + entry + png_data)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: make_ico.py <input.png> <output.ico>", file=sys.stderr)
        sys.exit(1)
    png_to_ico(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
