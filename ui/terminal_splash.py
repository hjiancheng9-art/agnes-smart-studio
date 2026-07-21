"""Terminal splash screen — CRUX pixel art welcome banner."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

CRUX_PIXEL = [
    "  ░░████████░░    ░░████████░░    ░░██░░░░██░░    ░░██░░░░██░░  ",
    "  ████████████    ████████████    ████████████    ████████████  ",
    " ████░░░░░░████  ████░░░░████    ████░░░░████    ████░░░░████  ",
    " ████░░░░░░████  ██████████      ████░░░░████    ██░░████░░██  ",
    " ████░░░░░░████  ██████████      ████████████    ██░░░░░░░░██  ",
    " ████░░░░░░████  ████░░████      ████░░░░████    ██░░████░░██  ",
    "  ████████████   ████░░░░████    ████░░░░████    ████░░░░████  ",
    "   ██████████    ████░░░░░░██    ████░░░░████    ████░░░░████  ",
    "     ██████      ████████████    ████████████    ████████████  ",
]

_TEXT_BANNER = [
    "CRUX Studio v6.2.0",
    "平时如刀，出事成阵  ·  Multi-Agent TUI",
]

# Extra line format: (label, ansi_style, content, description)
ExtraLine = tuple[str, str, str, str]


def build_logo_lines() -> list[str]:
    """Return CRUX pixel art logo as a list of strings."""
    return list(CRUX_PIXEL)


def build_border_line(char: str = "═") -> str:
    """Build a horizontal border line to fill the terminal width."""
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    return char * cols


def build_scanline() -> str:
    """Return a decorative scanline pattern."""
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    return "▓░" * (cols // 2)


def print_splash(extra_lines: Sequence[ExtraLine] | None = None) -> None:
    """Print the CRUX splash screen to stdout.

    Args:
        extra_lines: Optional list of (label, ansi_style, content, description) tuples.
    """
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    border = "═" * cols

    print()
    print(border)
    print()
    for line in build_logo_lines():
        print(line)
    print()
    for line in _TEXT_BANNER:
        print(line.center(cols))
    print()
    if extra_lines:
        print("─" * cols)
        for label, _ansi, content, _desc in extra_lines:
            print(f"  {label}: {content}")
        print("─" * cols)
    print()
    print(border)
    print()
