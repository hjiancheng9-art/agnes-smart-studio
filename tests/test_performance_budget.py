"""Performance budget tests — key operations must stay within time limits.

These prevent regression where new features silently slow down critical paths.
"""

import time

import pytest

from core.interfaces import ToolCategory, ToolSpec, execute_tool

# ═══════════════════════════════════════════════════
#  Budget: tool execution overhead
# ═══════════════════════════════════════════════════


class TestToolExecutionOverhead:
    """Tool execution wrapper must have minimal overhead."""

    @pytest.mark.slow
    def test_tool_overhead_under_10ms(self):
        """Tool execution overhead (wrapping a no-op handler) < 10ms."""
        spec = ToolSpec(
            name="noop",
            description="No operation",
            category=ToolCategory.UTILITY,
            _handler=lambda: None,
        )
        times = []
        for _ in range(100):
            start = time.perf_counter()
            r = execute_tool(spec)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        assert r.success
        assert avg < 10.0, f"Average tool overhead {avg:.2f}ms exceeds 10ms budget"

    @pytest.mark.slow
    def test_tool_error_overhead_under_10ms(self):
        """Tool error wrapping overhead < 10ms."""
        spec = ToolSpec(
            name="broken",
            description="Broken",
            category=ToolCategory.UTILITY,
            _handler=lambda: 1 / 0,
        )
        times = []
        for _ in range(100):
            start = time.perf_counter()
            r = execute_tool(spec)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        assert not r.success
        assert avg < 10.0, f"Average error overhead {avg:.2f}ms exceeds 10ms budget"


# ═══════════════════════════════════════════════════
#  Budget: test collection time
# ═══════════════════════════════════════════════════


class TestTestCollectionSpeed:
    """Test collection must stay fast for quick feedback."""

    @pytest.mark.slow
    def test_smoke_collection_under_5s(self):
        """Smoke test collection (unit-only) < 5 seconds."""
        import subprocess

        start = time.perf_counter()
        subprocess.run(
            ["python", "-m", "pytest", "tests/", "--co", "-q", "-m", "unit", "--ignore=tests/manual"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=".",
        )
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"Smoke collection took {elapsed:.2f}s, budget is 5s"


# ═══════════════════════════════════════════════════
#  Budget: import time
# ═══════════════════════════════════════════════════


class TestImportSpeed:
    """Key modules must import quickly."""

    @pytest.mark.parametrize(
        "module",
        [
            "core.interfaces",
            "core.interfaces.errors",
            "core.interfaces.tool",
        ],
    )
    @pytest.mark.slow
    def test_core_interface_imports_under_1s(self, module):
        """Core interface imports < 1 second."""
        import subprocess

        start = time.perf_counter()
        r = subprocess.run(["python", "-c", f"import {module}"], capture_output=True, text=True, timeout=10, cwd=".")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Import {module} took {elapsed:.2f}s, budget is 1s"
        assert r.returncode == 0
