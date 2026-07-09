"""
Intelligence Hook — CRUX 智能路由集成层 (V2)
=============================================
V2 核心改进: 不破坏 send_stream 协议

设计:
1. analyze() 在 send_stream 之前调用，不 yield 任何内容
2. 分析结果存储在 self._intel_mode / self._intel_analysis
3. yield 只发生在调用方通过 get_status_yield() 主动请求时
4. 失败静默 fallback — 不阻塞原流程
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .intelligence_policy import (
    IntelligenceMode,
    IntelligencePolicyRouter,
)

logger = logging.getLogger(__name__)


class IntelligenceHook:
    """Intelligence 集成钩子 — V2 安全版"""

    def __init__(self) -> None:
        self.router = IntelligencePolicyRouter()
        self._enabled = True
        self._last_mode: IntelligenceMode | None = None
        self._last_summary: dict[str, Any] = {}
        self._last_error: str = ""

    @property
    def last_mode(self) -> IntelligenceMode | None:
        return self._last_mode

    @property
    def last_summary(self) -> dict[str, Any]:
        return self._last_summary

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    # ── V2 核心: analyze + store, 不 yield ──

    def analyze(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """V2: 分析请求并存储结果。不 yield。失败静默 fallback。"""
        if not self._enabled:
            return {"mode": IntelligenceMode.BALANCED.value, "pipeline": False}

        try:
            summary = self.router.summary(user_text, context)
            mode = summary["mode"]
            self._last_mode = IntelligenceMode(mode)
            self._last_summary = summary
            self._last_error = ""

            pipeline_modes = {"DEEP", "SAFE", "RESEARCH"}
            needs_pipeline = mode in pipeline_modes

            return {
                "mode": mode,
                "pipeline": needs_pipeline,
                "summary": summary,
                "profile": summary.get("profile", {}),
                "config": summary.get("config", {}),
                "signal_scores": summary.get("signal_scores", {}),
                "mode_hint": self._build_mode_hint(mode, summary.get("profile", {}), summary.get("config", {})),
            }
        except Exception as e:
            logger.warning(f"IntelligenceHook.analyze 失败 (fallback to BALANCED): {e}")
            self._last_error = str(e)
            self._last_mode = IntelligenceMode.BALANCED
            return {
                "mode": IntelligenceMode.BALANCED.value,
                "pipeline": False,
                "error": str(e),
            }

    def get_status_yield(self) -> list[tuple[str, str]]:
        """V2: 生成 yield 列表（由调用方决定是否 yield）"""
        if not self._enabled or not self._last_mode:
            return []

        yields: list[tuple[str, str]] = []
        mode = self._last_mode.value

        if mode in ("DEEP", "SAFE", "RESEARCH"):
            yields.append(("status", f"[Intelligence] 检测到复杂任务，启用 {mode} 模式"))
            if self._last_summary:
                yields.append(("intel_analysis", json.dumps(self._last_summary, ensure_ascii=False)))
        elif mode == "CREATIVE":
            yields.append(("status", "[Intelligence] 创意模式"))

        return yields

    # ── 模式提示 ──

    def _build_mode_hint(self, mode: str, profile: dict[str, Any], config: dict[str, Any]) -> str:
        icons = {
            "FAST": "⚡", "BALANCED": "⚖️", "DEEP": "🧠",
            "SAFE": "🛡️", "RESEARCH": "🔬", "CREATIVE": "🎨",
        }
        explanations = {
            "FAST": "快速回答（零开销）",
            "BALANCED": "标准推理",
            "DEEP": "深度推理: Plan → Attack → Criticize → Repair",
            "SAFE": "安全模式: 高风险操作",
            "RESEARCH": "研究模式: 多轮搜索",
            "CREATIVE": "创意模式",
        }
        icon = icons.get(mode, "❓")
        desc = explanations.get(mode, "")

        extras: list[str] = []
        if config.get("tests_required"):
            extras.append("需要测试")
        if config.get("critic"):
            extras.append("CriticAgent审查")
        if config.get("multi_agent"):
            extras.append("多Agent")
        if config.get("approval_required"):
            extras.append("需审批")

        extra_str = " · ".join(extras)
        sep = " | " if extra_str else ""
        return f"{icon} [{mode}] {desc}{sep}{extra_str}"

    # ── Pipeline 执行 ──

    async def execute_pipeline(self, user_text: str, context: dict[str, Any] | None = None,
                               toolbus: Any = None) -> dict[str, Any]:
        """执行 DEEP/SAFE/RESEARCH pipeline"""
        from .deliberate_workflow import DeliberateWorkflow

        workflow = DeliberateWorkflow(toolbus=toolbus, policy_router=self.router)
        mode = self.route_text(user_text)

        try:
            result = await workflow.execute(request=user_text, context=context, mode=mode)
            return result.to_dict()
        except Exception as e:
            logger.exception("Intelligence pipeline failed")
            return {
                "mode": mode.value if mode else "BALANCED",
                "passed": False,
                "summary": f"Pipeline 执行失败: {e}",
                "steps": [],
                "error": str(e),
            }

    def route_text(self, user_text: str) -> IntelligenceMode:
        if not self._enabled:
            return IntelligenceMode.BALANCED
        return self.router.route(user_text)

    def get_stats(self) -> dict[str, int]:
        return self.router.get_stats()

    def reset_stats(self) -> None:
        self.router._stats = {"total": 0}
