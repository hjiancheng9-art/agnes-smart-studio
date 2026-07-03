"""Skin — CRUX 皮囊层。SSOT 保证像素身份穿越所有层。
Layers: terminal(Rich) | svg(矢量) | web(HTML仪表盘) | api(REST)
All consume the SAME inline pixel grid defined below.
Usage: from core.skin import get_skin
get_skin().render("logo", "web")
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.skin")
ROOT = Path(__file__).resolve().parent.parent

# ── Inline logo (replaces removed ui/terminal_logo.py) ──────────

_INLINE_LOGO = r"""
    ╔═══════════════════════════════════════╗
    ║                                       ║
    ║       ⚒  CRUX  STUDIO  v5.0          ║
    ║       暗夜工坊 · Night Atelier        ║
    ║                                       ║
    ║   白虎为骨 · 青龙为脉 · 朱雀为眼      ║
    ║   玄武为甲 · 麒麟为手 · 螣蛇为忆      ║
    ║   应龙为令 · MCP 网格 · 万象共生      ║
    ║                                       ║
    ╚═══════════════════════════════════════╝
"""

# Default pixel grid for SVG/Web (minimal 8x8 CRUX cruciform)
_DEFAULT_GRID = [
    [None, None, None, "o", "o", None, None, None],
    [None, None, "o", "o", "o", "o", None, None],
    [None, "o", "o", "o", "o", "o", "o", None],
    ["o", "o", None, None, None, None, "o", "o"],
    ["o", "o", None, None, None, None, "o", "o"],
    [None, "o", "o", "o", "o", "o", "o", None],
    [None, None, "o", "o", "o", "o", None, None],
    [None, None, None, "o", "o", None, None, None],
]


def _grid_to_svg_fallback(grid) -> str:
    """Render pixel grid to SVG (standalone helper)."""
    from core.theme import COLORS

    P, rows, cols = 10, len(grid), len(grid[0]) if grid else 0
    rects = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            if isinstance(cell, dict):
                fill = COLORS.get(cell.get("color", ""), COLORS["primary"])
                op = 0.55 if cell.get("shadow") else 1.0
            elif isinstance(cell, str) and cell.strip():
                fill = COLORS["accent"]
                op = 1.0
            else:
                continue
            rects.append(
                f'<rect x="{c * P}" y="{r * P}" width="{P}" height="{P}" '
                f'fill="{fill}" opacity="{op}"/>'
            )
    w, h = cols * P, rows * P
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'shape-rendering="crispEdges">{"".join(rects)}</svg>'
    )


def _grid_to_web_fallback(grid) -> str:
    """Render pixel grid to inline SVG for web (standalone helper)."""
    from core.theme import COLORS

    P, rows, cols = 4, len(grid), len(grid[0]) if grid else 0
    rects = []
    for r, row in enumerate(grid):
        for c, cell in enumerate(row):
            if cell is None:
                continue
            if isinstance(cell, dict):
                fill = COLORS.get(cell.get("color", ""), COLORS["primary"])
                op = 0.55 if cell.get("shadow") else 1.0
            elif isinstance(cell, str) and cell.strip():
                fill = COLORS["primary"]
                op = 1.0
            else:
                continue
            rects.append(
                f'<rect x="{c * P}" y="{r * P}" width="{P}" height="{P}" '
                f'fill="{fill}" opacity="{op}"/>'
            )
    w, h = cols * P, rows * P
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'shape-rendering="crispEdges" style="image-rendering:pixelated">'
        f'<rect width="{w}" height="{h}" fill="{COLORS["surface"]}"/>'
        f'{"".join(rects)}</svg>'
    )


class SkinLayer(Enum):
    TERMINAL = "terminal"
    SVG = "svg"
    WEB = "web"
    API = "api"


@dataclass
class SkinAsset:
    name: str
    data: dict[SkinLayer, Any] = field(default_factory=dict)


class SkinManager:
    def __init__(self):
        self._assets: dict[str, SkinAsset] = {}
        self._init_all()

    def _init_all(self):
        self._init_logo()
        with contextlib.suppress(Exception):
            self._init_banner()

    def _init_logo(self):
        try:
            # Logo is now embedded in ui/message_pane.py._render_empty_state()
            # Provide a simple ASCII fallback for skin layer
            banner = _INLINE_LOGO
            asset = SkinAsset(name="logo")
            asset.data[SkinLayer.TERMINAL] = banner
            # SVG/Web layers need pixel grid; defer to external asset file if needed
            svg_path = ROOT / "assets" / "crux_logo.svg"
            if svg_path.exists():
                asset.data[SkinLayer.SVG] = svg_path.read_text(encoding="utf-8")
            else:
                asset.data[SkinLayer.SVG] = _grid_to_svg_fallback(_DEFAULT_GRID)
                asset.data[SkinLayer.WEB] = _grid_to_web_fallback(_DEFAULT_GRID)
            self._assets["logo"] = asset
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Logo init: %s", e)

    def _init_banner(self):
        try:
            self._assets["banner"] = SkinAsset(name="banner", data={SkinLayer.TERMINAL: _INLINE_LOGO})
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("[Skin] banner init dynamic failed: %s", e)

    def render(self, name: str, layer: SkinLayer = SkinLayer.TERMINAL) -> Any:
        a = self._assets.get(name)
        return a.data.get(layer) if a else None

    def list_assets(self) -> list[str]:
        return list(self._assets.keys())

    def list_layers(self, name: str) -> list[str]:
        a = self._assets.get(name)
        return [layer.value for layer in a.data] if a else []

    def summary(self) -> str:
        lines = ["\n## Skin (皮肤系统)"]
        for name, asset in self._assets.items():
            layers = ", ".join(layer.value for layer in asset.data)
            lines.append(f"  {name}: {layers}")
        return "\n".join(lines)


# Global — held by reference, not GC'd
_skin: SkinManager | None = None


def get_skin() -> SkinManager:
    global _skin
    if _skin is None:
        _skin = SkinManager()
    return _skin
