#!/usr/bin/env python3
"""Generate CRUX Studio app icon (crux.ico) — convergence diamond symbol."""
from PIL import Image, ImageDraw

def create_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark rounded-rectangle background (Organic surface color)
    margin = 12
    radius = 40
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=(28, 35, 51),  # #1C2333 surface
    )

    # Convergence diamond symbol — white with accent inner detail
    cx, cy = size // 2, size // 2
    diamond_size = 80

    # Outer diamond (white)
    top = (cx, cy - diamond_size)
    right = (cx + diamond_size, cy)
    bottom = (cx, cy + diamond_size)
    left = (cx - diamond_size, cy)
    draw.polygon([top, right, bottom, left], fill=(255, 255, 255))

    # Inner accent diamond (lavender #C084FC)
    inner_size = 28
    itop = (cx, cy - inner_size)
    iright = (cx + inner_size, cy)
    ibottom = (cx, cy + inner_size)
    ileft = (cx - inner_size, cy)
    draw.polygon([itop, iright, ibottom, ileft], fill=(192, 132, 252))

    # Core point (leaf green #7BC47F)
    core_size = 8
    draw.ellipse(
        [cx - core_size, cy - core_size, cx + core_size, cy + core_size],
        fill=(123, 196, 127),
    )

    # Save as ico (multi-size)
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon_path = "crux.ico"
    img.save(icon_path, format="ICO", sizes=ico_sizes)
    print(f"Icon saved: {icon_path}")

    # PNG preview
    img.save("crux_icon_preview.png")
    print("Preview saved: crux_icon_preview.png")

if __name__ == "__main__":
    create_icon()
