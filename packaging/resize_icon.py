#!/usr/bin/env python3
import cairo
import sys
import math

def resize_image(input_path, output_path, target_size):
    # Load the source image
    surface = cairo.ImageSurface.create_from_png(input_path)
    src_width = surface.get_width()
    src_height = surface.get_height()

    # Create destination surface
    dest_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, target_size, target_size)
    ctx = cairo.Context(dest_surface)

    # Calculate scale
    scale = target_size / max(src_width, src_height)
    
    # Center the image
    translate_x = (target_size - (src_width * scale)) / 2
    translate_y = (target_size - (src_height * scale)) / 2

    ctx.translate(translate_x, translate_y)
    ctx.scale(scale, scale)
    
    ctx.set_source_surface(surface, 0, 0)
    ctx.paint()
    
    dest_surface.write_to_png(output_path)
    print(f"Resized {input_path} to {output_path} ({target_size}x{target_size})")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: resize_icon.py <input> <output> <size>")
        sys.exit(1)
        
    resize_image(sys.argv[1], sys.argv[2], int(sys.argv[3]))
