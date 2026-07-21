"""Overlay views — full-screen screens (dashboard, incidents, etc.) and command palette."""

from prompt_toolkit.formatted_text import FormattedText

from ..state import UiState
from .palette import render_palette


def render_overlay(state: UiState) -> FormattedText:
    """Render the active overlay: palette first, then screen."""
    # ── Command palette (highest priority) ──
    if state.palette.open:
        return render_palette(
            query=state.palette.query,
            selected=state.palette.selected,
            width=state.terminal.cols,
        )

    # ── Screen overlays ──
    tw = state.terminal.cols
    if hasattr(state, "screen") and state.screen is not None:
        from ..state import Screen

        if state.screen != Screen.MAIN and hasattr(Screen, state.screen.name):
            screen_name = state.screen.name
            lines: list[tuple[str, str]] = [
                ("bold", f"{'=' * tw}\n"),
                ("bold class:header", f"  {screen_name}\n"),
                ("class:dim", f"  {'-' * (tw - 2)}\n"),
                ("class:dim", f"  Screen: {screen_name}\n"),
                ("class:dim", "\n  Esc: back\n"),
            ]
            return FormattedText(lines)

    return FormattedText([])
