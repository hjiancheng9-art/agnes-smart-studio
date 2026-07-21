"""Status bar view — reads UiState, renders FormattedText."""

from prompt_toolkit.formatted_text import FormattedText

from ..state import InteractionMode, ScrollMode, StreamStatus, UiState


def render_status(state: UiState) -> FormattedText:
    """Bottom status bar: model, cwd, git, context%, latency, method level."""
    cols = state.terminal.cols
    pieces: list[tuple[str, str]] = []

    s = state.session
    st = state.stream

    # ── Copy mode indicator ──
    if state.interaction.mode == InteractionMode.COPY:
        idx = state.interaction.focus_idx
        pieces.append(("class:status-bar-level-c", f" COPY [{idx}] "))
        pieces.append(("class:status-bar-context", " ↑↓ "))
        pieces.append(("class:status-bar", " c "))
        pieces.append(("class:status-bar-context", " Esc "))

    # ── Vim mode indicator ──
    if state.interaction.mode == InteractionMode.VIM:
        pieces.append(("class:status-bar-beast-qilin", " VIM "))

    # ── Status dot (animated pulse) ──
    import time

    if st.status in (StreamStatus.THINKING, StreamStatus.STREAMING):
        _pulse = int(time.time() * 2.5) % 4
        _dot = ["◉", "◎", "◉", "○"][_pulse]
        pieces.append(("class:status-bar-beast-qilin", f" {_dot} {st.status.name[:4]} "))
    else:
        pieces.append(("class:status-bar-beast-xuanwu", f" ● {st.status.name[:4]} "))

    # ── Model ──
    pieces.append(("class:status-bar-model", s.model or "CRUX"))

    # ── Phase (when active) ──
    if st.status == StreamStatus.THINKING:
        pieces.append(("class:status-bar-beast-qilin", " thinking"))
    elif st.status == StreamStatus.STREAMING and st.tool_name:
        pieces.append(("class:status-bar-beast-qilin", f" #{st.tool_seq} {st.tool_name}"))

    # ── Workspace ──
    cwd = s.cwd
    home = __import__("os").path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home) :]
    pieces.append(("class:status-bar-path", f"  {cwd}"))

    if s.git_branch:
        pieces.append(("class:status-bar-git", f" {s.git_branch}"))

    # ── Scroll position indicator ──
    if state.scroll.mode == ScrollMode.MANUAL and state.scroll.unseen > 0:
        pieces.append(("class:status-bar-beast-qilin", f"  {state.scroll.unseen} new | End: follow "))

    # ── Right side ──
    right: list[tuple[str, str]] = []

    # Method level
    if s.method_level:
        level_style = {
            "A": "class:status-bar-level-a",
            "B": "class:status-bar-level-b",
            "C": "class:status-bar-level-c",
            "D": "class:status-bar-level-d",
        }.get(s.method_level, "class:status-bar")
        right.append((level_style, f"[{s.method_level}]"))

    # Context bar
    if s.context_pct > 0:
        filled = int(s.context_pct / 100 * 8)
        bar = "█" * filled + "░" * (8 - filled)
        right.append(("class:status-bar-context", f" {bar} {s.context_pct:.0f}%"))

    # Latency
    if s.latency is not None and s.latency > 0:
        right.append(("class:status-bar-context", f" {s.latency:.1f}s"))

    # ── Padding ──
    left_vis = sum(len(t) for _, t in pieces)
    right_text = "".join(t for _, t in right)
    pad = max(2, cols - left_vis - len(right_text) - 2)
    pieces.append(("class:status-bar", " " * pad))

    pieces.extend(right)

    return FormattedText(pieces)
