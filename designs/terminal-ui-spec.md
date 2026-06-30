# CRUX Terminal UI Redesign Spec

## Goal
Rebuild the CRUX chat interface as a full-screen terminal application with a **fixed input box** that never scrolls away — same UX as Claude Code.

## Current Pain
- Input prompt disappears during AI streaming
- User sees "AI generating... please wait" and can't type
- Messages and input box share the same scroll region

## Target Layout
```
┌──────────────────────────────────┐
│  Header: ● CRUX Studio vX  ·  model  │  1 line, fixed
├──────────────────────────────────┤
│                                  │
│  Message Area                    │  Scrollable, fills remaining space
│  - User messages (right-aligned) │
│  - AI responses (Markdown)      │
│  - System/tool messages          │
│  - Streaming updates in-place    │
│                                  │
├──────────────────────────────────┤
│  Status: model · 12 tokens · 0.3s│  1 line, dim
├──────────────────────────────────┤
│  › _                             │  1-3 lines, fixed at bottom
└──────────────────────────────────┘
```

## Technology
- **prompt_toolkit Application** (full_screen=True) for the TUI shell
- **Rich** for Markdown → ANSI conversion (keep all existing rendering)
- **Thread-safe queue** between streaming thread and UI thread

## Key Design Decisions

### 1. Rich → ANSI → prompt_toolkit pipeline
All existing `console.print()` output is captured via `_ConsoleProxy` / `_LayoutSink` (already exists in ui/theme.py), rendered to ANSI string via Rich, then displayed in prompt_toolkit as `ANSI(...)` formatted text. Zero changes to existing rendering code.

### 2. Streaming updates
The chat streaming runs in a background thread. It pushes text chunks to a `queue.Queue`. The prompt_toolkit app polls this queue via `invalidate()` and updates the message area display in real time — the input box remains interactive throughout.

### 3. Input handling
- **Enter** → submit message
- **Alt+Enter** / **Ctrl+J** → newline in input
- **Ctrl+V** → paste (image → auto-save to file, text → normal paste)
- **Ctrl+C** → interrupt streaming
- **Up/Down** → browse history

### 4. Command system preserved
All `/` commands (/help, /clear, /code, /agent, /tools, /img, /video, /plan, /sub, /commit, /self, /audit, /provider, /model, /deploy, /todo, /refactor, /rules, /evolve, /know, /skill) continue to work identically.

## Files to Create

### `ui/terminal_app.py` — Main terminal application (~400 lines)
- `CruxTerminalApp` class
  - `__init__(on_submit: Callable)` — build layout, keybindings, styles
  - `add_message(role: str, text: str)` — thread-safe, appends formatted message
  - `add_stream_chunk(text: str)` — append to current streaming message
  - `commit_stream()` — finalize current streaming message
  - `set_status(text: str)` — update status bar
  - `run()` — start the prompt_toolkit application (blocking)
  - `exit()` — clean shutdown
- Layout built with prompt_toolkit:
  - `HSplit([header_window, ScrollablePane(message_window), status_window, input_area])`
- Styles matching the existing Dark Atelier theme (COLORS dict in ui/theme.py)

### `ui/message_buffer.py` — Message storage (~100 lines)
- `MessageBuffer` class
  - Thread-safe message list with timestamps
  - `render() -> FormattedText` — render all messages as formatted text
  - `render_streaming(preview: str) -> FormattedText` — render with live preview
  - Rich console with `capture()` for ANSI conversion

## Files to Modify

### `ui/cli.py`
- Add `_chat_terminal()` method that creates `CruxTerminalApp` and wires it to `ChatSession`
- Keep `_chat()` as fallback (--no-tui flag)
- Terminal mode becomes the default

### `ui/theme.py`
- Add `TERMINAL_APP_STYLE` dict for prompt_toolkit styles
- Export prompt_toolkit `Style` object built from COLORS

### `crux_studio.py`
- No changes needed (already calls `cli._chat()`)

## Implementation Order
1. Create `ui/message_buffer.py` — message storage & Rich→ANSI rendering
2. Create `ui/terminal_app.py` — full prompt_toolkit Application
3. Modify `ui/theme.py` — add prompt_toolkit styles
4. Modify `ui/cli.py` — add `_chat_terminal()` method, make it default

## Edge Cases
- Very long messages: ScrollablePane handles overflow with scrollbar
- Very fast streaming: Throttle UI updates to ~15 fps via `invalidate()` debounce
- Window resize: prompt_toolkit handles resize automatically
- Small terminal (< 10 lines): Input area collapses to 1 line minimum
- Unicode/emoji: wcwidth-aware rendering via prompt_toolkit
- Windows Terminal: Full support (prompt_toolkit is Windows-compatible)
