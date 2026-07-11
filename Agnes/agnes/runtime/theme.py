"""应用主题配色。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Theme:
    """Agnes 桌面端配色方案。"""

    bg: str = "#1E1E2E"
    fg: str = "#e0e0e0"
    accent: str = "#6c63ff"
    success: str = "#4caf50"
    warning: str = "#ff9800"
    error: str = "#f44336"
    card_bg: str = "#16213e"
    input_bg: str = "#0f3460"
