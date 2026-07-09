"""ZCode TDD: Issue 3 (TUI height guard) + Issue 4 (self_heal fixer logging).

RED phase tests — must FAIL before GREEN implementation.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
CRUX_STUDIO = ROOT / "crux_studio.py"
SELF_HEAL = ROOT / "core" / "self_heal.py"


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Issue 3: TUI minimum height guard ──────────────────────────────


def test_tui_has_height_guard():
    """Verify _chat_tui has terminal height check before TuiApp.run()."""
    source = _read_source(CRUX_STUDIO)

    # Must have a terminal size check with < threshold
    assert "get_terminal_size" in source, "crux_studio.py must call shutil.get_terminal_size() for height guard"

    # Must check lines against a threshold (10)
    assert re.search(r"\.lines\s*<\s*(10|8|12)", source), (
        "crux_studio.py must check terminal size .lines < N before launching TUI"
    )

    # Parse AST to verify the guard appears before TuiApp creation
    tree = ast.parse(source)
    found_guard = False
    found_tui_import_or_create = False
    guard_before_tui = False

    for node in ast.walk(tree):
        # Check for the height guard condition
        if isinstance(node, ast.Compare):
            code_snippet = ast.get_source_segment(source, node) or ""
            if "lines" in code_snippet and "<" in code_snippet:
                found_guard = True

        # Check for TuiApp / TuiAppV2 import or creation
        if isinstance(node, ast.ImportFrom) and node.module in ("ui.tui_app", "ui.tui_v2"):
            found_tui_import_or_create = True
            if found_guard:
                guard_before_tui = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("TuiApp", "TuiAppV2"):
            found_tui_import_or_create = True
            if found_guard:
                guard_before_tui = True

    assert found_guard, "crux_studio.py missing height guard (lines < N check)"
    assert found_tui_import_or_create, "crux_studio.py missing TuiApp/TuiAppV2 reference"
    assert guard_before_tui, "Height guard must appear BEFORE TuiApp import/creation in source"


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
