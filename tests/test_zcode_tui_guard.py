"""ZCode TDD: Issue 3 (TUI height guard) + Issue 4 (self_heal fixer logging).

RED phase tests — must FAIL before GREEN implementation.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CRUX_STUDIO = ROOT / "crux_studio.py"
SELF_HEAL = ROOT / "core" / "self_heal.py"


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Issue 3: TUI minimum height guard ──────────────────────────────


def test_tui_has_height_guard():
    """Verify _chat_repl_v3 has terminal height check before V3App.run()."""
    source = _read_source(CRUX_STUDIO)

    assert "get_terminal_size" in source, "crux_studio.py must call shutil.get_terminal_size() for height guard"
    assert re.search(r"\.lines\s*<\s*(10|8|12)", source), (
        "crux_studio.py must check terminal size .lines < N before launching TUI"
    )

    # Verify guard appears inside _chat_repl_v3, before V3App is used
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_chat_repl_v3":
            func_source = ast.get_source_segment(source, node) or ""
            guard_pos = func_source.find("get_terminal_size")
            v3_pos = func_source.find("V3App")
            assert guard_pos >= 0, "Height guard missing from _chat_repl_v3"
            assert v3_pos >= 0, "V3App missing from _chat_repl_v3"
            assert guard_pos < v3_pos, "Height guard must appear BEFORE V3App in _chat_repl_v3"
            return
    pytest.fail("_chat_repl_v3 function not found")


# ── Issue 4: self_heal fixer silent failures ────────────────────────


def test_self_heal_fixer_has_logging():
    """Verify fix_silent_exceptions has logger.warning/debug in except block."""
    source = _read_source(SELF_HEAL)

    # Parse the fix_silent_exceptions method
    tree = ast.parse(source)
    method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "fix_silent_exceptions":
            method = node
            break

    assert method is not None, "fix_silent_exceptions method not found in self_heal.py"

    # Find all except handlers in this method
    found_logger_call = False
    for node in ast.walk(method):
        if isinstance(node, ast.ExceptHandler):
            # Walk inside the except handler body for logger.warning or logger.debug
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.Call):
                    if isinstance(subnode.func, ast.Attribute):
                        obj = subnode.func.value
                        attr = subnode.func.attr
                        if (
                            isinstance(obj, ast.Name)
                            and obj.id == "logger"
                            and attr in ("warning", "debug", "error", "info")
                        ):
                            found_logger_call = True
                            break
                    elif isinstance(subnode.func, ast.Name):
                        if subnode.func.id == "logger":
                            found_logger_call = True
                            break
            if found_logger_call:
                break

    assert found_logger_call, (
        "fix_silent_exceptions except block must call logger.warning/logger.debug/etc. with exception info"
    )
