"""
Adaptive Learner — CRUX 自适应学习引擎
======================================
Phase 5 核心：让 CRUX 从每次任务中自动学习。

学习闭环:
1. 从 TraceStore 加载失败轨迹
2. 诊断失败类型和根因
3. 生成调参建议 (policy_patch)
4. 验证调参效果
5. 应用到 Router (信号权重/模式配置)

失败类型:
- route_mismatch: 路由模式选错了（期望 DEEP 给了 BALANCED）
- plan_incomplete: Plan 不完整或 PlanGate 未通过
- critic_missed: 审查漏掉了关键问题
- repair_failed: 修复步骤失败
- verify_failed: 验证步骤不通过
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from .intelligence_trace import TraceStore, get_trace_store
from .learning_store import LearningRecord, LearningStore, LearningSummary
from .routing_signals import SIGNAL_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class FailureDiagnosis:
    """失败诊断结果"""

    episode_id: str = ""
    trace_run_id: str = ""
    failure_type: str = ""
    severity: str = "medium"
    root_cause: str = ""
    diagnosis: str = ""
    policy_patch: dict[str, Any] | None = None
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "diagnosis": self.diagnosis[:200],
            "policy_patch": self.policy_patch,
            "confidence": self.confidence,
        }


class FailureAnalyzer:
    """失败分析器 — 诊断失败类型和根因"""

    # ── 路由混淆模式 ──
    ROUTE_CONFUSION_PATTERNS: dict[str, list[str]] = {
        "DEEP_TO_BALANCED": [
            r"测试.*通过.*但",
            r"排查.*根因",
            r"间歇.*问题",
            r"复杂.*调试",
        ],
        "BALANCED_TO_DEEP": [
            r"重构.*函数|重构.*方法|重构.*变量|重构.*参数",
        ],
        "CREATIVE_MISMATCH": [
            r"设计.*方案|方案.*设计",
            r"架构.*设计",
            r"系统.*设计",
            r"机制",
        ],
    }

    def diagnose_from_trace(
        self, trace: dict[str, Any] | None, expected_mode: str | None = None
    ) -> FailureDiagnosis | None:
        """从轨迹诊断失败"""
        if not trace:
            return None

        diagnosis = FailureDiagnosis(
            trace_run_id=trace.get("run_id", ""),
        )

        actual_mode = trace.get("mode", "")
        _status = trace.get("status", "")
        steps = trace.get("steps", [])
        request = trace.get("user_request", "").lower()

        # ── 1. 路由不匹配 ──
        if expected_mode and actual_mode != expected_mode:
            diagnosis.failure_type = "route_mismatch"
            diagnosis.severity = "high"
            diagnosis.root_cause = f"路由 {actual_mode} 但期望 {expected_mode}"
            diagnosis.diagnosis = f"请求应走 {expected_mode} 模式，实际走了 {actual_mode}"

            # 具体诊断子类型
            if expected_mode == "DEEP" and actual_mode == "BALANCED":
                for name, patterns in self.ROUTE_CONFUSION_PATTERNS.items():
                    for p in patterns:
                        if re.search(p, request):
                            diagnosis.diagnosis += f"。信号模式: {name}"
                            diagnosis.confidence = 0.7
                            break
            elif expected_mode == "BALANCED" and actual_mode == "DEEP":
                diagnosis.diagnosis += "。过度路由，小范围重构不应走 DEEP"
                diagnosis.confidence = 0.6

            # 信号权重调整建议
            diagnosis.policy_patch = {
                "type": "signal_weight_adjust",
                "target_signals": self._suggest_signal_adjustments(actual_mode, expected_mode, request),
                "suggestion": f"降低过度路由倾向，提高 {expected_mode} 在类似请求上的得分",
            }

            return diagnosis

        # ── 2. Plan 问题 ──
        plan_steps = [s for s in steps if "plan" in s.get("name", "")]
        if plan_steps and any(s.get("status") == "failed" for s in plan_steps):
            diagnosis.failure_type = "plan_incomplete"
            diagnosis.severity = "high"
            diagnosis.root_cause = "Plan 步骤失败"
            diagnosis.diagnosis = "Plan 阶段未能生成有效计划，可能是 PlanGate 未通过"
            diagnosis.policy_patch = {
                "type": "plan_config_tune",
                "suggestion": "增加 max_rounds 或放宽 PlanGate 阈值",
            }
            diagnosis.confidence = 0.6
            return diagnosis

        # ── 3. 审查遗漏 ──
        critic_steps = [s for s in steps if "critic" in s.get("name", "")]
        failed_critic = [s for s in critic_steps if s.get("status") == "failed"]
        if failed_critic:
            diagnosis.failure_type = "critic_missed"
            diagnosis.severity = critic_steps[0].get("output_summary", "").count("critical") > 0 and "high" or "medium"
            diagnosis.root_cause = "审查发现了阻塞性问题"
            diagnosis.diagnosis = "CriticAgent 发现了必须修复的问题"
            diagnosis.confidence = 0.8
            return diagnosis

        # ── 4. 修复失败 ──
        repair_steps = [s for s in steps if "repair" in s.get("name", "")]
        if repair_steps and any(s.get("status") == "failed" for s in repair_steps):
            diagnosis.failure_type = "repair_failed"
            diagnosis.severity = "high"
            diagnosis.root_cause = "修复步骤执行失败"
            diagnosis.policy_patch = {
                "type": "repair_retry",
                "suggestion": "增加修复重试次数或使用更强修复策略",
            }
            diagnosis.confidence = 0.7
            return diagnosis

        # ── 5. 验证失败 ──
        verify_steps = [s for s in steps if "verify" in s.get("name", "")]
        if verify_steps and any(s.get("status") == "failed" for s in verify_steps):
            diagnosis.failure_type = "verify_failed"
            diagnosis.severity = "medium"
            diagnosis.root_cause = "验证步骤未通过"
            diagnosis.policy_patch = {
                "type": "verify_threshold_tune",
                "suggestion": "降低验证阈值或增加验证轮次",
            }
            diagnosis.confidence = 0.5
            return diagnosis

        return None

    def _suggest_signal_adjustments(self, actual: str, expected: str, request: str) -> list[dict[str, Any]]:
        """建议信号权重调整"""
        suggestions: list[dict[str, Any]] = []

        if expected == "DEEP" and actual == "BALANCED":
            # 应该走 DEEP 但走了 BALANCED → 提高 DEEP 相关信号权重
            suggestions.append(
                {
                    "signal": "has_multi_step",
                    "action": "increase",
                    "delta": 0.5,
                    "reason": f"请求 '{request[:40]}...' 含多步骤但未触发 DEEP",
                }
            )
            suggestions.append(
                {
                    "signal": "has_debug_symptom",
                    "action": "increase",
                    "delta": 0.3,
                    "reason": "调试类请求应更容易触发 DEEP",
                }
            )

        elif expected == "BALANCED" and actual == "DEEP":
            # 应该走 BALANCED 但走了 DEEP → 降低过度路由
            suggestions.append(
                {
                    "signal": "is_architecture",
                    "action": "decrease_for_small_scope",
                    "delta": 0.3,
                    "reason": "函数级重构不应触发 DEEP",
                }
            )

        return suggestions


class PolicyAdapter:
    """策略适配器 — 将学习结果应用到路由"""

    def __init__(self, router: Any = None):
        self.router = router
        self._pending_patches: list[dict[str, Any]] = []

    def apply_patch(self, patch: dict[str, Any] | None) -> bool:
        """应用调参建议"""
        if not patch:
            return False

        patch_type = patch.get("type", "")

        if patch_type == "signal_weight_adjust":
            return self._apply_signal_adjustments(patch.get("target_signals", []))

        elif patch_type == "plan_config_tune":
            return self._apply_plan_tune(patch)

        elif patch_type == "repair_retry":
            return self._apply_repair_retry(patch)

        return False

    def _apply_signal_adjustments(self, adjustments: list[dict[str, Any]]) -> bool:
        """调整信号权重"""
        applied = False
        for adj in adjustments:
            signal_name = adj.get("signal", "")
            action = adj.get("action", "")
            delta = adj.get("delta", 0.0)

            for entry in SIGNAL_REGISTRY:
                if entry.name == signal_name:
                    if action == "increase":
                        entry.weight += delta
                        applied = True
                        logger.info(f"Adaptive: 增加信号 '{signal_name}' 权重 {delta} → {entry.weight}")
                    elif action == "decrease_for_small_scope":
                        entry.weight = max(1.0, entry.weight - delta)
                        applied = True
                        logger.info(f"Adaptive: 降低信号 '{signal_name}' 权重 {delta} → {entry.weight}")
                    break

        return applied

    def _apply_plan_tune(self, patch: dict[str, Any]) -> bool:
        """调整 Plan 配置"""
        # 记录待处理补丁（DeliberateWorkflow 启动时读取）
        self._pending_patches.append(patch)
        logger.info(f"Adaptive: 记录 Plan 配置补丁: {patch.get('suggestion', '')}")
        return True

    def _apply_repair_retry(self, patch: dict[str, Any]) -> bool:
        """调整修复策略"""
        self._pending_patches.append(patch)
        logger.info(f"Adaptive: 记录修复策略补丁: {patch.get('suggestion', '')}")
        return True

    def get_pending_patches(self) -> list[dict[str, Any]]:
        patches = list(self._pending_patches)
        self._pending_patches.clear()
        return patches


class AdaptiveLearner:
    """自适应学习引擎 — 主控制器"""

    def __init__(
        self,
        trace_store: TraceStore | None = None,
        learning_store: LearningStore | None = None,
        analyzer: FailureAnalyzer | None = None,
        adapter: PolicyAdapter | None = None,
    ):
        self.trace_store = trace_store or get_trace_store()
        self.learning_store = learning_store or LearningStore()
        self.analyzer = analyzer or FailureAnalyzer()
        self.adapter = adapter or PolicyAdapter()
        self._learning_enabled = True

    @property
    def learning_enabled(self) -> bool:
        return self._learning_enabled

    def enable_learning(self) -> None:
        self._learning_enabled = True

    def disable_learning(self) -> None:
        self._learning_enabled = False

    # ── 核心学习循环 ──

    def learn_from_trace(self, trace: dict[str, Any], expected_mode: str | None = None) -> LearningRecord | None:
        """从单条轨迹学习"""
        if not self._learning_enabled:
            return None

        # 1. 诊断
        diagnosis = self.analyzer.diagnose_from_trace(trace, expected_mode)
        if not diagnosis:
            return None

        # 2. 生成学习记录
        record = LearningRecord(
            trace_run_id=diagnosis.trace_run_id,
            failure_type=diagnosis.failure_type,
            request=trace.get("user_request", ""),
            routed_mode=trace.get("mode", ""),
            expected_mode=expected_mode or "",
            diagnosis=diagnosis.diagnosis,
            severity=diagnosis.severity,
            root_cause=diagnosis.root_cause,
            policy_patch=diagnosis.policy_patch,
        )

        # 3. 存储
        self.learning_store.record(record)

        # 4. 自动应用高置信度补丁
        if diagnosis.confidence >= 0.7 and diagnosis.policy_patch:
            applied = self.adapter.apply_patch(diagnosis.policy_patch)
            if applied:
                self.learning_store.mark_applied(record.episode_id, effectiveness=0.5)

        return record

    def run_learning_cycle(self, limit: int = 20) -> list[LearningRecord]:
        """运行一次学习循环：分析最近失败轨迹 → 学习"""
        if not self._learning_enabled:
            return []

        # 1. 从 TraceStore 加载失败轨迹
        failed_traces = self.trace_store.query(status="fail", limit=limit)
        partial_traces = self.trace_store.query(status="partial", limit=limit)

        all_traces = failed_traces + partial_traces
        records: list[LearningRecord] = []

        for trace in all_traces:
            record = self.learn_from_trace(trace)
            if record:
                records.append(record)

        logger.info(f"Adaptive: 学习循环完成，处理 {len(all_traces)} 条轨迹，生成 {len(records)} 条学习记录")
        return records

    def get_summary(self) -> LearningSummary:
        """获取学习汇总"""
        return self.learning_store.get_summary()

    def get_pending_patches(self) -> list[dict[str, Any]]:
        """获取待应用的补丁"""
        return self.adapter.get_pending_patches()

    def clear(self) -> None:
        """清空学习记录"""
        self.learning_store.clear()
