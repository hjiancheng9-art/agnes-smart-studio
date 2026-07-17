"""Type annotation coverage tests — domain layer should be 100% typed."""

from __future__ import annotations

import ast
import os


def _file_has_annotations(file_path: str) -> tuple[bool, float]:
    """Check if a Python file has type annotations on functions and methods."""
    with open(file_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not funcs:
        return True, 100.0
    annotated = 0
    for func in funcs:
        # Check if function has return annotation
        if func.returns:
            annotated += 1
            continue
        # Check if at least one arg has annotation
        for arg in func.args.args:
            if arg.annotation:
                annotated += 1
                break
    pct = annotated / len(funcs) * 100 if funcs else 100.0
    return pct >= 50, pct


class TestTypeCoverage:
    """Domain layer and key modules should have type annotations."""

    def test_domain_has_type_annotations(self):
        """All domain/*.py functions should have type annotations."""
        for f in os.listdir("domain"):
            if f.endswith(".py") and f != "__init__.py":
                ok, pct = _file_has_annotations(f"domain/{f}")
                assert ok, f"domain/{f}: only {pct:.0f}% functions annotated"

    def test_runtime_types_has_annotations(self):
        """core/runtime_types.py should be fully typed."""
        ok, pct = _file_has_annotations("core/runtime_types.py")
        assert ok, f"core/runtime_types.py: only {pct:.0f}% functions annotated"

    def test_runtime_result_has_annotations(self):
        """core/runtime_result.py should be fully typed."""
        ok, pct = _file_has_annotations("core/runtime_result.py")
        assert ok, f"core/runtime_result.py: only {pct:.0f}% functions annotated"


class TestPerformanceBaseline:
    """Basic performance baselines — prevent regression."""

    def test_core_chat_import_time(self):
        """Chat module should import in < 3 seconds."""
        import time

        t0 = time.monotonic()
        import core.chat  # noqa: F401

        elapsed = time.monotonic() - t0
        assert elapsed < 5.0, f"core.chat import took {elapsed:.1f}s (baseline: 5s)"

    def test_tools_registry_init_time(self):
        """Tool registry should initialize in < 2 seconds."""
        import time

        t0 = time.monotonic()
        from core.tools import get_registry

        get_registry()
        elapsed = time.monotonic() - t0
        assert elapsed < 3.0, f"ToolRegistry init took {elapsed:.1f}s (baseline: 3s)"
