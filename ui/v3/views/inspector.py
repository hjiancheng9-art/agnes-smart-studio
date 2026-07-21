"""CRUX TUI v3 — Inspector panel view.

Shows contextual information on the right side:
  - Current file(s) being discussed (with status, line info)
  - Agent status (multi-agent)
  - Quick session stats

Only renders when: cols >= 110 and not focus_mode and screen == MAIN.
"""

from __future__ import annotations

from dataclasses import dataclass

from prompt_toolkit.formatted_text import FormattedText


@dataclass(frozen=True)
class InspectorFile:
    """A file currently relevant to the conversation."""

    path: str  # relative path
    status: str = ""  # "reading", "editing", "searching", ""
    line: int = 0  # current line (0 = unknown)


@dataclass(frozen=True)
class InspectorAgent:
    """An active or recently-active agent."""

    name: str
    status: str = "idle"  # "running", "done", "waiting", "error"


def render_inspector(
    files: tuple[InspectorFile, ...] = (),
    agents: tuple[InspectorAgent, ...] = (),
    context_pct: int = 0,
    width: int = 30,
) -> FormattedText:
    """Render the right-side inspector panel.

    Args:
        files: Current files with status.
        agents: Active/recent agents.
        context_pct: Context window usage 0-100.
        width: Available columns for the panel.
    """
    ft: list[tuple[str, str]] = []
    menu_w = max(20, width - 2)

    # ── Title ──
    ft.append(("class:inspector-title", f" {'─' * (menu_w - 2)} "))
    ft.append(("", "\n"))
    ft.append(("class:inspector-title", f" {'INSPECTOR':^{menu_w - 2}} "))
    ft.append(("", "\n"))
    ft.append(("class:inspector-title", f" {'─' * (menu_w - 2)} "))
    ft.append(("", "\n"))

    # ── Files ──
    if files:
        ft.append(("class:inspector-header", f"\n {'FILES':<{menu_w - 2}}"))
        for f in files:
            name = f.path.replace("\\", "/")
            if len(name) > menu_w - 5:
                name = "…" + name[-(menu_w - 8) :]
            icon = {"reading": "📖", "editing": "✏️", "searching": "🔍"}.get(f.status, " ")
            ft.append(("", "\n"))
            ft.append(("class:inspector-file", f"  {icon} {name}"))
            if f.line:
                ft.append(("class:dim", f":{f.line}"))
    else:
        ft.append(("", "\n"))
        ft.append(("class:dim", "  (no files)"))

    # ── Agents ──
    if agents:
        ft.append(("class:inspector-header", f"\n\n {'AGENTS':<{menu_w - 2}}"))
        for a in agents:
            icon = {"running": "●", "done": "✓", "waiting": "○", "error": "✗"}.get(a.status, "?")
            style = {
                "running": "class:success",
                "done": "class:dim",
                "waiting": "class:dim",
                "error": "class:error",
            }.get(a.status, "")
            ft.append(("", "\n"))
            ft.append(("class:dim", f"  {icon} "))
            ft.append((style, f"{a.name}"))
            ft.append(("class:dim", f"  {a.status}"))

    # ── Context bar ──
    ft.append(("class:inspector-header", f"\n\n {'CTX':<{menu_w - 2}}"))
    ft.append(("", "\n"))
    bar_w = menu_w - 4
    filled = max(0, min(bar_w, int(bar_w * context_pct / 100)))
    ft.append(("class:dim", "  "))
    if filled > 0:
        ft.append(("class:context-bar-fill", "█" * filled))
    ft.append(("class:context-bar-empty", "░" * (bar_w - filled)))
    ft.append(("", "\n"))
    ft.append(("class:dim", f"  {context_pct}%"))

    return FormattedText(ft)
