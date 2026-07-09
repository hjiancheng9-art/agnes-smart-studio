"""CRUX TUI — Theme compatibility layer (delegates to theme_v2).

Maintains backward-compatible API while all real theming logic lives in ui/theme_v2.py.

Old theme names → v2 modes:
    polar_night → mocha (dark Catppuccin)
    lava        → blade
    jade        → normal
    blade       → blade

Exports (backward-compatible):
    THEMES          — dict of legacy theme definitions
    C               — active theme dict (dynamic, for color lookup)
    build_style()   → Style
    set_theme()     → None
    get_active_theme() → dict
    list_themes()   → list[dict]
"""

from __future__ import annotations

from prompt_toolkit.styles import Style

from ui.theme_v2 import build_style_v2, list_themes_v2

# ── Legacy theme name → v2 mode mapping ──
_LEGACY_MAP: dict[str, str] = {
    "polar_night": "mocha",
    "lava": "blade",
    "jade": "normal",
    "blade": "blade",
}

# ── Legacy theme color dicts (kept for code that use C["bg"] style access) ──
# These are approximate Catppuccin Mocha equivalents of the old themes.
POLAR_NIGHT: dict[str, str] = {
    "id": "polar_night",
    "name": "极夜 Polar Night",
    "mode": "mocha",
    "bg": "#1E1E2E",
    "panel": "#181825",
    "fg": "#CDD6F4",
    "primary": "#89B4FA",
    "secondary": "#A6E3A1",
    "accent": "#F5C2E7",
    "danger": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "muted": "#6C7086",
    "border": "#313244",
    "surface": "#111827",
    "error": "#FF0055",
    "crux": "#A78BFF",
    "user": "#4A9EFF",
}

LAVA: dict[str, str] = {
    "id": "lava",
    "name": "熔岩 Lava",
    "mode": "blade",
    "bg": "#1E1E2E",
    "panel": "#181825",
    "fg": "#CDD6F4",
    "primary": "#FAB387",
    "secondary": "#F38BA8",
    "accent": "#F5C2E7",
    "danger": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "muted": "#6C7086",
    "border": "#313244",
    "surface": "#111827",
    "error": "#FF0055",
    "crux": "#A78BFF",
    "user": "#4A9EFF",
}

JADE: dict[str, str] = {
    "id": "jade",
    "name": "翡翠 Jade",
    "mode": "normal",
    "bg": "#1E1E2E",
    "panel": "#181825",
    "fg": "#CDD6F4",
    "primary": "#A6E3A1",
    "secondary": "#89B4FA",
    "accent": "#94E2D5",
    "danger": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "muted": "#6C7086",
    "border": "#313244",
    "surface": "#111827",
    "error": "#FF0055",
    "crux": "#A78BFF",
    "user": "#4A9EFF",
}

BLADE: dict[str, str] = {
    "id": "blade",
    "name": "刀阵 Blade",
    "mode": "blade",
    "bg": "#1E1E2E",
    "panel": "#181825",
    "fg": "#CDD6F4",
    "primary": "#CBA6F7",
    "secondary": "#89B4FA",
    "accent": "#F5C2E7",
    "danger": "#F38BA8",
    "warning": "#FAB387",
    "success": "#A6E3A1",
    "muted": "#6C7086",
    "border": "#313244",
    "surface": "#111827",
    "error": "#FF0055",
    "crux": "#A78BFF",
    "user": "#4A9EFF",
}

THEMES: dict[str, dict[str, str]] = {
    "polar_night": POLAR_NIGHT,
    "lava": LAVA,
    "jade": JADE,
    "blade": BLADE,
}

# ── Active theme tracking ──
_active_theme_name: str = "blade"

# C is the active theme dict — code uses C["bg"], C["fg"], etc.
C: dict[str, str] = BLADE


def get_active_theme() -> dict[str, str]:
    """Return the currently active theme dict."""
    return C


def set_theme(name: str) -> None:
    """Switch active theme at runtime."""
    global _active_theme_name, C
    if name in THEMES:
        _active_theme_name = name
        C = THEMES[name]


def list_themes() -> list[dict]:
    """Return list of available themes."""
    v2_themes = list_themes_v2()
    if v2_themes:
        return v2_themes
    return [{"id": tid, "name": t["name"], "mode": t["mode"]} for tid, t in THEMES.items()]


def build_style(theme_name: str | None = None) -> Style:
    """Build a prompt_toolkit Style from the current/requested theme.

    Delegates to theme_v2.build_style_v2, mapping legacy names to v2 modes.
    """
    mode = "blade"
    if theme_name is not None:
        mode = _LEGACY_MAP.get(theme_name, theme_name)
    else:
        mode = _LEGACY_MAP.get(_active_theme_name, "blade")
    return build_style_v2(mode)
