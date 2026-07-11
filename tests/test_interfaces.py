"""Tests for unified interfaces — unit level, no I/O, no browser."""
import pytest

pytestmark = pytest.mark.unit

import pytest

from core.interfaces import (
    ToolCategory,
    ToolError,
    ToolResult,
    ToolRisk,
    ToolSpec,
    execute_tool,
)
from core.interfaces.errors import (
    AgentError,
    AgentLoopDetected,
    ApprovalRequired,
    BrowserError,
    CDPDisconnected,
    CDPTimeout,
    CRUXError,
    ExecutionError,
    LSPError,
    MCPDisconnected,
    MCPError,
    PermissionDenied,
    RateLimited,
    SandboxViolation,
    TimeoutError,
    ToolNotFound,
)

# ═══════════════════════════════════════════════════
#  ToolSpec tests
# ═══════════════════════════════════════════════════

class TestToolSpec:
    """ToolSpec validates and describes tools."""

    def test_creation_minimal(self):
        """ToolSpec with minimum required fields."""
        spec = ToolSpec(
            name="test",
            description="A test tool",
            category=ToolCategory.UTILITY,
            _handler=lambda **kw: "ok",
        )
        assert spec.name == "test"
        assert spec.category == ToolCategory.UTILITY
        assert spec.risk == ToolRisk.READONLY

    def test_creation_requires_handler(self):
        """ToolSpec without handler raises ValueError."""
        with pytest.raises(ValueError, match="handler"):
            ToolSpec(name="noop", description="No handler", category=ToolCategory.UTILITY)

    def test_full_config(self):
        """ToolSpec with all fields set."""
        spec = ToolSpec(
            name="browser_nav",
            description="Navigate browser",
            category=ToolCategory.BROWSER,
            risk=ToolRisk.BROWSER,
            timeout_seconds=60.0,
            max_retries=2,
            idempotent=False,
            requires_browser=True,
            requires_network=True,
            _handler=lambda url: f"navigated to {url}",
        )
        assert spec.risk == ToolRisk.BROWSER
        assert spec.requires_browser is True
        assert spec.timeout_seconds == 60.0
        assert spec.max_retries == 2
        assert not spec.idempotent

    def test_category_values(self):
        """All categories are valid enum values."""
        categories = set(c.value for c in ToolCategory)
        assert "search" in categories
        assert "execute" in categories
        assert "browser" in categories
        assert "mcp" in categories

    def test_risk_levels_increasing(self):
        """Risk levels cover the full spectrum."""
        risks = list(ToolRisk)
        assert ToolRisk.READONLY in risks
        assert ToolRisk.SHELL in risks
        assert ToolRisk.DESTRUCTIVE in risks


# ═══════════════════════════════════════════════════
#  ToolResult tests
# ═══════════════════════════════════════════════════

class TestToolResult:
    """ToolResult unifies success and failure."""

    def test_ok_result(self):
        """ok() creates successful result."""
        r = ToolResult.ok(data={"answer": 42}, tool_name="calc", elapsed_ms=10.0)
        assert r.success
        assert r.data == {"answer": 42}
        assert r.tool_name == "calc"
        assert r.error is None

    def test_fail_result(self):
        """fail() creates error result."""
        err = ToolError(ToolError.TIMEOUT, "Request timed out")
        r = ToolResult.fail(error=err, tool_name="api", elapsed_ms=5000.0)
        assert not r.success
        assert r.error.code == ToolError.TIMEOUT
        assert r.tool_name == "api"

    def test_ok_no_data(self):
        """ok() with no data works."""
        r = ToolResult.ok(None)
        assert r.success
        assert r.data is None


# ═══════════════════════════════════════════════════
#  ToolError tests
# ═══════════════════════════════════════════════════

class TestToolError:
    """ToolError provides structured error info."""

    def test_standard_codes(self):
        """All standard error codes are defined."""
        assert ToolError.TIMEOUT == "TIMEOUT"
        assert ToolError.NETWORK == "NETWORK"
        assert ToolError.PERMISSION_DENIED == "PERMISSION_DENIED"
        assert ToolError.BROWSER_ERROR == "BROWSER_ERROR"
        assert ToolError.MCP_ERROR == "MCP_ERROR"
        assert ToolError.LSP_ERROR == "LSP_ERROR"

    def test_recoverable_flag(self):
        """Recoverable errors can be retried."""
        err = ToolError(ToolError.TIMEOUT, "timeout", recoverable=True)
        assert err.recoverable

        err2 = ToolError(ToolError.PERMISSION_DENIED, "denied")
        assert not err2.recoverable

    def test_with_detail(self):
        """Detail field provides additional context."""
        err = ToolError("CUSTOM", "Bad stuff", detail="stack trace here")
        assert err.detail == "stack trace here"


# ═══════════════════════════════════════════════════
#  execute_tool tests
# ═══════════════════════════════════════════════════

class TestExecuteTool:
    """execute_tool wraps tool calls with error handling."""

    def test_successful_execution(self):
        """Successful tool returns ok result."""
        spec = ToolSpec(
            name="echo",
            description="Echo",
            category=ToolCategory.UTILITY,
            _handler=lambda msg: msg,
        )
        r = execute_tool(spec, msg="hello")
        assert r.success
        assert r.data == "hello"
        assert r.tool_name == "echo"
        assert r.elapsed_ms >= 0

    def test_exception_is_caught(self):
        """Tool exceptions become ToolError results."""
        spec = ToolSpec(
            name="crash",
            description="Always crashes",
            category=ToolCategory.UTILITY,
            _handler=lambda: (_ for _ in ()).throw(ValueError("boom")),
        )
        r = execute_tool(spec)
        assert not r.success
        assert r.error.code == ToolError.INVALID_INPUT
        assert "boom" in r.error.message

    def test_timeout_is_classified(self):
        """TimeoutError is classified correctly."""
        spec = ToolSpec(
            name="slow",
            description="Too slow",
            category=ToolCategory.UTILITY,
            _handler=lambda: (_ for _ in ()).throw(TimeoutError("too slow")),
        )
        r = execute_tool(spec)
        assert not r.success
        assert r.error.code == ToolError.TIMEOUT


# ═══════════════════════════════════════════════════
#  CRUXError hierarchy tests
# ═══════════════════════════════════════════════════

class TestErrorHierarchy:
    """Error hierarchy covers all domains."""

    def test_browser_errors(self):
        """Browser errors have correct hierarchy."""
        assert issubclass(CDPDisconnected, BrowserError)
        assert issubclass(CDPTimeout, BrowserError)
        assert issubclass(BrowserError, CRUXError)

    def test_mcp_errors(self):
        """MCP errors have correct hierarchy."""
        assert issubclass(MCPDisconnected, MCPError)
        assert issubclass(MCPError, CRUXError)

    def test_execution_errors(self):
        """Execution errors have correct hierarchy."""
        assert issubclass(SandboxViolation, ExecutionError)
        assert issubclass(TimeoutError, ExecutionError)
        assert issubclass(ExecutionError, CRUXError)

    def test_recoverable_errors(self):
        """Recoverable errors can be retried."""
        assert CDPDisconnected("test").recoverable
        assert CDPTimeout("test").recoverable
        assert MCPDisconnected("test").recoverable
        assert TimeoutError("test").recoverable
        assert not SandboxViolation("test").recoverable
        assert not PermissionDenied("test").recoverable

    def test_all_errors_have_code(self):
        """Every error type has a code."""
        errors = [
            BrowserError("b"),
            CDPDisconnected("c"),
            MCPError("m"),
            LSPError("l"),
            ExecutionError("e"),
            SandboxViolation("s"),
            PermissionDenied("p"),
            ApprovalRequired("a"),
            ToolNotFound("t"),
            RateLimited("r"),
            AgentError("ag"),
            AgentLoopDetected("al"),
        ]
        for e in errors:
            assert e.code, f"{type(e).__name__} has no code"
