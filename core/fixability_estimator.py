"""Fixability Estimator — 三阶段可修复性评估链

基于 GPT 架构规格建议：
  L0: StaticSeedFilter   — 秒级，字符串匹配（已有 seed policy）
  L1: LightweightProbes  — 5-10s，探针读取系统状态
  L2: LLMAnalyzer        — 30-60s，LLM 兜底长尾

核心接口：
  - FixabilityProbe: 单个探针，can_handle() + estimate()
  - ProbeRegistry: 探针注册表，可插拔扩展
  - FixabilityEstimator: 三阶段编排器

用法：
from core.error_sink import catch
  from core.fixability_estimator import estimate_fixability

  result = estimate_fixability("self_heal", "CUDA out of memory", ctx)
  if result.score < 0.3:
      # 不可修复，降级为诊断
      ...
  elif result.score < 0.6:
      # 不确定，谨慎重试
      ...
  else:
      # 可以尝试修复
      ...
"""

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Literal

from core.error_sink import catch

# ── 数据结构 ──────────────────────────────────────────────

FixabilityAction = Literal["retry", "diagnose", "escalate", "abort"]
RepairClass = Literal["code", "config", "env", "resource", "dependency", "network", "unknown", "impossible"]


@dataclass
class FixabilityResult:
    """可修复性评估结果。"""

    score: float = 0.0  # 0.0 - 1.0 可修复概率
    confidence: float = 0.0  # 评估的置信度
    action_hint: FixabilityAction = "diagnose"
    repair_class_hint: RepairClass = "unknown"
    requires_context_probe: bool = False
    reasons: list[str] = field(default_factory=list)
    source: str = ""  # 哪个阶段给出的结论
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "confidence": self.confidence,
            "action_hint": self.action_hint,
            "repair_class_hint": self.repair_class_hint,
            "requires_context_probe": self.requires_context_probe,
            "reasons": self.reasons,
            "source": self.source,
        }


# ── L0: Static Seed Filter ────────────────────────────────


class StaticSeedFilter:
    """L0：秒级字符串匹配，封装已有 seed policy。"""

    def __init__(self):
        # Lazy import to avoid circular
        self._seed_policy = None

    @property
    def seed_policy(self):
        if self._seed_policy is None:
            from core.fake_fix_seed_policy import get_seed_policy

            self._seed_policy = get_seed_policy()
        return self._seed_policy

    def evaluate(self, tool: str, error_type: str, context: dict | None = None) -> FixabilityResult | None:
        """L0 评估。如果匹配到规则，直接返回裁决；不匹配则返回 None。"""
        decision = self.seed_policy.classify(tool, error_type, context or {})

        result = FixabilityResult(source="L0:StaticSeed")

        if decision.action == "quarantine":
            result.score = 0.0
            result.confidence = 0.95
            result.action_hint = "abort"
            result.repair_class_hint = "impossible"
            result.reasons = [decision.reason]
            return result

        if decision.action == "downgrade_to_diagnosis":
            result.score = 0.05
            result.confidence = 0.85
            result.action_hint = "diagnose"
            result.repair_class_hint = "resource"
            result.reasons = [decision.reason]
            return result

        if decision.action == "requires_user_action":
            result.score = 0.1
            result.confidence = 0.80
            result.action_hint = "escalate"
            result.repair_class_hint = "env"
            result.reasons = [decision.reason]
            return result

        if decision.action == "limited_retry":
            result.score = 0.5
            result.confidence = 0.60
            result.action_hint = "retry"
            result.repair_class_hint = "code"
            result.reasons = [decision.reason]
            return result

        if decision.action == "allow_retry":
            # 种子策略放行，交给 L1 判断
            return None

        # 未知规则
        result.score = 0.3
        result.confidence = 0.50
        result.action_hint = "diagnose"
        result.reasons = [f"seed policy: {decision.action}"]
        return result


# ── L1: Lightweight Probes ────────────────────────────────


class FixabilityProbe:
    """L1 探针基类 — 每种常见错误类型一个探针。"""

    probe_name: str = ""
    probe_version: str = "1.0.0"

    def can_handle(self, error_type: str, context: dict) -> bool:
        """判断该探针是否能处理此错误。"""
        return False

    def estimate(self, error_type: str, context: dict) -> FixabilityResult:
        """评估可修复性，返回 0-1 score。"""
        return FixabilityResult(score=0.3, confidence=0.1, action_hint="diagnose", source=f"L1:{self.probe_name}")


class CUDAMemoryProbe(FixabilityProbe):
    """CUDA OOM 探针：检查显存使用和 batch_size。"""

    probe_name = "cuda-memory"

    def can_handle(self, error_type: str, context: dict) -> bool:
        return bool(
            "cuda" in error_type.lower() and ("oom" in error_type.lower() or "out of memory" in error_type.lower())
        )

    def estimate(self, error_type: str, context: dict) -> FixabilityResult:
        result = FixabilityResult(source="L1:cuda-memory")

        try:
            import torch

            batch_size = context.get("batch_size", 0)

            if torch.cuda.is_available():
                device = torch.cuda.current_device()
                total_mem = torch.cuda.get_device_properties(device).total_mem // (1024**2)
                allocated = torch.cuda.memory_allocated(device) // (1024**2)
                free = total_mem - allocated

                result.details = {"total_mem_mb": total_mem, "allocated_mb": allocated, "free_mb": free}

                if batch_size and batch_size > 1:
                    # 有可调参数 → 可能可修复
                    if free > total_mem * 0.1:  # 至少 10% 显存可用
                        result.score = 0.7
                        result.confidence = 0.75
                        result.action_hint = "retry"
                        result.repair_class_hint = "config"
                        result.reasons = [f"batch_size={batch_size} 可缩小, {free}MB 空闲显存"]
                    else:
                        result.score = 0.4
                        result.confidence = 0.65
                        result.action_hint = "diagnose"
                        result.repair_class_hint = "resource"
                        result.reasons = [f"显存严重不足, free={free}MB/{total_mem}MB, batch_size={batch_size}"]
                else:
                    result.score = 0.15
                    result.confidence = 0.80
                    result.action_hint = "diagnose"
                    result.repair_class_hint = "resource"
                    result.reasons = ["无 batch_size 可调，模型可能超出显存上限"]
            else:
                result.score = 0.5
                result.confidence = 0.3
                result.action_hint = "diagnose"
                result.repair_class_hint = "env"
                result.reasons = ["CUDA 不可用，可能是环境配置问题"]
        except ImportError:
            result.score = 0.3
            result.confidence = 0.3
            result.action_hint = "diagnose"
            result.repair_class_hint = "unknown"
            result.reasons = ["torch 未安装，无法评估显存"]

        return result


class ModuleImportProbe(FixabilityProbe):
    """ModuleNotFound 探针：检查包是否存在/版本。"""

    probe_name = "module-import"

    def can_handle(self, error_type: str, context: dict) -> bool:
        return bool("modulenotfound" in error_type.lower() or "no module named" in error_type.lower())

    def estimate(self, error_type: str, context: dict) -> FixabilityResult:
        result = FixabilityResult(source="L1:module-import")

        # Extract module name from error
        import re

        match = re.search(r"['\"](\S+)['\"]", error_type)
        module_name = match.group(1) if match else ""

        try:
            import subprocess

            r = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=columns"], capture_output=True, text=True, timeout=5
            )
            installed = r.stdout.lower()

            if module_name and module_name.lower() in installed:
                result.score = 0.5
                result.confidence = 0.6
                result.action_hint = "retry"
                result.repair_class_hint = "config"
                result.reasons = [f"{module_name} 已安装但 import 失败，可能是路径/版本问题"]
            else:
                result.score = 0.4
                result.confidence = 0.7
                result.action_hint = "escalate"
                result.repair_class_hint = "dependency"
                result.reasons = [f"{module_name} 未安装，需要 pip install"]
        except Exception:
            result.score = 0.3
            result.confidence = 0.4
            result.action_hint = "diagnose"
            result.reasons = ["无法查询 pip list"]

        result.requires_context_probe = True
        result.details = {"module": module_name}
        return result


class HTTPStatusProbe(FixabilityProbe):
    """HTTP 错误探针：检查 404/500/超时。"""

    probe_name = "http-status"

    def can_handle(self, error_type: str, context: dict) -> bool:
        return bool(any(k in error_type.lower() for k in ["404", "500", "502", "503", "timeout", "timed out"]))

    def estimate(self, error_type: str, context: dict) -> FixabilityResult:
        result = FixabilityResult(source="L1:http-status")

        url = context.get("url", "")
        has_variables = "{" in url or "<" in url or "{{" in url

        if "404" in error_type:
            if has_variables:
                result.score = 0.6
                result.confidence = 0.65
                result.action_hint = "retry"
                result.repair_class_hint = "config"
                result.reasons = ["URL 含模板变量，可能是参数错误"]
            else:
                result.score = 0.1
                result.confidence = 0.75
                result.action_hint = "abort"
                result.repair_class_hint = "env"
                result.reasons = ["URL 是常量，404 意味着资源不存在，不可修复"]
        elif "503" in error_type:
            result.score = 0.7
            result.confidence = 0.55
            result.action_hint = "retry"
            result.repair_class_hint = "network"
            result.reasons = ["503 通常是临时故障，重试可能恢复"]
        else:
            result.score = 0.4
            result.confidence = 0.4
            result.action_hint = "diagnose"
            result.repair_class_hint = "network"
            result.reasons = ["网络/超时错误，不确定是否可修复"]

        result.details = {"url": url[:200], "has_variables": has_variables}
        return result


class SyntaxErrorProbe(FixabilityProbe):
    """语法错误探针：检查能否通过 patch 修复。"""

    probe_name = "syntax-error"

    def can_handle(self, error_type: str, context: dict) -> bool:
        return bool(any(k in error_type.lower() for k in ["syntaxerror", "indentationerror", "taberror"]))

    def estimate(self, error_type: str, context: dict) -> FixabilityResult:
        result = FixabilityResult(source="L1:syntax-error")
        result.score = 0.75
        result.confidence = 0.70
        result.action_hint = "retry"
        result.repair_class_hint = "code"
        result.reasons = ["语法错误通常可以通过代码补丁修复"]
        return result


class Registry:
    """探针注册表。"""

    def __init__(self):
        self._probes: list[FixabilityProbe] = []

    def register(self, probe: FixabilityProbe) -> None:
        self._probes.append(probe)

    def all(self) -> list[FixabilityProbe]:
        return list(self._probes)

    def find(self, error_type: str, context: dict) -> FixabilityProbe | None:
        for probe in self._probes:
            if probe.can_handle(error_type, context):
                return probe
        return None


# ── 全局探针注册 ──────────────────────────────────────────
_PROBE_REGISTRY = Registry()
for probe_class in [CUDAMemoryProbe, ModuleImportProbe, HTTPStatusProbe, SyntaxErrorProbe]:
    _PROBE_REGISTRY.register(probe_class())


def get_probe_registry() -> Registry:
    return _PROBE_REGISTRY


def register_probe(probe: FixabilityProbe) -> None:
    """外部注册自定义探针。"""
    _PROBE_REGISTRY.register(probe)


# ── L2: LLM Analyzer ──────────────────────────────────────

LLM_FIXABILITY_PROMPT = """You are a fixability analyst for an autonomous agent system.

Given the following error, determine whether this error CAN be fixed by code/configuration changes,
or if it requires human intervention (environment setup, resource allocation, external service).

Error type: {error_type}
Tool: {tool}
Context: {context}
System state: {system_state}

Analyze and return a JSON response with:
- score: 0.0-1.0 probability that this can be fixed automatically
- confidence: 0.0-1.0 your confidence in this assessment
- action_hint: "retry" | "diagnose" | "escalate" | "abort"
- repair_class: "code" | "config" | "env" | "resource" | "dependency" | "network" | "unknown" | "impossible"
- reasons: list of strings explaining your reasoning

Rules:
- "resource" errors (OOM, disk full) usually CANNOT be fixed by code → score < 0.2
- "dependency" errors (ModuleNotFound, missing .so) CAN be fixed by pip/apt → score 0.3-0.6
- "code" errors (SyntaxError, TypeError) CAN be fixed by patches → score 0.7-0.9
- "network" errors (timeout, DNS) are transient → score 0.5-0.7
- "config" errors (wrong path, missing env var) CAN be fixed → score 0.6-0.8

Return ONLY valid JSON, no markdown."""


class LLMAnalyzer:
    """L2: LLM 深度分析。用于 L0+L1 都无法给出高置信度结论的场景。"""

    def __init__(self, max_tokens: int = 500):
        self.max_tokens = max_tokens
        self._prompt_template = LLM_FIXABILITY_PROMPT

    def evaluate(self, tool: str, error_type: str, context: dict | None = None) -> FixabilityResult:
        """LLM 分析（需要外部 LLM 调用支持）。"""
        ctx = context or {}

        # 收集系统状态
        system_state = {}
        try:
            system_state["python_version"] = sys.version[:30]
            system_state["platform"] = sys.platform
        except Exception as _es:
            catch(_es, "core.fixability_estimator", "swallowed")
        try:
            import torch

            system_state["torch_version"] = torch.__version__
            system_state["cuda_available"] = torch.cuda.is_available()
        except ImportError:
            pass
        try:
            import os
            import shutil

            _, _, free = shutil.disk_usage(os.getcwd())
            system_state["free_disk_mb"] = free // (1024 * 1024)
        except Exception as _es:
            catch(_es, "core.fixability_estimator", "swallowed")

        prompt = self._prompt_template.format(
            error_type=error_type,
            tool=tool,
            context=json.dumps(ctx, default=str)[:500],
            system_state=json.dumps(system_state, default=str)[:500],
        )

        # 标记需要 LLM 调用（实际调用由外部完成）
        return FixabilityResult(
            score=0.3,
            confidence=0.2,
            action_hint="diagnose",
            repair_class_hint="unknown",
            reasons=["LLM analysis pending"],
            source="L2:LLM",
            details={"prompt": prompt, "pending": True},
        )


# ── 三阶段编排器 ──────────────────────────────────────────


class FixabilityEstimator:
    """三阶段可修复性评估编排器。

    流程：
      L0 (StaticSeed) → 匹配 → 直接返回
      ↓ 不匹配
      L1 (Probes) → 有匹配且置信度 >= 0.6 → 返回
      ↓ 不匹配或置信度低
      L2 (LLM) → 兜底
    """

    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self):
        self.l0 = StaticSeedFilter()
        self.l1_registry = get_probe_registry()
        self.l2 = LLMAnalyzer()

    def estimate(self, tool: str, error_type: str, context: dict | None = None) -> FixabilityResult:
        """评估错误的可修复性。"""
        ctx = context or {}

        # ── L0: Static Seed Filter ──
        l0_result = self.l0.evaluate(tool, error_type, ctx)
        if l0_result is not None:
            return l0_result

        # ── L1: Lightweight Probes ──
        probe = self.l1_registry.find(error_type, ctx)
        if probe:
            l1_result = probe.estimate(error_type, ctx)
            if l1_result.confidence >= self.CONFIDENCE_THRESHOLD:
                return l1_result
            # 置信度不够，进入 L2 但保留 L1 信息
            l1_result.requires_context_probe = True
            l1_result.source += " (low confidence, escalate to L2)"
            return l1_result

        # ── L2: LLM Analysis ──
        l2_result = self.l2.evaluate(tool, error_type, ctx)
        l2_result.source = "L2:LLM(fallback)"
        return l2_result

    def should_attempt_fix(
        self, tool: str, error_type: str, context: dict | None = None
    ) -> tuple[bool, FixabilityResult]:
        """简便方法：是否应该尝试修复？"""
        result = self.estimate(tool, error_type, context)
        can_fix = result.score >= 0.5 and result.action_hint in ("retry", "diagnose")
        return can_fix, result


# ── 全局实例 ──────────────────────────────────────────────
_estimator: FixabilityEstimator | None = None


def get_estimator() -> FixabilityEstimator:
    global _estimator
    if _estimator is None:
        _estimator = FixabilityEstimator()
    return _estimator


def estimate_fixability(tool: str, error_type: str, context: dict | None = None) -> FixabilityResult:
    """快捷函数：评估错误的可修复性。"""
    return get_estimator().estimate(tool, error_type, context)
