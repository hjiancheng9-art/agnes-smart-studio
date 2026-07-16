"""CRUX TUI — Theme compatibility layer (delegates to theme_v2).

Maintains backward-compatible API while all real theming logic lives in ui/theme_v2.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ui.theme_v2 import BLADE as COLORS
from ui.theme_v2 import build_style_v2

if TYPE_CHECKING:
    from prompt_toolkit.styles import Style


def get_active_theme() -> dict[str, str]:
    """Return the currently active color palette."""
    return dict(COLORS)


def list_themes() -> list[dict]:
    """Return list of available themes (now single-palette)."""
    return [{"name": "default", "desc": "统一配色", "palette": dict(COLORS)}]


def build_style(mode: str | None = None) -> Style:
    """Build a prompt_toolkit Style.

    Args:
        mode: "normal" | "high_contrast" | "mono" (default "normal")
    """
    return build_style_v2(mode or "normal")
