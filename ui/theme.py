"""Organic theme engine — single source of truth for CRUX Studio terminal aesthetics.

All colors, icons, layout parameters, and the Rich Theme are defined here.
Every UI module must import from this file (never define colors/icons locally).

Style: Organic — curved borders, natural colors, flowing symbols, soft transitions.
The dual-DNA (primary + accent) is preserved but softened towards natural hues.
"""

from rich.console import Console
from rich.theme import Theme

__all__ = [
    "COLORS",
    "ORGANIC_THEME",
    "ICONS",
    "LAYOUT",
    "create_console",
    "console",
]

# ── Color palette (Organic) ──────────────────────────────────────
# Dual-DNA preserved: primary (river blue) + accent (lavender purple)
# All values shifted from hard/industrial to soft/natural

COLORS = {
    "primary": "#5BA3CF",  # River blue — calm flowing
    "accent": "#C084FC",  # Lavender — soft creative
    "success": "#7BC47F",  # Leaf green — natural growth
    "warning": "#E8B86D",  # Warm amber — steady caution
    "error": "#E86D6D",  # Coral red — warm alert
    "muted": "#8B9DAF",  # Fog blue-gray — gentle dim
    "surface": "#1C2333",  # Deep sea — Panel subtle background
    "highlight": "#F0C674",  # Golden wheat — focus accent
    "transition": "#A8D8EA",  # Ice blue — secondary/transition
}

# ── Rich Theme ────────────────────────────────────────────────────

ORGANIC_THEME = Theme(
    {
        "primary": "bold #5BA3CF",
        "accent": "bold #C084FC",
        "success": "#7BC47F",
        "warning": "#E8B86D",
        "error": "bold #E86D6D",
        "muted": "#8B9DAF",
        "surface": "on #1C2333",
        "highlight": "bold #F0C674",
        "transition": "#A8D8EA",
        "panel.title": "bold #C084FC",
        "panel.border": "#5BA3CF",
        "table.header": "bold #5BA3CF",
        "table.border": "#8B9DAF",
        "bar.fill": "#5BA3CF",
        "bar.background": "#8B9DAF",
    }
)

# ── Icon system (Geometric → Organic) ────────────────────────────
# Unicode symbols chosen for curved/flowing character

ICONS = {
    "primary": "❧",  # Rotated floral heart — replaces ◈ (diamond)
    "info": "∘",  # Hollow dot — replaces ⬡ (hexagon)
    "success": "✿",  # Flower — replaces ◆ (filled diamond)
    "warning": "⠶",  # Braille petal — replaces ◈
    "error": "⊗",  # Circled cross — replaces ✖ (hard cross)
    "video": "↝",  # Flowing arrow — replaces ▷ (hard arrow)
    "route": "〜",  # Wave — replaces ↳ (hard arrow)
    "on": "●",  # Filled circle (already organic)
    "off": "○",  # Hollow circle (already organic)
    "enabled": "✓",  # Check mark (kept)
    "disabled": "✗",  # Cross mark (kept)
    "star": "★",  # Star (kept)
    "empty": "◇",  # Curved diamond (kept)
    "pipeline": "∞",  # Infinity — replaces ⟐
    "history": "≋",  # Wave lines — replaces ▤
    "template": "❋",  # Six-petal flower — replaces ▦
    "separator": " · ",  # Separator (kept, minimal)
}

# ── Badge emoji (Organic) ────────────────────────────────────────

BADGE_ICONS = {
    "code": "🌿",  # Herb leaf — natural growth
    "agent": "🧬",  # DNA helix — intelligent organic
    "think": "✨",  # Sparkle — inspiration
    "model": "🌊",  # Wave — flowing
}

# ── Layout parameters ────────────────────────────────────────────

LAYOUT = {
    "panel_padding": (1, 2),  # (vertical, horizontal)
    "panel_border_style": "round",  # Curved border
    "table_show_lines": False,  # No internal row lines (more breathable)
    "table_box": "ROUNDED",  # Curved table frame
    "indent": "  ",  # 2-space indent
    "separator_len": 42,  # Separator line length
    "separator_char": "─",  # Separator character
    "badge_separator": "  ∘  ",  # Badge inter-item separator
    "bar_style": "#5BA3CF",  # Progress bar fill color
    "bar_complete_style": "#7BC47F",  # Progress bar completion color
}

# ── Console factory ──────────────────────────────────────────────


def create_console() -> Console:
    """Create an Organic-themed Console instance."""
    return Console(theme=ORGANIC_THEME, force_terminal=True)


# ── Global console (single instance) ────────────────────────────

console = create_console()
