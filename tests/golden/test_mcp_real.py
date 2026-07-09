"""MCP Client — 真实 HTTP 集成测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from comfyflow_compiler.orchestrator import (
    CompileOrchestrator, CompileMode, MCPClient, MCPUnavailableError, CompileRequest,
)


def _mk_local(success=True):
    from comfyflow_compiler.models import CompileResult as LR, QualityReport
    class M:
        def compile(self, prompt, **kw):
            if success:
                return LR(success=True, workflow_json={"prompt":{"1":{"class_type":"K"}}},
                          blueprint_used="local_bp", quality_report=QualityReport(passed=True, overall_score=0.8))
            return LR(success=False, blueprint_used="local_bp", error="本地失败")
    return M()


class TestMcpReal:
    def test_ok(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST",
            json={"success": True, "workflow": {"1": {"class_type": "K"}}, "blueprint_used": "mcp_bp"})
        mcp = MCPClient(endpoint=e, timeout=5)
        o = CompileOrchestrator(local_compiler=_mk_local(), mcp_client=mcp)
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert r.success and r.source == "mcp" and not r.fallback_used

    def test_timeout_local(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_exception(__import__("httpx").TimeoutException("t"), url=f"{e}/compile", method="POST")
        o = CompileOrchestrator(local_compiler=_mk_local(), mcp_client=MCPClient(endpoint=e, timeout=1, max_retries=0))
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert r.success and r.source == "local" and r.fallback_used

    def test_500_local(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST", status_code=500)
        o = CompileOrchestrator(local_compiler=_mk_local(), mcp_client=MCPClient(endpoint=e, timeout=5, max_retries=0))
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert r.success and r.source == "local" and r.fallback_used

    def test_invalid_local(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST", json={"success": True, "workflow": {"x": {}}})
        o = CompileOrchestrator(local_compiler=_mk_local(), mcp_client=MCPClient(endpoint=e, timeout=5, max_retries=0))
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert r.success and r.source == "local" and r.fallback_used

    def test_404_local(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST", status_code=404)
        o = CompileOrchestrator(local_compiler=_mk_local(), mcp_client=MCPClient(endpoint=e, timeout=5, max_retries=0))
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert r.success and r.source == "local" and r.fallback_used

    def test_both_fail(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST", status_code=502)
        o = CompileOrchestrator(local_compiler=_mk_local(success=False), mcp_client=MCPClient(endpoint=e, timeout=5, max_retries=0))
        r = o.compile("cat", mode=CompileMode.MCP_FIRST)
        assert not r.success and r.fallback_used

    def test_request_obj(self, httpx_mock):
        e = "http://mcp:8080"
        httpx_mock.add_response(url=f"{e}/compile", method="POST",
            json={"success": True, "workflow": {"1": {"class_type": "K"}}})
        mcp = MCPClient(endpoint=e, timeout=5)
        r = mcp.compile(CompileRequest(prompt="test", task_type="t2v"))
        assert r["success"] is True
