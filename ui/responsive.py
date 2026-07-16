"""
CRUX TUI v2 — Responsive Layout Manager
========================================
Implements breakpoint-driven layout adaptation per debate conclusions.

Breakpoints (columns):
    >= 160  → FULL     Dashboard expanded, all features
    140-159 → WIDE     Dashboard expanded
    110-139 → NORMAL   Dashboard compact (3 key indicators)
    90-109  → NARROW   Dashboard hidden, status bar enriched
    70-89   → TIGHT    Single column, pure conversation
    < 70    → MINIMAL  Simplified input, minimal chrome

Core principle: message area width ALWAYS prioritized.
"""

from __future__ import annotations

import contextlib
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class Breakpoint(Enum):
    """Terminal width breakpoints."""

    FULL = auto()  # >= 160
    WIDE = auto()  # 140-159
    NORMAL = auto()  # 110-139
    NARROW = auto()  # 90-109
    TIGHT = auto()  # 70-89
    MINIMAL = auto()  # < 70


class LayoutConfig:
    """Layout configuration for a specific breakpoint."""

    def __init__(
        self,
        dashboard_visible: bool,
        dashboard_compact: bool,
        thinking_panel_allowed: bool,
        animation_allowed: bool,
        status_bar_rich: bool,
        input_max_lines: int,
        message_min_width: int,
        sidebar_width: int = 0,
    ):
        self.dashboard_visible = dashboard_visible
        self.dashboard_compact = dashboard_compact
        self.thinking_panel_allowed = thinking_panel_allowed
        self.animation_allowed = animation_allowed
        self.status_bar_rich = status_bar_rich
        self.input_max_lines = input_max_lines
        self.message_min_width = message_min_width
        self.sidebar_width = sidebar_width


# ── Breakpoint → LayoutConfig mapping ──────────────────────

LAYOUT_CONFIGS: dict[Breakpoint, LayoutConfig] = {
    Breakpoint.FULL: LayoutConfig(
        dashboard_visible=True,
        dashboard_compact=False,
        thinking_panel_allowed=True,
        animation_allowed=True,
        status_bar_rich=True,
        input_max_lines=8,
        message_min_width=80,
        sidebar_width=35,
    ),
    Breakpoint.WIDE: LayoutConfig(
        dashboard_visible=True,
        dashboard_compact=False,
        thinking_panel_allowed=True,
        animation_allowed=True,
        status_bar_rich=True,
        input_max_lines=6,
        message_min_width=75,
        sidebar_width=30,
    ),
    Breakpoint.NORMAL: LayoutConfig(
        dashboard_visible=True,
        dashboard_compact=True,  # only 3 key indicators
        thinking_panel_allowed=True,
        animation_allowed=True,
        status_bar_rich=True,
        input_max_lines=5,
        message_min_width=65,
        sidebar_width=25,
    ),
    Breakpoint.NARROW: LayoutConfig(
        dashboard_visible=False,  # hidden entirely
        dashboard_compact=False,
        thinking_panel_allowed=False,  # collapsed
        animation_allowed=True,
        status_bar_rich=True,  # status bar carries extra info
        input_max_lines=4,
        message_min_width=60,
        sidebar_width=0,
    ),
    Breakpoint.TIGHT: LayoutConfig(
        dashboard_visible=False,
        dashboard_compact=False,
        thinking_panel_allowed=False,
        animation_allowed=False,  # no animations
        status_bar_rich=False,  # minimal status
        input_max_lines=3,
        message_min_width=50,
        sidebar_width=0,
    ),
    Breakpoint.MINIMAL: LayoutConfig(
        dashboard_visible=False,
        dashboard_compact=False,
        thinking_panel_allowed=False,
        animation_allowed=False,
        status_bar_rich=False,
        input_max_lines=2,
        message_min_width=40,
        sidebar_width=0,
    ),
}


# ── Environment detection ──────────────────────────────────


class EnvironmentInfo:
    """Detected environment capabilities."""

    def __init__(
        self,
        is_ssh: bool = False,
        is_tmux: bool = False,
        has_truecolor: bool = True,
        has_clipboard: bool = True,
        unicode_support: bool = True,
    ):
        self.is_ssh = is_ssh
        self.is_tmux = is_tmux
        self.has_truecolor = has_truecolor
        self.has_clipboard = has_clipboard
        self.unicode_support = unicode_support

    @classmethod
    def detect(cls) -> EnvironmentInfo:
        """Auto-detect environment capabilities."""
        import os

        is_ssh = bool(os.environ.get("SSH_TTY") or os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"))

        is_tmux = bool(os.environ.get("TMUX"))

        # Check color capability
        colorterm = os.environ.get("COLORTERM", "")
        term = os.environ.get("TERM", "")
        wt_session = os.environ.get("WT_SESSION", "")
        # Windows Terminal supports true color; COLORTERM/TERM may not reflect it
        has_truecolor = (
            colorterm in ("truecolor", "24bit")
            or "256color" in term
            or bool(wt_session)
            or (os.name == "nt" and not is_ssh)
        )

        # Clipboard: assume no in SSH/tmux
        has_clipboard = not (is_ssh or is_tmux)

        # Unicode: Windows supports UTF-8 (especially with PYTHONUTF8/chcp 65001).
        # On POSIX, check LANG for UTF-8. LANG is typically unset on Windows.
        if os.name == "nt":
            unicode_support = True
        else:
            lang = os.environ.get("LANG", "")
            unicode_support = "UTF-8" in lang.upper() or "utf-8" in lang.lower()

        return cls(
            is_ssh=is_ssh,
            is_tmux=is_tmux,
            has_truecolor=has_truecolor,
            has_clipboard=has_clipboard,
            unicode_support=unicode_support,
        )


class LayoutManager:
    """
    Manages responsive layout based on terminal width and environment.

    Usage:
        manager = LayoutManager()
        config = manager.update(width=120)
        if config.dashboard_visible:
            ...
    """

    def __init__(self, env: EnvironmentInfo | None = None):
        self._env = env or EnvironmentInfo.detect()
        self._current_bp: Breakpoint = Breakpoint.NORMAL
        self._current_config: LayoutConfig = LAYOUT_CONFIGS[Breakpoint.NORMAL]
        self._last_width: int = 120
        self._listeners: list[Callable[[LayoutConfig], None]] = []

    @property
    def env(self) -> EnvironmentInfo:
        return self._env

    @property
    def breakpoint(self) -> Breakpoint:
        return self._current_bp

    @property
    def config(self) -> LayoutConfig:
        return self._current_config

    @staticmethod
    def width_to_breakpoint(width: int) -> Breakpoint:
        """Map terminal column width to breakpoint."""
        if width >= 160:
            return Breakpoint.FULL
        if width >= 140:
            return Breakpoint.WIDE
        if width >= 110:
            return Breakpoint.NORMAL
        if width >= 90:
            return Breakpoint.NARROW
        if width >= 70:
            return Breakpoint.TIGHT
        return Breakpoint.MINIMAL

    def update(self, width: int) -> LayoutConfig:
        """
        Update layout for given terminal width.
        Returns the new config (or same if unchanged).
        """
        bp = self.width_to_breakpoint(width)

        if bp == self._current_bp and width == self._last_width:
            return self._current_config

        self._last_width = width
        self._current_bp = bp

        new_config = LAYOUT_CONFIGS[bp]

        # Apply environment overrides
        if self._env.is_ssh:
            new_config = LayoutConfig(
                dashboard_visible=False,
                dashboard_compact=False,
                thinking_panel_allowed=False,
                animation_allowed=False,
                status_bar_rich=False,
                input_max_lines=min(new_config.input_max_lines, 3),
                message_min_width=new_config.message_min_width,
                sidebar_width=0,
            )

        self._current_config = new_config

        # Notify listeners
        for listener in self._listeners:
            with contextlib.suppress(Exception):
                listener(new_config)

        return new_config

    def on_change(self, callback: Callable[[LayoutConfig], None]):
        """Register a listener for layout changes."""
        self._listeners.append(callback)

    @property
    def can_animate(self) -> bool:
        """Whether animations are allowed in current config."""
        if self._env.is_ssh or self._env.is_tmux:
            return False
        return self._current_config.animation_allowed

    @property
    def theme_mode(self) -> str:
        """
        Determine theme mode based on environment.
        Returns: 'normal', 'high_contrast', or 'mono'
        """
        if not self._env.has_truecolor or self._env.is_ssh:
            return "mono"
        if not self._env.unicode_support:
            return "high_contrast"
        return "normal"

    def degradation_flags(self) -> dict:
        """Return CLI-compatible degradation flags."""
        return {
            "no_color": self.theme_mode == "mono",
            "no_animation": not self.can_animate,
            "no_unicode": not self._env.unicode_support,
            "ascii_only": not self._env.unicode_support,
            "high_contrast": self.theme_mode == "high_contrast",
        }
