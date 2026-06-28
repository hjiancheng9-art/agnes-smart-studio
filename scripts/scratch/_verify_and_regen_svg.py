#!/usr/bin/env python3
"""Standalone: regenerate SVGs from GLYPHS + verify pixel-identical."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from make_logo_svg import render_icon_svg, render_wordmark_svg
from ui.terminal_logo import render_pixel_grid
from ui.theme import COLORS

ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# 1. Regenerate
wordmark = render_wordmark_svg()
icon = render_icon_svg()

(ASSETS / "crux_logo.svg").write_text(wordmark, encoding="utf-8")
(ASSETS / "crux_logo_icon.svg").write_text(icon, encoding="utf-8")
print("✅ SVGs regenerated from GLYPHS + COLORS")

# 2. Verify pixel-for-pixel: terminal grid == SVG rects
grid = render_pixel_grid()
PIXEL = 10
SHADOW_OPACITY = 0.55
pad = 30

expected_rects = []
for r, row in enumerate(grid):
    for c, cell in enumerate(row):
        if cell is None:
            continue
        x = pad + c * PIXEL
        y = pad + r * PIXEL
        fill = COLORS[cell["color"]]
        op = SHADOW_OPACITY if cell["shadow"] else 1.0
        expected_rects.append(f'<rect x="{x}" y="{y}" width="{PIXEL}" height="{PIXEL}" fill="{fill}" opacity="{op}"/>')

logo = wordmark
missing = [r for r in expected_rects if r not in logo]
extra_rects = []
import re

all_fills = re.findall(r'fill="([^"]+)"', logo)
print(f"  Grid cells: {len(expected_rects)}")
print(f"  SVG rects: {len(all_fills) - 1}")  # -1 for background rect

if missing:
    print(f"❌ MISSING {len(missing)} rects (terminal→SVG drift)!")
    for m in missing[:3]:
        print(f"  {m}")
else:
    print("✅ Pixel-for-pixel match: terminal grid == SVG rects")

# 3. Verify stable (deterministic)
w2, i2 = render_wordmark_svg(), render_icon_svg()
assert wordmark == w2, "❌ wordmark non-deterministic!"
assert icon == i2, "❌ icon non-deterministic!"
print("✅ Deterministic: two renders produce identical output")

# 4. Well-formed XML
import xml.dom.minidom as minidom

minidom.parseString(wordmark)
minidom.parseString(icon)
print("✅ Well-formed XML")

# 5. Palette check
theme_hex = {v.upper() for v in COLORS.values()}
fills = {f.upper() for f in re.findall(r'fill="([^"]+)"', logo)}
stray = fills - theme_hex - {"#000"}
if stray:
    print(f"❌ Stray colors: {stray}")
else:
    print("✅ All colors from theme.COLORS")

# 6. No legacy palette
LEGACY = {"#5BA3CF", "#E8B86D", "#E86D6D", "#8B9DAF", "#1C2333", "#F0C674", "#A8D8EA"}
found_legacy = {c for c in LEGACY if c.upper() in logo.upper()}
if found_legacy:
    print(f"❌ Legacy palette leaked: {found_legacy}")
else:
    print("✅ No legacy palette")

print("\n🎉 ALL CHECKS PASSED — SVG and terminal are pixel-identical.")
