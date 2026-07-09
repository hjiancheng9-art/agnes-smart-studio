"""Orchestrator — 统一编译结果契约"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CompileMode(str, Enum):
    """编译模式"""
    MCP_FIRST = "mcp_first"      # 默认：优先 MCP，失败降级本地
    LOCAL_ONLY = "local_only"    # 仅本地编译
    MCP_ONLY = "mcp_only"        # 仅 MCP 编译


@dataclass
class CompileResult:
    """统一编译结果 — MCP 和本地共用"""
    success: bool = False
    task_type: str = ""
    workflow: Optional[dict[str, Any]] = None
    blueprint_used: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # "mcp_timeout" | "mcp_unavailable" | "mcp_invalid" | "missing_blueprint" | "local_error"
    source: str = "local"            # "mcp" | "local"
    mode: str = "local_only"
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def to_legacy_result(orcr: CompileResult,
                     hardware_used: str = "",
                     estimated_vram: str = "",
                     user_summary: str = "") -> Any:
    """将 orchestrator CompileResult 转换为旧的 models.CompileResult（兼容旧接口）"""
    from comfyflow_compiler.models import CompileResult as LegacyResult
    from comfyflow_compiler.models import QualityReport

    return LegacyResult(
        success=orcr.success,
        workflow_json={"prompt": orcr.workflow} if orcr.workflow else None,
        quality_report=QualityReport(passed=orcr.success, overall_score=0.0) if orcr.success else None,
        blueprint_used=orcr.blueprint_used or "",
        hardware_used=hardware_used,
        estimated_vram=estimated_vram,
        user_summary=user_summary,
        user_result=None,
        error=orcr.error,
        fallback_chain_used=[orcr.fallback_reason] if orcr.fallback_reason else [],
    )
