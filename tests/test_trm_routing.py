"""Tests for Tool Registry Mesh (TRM) — routing accuracy and fallback."""

import pytest

pytestmark = pytest.mark.unit


import pytest

from core.interfaces.errors import ToolNotFound
from core.interfaces.tool import ToolCategory, ToolError, ToolResult, ToolRisk, ToolSpec, execute_tool

# ═══════════════════════════════════════════════════
#  Fake TRM for testing routing logic
# ═══════════════════════════════════════════════════


class FakeTRM:
    """Fake Tool Registry Mesh for testing routing decisions."""

    def __init__(self):
        self.tools: dict[str, ToolSpec] = {}
        self.route_calls: list[dict] = []

    def register(self, spec: ToolSpec) -> None:
        self.tools[spec.name] = spec

    def route(self, intent: str, **kwargs) -> ToolSpec:
        """Route by intent. Returns first matching tool or raises."""
        self.route_calls.append({"intent": intent, "kwargs": kwargs})

        for spec in self.tools.values():
            if spec.category.value == intent:
                return spec

        raise ToolNotFound(f"No tool for intent '{intent}'")

    def execute(self, intent: str, **kwargs) -> ToolResult:
        """Route + execute in one call."""
        try:
            spec = self.route(intent, **kwargs)
            return execute_tool(spec, **kwargs)
        except ToolNotFound as e:
            return ToolResult.fail(ToolError(ToolError.TOOL_NOT_FOUND, str(e)))


# ═══════════════════════════════════════════════════


class TestTRMRouting:
    """TRM should route intents to correct tools."""

    @pytest.fixture
    def trm(self):
        trm = FakeTRM()
        trm.register(
            ToolSpec(
                name="search_code",
                description="Search code",
                category=ToolCategory.SEARCH,
                _handler=lambda query: f"found: {query}",
            )
        )
        trm.register(
            ToolSpec(
                name="run_python",
                description="Run Python",
                category=ToolCategory.EXECUTE,
                risk=ToolRisk.SHELL,
                _handler=lambda code: f"ran: {code[:20]}",
            )
        )
        trm.register(
            ToolSpec(
                name="review_code",
                description="Review code",
                category=ToolCategory.REVIEW,
                _handler=lambda files: "approved",
            )
        )
        return trm

    def test_route_search(self, trm):
        """Search intent routes to SEARCH category."""
        spec = trm.route("search", query="class Agent")
        assert spec.name == "search_code"
        assert spec.category == ToolCategory.SEARCH

    def test_route_execute(self, trm):
        """Execute intent routes to EXECUTE category."""
        spec = trm.route("execute", code="print(1)")
        assert spec.name == "run_python"
        assert spec.risk == ToolRisk.SHELL

    def test_route_unknown(self, trm):
        """Unknown intent raises ToolNotFound."""
        with pytest.raises(ToolNotFound):
            trm.route("nonexistent")

    def test_execute_success(self, trm):
        """TRM execute wraps route + tool execution."""
        r = trm.execute("search", query="Agent")
        assert r.success
        assert "Agent" in str(r.data)

    def test_execute_unknown(self, trm):
        """TRM execute returns failure for unknown intents."""
        r = trm.execute("nonexistent")
        assert not r.success
        assert r.error.code == ToolError.TOOL_NOT_FOUND


class TestTRMFallback:
    """TRM should have fallback mechanisms."""

    def test_multiple_same_category(self):
        """When multiple tools match, first registered wins."""
        trm = FakeTRM()
        trm.register(
            ToolSpec(
                name="search_a",
                description="Search A",
                category=ToolCategory.SEARCH,
                _handler=lambda q: "A",
            )
        )
        trm.register(
            ToolSpec(
                name="search_b",
                description="Search B",
                category=ToolCategory.SEARCH,
                _handler=lambda q: "B",
            )
        )
        spec = trm.route("search")
        assert spec.name == "search_a"  # First registered

    def test_empty_registry(self):
        """Empty registry should fail gracefully."""
        trm = FakeTRM()
        with pytest.raises(ToolNotFound):
            trm.route("search")
