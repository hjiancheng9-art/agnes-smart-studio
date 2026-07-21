"""CRUX TUI v3 — Command palette overlay. Ctrl+P.

Design:
  - Single source of truth: reads from core.commands.COMMANDS registry
  - Result limit: max 12, stable sort order
  - selected clamped on query change
  - Modal: blocks all underlying keybindings
"""

from __future__ import annotations

from prompt_toolkit.formatted_text import FormattedText

_MAX_RESULTS = 12


def _load_commands() -> list[tuple[str, str]]:
    """Read command list from the canonical CommandRegistry (single source)."""
    try:
        from core.commands import COMMANDS as _reg

        results = []
        for cmd in _reg:
            desc = cmd.desc or ""
            label = cmd.name if cmd.name.startswith("/") else f"/{cmd.name}"
            results.append((label, desc))
        return sorted(results, key=lambda x: x[0])
    except ImportError:
        pass
    # Fallback — minimal set so palette never breaks
    return sorted(
        [
            ("/help", "帮助"),
            ("/clear", "清屏"),
            ("/method", "方法论状态"),
            ("/done", "完成前验证"),
            ("/cost", "费用统计"),
            ("/export", "导出对话"),
            ("/self audit", "自愈审计"),
            ("/model light", "切换轻量模型"),
            ("/model pro", "切换专业模型"),
            ("/tdd start", "开始 TDD"),
            ("q", "退出"),
            ("--tui", "TUI 界面模式"),
        ],
        key=lambda x: x[0],
    )


# Cached at import — command registry doesn't change at runtime
_COMMANDS = _load_commands()


def match_commands(query: str) -> list[tuple[str, str]]:
    """Fuzzy-filter from canonical registry. Always sorted, max 12 results."""
    if not query:
        return _COMMANDS[:_MAX_RESULTS]
    q = query.lower().lstrip("/")
    results = []
    for cmd, desc in _COMMANDS:
        if q in cmd.lower() or q in desc:
            results.append((cmd, desc))
        if len(results) >= _MAX_RESULTS:
            break
    return results


def _clamp_selected(query: str, selected: int) -> int:
    """Clamp selected index after query changes."""
    matches = match_commands(query)
    if not matches:
        return 0
    return min(max(0, selected), len(matches) - 1)


def render_palette(
    query: str = "",
    selected: int = 0,
    width: int = 60,
) -> FormattedText:
    """Render the command palette overlay.

    Args:
        query: Current filter text.
        selected: Index of highlighted item (already clamped by reducer).
        width: Terminal width.
    """
    ft: list[tuple[str, str]] = []
    matches = match_commands(query)
    w = min(width - 4, 70)

    # ── Header ──
    ft.append(("class:palette-title", f" {'─' * (w - 2)} "))
    ft.append(("", "\n"))
    ft.append(("class:palette-title", f"  Command Palette  {' ' * (w - 20)}"))
    ft.append(("", "\n"))
    ft.append(("class:palette-title", f" {'─' * (w - 2)} "))
    ft.append(("", "\n"))

    # ── Search bar ──
    prompt = f"> {query}" if query else "> Type to filter..."
    ft.append(("", "\n"))
    ft.append(("class:palette-search", f"  {prompt}{' ' * max(0, w - len(prompt) - 2)}"))
    ft.append(("", "\n"))

    # ── Results ──
    ft.append(("class:palette-title", f"\n {'─' * (w - 2)} "))
    ft.append(("", "\n"))
    if not matches:
        ft.append(("", "\n"))
        ft.append(("class:dim", "  No matches"))
    else:
        for i, (cmd, desc) in enumerate(matches):
            is_sel = i == selected
            sel = "class:palette-selected" if is_sel else "class:palette-item"
            cmd_s = "class:palette-cmd-selected" if is_sel else "class:palette-cmd"
            ft.append(("", "\n"))
            ft.append((sel, f"  {'>' if is_sel else ' '} "))
            ft.append((cmd_s, f"{cmd:<32}"))
            ft.append(("class:dim", f"  {desc}"))

    # ── Footer ──
    ft.append(("", "\n"))
    ft.append(("class:palette-title", f"\n {'─' * (w - 2)} "))
    ft.append(("", "\n"))
    ft.append(("class:dim", "  ↑↓ navigate  Enter select  Esc close"))
    return FormattedText(ft)
