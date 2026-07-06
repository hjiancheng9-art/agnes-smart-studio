"""ComfyUI API 集成 — Compiler + Validator 的 API 入口 (CWIM 原则 3+4 的 C step)

将 Compiler 和 Validator 集成到 ComfyUI 工具的执行流程中：
- build_and_validate: TaskSpec → Compile → Validate → 可执行 workflow
- validate_existing: 对已有 workflow 执行 5 层校验
- safe_submit: 校验后安全提交到 ComfyUI

使用路径：
    from core.comfyui_api import build_and_validate, safe_submit
    result = build_and_validate(spec)
    if result.is_valid:
        prompt_id = safe_submit(result.workflow)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import logging
import json

from core.comfyui_compiler import (
    TaskSpec, WorkflowIR, GraphCompiler, CompiledWorkflow,
    build_txt2img_spec, compile_spec,
)
from core.comfyui_validator import (
    ComfyUIValidator, ValidationResult, validate_workflow,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 统一构建结果
# ═══════════════════════════════════════════════════════════════════

@dataclass
class BuildResult:
    """编译 + 校验的完整结果。"""
    success: bool
    workflow: dict | None = None
    compiled: CompiledWorkflow | None = None
    validation: ValidationResult | None = None
    error: str | None = None
    summary: str = ""

    @property
    def is_valid(self) -> bool:
        return self.success and self.validation is not None and self.validation.is_valid

    @property
    def error_count(self) -> int:
        if self.validation:
            return len(self.validation.errors)
        return 0

    @property
    def warning_count(self) -> int:
        if self.validation:
            return len(self.validation.warnings)
        return 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "error": self.error,
            "summary": self.summary,
            "node_count": len(self.workflow) if self.workflow else 0,
        }


# ═══════════════════════════════════════════════════════════════════
# 主要 API 函数
# ═══════════════════════════════════════════════════════════════════

def build_and_validate(spec: TaskSpec, node_ontology: dict | None = None,
                       model_inventory: dict | None = None) -> BuildResult:
    """TaskSpec → Compile → Validate 一条龙。

    即：原则 3 (Compiler) + 原则 4 (Validator) 的 API 集成。
    """
    try:
        # Step 1: Compile
        compiled = compile_spec(spec)
        if not compiled.is_valid:
            return BuildResult(
                success=False,
                compiled=compiled,
                error="编译失败",
                summary="; ".join(compiled.diagnostics[-3:]) if compiled.diagnostics else "未知编译错误",
            )

        # Step 2: Validate
        validation = validate_workflow(
            compiled.workflow,
            node_ontology=node_ontology,
            model_inventory=model_inventory,
        )

        # Step 3: Build summary
        parts = []
        parts.append(f"编译: {'✅' if compiled.is_valid else '❌'}")
        parts.append(f"节点: {len(compiled.workflow)}")
        parts.append(f"校验: {'✅' if validation.is_valid else '⚠️' if validation.errors else '✅'}")

        if validation.errors:
            error_msgs = [e.message for e in validation.errors[:3]]
            parts.append(f"错误: {'; '.join(error_msgs)}")
        if validation.warnings:
            warn_msgs = [w.message for w in validation.warnings[:3]]
            parts.append(f"警告: {'; '.join(warn_msgs)}")

        return BuildResult(
            success=True,
            workflow=compiled.workflow,
            compiled=compiled,
            validation=validation,
            summary=" | ".join(parts),
        )
    except Exception as e:
        logger.exception("build_and_validate failed")
        return BuildResult(success=False, error=str(e), summary=f"异常: {e}")


def validate_existing(workflow: dict, node_ontology: dict | None = None,
                      model_inventory: dict | None = None) -> ValidationResult:
    """对已有 workflow 执行校验（不经过 Compiler）。"""
    return validate_workflow(workflow, node_ontology, model_inventory)


def safe_submit(workflow: dict, node_ontology: dict | None = None,
                model_inventory: dict | None = None) -> dict:
    """校验 + 提交：先 Validate，通过后再提交到 ComfyUI。

    Returns:
        {"submitted": True/False, "prompt_id": ..., "validation": ...}
    """
    # First validate
    validation = validate_workflow(workflow, node_ontology, model_inventory)

    if validation.errors:
        return {
            "submitted": False,
            "reason": "validation_failed",
            "validation": {
                "is_valid": validation.is_valid,
                "errors": [{"message": e.message, "fix": e.fix_hint} for e in validation.errors],
                "warnings": [w.message for w in validation.warnings],
            },
        }

    # Try to submit
    try:
        from core.comfyui_tools import submit_comfyui_workflow
        result = submit_comfyui_workflow(workflow)
        return {
            "submitted": True,
            "prompt_id": result.get("prompt_id"),
            "validation": {"is_valid": True, "warnings": [w.message for w in validation.warnings]},
        }
    except Exception as e:
        return {
            "submitted": False,
            "reason": "submit_failed",
            "error": str(e),
            "validation": {"is_valid": True},
        }


def quick_txt2img(prompt: str, width: int = 1024, height: int = 1024,
                  model: str | None = None, loras: list[str] | None = None) -> BuildResult:
    """快速文生图：从 prompt 直达可执行的 validated workflow。

    这是最常用的入口。
    """
    spec = build_txt2img_spec(
        intent=prompt,
        prompt=prompt,
        width=width,
        height=height,
        model_preference=model,
        lora_refs=loras or [],
    )
    return build_and_validate(spec)


# ═══════════════════════════════════════════════════════════════════
# 工具描述注入 — Tool Contract (prep for Step A)
# ═══════════════════════════════════════════════════════════════════

COMPILER_TOOL_DESCRIPTION = """编译工具：将任务规格编译为可执行的 ComfyUI workflow。
遵循 CWIM 原则 3：TaskSpec → WorkflowIR → GraphCompiler → ComfyUI JSON。
返回编译产物 + 校验结果。"""

VALIDATOR_TOOL_DESCRIPTION = """校验工具：对 ComfyUI workflow 执行 5 层校验。
遵循 CWIM 原则 4：L1 JSON结构 → L2 Schema → L3 拓扑 → L4 资源 → L5 语义。
返回校验报告。"""
