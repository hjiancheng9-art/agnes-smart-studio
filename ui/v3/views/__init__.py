"""CRUX TUI v3 views — pure render functions.

Each view is a function:
    (UiState, cols: int) → FormattedText

Views never mutate state. They only READ from the frozen UiState.
"""
