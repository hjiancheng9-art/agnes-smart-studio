"""Guard tests: SVG assets must stay in sync with GLYPHS/COLORS (single source of truth).

These prevent the historical drift from recurring:
  - SVGs used to be hand-edited, so they fell out of sync with the
    terminal banner (different colors, a leftover ``%d`` placeholder bug,
    stale legacy palette).
  - Now both surfaces consume ``render_pixel_grid()`` + ``COLORS`` via
    ``make_logo_svg.py``. These tests pin that contract.

If a test fails, the fix is to re-run ``python make_logo_svg.py`` (and
``python make_icon.py`` for the .ico), NOT to hand-edit the SVG.
"""

import re
import sys
import xml.dom.minidom as minidom
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from make_logo_svg import PIXEL, SHADOW_OPACITY, render_icon_svg, render_wordmark_svg  # noqa: E402
from ui.terminal_logo import ICON, PIXEL_KIND, render_pixel_grid  # noqa: E402
from ui.theme import COLORS  # noqa: E402

ASSETS = ROOT / "assets"
LOGO_SVG = ASSETS / "crux_logo.svg"
ICON_SVG = ASSETS / "crux_logo_icon.svg"

# Palette that predates the Retro 8-bit rebrand — must never reappear.
LEGACY_COLORS = {
    "#5BA3CF",
    "#E8B86D",
    "#E86D6D",
    "#8B9DAF",
    "#1C2333",
    "#F0C674",
    "#A8D8EA",
}


# ── generators must be importable & deterministic ────────────────


def test_generators_produce_stable_output():
    """Regenerating twice yields identical SVGs (no timestamps/randomness)."""
    assert render_wordmark_svg() == render_wordmark_svg()
    assert render_icon_svg() == render_icon_svg()


# ── on-disk SVGs must match what the generator emits ─────────────


@pytest.mark.parametrize(
    "path,fn",
    [
        (LOGO_SVG, render_wordmark_svg),
        (ICON_SVG, render_icon_svg),
    ],
)
def test_disk_svg_matches_generator(path, fn):
    """If this fails, re-run `python make_logo_svg.py` — the SVG was hand-edited."""
    assert path.exists(), f"{path} missing — run python make_logo_svg.py"
    assert path.read_text(encoding="utf-8") == fn()


# ── SVG wordmark must equal render_pixel_grid() pixel-for-pixel ──


def test_wordmark_svg_matches_pixel_grid():
    """The single most important invariant: SVG == terminal banner.

    Every pixel cell from render_pixel_grid() must appear as a matching
    <rect> in crux_logo.svg (same x/y/size/color/opacity). This is what
    guarantees the exported SVG can never drift from the terminal.
    """
    logo = LOGO_SVG.read_text(encoding="utf-8")
    grid = render_pixel_grid()
    pad = 30  # must mirror render_wordmark_svg's `pad`

    expected_rects = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            x = pad + c * PIXEL
            y = pad + r * PIXEL
            fill = COLORS[cell["color"]]
            op = SHADOW_OPACITY if cell["shadow"] else 1.0
            expected_rects.append(
                f'<rect x="{x}" y="{y}" width="{PIXEL}" height="{PIXEL}" fill="{fill}" opacity="{op}"/>'
            )

    missing = [r for r in expected_rects if r not in logo]
    assert not missing, (
        f"{len(missing)} pixel rects from render_pixel_grid() are missing from "
        f"{LOGO_SVG.name}. Re-run `python make_logo_svg.py`. First missing:\n" + "\n".join(missing[:5])
    )


# ── palette containment ─────────────────────────────────────────


@pytest.mark.parametrize("path", [LOGO_SVG, ICON_SVG])
def test_svg_palette_is_subset_of_theme(path):
    """Every fill in the SVG must come from ui.theme.COLORS (#000 scanlines excepted)."""
    txt = path.read_text(encoding="utf-8")
    fills = {f.upper() for f in re.findall(r'fill="([^"]+)"', txt)}
    theme_hex = {v.upper() for v in COLORS.values()}
    stray = fills - theme_hex - {"#000"}
    assert not stray, f"{path.name} uses colors not in theme.COLORS: {stray}"


@pytest.mark.parametrize("path", [LOGO_SVG, ICON_SVG])
def test_no_legacy_palette(path):
    """The pre-Retro palette must never leak back in."""
    txt = path.read_text(encoding="utf-8")
    found = {c for c in LEGACY_COLORS if c.upper() in txt.upper()}
    assert not found, f"{path.name} contains legacy palette: {found}"


@pytest.mark.parametrize("path", [LOGO_SVG, ICON_SVG])
def test_no_format_placeholder_leak(path):
    """The old `%d` placeholder bug must not return."""
    txt = path.read_text(encoding="utf-8")
    assert "%d" not in txt and "%s" not in txt, f"{path.name} has format placeholder"


# ── well-formedness ─────────────────────────────────────────────


@pytest.mark.parametrize("path", [LOGO_SVG, ICON_SVG])
def test_svg_is_well_formed_xml(path):
    minidom.parseString(path.read_text(encoding="utf-8"))  # raises on malformed


# ── generator itself must honor the glyph alphabet ──────────────


def test_icon_svg_only_uses_icon_glyph_kinds():
    """The icon SVG must be driven by the ICON glyph, nothing else."""
    kinds_in_icon = {px for row in ICON for px in row if px != "."}
    assert kinds_in_icon.issubset(set(PIXEL_KIND)), (
        f"ICON uses chars not in PIXEL_KIND: {kinds_in_icon - set(PIXEL_KIND)}"
    )


if __name__ == "__main__":
    import pytest as _pytest

    _pytest.main([__file__, "-v"])
