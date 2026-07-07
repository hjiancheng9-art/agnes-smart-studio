"""
CRUX TUI v2 — Input Completer (File + Commands + History)
===========================================================
Per 3-platform debate conclusions:

@file completion:
  - @file → list files in current dir
  - @dir/ → list files in subdirectory
  - @f → fuzzy match filenames
  - Priority: @file > @folder > @symbol

/command completion:
  - /clear    Clear conversation
  - /model    Switch model
  - /help     Show help
  - /export   Export conversation
  - /system   Set system prompt
  - /theme    Switch theme
  - /undo     Undo last action
  - /retry    Retry last action

Behavior:
  - When user types @ → enter file completion mode
  - When user types / → enter command completion mode
  - Otherwise: normal word completion (from history)
"""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

# ── Slash commands (per debate: max 8) ────────────────────

COMMANDS = [
    ("/clear", "清除对话历史"),
    ("/model", "切换 AI 模型"),
    ("/help", "显示帮助信息"),
    ("/export", "导出对话"),
    ("/system", "设置系统提示词"),
    ("/theme", "切换主题 (normal/high_contrast/mono)"),
    ("/undo", "撤销上一步操作"),
    ("/retry", "重试上一次请求"),
]

# Files/folders to exclude from completion
EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', '.tox', '.crux', '.codebuddy'}
EXCLUDE_EXTS = {'.pyc', '.pyo', '.so', '.dll', '.exe'}


def _list_files(prefix: str) -> list[tuple[str, str, str]]:
    """
    List files matching prefix. Returns [(path, display, type)].
    Follows @file, @dir/ syntax.
    """
    results = []
    try:
        cwd = Path.cwd()
        search_dir = cwd
        search_prefix = prefix
        base_path = prefix  # base to reconstruct full paths

        # Handle nested paths and trailing slashes
        if prefix:
            p = Path(prefix)
            if prefix.endswith('/') or prefix.endswith('\\'):
                # @dir/ → list contents of dir
                search_dir = cwd / p
                search_prefix = ""
                base_path = prefix
                if not search_dir.exists():
                    return []
            elif p.parent != Path("."):
                # @parent/child → look in parent directory
                search_dir = cwd / p.parent
                search_prefix = p.name
                base_path = str(p.parent) + "/" if str(p.parent) != "." else ""
            else:
                # @file → look in current dir
                search_prefix = prefix
                base_path = ""

        if not search_dir.exists():
            return results

        for entry in sorted(search_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            name = entry.name

            if name.startswith('.') and not search_prefix.startswith('.'):
                continue
            if entry.is_dir() and name in EXCLUDE_DIRS:
                continue
            if entry.suffix.lower() in EXCLUDE_EXTS:
                continue
            if search_prefix and not name.lower().startswith(search_prefix.lower()):
                continue

            full = f"{base_path}{name}/" if entry.is_dir() else f"{base_path}{name}"
            results.append((full, f"{name}/" if entry.is_dir() else name, "dir" if entry.is_dir() else "file"))

    except PermissionError:
        pass

    return results


class TuiCompleter(Completer):
    """
    Smart completer for CRUX TUI input.
    
    Modes:
      / → command completion
      @ → file path completion
      default → word completion from history
    """

    def __init__(self, history_words: list[str] | None = None):
        self._history_words = history_words or []

    def update_history_words(self, words: list[str]):
        """Update history word list, filtering short words."""
        self._history_words = [w for w in words if len(w) >= 3]

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor

        # ── Mode 1: Slash command completion ────────────
        if text.startswith('/'):
            word = text.lstrip('/')
            for cmd, desc in COMMANDS:
                cmd_name = cmd.lstrip('/')
                if cmd_name.startswith(word):
                    yield Completion(
                        text=cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                        style="class:command-completion",
                    )
            return

        # ── Mode 2: @file completion ───────────────────
        # Find the last @ in the text
        at_pos = text.rfind('@')
        if at_pos >= 0:
            # Check if @ is at a word boundary
            if at_pos == 0 or text[at_pos-1] in (' ', '\t', '\n', ''):
                prefix = text[at_pos+1:]  # what comes after @

                for full_path, display, entry_type in _list_files(prefix):
                    style = "class:file-completion" if entry_type == "file" else "class:dir-completion"
                    meta = "📄 file" if entry_type == "file" else "📁 dir"

                    yield Completion(
                        text=full_path,
                        start_position=-len(prefix),
                        display=display,
                        display_meta=meta,
                        style=style,
                    )
                return

        # ── Mode 3: Word completion from history ──────
        if text and not text.startswith(('@', '/', '#')):
            last_word = text.split()[-1] if text.split() else text
            if len(last_word) >= 2:  # only complete words with 2+ chars
                seen = set()
                for word in self._history_words:
                    if word.lower().startswith(last_word.lower()):
                        if word not in seen:
                            seen.add(word)
                            yield Completion(
                                text=word,
                                start_position=-len(last_word),
                                display=word,
                                style="class:history-completion",
                            )
