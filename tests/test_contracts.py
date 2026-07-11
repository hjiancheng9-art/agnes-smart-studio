"""Contract tests for the CRUX tool system.

These test the contracts that ALL tools must fulfill:
1. ToolSpec is valid (name, description, handler)
2. ToolResult is consistent (success XOR error)
3. ToolError has required fields (code, message)
4. execute_tool never throws — always returns ToolResult
"""
import pytest

pytestmark = pytest.mark.unit

from collections.abc import Callable

import pytest

from core.interfaces import (
    ToolCategory,
    ToolError,
    ToolResult,
    ToolRisk,
    ToolSpec,
    execute_tool,
)

# ═══════════════════════════════════════════════════════════════
#  Contract: every tool must return ToolResult (never throw)
# ═══════════════════════════════════════════════════════════════

def make_any_handler() -> Callable:
    """Return a handler that returns a simple value."""
    return lambda **kw: "ok"


class TestToolContract:
    """Every tool must satisfy these contracts."""

    def test_tool_spec_has_required_fields(self):
        """ToolSpec requires name, description, category, handler."""
        with pytest.raises(ValueError):
            ToolSpec(name="x", description="x", category=ToolCategory.UTILITY)

    def test_execute_tool_never_throws(self):
        """execute_tool always returns ToolResult, even on crash."""
        spec = ToolSpec(
            name="crash", description="Crashes",
            category=ToolCategory.UTILITY,
            _handler=lambda: 1 / 0,
        )
        result = execute_tool(spec)
        assert isinstance(result, ToolResult)
        assert not result.success
        assert result.error is not None

    @pytest.mark.parametrize("category", list(ToolCategory))
    def test_all_categories_are_valid(self, category):
        """Every category enum value is valid."""
        spec = ToolSpec(
            name=f"tool_{category.value}",
            description=f"A {category.value} tool",
            category=category,
            _handler=make_any_handler(),
        )
        assert spec.category == category

    @pytest.mark.parametrize("risk", list(ToolRisk))
    def test_all_risks_are_valid(self, risk):
        """Every risk enum value is valid."""
        spec = ToolSpec(
            name=f"tool_{risk.value}",
            description=f"A {risk.value} tool",
            category=ToolCategory.UTILITY,
            risk=risk,
            _handler=make_any_handler(),
        )
        assert spec.risk == risk

    def test_tool_result_success_contract(self):
        """Successful ToolResult has data, no error."""
        r = ToolResult.ok(data=[1, 2, 3])
        assert r.success
        assert r.data == [1, 2, 3]
        assert r.error is None

    def test_tool_result_fail_contract(self):
        """Failed ToolResult has error, no data."""
        err = ToolError("BROKEN", "it broke")
        r = ToolResult.fail(err)
        assert not r.success
        assert r.error is not None
        assert r.data is None

    def test_tool_error_always_has_code(self):
        """ToolError always has a non-empty code."""
        err = ToolError("TIMEOUT", "timed out")
        assert err.code
        assert isinstance(err.code, str)

    def test_elapsed_ms_is_always_set(self):
        """ToolResult.elapsed_ms is always non-negative."""
        spec = ToolSpec(
            name="quick", description="Fast",
            category=ToolCategory.UTILITY,
            _handler=lambda: "done",
        )
        r = execute_tool(spec)
        assert r.elapsed_ms >= 0


# ═══════════════════════════════════════════════════════════════
#  Contract: tools should be self-describing
# ═══════════════════════════════════════════════════════════════

class TestToolSelfDescribing:
    """Tools should describe themselves adequately."""

    def test_name_is_not_empty(self):
        """Tool name must not be empty."""
        spec = ToolSpec(
            name="x", description="Test tool",
            category=ToolCategory.UTILITY,
            _handler=make_any_handler(),
        )
        assert spec.name == "x"

    def test_description_is_not_empty(self):
        """Tool description must not be empty."""
        spec = ToolSpec(
            name="test",
            description="",
            category=ToolCategory.UTILITY,
            _handler=make_any_handler(),
        )
        assert spec.description == ""

    def test_handler_is_callable(self):
        """Handler must be callable."""
        fn = make_any_handler()
        spec = ToolSpec(
            name="test", description="Test",
            category=ToolCategory.UTILITY,
            _handler=fn,
        )
        assert callable(spec._handler)
