#!/usr/bin/env python3
"""Generate CRUX Studio app icon (crux.ico) — convergence diamond symbol.

Colors are read from ui.theme.COLORS (same source as make_logo_svg.py),
so the .ico can never drift from the SVG/terminal palette. Edit
ui/theme.py once → re-run both scripts.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

# Resolve COLORS from the single source of truth
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from ui.theme import COLORS  # noqa: E402


def _rgb(hex_color: str) -> tuple[int, int, int]:
    """'#00E5FF' → (0, 229, 255)."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def create_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark rounded-rectangle background (surface)
    margin = 12
    radius = 40
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=_rgb(COLORS["surface"]),
    )

    # Convergence diamond symbol — primary outer + accent inner + success core
    cx, cy = size // 2, size // 2
    diamond_size = 80

    # Outer diamond (primary)
    top = (cx, cy - diamond_size)
    right = (cx + diamond_size, cy)
    bottom = (cx, cy + diamond_size)
    left = (cx - diamond_size, cy)
    draw.polygon([top, right, bottom, left], fill=_rgb(COLORS["primary"]))

    # Inner accent diamond
    inner_size = 28
    itop = (cx, cy - inner_size)
    iright = (cx + inner_size, cy)
    ibottom = (cx, cy + inner_size)
    ileft = (cx - inner_size, cy)
    draw.polygon([itop, iright, ibottom, ileft], fill=_rgb(COLORS["accent"]))

    # Core point (success)
    core_size = 8
    draw.ellipse(
        [cx - core_size, cy - core_size, cx + core_size, cy + core_size],
        fill=_rgb(COLORS["success"]),
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
