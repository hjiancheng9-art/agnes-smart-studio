#!/usr/bin/env python3
"""Generate CRUX Studio logo SVGs from the SAME glyphs/colors as the terminal.

Single-source-of-truth SVG generation:
  - Pixel layout  → ui.terminal_logo.render_pixel_grid() + ICON
  - Colors        → ui.theme.COLORS
  - Glyph chars   → ui.terminal_logo.PIXEL_KIND (# / @ / + / .)

Because the SVG and the terminal banner both read render_pixel_grid(),
they can NEVER drift apart by hand-editing. Edit GLYPHS once → both
surfaces update. Run after any GLYPHS/theme change:

    python make_logo_svg.py

Outputs (overwritten in place):
    assets/crux_logo.svg        — full banner (wordmark + version line)
    assets/crux_logo_icon.svg   — square cross-star icon (from ICON glyph)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root importable when run as a script
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ui.terminal_logo import ICON, PIXEL_KIND, render_pixel_grid  # noqa: E402
from ui.theme import COLORS  # noqa: E402

ASSETS = ROOT / "assets"
PIXEL = 10  # SVG units per pixel cell (matches legacy scale)

# Shadow opacity — terminal renders shadow as solid muted color; SVG gives
# it a touch more transparency so it reads as depth, not a second letter.
SHADOW_OPACITY = 0.55


# ── helpers ─────────────────────────────────────────────────────


def _svg_header(width: int, height: int, bg: str = "surface") -> list[str]:
    """Open an SVG document with the retro surface background + CRT scanlines."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'  <rect width="{width}" height="{height}" fill="{COLORS[bg]}"/>',
    ]
    return lines


def _scanlines(width: int, height: int) -> str:
    """Faint CRT scanline overlay as one opaque group for compactness."""
    lines = [
        '  <g opacity="0.06">',
    ]
    for y in range(4, height, 4):
        lines.append(f'    <line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="#000" stroke-width="1"/>')
    lines.append("  </g>")
    return "\n".join(lines)


def _rect(x: int, y: int, color: str, *, shadow: bool, opacity: float = 1.0) -> str:
    """One pixel cell as an SVG <rect>."""
    fill = COLORS[color]
    op = SHADOW_OPACITY if shadow else opacity
    return f'    <rect x="{x}" y="{y}" width="{PIXEL}" height="{PIXEL}" fill="{fill}" opacity="{op}"/>'


# ── wordmark SVG ────────────────────────────────────────────────


def render_wordmark_svg() -> str:
    """Build assets/crux_logo.svg from render_pixel_grid() + version row.

    The pixel grid IS the wordmark — every rect here corresponds 1:1 to a
    cell from render_pixel_grid(), so the exported SVG matches the terminal
    banner exactly (same glyph shape, same shadow offset, same colors).
    """
    grid = render_pixel_grid()
    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    # Layout: padding around the wordmark, plus a text row beneath.
    pad = 30
    text_row_h = 50
    wordmark_w = cols * PIXEL
    wordmark_h = rows * PIXEL
    width = wordmark_w + 2 * pad
    height = wordmark_h + pad + text_row_h

    out = _svg_header(width, height)

    # Pixels — two passes so shadows are emitted before mains (correct draw
    # order; main pixels on top where they coincide). The grid already
    # encodes which cells are shadow vs main.
    pixels: list[str] = []
    for r, grid_row in enumerate(grid):
        for c, cell in enumerate(grid_row):
            if cell is None:
                continue
            x = pad + c * PIXEL
            y = pad + r * PIXEL
            pixels.append(_rect(x, y, cell["color"], shadow=cell["shadow"]))
    out.append("  <g>")  # wrap pixels so the group is easy to transform/debug
    out.extend(pixels)
    out.append("  </g>")

    # Version row: ★ v5.0 ·  N tools ·  M skills
    star_y = pad + wordmark_h + 28
    out.append(
        f'  <text x="{pad}" y="{star_y}" font-family="Consolas, Courier New, monospace" '
        f'font-size="15" fill="{COLORS["accent"]}">{chr(0x2605)}</text>'
    )
    out.append(
        f'  <text x="{pad + 24}" y="{star_y}" font-family="Consolas, Courier New, monospace" '
        f'font-size="14" fill="{COLORS["highlight"]}">v5.0</text>'
    )
    out.append(
        f'  <text x="{pad + 68}" y="{star_y}" font-family="Consolas, Courier New, monospace" '
        f'font-size="13" fill="{COLORS["muted"]}">  ·  84 tools  ·  734 skills  ·  五兽归真 · AI-native creative platform</text>'
    )

    out.append(_scanlines(width, height))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ── icon SVG (from ICON glyph) ──────────────────────────────────


def render_icon_svg() -> str:
    """Build assets/crux_logo_icon.svg directly from the ICON glyph.

    ICON is 7 wide × 5 tall. Rendered centered on a square canvas with a
    shadow layer offset +1/+1 (same depth convention as the wordmark).
    """
    rows = len(ICON)
    cols = len(ICON[0]) if ICON else 0

    canvas = 64
    # Center the icon block, scaled up so it fills the small canvas nicely.
    cell = 6
    block_w = cols * cell
    block_h = rows * cell
    ox = (canvas - block_w) // 2
    oy = (canvas - block_h) // 2

    out = _svg_header(canvas, canvas)

    # Shadow layer first (offset +1/+1), then main pixels.
    shadow_cells: list[str] = []
    main_cells: list[str] = []
    for r, row_str in enumerate(ICON):
        for c, px in enumerate(row_str):
            kind = PIXEL_KIND.get(px)
            if kind is None:
                continue
            x = ox + c * cell
            y = oy + r * cell
            main_cells.append(_rect(x, y, kind, shadow=False, opacity=1.0))
            sx, sy = x + cell // 3, y + cell // 3
            shadow_cells.append(
                f'    <rect x="{sx}" y="{sy}" width="{cell}" height="{cell}" fill="{COLORS["muted"]}" opacity="0.5"/>'
            )

    out.append('  <g opacity="0.6">')
    out.extend(shadow_cells)
    out.append("  </g>")
    out.append("  <g>")
    out.extend(main_cells)
    out.append("  </g>")

    out.append(_scanlines(canvas, canvas))
    out.append("</svg>")
    return "\n".join(out) + "\n"


# ── entrypoint ──────────────────────────────────────────────────


def main() -> int:
    """Regenerate both SVGs. Returns process exit code (0 = ok)."""
    ASSETS.mkdir(exist_ok=True)

    wordmark_svg = render_wordmark_svg()
    icon_svg = render_icon_svg()

    (ASSETS / "crux_logo.svg").write_text(wordmark_svg, encoding="utf-8")
    (ASSETS / "crux_logo_icon.svg").write_text(icon_svg, encoding="utf-8")

    print("SVG generated from GLYPHS + COLORS (single source of truth):")
    print(f"  {ASSETS / 'crux_logo.svg'}")
    print(f"  {ASSETS / 'crux_logo_icon.svg'}")
    print()
    print("Edit ui/terminal_logo.py (GLYPHS) or ui/theme.py (COLORS) and re-run")
    print("this script — terminal + SVG stay pixel-identical automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
