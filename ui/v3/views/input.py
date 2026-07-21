"""Input bar view — prompt + buffer placeholder."""

from prompt_toolkit.formatted_text import FormattedText

from ..state import StreamStatus, UiState


def render_input_hint(state: UiState) -> FormattedText:
    """Hint text shown in the input frame bottom border."""
    st = state.stream
    if st.status in (StreamStatus.THINKING, StreamStatus.STREAMING):
        return FormattedText([("class:welcome-desc", " streaming: Enter queue | Ctrl+C cancel ")])
    if state.activity.expanded:
        return FormattedText([])
    return FormattedText([("class:welcome-desc", "")])


def render_input_prompt(state: UiState) -> str:
    """Prompt prefix for the input buffer."""
    if state.stream.status in (StreamStatus.THINKING, StreamStatus.STREAMING):
        return "* "
    return "> "
