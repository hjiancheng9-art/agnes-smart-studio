"""Skin — CRUX 皮囊层。SSOT 保证像素身份穿越所有层。
Layers: terminal(Rich) | svg(矢量) | web(HTML仪表盘) | api(REST)
All consume the SAME pixel grid from terminal_logo.render_pixel_grid().
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
            from ui.terminal_logo import build_banner, render_pixel_grid

            grid = render_pixel_grid()
            banner = build_banner()
            svg = self._grid_to_svg(grid)
            web = self._grid_to_web(grid)
            asset = SkinAsset(name="logo")
            asset.data[SkinLayer.TERMINAL] = banner
            asset.data[SkinLayer.SVG] = svg
            asset.data[SkinLayer.WEB] = web
            self._assets["logo"] = asset
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("Logo init: %s", e)

    def _init_banner(self):
        try:
            from ui.terminal_logo import build_banner

            self._assets["banner"] = SkinAsset(name="banner", data={SkinLayer.TERMINAL: build_banner()})
        except (ImportError, RuntimeError, OSError) as e:
            logger.debug("[Skin] banner init dynamic failed: %s", e)

    def _grid_to_svg(self, grid) -> str:
        from ui.theme import COLORS

        P, rows, cols = 10, len(grid), len(grid[0]) if grid else 0
        rects = []
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                fill = COLORS.get(cell["color"], COLORS["primary"])
                op = 0.55 if cell.get("shadow") else 1.0
                rects.append(f'<rect x="{c * P}" y="{r * P}" width="{P}" height="{P}" fill="{fill}" opacity="{op}"/>')
        w, h = cols * P, rows * P
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">{chr(10).join(rects)}</svg>'

    def _grid_to_web(self, grid) -> str:
        """HTML canvas rendering of the pixel logo."""
        from ui.theme import COLORS

        P, rows, cols = 4, len(grid), len(grid[0]) if grid else 0
        rects = []
        for r, row in enumerate(grid):
            for c, cell in enumerate(row):
                if cell is None:
                    continue
                fill = COLORS.get(cell["color"], COLORS["primary"])
                op = 0.55 if cell.get("shadow") else 1.0
                rects.append(f'<rect x="{c * P}" y="{r * P}" width="{P}" height="{P}" fill="{fill}" opacity="{op}"/>')
        w, h = cols * P, rows * P
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges" style="image-rendering:pixelated"><rect width="{w}" height="{h}" fill="{COLORS["surface"]}"/>{"".join(rects)}</svg>'

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
