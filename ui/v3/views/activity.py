"""Activity log view — shows tool execution status."""

from prompt_toolkit.formatted_text import FormattedText

from ..state import StreamStatus, UiState


def render_activity(state: UiState) -> FormattedText:
    """Render the activity log (tool execution bar between chat and input)."""
    items = state.activity.items
    if not items and state.stream.tool_seq == 0:
        if state.activity.expanded:
            return FormattedText([("class:dim", "  Activity log (empty — tools run during chat will appear here)")])
        return FormattedText([])

    pieces: list[tuple[str, str]] = []

    # Show active tool if streaming
    if state.stream.status in (StreamStatus.THINKING, StreamStatus.STREAMING) and state.stream.tool_name:
        pieces.append(("class:activity-running", f"● #{state.stream.tool_seq} {state.stream.tool_name}"))
        pieces.append(("", "\n"))

    # Show recent activity items
    max_show = 8 if state.activity.expanded else 2
    for item in items[-max_show:]:
        if len(item) == 3:
            icon, style_class, msg = item
        elif len(item) == 2:
            icon, msg = item
            style_class = ""
        else:
            continue
        text = f"{icon} {msg}".replace("\n", " ")[: state.terminal.cols - 4]
        pieces.append((style_class, text))
        pieces.append(("", "\n"))

    return FormattedText(pieces)
