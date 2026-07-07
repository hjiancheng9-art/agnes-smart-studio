"""ComfyUI 错误恢复系统 — CWIM 原则 5 实现 (D-step)

将 Validator 从"检查器"升级为 Executor 的"自愈反馈源"。

流程:
    Validator Report
        ↓
    RecoveryPlan (分层级恢复策略)
        ↓
    RepairPatch (确定性修复)
        ↓
    Retry (有限重试)
        ↓
    ErrorKnowledgeBase (学习)

参考: COMFYUI_METHODOLOGY.md 原则 5 (失败学习)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
from enum import Enum
import json
import logging
import sqlite3
import os
import time

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 错误分类
# ═══════════════════════════════════════════════════════════════════


class ErrorLayer(Enum):
    L1_JSON = "L1"  # JSON 结构 — 中止，不自愈
    L2_GRAPH = "L2"  # 图拓扑 — 高自动修复率
    L3_CONTRACT = "L3"  # 节点契约 — 中自动修复率
    L4_RESOURCE = "L4"  # 运行时资源 — 中自动修复率
    L5_SEMANTIC = "L5"  # 业务语义 — 仅通知

    @classmethod
    def from_str(cls, s: str) -> "ErrorLayer":
        for e in cls:
            if e.value == s:
                return e
        return cls.L5_SEMANTIC


class AutoFixLevel(Enum):
    ABORT = "abort"  # 不修复，直接反馈用户
    HIGH = "high"  # 规则化修复，高成功率
    MEDIUM = "medium"  # 可尝试修复，需验证
    CAUTIOUS = "cautious"  # 小心修复，依赖上下文


@dataclass
class ErrorRecord:
    """错误记录 — 来自 Validator 的单个问题。"""

    layer: str  # L1/L2/L3/L4/L5
    message: str  # 错误描述
    node_id: str | None = None
    fix_hint: str | None = None
    error_code: str | None = None  # 标准化错误码

    def __post_init__(self):
        if not self.error_code:
            # 从消息生成标准错误码
            code = self.message.replace(" ", "_").upper()[:40]
            self.error_code = f"{self.layer}_{code}"


@dataclass
class RecoveryDecision:
    """对单个错误的修复决策。"""

    error: ErrorRecord
    fix_level: AutoFixLevel
    strategy: str  # 修复策略描述
    can_auto_fix: bool = True
    repair: str | None = None  # 修复方法描述
    fallback: str | None = None  # 回退方案


# ═══════════════════════════════════════════════════════════════════
# RecoveryPlan — 分层级恢复策略
# ═══════════════════════════════════════════════════════════════════


@dataclass
class RepairPatch:
    """单个确定性修复补丁。"""

    action: str  # delete_node / add_node / reconnect / clamp_param / replace_model
    target: str  # node_id 或其他目标
    params: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class RecoveryPlan:
    """完整恢复计划 — 由 Validator 报告生成。"""

    can_recover: bool = False
    patches: list[RepairPatch] = field(default_factory=list)
    decisions: list[RecoveryDecision] = field(default_factory=list)
    max_retries: int = 3
    requires_user_input: bool = False
    summary: str = ""

    def add_patch(self, action: str, target: str, **params):
        self.patches.append(
            RepairPatch(action=action, target=target, params=params, description=f"{action} on {target}")
        )
        self.can_recover = True


@dataclass
class RecoveryResult:
    """恢复执行结果。"""

    success: bool
    plan: RecoveryPlan
    applied_patches: list[RepairPatch] = field(default_factory=list)
    retry_count: int = 0
    final_error: str | None = None
    audit_log: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# ErrorKnowledgeBase — SQLite 错误知识库
# ═══════════════════════════════════════════════════════════════════

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "comfyui_error_kb.sqlite")


class ErrorKnowledgeBase:
    """错误知识库 — CWIM 原则 5 的学习引擎。

    存储: error_pattern, fix_applied, success, source
    查询: 相同错误签名 → 复用修复
    """

    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_code TEXT NOT NULL,
                    error_pattern TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    fix_applied TEXT NOT NULL,
                    success INTEGER NOT NULL DEFAULT 1,
                    source_workflow TEXT,
                    created_at REAL NOT NULL,
                    retry_after_fix INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_error_pattern
                ON error_knowledge(error_code, success)
            """)
            conn.commit()

    def record(
        self,
        error_code: str,
        error_pattern: str,
        layer: str,
        fix_applied: str,
        success: bool,
        source_workflow: str | None = None,
    ):
        """记录一次错误修复。"""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO error_knowledge (error_code, error_pattern, layer, fix_applied, success, source_workflow, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    error_code,
                    error_pattern[:200],
                    layer,
                    fix_applied,
                    1 if success else 0,
                    source_workflow,
                    time.time(),
                ),
            )
            conn.commit()

    def find_similar(self, error_code: str, limit: int = 3) -> list[dict]:
        """查询相似错误的历史修复记录。"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT error_pattern, fix_applied, success, retry_after_fix, created_at "
                "FROM error_knowledge WHERE error_code = ? AND success = 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (error_code, limit),
            ).fetchall()
        return [{"pattern": r[0], "fix": r[1], "success": bool(r[2]), "retry_after": r[3]} for r in rows]

    def get_stats(self) -> dict:
        """获取知识库统计。"""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM error_knowledge").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM error_knowledge WHERE success = 1").fetchone()[0]
            layers = conn.execute("SELECT layer, COUNT(*) FROM error_knowledge GROUP BY layer").fetchall()
        return {
            "total": total,
            "success_rate": round(success / total * 100, 1) if total else 0,
            "by_layer": {l: c for l, c in layers},
        }


# ═══════════════════════════════════════════════════════════════════
# ExecutionRecovery — 执行恢复器
# ═══════════════════════════════════════════════════════════════════


class ExecutionRecovery:
    """执行恢复器 — 将 Validator 结果转化为修复计划并执行。"""

    def __init__(self, error_kb: ErrorKnowledgeBase | None = None):
        self._kb = error_kb or ErrorKnowledgeBase()

    def analyze(self, errors: list[ErrorRecord]) -> RecoveryPlan:
        """分析错误列表并生成恢复计划。"""
        plan = RecoveryPlan()
        decisions: list[RecoveryDecision] = []

        for err in errors:
            layer = ErrorLayer.from_str(err.layer)
            decision = self._decide_fix(err, layer)
            decisions.append(decision)

            if decision.can_auto_fix:
                self._apply_decision_to_plan(plan, decision)

        plan.decisions = decisions
        plan.can_recover = any(d.can_auto_fix for d in decisions)

        # Summary
        parts = []
        parts.append(f"{len(decisions)} 个错误")
        auto = sum(1 for d in decisions if d.can_auto_fix)
        parts.append(f"{auto} 个可自动修复")
        parts.append(f"{len(plan.patches)} 个补丁")
        plan.summary = " | ".join(parts)

        return plan

    def _decide_fix(self, err: ErrorRecord, layer: ErrorLayer) -> RecoveryDecision:
        """对单个错误决定修复策略。"""
        msg = err.message.lower()

        if layer == ErrorLayer.L1_JSON:
            return RecoveryDecision(
                error=err,
                fix_level=AutoFixLevel.ABORT,
                strategy="L1 结构错误，禁止自动修复",
                can_auto_fix=False,
                fallback="反馈用户：工作流结构异常，请检查 JSON 格式",
            )

        if layer == ErrorLayer.L2_GRAPH:
            if "孤立" in msg or "orphan" in msg or "无连接" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.HIGH,
                    strategy="删除孤立节点",
                    can_auto_fix=True,
                    repair=f"删除孤立节点 {err.node_id}",
                    fallback="跳过节点",
                )
            if "死端" in msg or "dead" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.HIGH,
                    strategy="删除死端节点或接入主链",
                    can_auto_fix=True,
                    repair=f"删除死端节点 {err.node_id}",
                )
            if "循环" in msg or "cycle" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.MEDIUM,
                    strategy="断开循环连接",
                    can_auto_fix=True,
                    repair="断开循环引用",
                )
            return RecoveryDecision(
                error=err,
                fix_level=AutoFixLevel.MEDIUM,
                strategy="检查图拓扑连接",
                can_auto_fix=True,
                repair="自动重连",
            )

        if layer == ErrorLayer.L3_CONTRACT:
            if "缺少必需输入" in msg or "missing" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.MEDIUM,
                    strategy="查找上游可兼容输出并连接",
                    can_auto_fix=True,
                    repair=f"为 {err.node_id} 补充缺少的输入",
                    fallback="使用默认值替代",
                )
            if "节点类型不在本体" in msg or "unknown" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.CAUTIOUS,
                    strategy="查 extension_map 或降级替换",
                    can_auto_fix=True,
                    repair=f"替换未知节点 {err.node_id}",
                    fallback="移除该节点",
                )
            return RecoveryDecision(
                error=err,
                fix_level=AutoFixLevel.MEDIUM,
                strategy="尝试参数范围修正",
                can_auto_fix=True,
                repair="clamp 参数到合法范围",
            )

        if layer == ErrorLayer.L4_RESOURCE:
            if "显存" in msg or "vram" in msg or "batch" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.HIGH,
                    strategy="降分辨率/减 batch_size",
                    can_auto_fix=True,
                    repair="降低 batch_size 到 1",
                    fallback="降低分辨率到 512x512",
                )
            if "模型" in msg or "model" in msg or "checkpoint" in msg:
                return RecoveryDecision(
                    error=err,
                    fix_level=AutoFixLevel.MEDIUM,
                    strategy="尝试替代模型",
                    can_auto_fix=True,
                    repair=f"查找 {err.node_id} 的替代模型",
                    fallback="提示用户安装缺失模型",
                )
            return RecoveryDecision(
                error=err,
                fix_level=AutoFixLevel.MEDIUM,
                strategy="检查资源约束",
                can_auto_fix=True,
                repair="调整资源配置",
            )

        # L5: 仅通知
        return RecoveryDecision(
            error=err,
            fix_level=AutoFixLevel.CAUTIOUS,
            strategy="语义问题，需用户确认",
            can_auto_fix=False,
            fallback="向用户展示语义检查结果",
        )

    def _apply_decision_to_plan(self, plan: RecoveryPlan, decision: RecoveryDecision):
        """将修复决策转化为补丁。"""
        err = decision.error
        if not err.node_id:
            return

        msg_lower = (err.message + (decision.repair or "")).lower()

        if "孤立" in msg_lower or "orphan" in msg_lower:
            plan.add_patch("delete_node", err.node_id)
        elif "死端" in msg_lower or "dead" in msg_lower:
            plan.add_patch("delete_node", err.node_id)
        elif "缺少必需输入" in msg_lower or "missing" in msg_lower:
            plan.add_patch("auto_connect", err.node_id, hint=err.fix_hint or "")
        elif "显存" in msg_lower or "vram" in msg_lower or "batch" in msg_lower:
            plan.add_patch("reduce_resources", err.node_id, target_batch=1)
        elif "模型" in msg_lower or "model" in msg_lower:
            plan.add_patch("swap_model", err.node_id)
        else:
            plan.add_patch("review", err.node_id, message=err.message)

    def execute(self, workflow: dict, plan: RecoveryPlan) -> RecoveryResult:
        """执行恢复计划（直接修改 workflow 原字典）。"""
        patches_applied: list[RepairPatch] = []
        audit: list[str] = []

        for patch in plan.patches:
            try:
                if patch.action == "delete_node":
                    if patch.target in workflow:
                        # 删除指向该节点的连接
                        for node in workflow.values():
                            for input_name, input_value in list(node.get("inputs", {}).items()):
                                if isinstance(input_value, list) and str(input_value[0]) == patch.target:
                                    del node["inputs"][input_name]
                        del workflow[patch.target]
                        patches_applied.append(patch)
                        audit.append(f"✓ 删除节点 {patch.target}")
                    else:
                        # 节点已被删除（幂等）
                        patches_applied.append(patch)
                        audit.append(f"✓ 节点 {patch.target} 已不存在（幂等）")

                elif patch.action == "reduce_resources":
                    if patch.target in workflow:
                        node = workflow[patch.target]
                        if "batch_size" in node.get("inputs", {}):
                            node["inputs"]["batch_size"] = patch.params.get("target_batch", 1)
                            patches_applied.append(patch)
                            audit.append(f"✓ 降低 {patch.target} batch_size → 1")

                else:
                    audit.append(f"  ? 跳过补丁: {patch.action} {patch.target}")

            except Exception as e:
                audit.append(f"✗ 补丁失败: {patch.action} {patch.target}: {e}")

        return RecoveryResult(
            success=len(patches_applied) > 0 or len(plan.patches) == 0,
            plan=plan,
            applied_patches=patches_applied,
            audit_log=audit,
        )


# 便捷函数
# ═══════════════════════════════════════════════════════════════════


def create_error_record(validation_issue: Any) -> ErrorRecord:
    """从 ValidationIssue 创建 ErrorRecord。"""
    return ErrorRecord(
        layer=validation_issue.layer,
        message=validation_issue.message,
        node_id=validation_issue.node_id,
        fix_hint=validation_issue.fix_hint,
    )


def auto_recover(
    workflow: dict, validation_errors: list[Any], error_kb: ErrorKnowledgeBase | None = None
) -> RecoveryResult:
    """一键自动恢复：分析 → 修复 → 返回结果。"""
    recovery = ExecutionRecovery(error_kb)
    errors = [create_error_record(e) for e in validation_errors]
    plan = recovery.analyze(errors)
    result = recovery.execute(workflow, plan)
    return result
