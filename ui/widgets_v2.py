"""CRUX TUI v2 — Reusable widgets.

Components:
  Spinner      — animated braille spinner for activity indication
  Panel        — box-drawing border helpers
  WelcomeScreen — pixel-art welcome display (integrated in message area)
  ThinkingPanel — collapsible chain-of-thought display
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable

from prompt_toolkit.formatted_text import FormattedText

# ══════════════════════════════════════════════════════════════════
#  Spinner — animated braille spinner
# ══════════════════════════════════════════════════════════════════

BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Animated braille spinner for activity indication.

    Runs a background thread that advances the frame every 80ms.
    Callers provide an `on_tick` callback that triggers UI repaint.
    """

    def __init__(self, on_tick: Callable[[], None]) -> None:
        self._frame = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._on_tick = on_tick
        self._lock = threading.Lock()

    @property
    def current(self) -> str:
        with self._lock:
            return BRAILLE_FRAMES[self._frame % len(BRAILLE_FRAMES)]

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _spin(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    break
            self._frame += 1
            with contextlib.suppress(Exception):
                self._on_tick()
            time.sleep(0.08)


# ══════════════════════════════════════════════════════════════════
#  Box-drawing constants
# ══════════════════════════════════════════════════════════════════

# Single-line
_SL_TL, _SL_TR, _SL_BL, _SL_BR = "┌", "┐", "└", "┘"
_SL_H, _SL_V = "─", "│"
_SL_LEFT_T = "├"
_SL_RIGHT_T = "┤"
_SL_BOT_T = "┴"
_SL_TOP_T = "┬"
_SL_CROSS = "┼"

# Double-line
_DL_TL, _DL_TR, _DL_BL, _DL_BR = "╔", "╗", "╚", "╝"
_DL_H, _DL_V = "═", "║"
_DL_LEFT_T = "╠"
_DL_RIGHT_T = "╣"
_DL_BOT_T = "╩"
_DL_TOP_T = "╦"
_DL_CROSS = "╬"


def panel_top(title: str, width: int, double: bool = False) -> str:
    """Top border of a panel with title: ┌─ Title ──────────┐"""
    if double:
        h, tl, tr = _DL_H, _DL_TL, _DL_TR
    else:
        h, tl, tr = _SL_H, _SL_TL, _SL_TR
    inner = width - 2
    if inner >= len(title) + 4:
        left_pad = 2
        right_pad = inner - len(title) - left_pad - 2
        return f"{tl}{h * left_pad} {title} {h * right_pad}{tr}"
    elif inner >= 2:
        return f"{tl}{title[:inner - 2]:^{inner}}{tr}"
    return f"{tl}{tr}"


def panel_bottom(width: int, double: bool = False) -> str:
    """Bottom border: └────────────────────┘"""
    if double:
        return f"{_DL_BL}{_DL_H * (width - 2)}{_DL_BR}"
    return f"{_SL_BL}{_SL_H * (width - 2)}{_SL_BR}"


def panel_line(text: str, width: int, double: bool = False) -> str:
    """A content line with side borders: │ text               │"""
    v = _DL_V if double else _SL_V
    content = text[: width - 4] if len(text) > width - 4 else text
    return f"{v} {content}{' ' * max(0, width - len(content) - 4)} {v}"


def h_line(width: int, double: bool = False) -> str:
    """Horizontal separator line."""
    return (_DL_H if double else _SL_H) * width


# ══════════════════════════════════════════════════════════════════
#  Welcome Screen — CRUX pixel-art welcome (FormattedText)
# ══════════════════════════════════════════════════════════════════

# Pixel art CRUX logo (from terminal_splash.py)
CRUX_PIXEL = [
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "  ████████████    ████████████    ████████████    ████████████  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ████░░░░████  ",
    " ████░░░░░░████  ██████████      ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ██████████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░░████     ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ██░░░░░░░░██  ",
    "  ████████████    ████████████    ████░░░░████    ██░░░░░░░░██  ",
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "                                ",
]


def build_welcome_formatted(
    model_name: str = "",
    cwd: str = "",
    branch: str = "",
) -> FormattedText:
    """Build the welcome screen as FormattedText for prompt_toolkit.

    When there are no messages, this is shown in the message area.
    Once the first message arrives, the welcome disappears.
    """
    pieces: list[tuple[str, str]] = []

    # ── Top border ──
    pieces.append(("class:welcome-border", "  ┌──── Welcome ──────────────────────────────────────┐\n"))

    # ── Pixel logo ──
    for row in CRUX_PIXEL:
        line = "  │ "
        for ch in row:
            if ch in ("█", "▓") or ch in ("▒", "░"):
                line += ch
            else:
                line += " "
        line += " │\n"
        pieces.append(("class:pixel-bright" if "█" in row or "▓" in row else "class:pixel-dim", line))

    # ── Tagline ──
    pieces.append(("class:welcome-border", "  │                                                 │\n"))
    pieces.append(("class:welcome-tagline", "  │     ⚡ AI · Code · Create                       │\n"))
    pieces.append(("class:welcome-border", "  │                                                 │\n"))

    # ── Quick Start ──
    pieces.append(("class:welcome-title",     "  │  Quick Start                                    │\n"))
    tips = [
        ("/help",   "show all commands"),
        ("@model",  "switch AI model"),
        ("/image",  "generate image"),
        ("/video",  "generate video"),
        ("Ctrl+V",  "paste image for vision analysis"),
    ]
    for cmd, desc in tips:
        pieces.append(("class:welcome-key",  f"  │    {cmd:<16}"))
        pieces.append(("class:welcome-desc", f"{desc:<32}│\n"))

    pieces.append(("class:welcome-border", "  │                                                 │\n"))

    # ── Session info ──
    pieces.append(("class:welcome-title", "  │  Session                                        │\n"))
    if model_name:
        pieces.append(("class:welcome-session", f"  │    ◈ Model: {model_name:<40}│\n"))
    if cwd:
        from pathlib import Path
        home = str(Path.home())
        cwd_display = cwd.replace(home, "~") if cwd.startswith(home) else cwd
        pieces.append(("class:welcome-session", f"  │    ◈ CWD: {cwd_display:<42}│\n"))
    if branch:
        pieces.append(("class:welcome-session", f"  │    ◈ Branch: {branch:<40}│\n"))

    pieces.append(("class:welcome-border", "  │                                                 │\n"))

    # ── Beast system status ──
    pieces.append(("class:welcome-title", "  │  Seven Beasts                                   │\n"))
    beasts_line = "  │    虎 龙 雀 武 麟 蛇 翼                          │\n"
    pieces.append(("class:welcome-text", beasts_line))

    pieces.append(("class:welcome-border", "  └─────────────────────────────────────────────────┘\n"))

    return FormattedText(pieces)


# ══════════════════════════════════════════════════════════════════
#  Thinking Panel — collapsible chain-of-thought display
# ══════════════════════════════════════════════════════════════════


class ThinkingPanel:
    """A collapsible panel that shows model reasoning / thinking steps.

    Features:
    - Auto-expands when thinking content arrives
    - Collapses when thinking completes (or stays open if pinned)
    - Max height capping with "..."
    """

    MAX_LINES = 8  # max visible lines before truncation

    def __init__(self) -> None:
        self._content: str = ""
        self._visible: bool = False
        self._pinned: bool = False
        self._lock = threading.Lock()

    @property
    def visible(self) -> bool:
        with self._lock:
            return self._visible

    @property
    def content(self) -> str:
        with self._lock:
            return self._content

    @property
    def has_content(self) -> bool:
        with self._lock:
            return bool(self._content)

    def toggle_pin(self) -> None:
        """Toggle whether panel stays visible after thinking completes."""
        with self._lock:
            self._pinned = not self._pinned
            if not self._pinned and not self._content:
                self._visible = False

    def append(self, text: str) -> None:
        """Append text to the thinking buffer. Auto-shows panel."""
        with self._lock:
            self._content += text
        self._visible = True

    def clear(self) -> None:
        """Clear thinking content. Hides panel unless pinned."""
        with self._lock:
            self._content = ""
            if not self._pinned:
                self._visible = False

    def done(self) -> None:
        """Called when thinking is complete. Hides unless pinned."""
        with self._lock:
            if not self._pinned:
                self._visible = False

    def render(self, width: int) -> FormattedText:
        """Render the thinking panel content as FormattedText.

        Returns empty FormattedText when invisible or no content.
        """
        with self._lock:
            if not self._visible or not self._content:
                return FormattedText([])

            pieces: list[tuple[str, str]] = []

            # ── Top border with title ──
            title = " 💭 深度思考 "
            h_rem = max(0, width - len(title) - 4)
            left_w = h_rem // 2
            h_rem - left_w
            top = f"┌─{title}{'─' * left_w}┐"
            top = top[: width - 1] + "┐" if len(top) > width else top
            pieces.append(("class:thinking-panel-border", top[:width] + "\n"))

            # ── Content lines (capped at MAX_LINES) ──
            content = self._content
            # Split into visual lines based on width
            visual_lines: list[str] = []
            for paragraph in content.split("\n"):
                if not paragraph:
                    visual_lines.append("")
                    continue
                # Simple wrap: chop at width boundaries
                while len(paragraph) > width - 4:
                    visual_lines.append(paragraph[: width - 4])
                    paragraph = paragraph[width - 4 :]
                visual_lines.append(paragraph)

            shown = visual_lines[: self.MAX_LINES]
            for line in shown:
                line_w = len(line)
                pad = max(0, width - line_w - 4)
                pieces.append(("class:thinking-panel-border", "│ "))
                pieces.append(("class:thinking-panel-text", line))
                pieces.append(("class:thinking-panel-border", " " * pad + " │\n"))

            if len(visual_lines) > self.MAX_LINES:
                pieces.append(("class:thinking-panel-text", f"│ ... (+{len(visual_lines) - self.MAX_LINES} more lines) ... │\n"))

            # ── Bottom border ──
            bot = "└" + "─" * (width - 2) + "┘"
            pieces.append(("class:thinking-panel-border", bot[:width] + "\n"))

            return FormattedText(pieces)

    def height(self, width: int) -> int:
        """Calculate the rendered height (0 when invisible)."""
        with self._lock:
            if not self._visible or not self._content:
                return 0
            content = self._content
        # Count lines after wrapping
        content = self._content
        total_lines = 0
        for paragraph in content.split("\n"):
            if not paragraph:
                total_lines += 1
            else:
                total_lines += max(1, -(-len(paragraph) // (width - 4)))  # ceil division
        line_count = min(total_lines, self.MAX_LINES)
        if total_lines > self.MAX_LINES:
            line_count += 1  # for the "...(+N more)" line
        return line_count + 2  # +2 for top/bottom borders


# ══════════════════════════════════════════════════════════════════
#  Context bar — visual progress bar
# ══════════════════════════════════════════════════════════════════


def context_bar(percentage: float, width: int = 10) -> str:
    """Build a visual context usage bar: ████░░░░░░"""
    filled = max(0, min(width, int(percentage / 100 * width)))
    empty = width - filled
    return "█" * filled + "░" * empty
