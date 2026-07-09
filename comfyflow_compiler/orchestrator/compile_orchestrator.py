"""Compile Orchestrator — MCP 优先编译，失败自动降级本地"""

from __future__ import annotations

from typing import Any, Optional

from .result import CompileResult, CompileMode
from .mcp_client import MCPClient, MCPUnavailableError, MCPTimeoutError, MCPInvalidWorkflowError
from .fallback_policy import FallbackPolicy


class CompileOrchestrator:
    """编译编排器 — MCP_FIRST / LOCAL_ONLY / MCP_ONLY"""

    def __init__(
        self,
        local_compiler: Any,
        mcp_client: Optional[MCPClient] = None,
        policy: Optional[FallbackPolicy] = None,
    ):
        """
        Args:
            local_compiler: 本地编译器实例（须有 compile 方法返回 CompileResult-like）
            mcp_client: MCP 客户端（None 时自动从环境变量配置）
            policy: 降级策略
        """
        self.local = local_compiler
        self.mcp = mcp_client or MCPClient()
        self.policy = policy or FallbackPolicy()

    def compile(
        self,
        prompt: str,
        *,
        mode: CompileMode = CompileMode.MCP_FIRST,
        task_type: str = "",
        style: list[str] | None = None,
        **kwargs,
    ) -> CompileResult:
        """编译入口

        Args:
            prompt: 用户输入
            mode: 编译模式
            task_type: （可选）预识别的任务类型
            style: （可选）风格
            **kwargs: 传递给编译器的额外参数

        Returns:
            CompileResult
        """
        if mode == CompileMode.LOCAL_ONLY:
            return self._compile_local(prompt, task_type, style, **kwargs)

        if mode == CompileMode.MCP_ONLY:
            return self._compile_mcp(prompt, task_type, style, **kwargs)

        # MCP_FIRST: 优先 MCP，失败降级
        return self._compile_mcp_with_fallback(prompt, task_type, style, **kwargs)

    def _compile_mcp(self, prompt: str, task_type: str = "",
                     style: list[str] | None = None,
                     **kwargs) -> CompileResult:
        """仅 MCP 编译"""
        try:
            mcp_result = self.mcp.compile(prompt, task_type, style, **kwargs)
        except MCPTimeoutError as e:
            return CompileResult(
                success=False,
                task_type=task_type,
                error=str(e),
                error_type="mcp_timeout",
                source="mcp",
                mode="mcp_only",
            )
        except MCPUnavailableError as e:
            return CompileResult(
                success=False,
                task_type=task_type,
                error=str(e),
                error_type="mcp_unavailable",
                source="mcp",
                mode="mcp_only",
            )
        except MCPInvalidWorkflowError as e:
            return CompileResult(
                success=False,
                task_type=task_type,
                error=str(e),
                error_type="mcp_invalid",
                source="mcp",
                mode="mcp_only",
            )
        except Exception as e:
            return CompileResult(
                success=False,
                task_type=task_type,
                error=str(e),
                error_type="mcp_unavailable",
                source="mcp",
                mode="mcp_only",
            )

        success = mcp_result.get("success", True)
        workflow = mcp_result.get("workflow", mcp_result)
        blueprint = mcp_result.get("blueprint_used", "")

        return CompileResult(
            success=bool(success),
            task_type=task_type,
            workflow=workflow if success else None,
            blueprint_used=blueprint,
            error=mcp_result.get("error") if not success else None,
            source="mcp",
            mode="mcp_only",
            error_type=None if success else "mcp_error",
        )

    def _compile_local(self, prompt: str, task_type: str = "",
                       style: list[str] | None = None,
                       **kwargs) -> CompileResult:
        """仅本地编译"""
        local_result = self.local.compile(prompt, **kwargs)

        cr = CompileResult(
            success=local_result.success,
            task_type=task_type,
            blueprint_used=local_result.blueprint_used,
            error=local_result.error,
            source="local",
            mode="local_only",
        )

        if local_result.success and local_result.workflow_json:
            cr.workflow = local_result.workflow_json.get("prompt", local_result.workflow_json)

        # 标记 missing_blueprint
        if local_result.blueprint_used == "missing_blueprint":
            cr.error_type = "missing_blueprint"

        return cr

    def _compile_mcp_with_fallback(self, prompt: str, task_type: str = "",
                                    style: list[str] | None = None,
                                    **kwargs) -> CompileResult:
        """MCP 优先 + 失败自动降级本地"""
        # Step 1: 尝试 MCP
        mcp_result = self._compile_mcp(prompt, task_type, style, **kwargs)

        if mcp_result.success:
            return mcp_result

        # Step 2: 分类错误
        grade = self.policy.classify_error(mcp_result.error or "")
        fallback_reason = self.policy.format_fallback_reason(grade, mcp_result.error)

        # Step 3: 判断是否降级
        if not self.policy.should_fallback(grade):
            mcp_result.fallback_used = False
            mcp_result.fallback_reason = fallback_reason
            mcp_result.mode = "mcp_first"
            return mcp_result

        # Step 4: 降级到本地
        local_result = self._compile_local(prompt, task_type, style, **kwargs)

        # 包装本地结果
        local_result.source = "local"
        local_result.mode = "mcp_first"
        local_result.fallback_used = True
        local_result.fallback_reason = f"MCP 降级: {fallback_reason}"
        local_result.warnings.append(f"MCP 不可用，已降级到本地编译: {fallback_reason}")

        return local_result
