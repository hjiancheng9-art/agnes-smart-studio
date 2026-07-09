"""Orchestrator -- MCP Fallback 测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from unittest.mock import MagicMock
from comfyflow_compiler.orchestrator import (
    CompileOrchestrator, CompileMode, CompileResult,
    MCPClient, MCPTimeoutError, MCPUnavailableError, MCPInvalidWorkflowError,
    FallbackPolicy, FailureGrade,
)


class MockLocal:
    def __init__(self, success=True, bp="test_bp", missing=False):
        from comfyflow_compiler.models import CompileResult as LR, QualityReport
        self._success = success
        self._bp = bp
        self._missing = missing

    def compile(self, prompt, **kw):
        from comfyflow_compiler.models import CompileResult as LR, QualityReport
        if self._missing:
            return LR(success=False, blueprint_used="missing_blueprint", error="t2v missing")
        if self._success:
            return LR(success=True, workflow_json={"prompt": {"1": {"class_type": "K"}}},
                      blueprint_used=self._bp, quality_report=QualityReport(passed=True, overall_score=0.8))
        return LR(success=False, blueprint_used=self._bp, error="local error")


# ---- FallbackPolicy ----

def test_should_fallback_timeout():
    assert FallbackPolicy().should_fallback(FailureGrade.TIMEOUT) is True

def test_should_not_fallback_missing_bp():
    assert FallbackPolicy().should_fallback(FailureGrade.BLUEPRINT_MISSING) is False

def test_classify_timeout():
    assert FallbackPolicy().classify_error("timeout") == FailureGrade.TIMEOUT

def test_classify_unavailable():
    assert FallbackPolicy().classify_error("connection refused") == FailureGrade.UNAVAILABLE

def test_classify_missing_bp():
    assert FallbackPolicy().classify_error("missing_blueprint") == FailureGrade.BLUEPRINT_MISSING

# ---- LOCAL_ONLY ----

def test_local_success():
    o = CompileOrchestrator(local_compiler=MockLocal())
    r = o.compile("a cat", mode=CompileMode.LOCAL_ONLY)
    assert r.success, "local success"
    assert r.source == "local"
    assert r.fallback_used is False

def test_local_missing_bp():
    o = CompileOrchestrator(local_compiler=MockLocal(missing=True))
    r = o.compile("video", mode=CompileMode.LOCAL_ONLY)
    assert r.success is False
    assert r.error_type == "missing_blueprint"

# ---- MCP_ONLY ----

def test_mcp_only_unavailable():
    o = CompileOrchestrator(local_compiler=MockLocal(), mcp_client=MCPClient(endpoint=""))
    r = o.compile("a cat", mode=CompileMode.MCP_ONLY)
    assert r.success is False
    assert r.source == "mcp"
    assert r.error_type == "mcp_unavailable"

# ---- MCP_FIRST ----

def test_mcp_first_wins():
    mcp = MagicMock(spec=MCPClient)
    mcp.compile.return_value = {"success": True, "workflow": {"1": {"class_type": "K"}}, "blueprint_used": "mcp_bp"}
    o = CompileOrchestrator(local_compiler=MockLocal(), mcp_client=mcp)
    r = o.compile("a cat", mode=CompileMode.MCP_FIRST)
    assert r.success is True
    assert r.source == "mcp"
    assert r.fallback_used is False

def test_mcp_unavailable_fallback():
    mcp = MagicMock(spec=MCPClient)
    mcp.compile.side_effect = MCPUnavailableError("unavailable")
    o = CompileOrchestrator(local_compiler=MockLocal(), mcp_client=mcp)
    r = o.compile("a cat", mode=CompileMode.MCP_FIRST)
    assert r.success is True
    assert r.source == "local"
    assert r.fallback_used is True
    assert len(r.warnings) > 0

def test_mcp_timeout_fallback():
    mcp = MagicMock(spec=MCPClient)
    mcp.compile.side_effect = MCPTimeoutError("timeout 10s")
    o = CompileOrchestrator(local_compiler=MockLocal(), mcp_client=mcp)
    r = o.compile("a cat", mode=CompileMode.MCP_FIRST)
    assert r.success is True
    assert r.source == "local"
    assert r.fallback_used is True

def test_mcp_invalid_workflow_fallback():
    mcp = MagicMock(spec=MCPClient)
    mcp.compile.side_effect = MCPInvalidWorkflowError("missing class_type")
    o = CompileOrchestrator(local_compiler=MockLocal(), mcp_client=mcp)
    r = o.compile("a cat", mode=CompileMode.MCP_FIRST)
    assert r.success is True
    assert r.source == "local"
    assert r.fallback_used is True

def test_mcp_both_fail():
    mcp = MagicMock(spec=MCPClient)
    mcp.compile.side_effect = MCPUnavailableError("unavailable")
    o = CompileOrchestrator(local_compiler=MockLocal(success=False), mcp_client=mcp)
    r = o.compile("a cat", mode=CompileMode.MCP_FIRST)
    assert r.success is False
    assert r.source == "local"
    assert r.fallback_used is True

# ---- Legacy conversion ----

def test_legacy_conversion():
    from comfyflow_compiler.orchestrator.result import to_legacy_result
    orcr = CompileResult(success=True, task_type="txt2img",
                         workflow={"1": {"class_type": "K"}},
                         blueprint_used="test_bp")
    legacy = to_legacy_result(orcr, hardware_used="GPU")
    assert legacy.success is True
    assert legacy.blueprint_used == "test_bp"
