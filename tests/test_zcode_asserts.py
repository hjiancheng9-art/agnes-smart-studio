"""RED: Verify no bare assert in function bodies of target files.
These tests fail until the 4 files replace `assert x is not None; raise x`
with proper if/raise + RuntimeError fallback.
"""

import ast
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

TARGET_FILES = [
    PROJECT_ROOT / "core" / "client.py",
    PROJECT_ROOT / "core" / "agent.py",
    PROJECT_ROOT / "core" / "async_client.py",
    PROJECT_ROOT / "core" / "resilience.py",
]


def _function_asserts(filepath: pathlib.Path) -> list[tuple[str, int, str]]:
    """Return list of (func_name, lineno, assert_text) for every assert in a function body."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    results: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Assert):
                    src = ast.get_source_segment(filepath.read_text(encoding="utf-8"), child) or ""
                    results.append((node.name, child.lineno, src.strip()))
    return results


def _collect_all() -> list[tuple[str, str, int, str]]:
    """Return flat list of (file_stem, func_name, lineno, src)."""
    all_results: list[tuple[str, str, int, str]] = []
    for f in TARGET_FILES:
        for func_name, lineno, src in _function_asserts(f):
            all_results.append((f.stem, func_name, lineno, src))
    return all_results


def test_client_no_bare_assert():
    """client.py must have no assert statements in any function body."""
    results = _function_asserts(PROJECT_ROOT / "core" / "client.py")
    assert results == [], f"client.py has bare asserts: {results}"


def test_agent_no_bare_assert():
    """agent.py must have no assert statements in any function body."""
    results = _function_asserts(PROJECT_ROOT / "core" / "agent.py")
    assert results == [], f"agent.py has bare asserts: {results}"


def test_async_client_no_bare_assert():
    """async_client.py must have no assert statements in any function body."""
    results = _function_asserts(PROJECT_ROOT / "core" / "async_client.py")
    assert results == [], f"async_client.py has bare asserts: {results}"


def test_resilience_no_bare_assert():
    """resilience.py must have no assert statements in any function body."""
    results = _function_asserts(PROJECT_ROOT / "core" / "resilience.py")
    assert results == [], f"resilience.py has bare asserts: {results}"


def test_collective_no_bare_asserts():
    """Catch-all: all 4 target files must be clean."""
    all_results = _collect_all()
    assert all_results == [], f"Bare asserts found: {all_results}"
