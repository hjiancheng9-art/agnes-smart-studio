"""ComfyUI 错误恢复工具 — CWIM 原则 5 的执行入口

注入到 COMFYUI_PIPELINE_EXECUTOR_MAP 中。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def execute_recover_workflow(
    workflow_json: str,
    validation_report: str = "[]",
    **kwargs,
) -> str:
    """CWIM D-step: 对校验失败的 workflow 执行自动恢复。

    1. 分析 Validator 报告
    2. 生成 RecoveryPlan
    3. 执行修复补丁
    4. 记录到 ErrorKnowledgeBase
    """
    from core.comfyui_recovery import (
        ErrorKnowledgeBase,
        ErrorRecord,
        auto_recover,
    )
    from core.comfyui_validator import validate_workflow

    try:
        workflow = json.loads(workflow_json)
    except json.JSONDecodeError:
        return json.dumps({"success": False, "error": "Invalid workflow JSON"}, ensure_ascii=False)

    try:
        report_errors = json.loads(validation_report) if validation_report != "[]" else []
    except json.JSONDecodeError:
        report_errors = []

    # If no report provided, run validator first
    if not report_errors:
        validation = validate_workflow(workflow)
        report_errors = []
        for issue in validation.issues:
            if issue.level == "error":
                report_errors.append(
                    {
                        "layer": issue.layer,
                        "message": issue.message,
                        "node_id": issue.node_id,
                        "fix_hint": issue.fix_hint,
                    }
                )

    # Convert to ErrorRecords
    errors = [
        ErrorRecord(
            layer=e.get("layer", "L5"),
            message=e.get("message", "Unknown error"),
            node_id=e.get("node_id"),
            fix_hint=e.get("fix_hint"),
        )
        for e in report_errors
    ]

    if not errors:
        return json.dumps(
            {
                "success": True,
                "needs_recovery": False,
                "message": "无需恢复 — 无错误",
            },
            ensure_ascii=False,
        )

    # Auto-recover
    result = auto_recover(workflow, errors)

    # Record to knowledge base
    kb = ErrorKnowledgeBase()
    for decision in result.plan.decisions:
        kb.record(
            error_code=decision.error.error_code or f"{decision.error.layer}_UNKNOWN",
            error_pattern=decision.error.message[:200],
            layer=decision.error.layer,
            fix_applied=decision.repair or decision.fallback or "none",
            success=result.success,
            source_workflow=json.dumps({"node_count": len(workflow)}),
        )

    return json.dumps(
        {
            "success": result.success,
            "needs_recovery": True,
            "patches_applied": len(result.applied_patches),
            "total_errors": len(errors),
            "auto_fixable": sum(1 for d in result.plan.decisions if d.can_auto_fix),
            "summary": result.plan.summary,
            "audit": result.audit_log,
            "patches": [
                {"action": p.action, "target": p.target, "description": p.description} for p in result.applied_patches
            ],
            "recovered_workflow": workflow,  # may have been modified
        },
        ensure_ascii=False,
    )


def execute_error_kb_query(
    error_code: str = "",
    **kwargs,
) -> str:
    """查询错误知识库，获取相似错误的修复方案。"""
    from core.comfyui_recovery import ErrorKnowledgeBase

    kb = ErrorKnowledgeBase()
    if error_code:
        similar = kb.find_similar(error_code)
    else:
        similar = []

    stats = kb.get_stats()

    return json.dumps(
        {
            "success": True,
            "stats": stats,
            "matched_fixes": similar,
        },
        ensure_ascii=False,
    )
