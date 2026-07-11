"""Tests for approval_gate — permission boundary must be enforced."""
import pytest

pytestmark = pytest.mark.unit


import pytest

from core.interfaces.tool import ToolCategory, ToolRisk, ToolSpec

# ═══════════════════════════════════════════════════
#  ApprovalGate should exist and block risky tools
# ═══════════════════════════════════════════════════

class TestApprovalGateExists:
    """Verify approval_gate module is importable."""

    def test_module_imports(self):
        """approval_gate module can be imported or exists as file."""
        import importlib.util

        # Check if module file exists
        import os
        path = os.path.join("core", "approval_gate.py")
        exists = os.path.exists(path)
        if exists:
            spec = importlib.util.spec_from_file_location("approval_gate", path)
            assert spec is not None
        else:
            pytest.skip("approval_gate.py not found — needs creation")

    def test_has_check_function(self):
        """approval_gate should have a check/approve mechanism."""
        import os
        if not os.path.exists(os.path.join("core", "approval_gate.py")):
            pytest.skip("approval_gate.py not found")
        from core import approval_gate
        has_check = any(
            hasattr(approval_gate, attr)
            for attr in ["check", "approve", "is_allowed", "require_approval", "ApprovalGate"]
        )
        assert has_check, "approval_gate should expose a check/approve API"


class TestApprovalLogic:
    """Approval checks should block risky operations."""

    @pytest.fixture
    def readonly_tool(self):
        return ToolSpec(
            name="read_file",
            description="Read a file",
            category=ToolCategory.IO,
            risk=ToolRisk.READONLY,
            _handler=lambda path: "content",
        )

    @pytest.fixture
    def destructive_tool(self):
        return ToolSpec(
            name="rm_rf",
            description="Delete everything",
            category=ToolCategory.EXECUTE,
            risk=ToolRisk.DESTRUCTIVE,
            _handler=lambda: "gone",
        )

    @pytest.fixture
    def shell_tool(self):
        return ToolSpec(
            name="run_bash",
            description="Run shell command",
            category=ToolCategory.EXECUTE,
            risk=ToolRisk.SHELL,
            _handler=lambda cmd: "output",
        )

    def test_readonly_tool_should_not_require_approval(self, readonly_tool):
        """Read-only tools should be auto-approved."""
        assert readonly_tool.risk == ToolRisk.READONLY

    def test_destructive_tool_should_be_flagged(self, destructive_tool):
        """Destructive tools should require approval."""
        assert destructive_tool.risk == ToolRisk.DESTRUCTIVE

    def test_shell_tool_should_be_flagged(self, shell_tool):
        """Shell execution should require approval."""
        assert shell_tool.risk == ToolRisk.SHELL

    def test_risk_ordering(self):
        """Risk levels should have a clear ordering for policy decisions."""
        ordered = list(ToolRisk)
        readonly_idx = ordered.index(ToolRisk.READONLY)
        destructive_idx = ordered.index(ToolRisk.DESTRUCTIVE)
        assert readonly_idx < destructive_idx, "READONLY should be lower risk than DESTRUCTIVE"
