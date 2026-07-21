"""#2 反思步骤（self-critique span）—— 智能体质量增强。

每 N 次工具调用后，用辅助模型（默认 deepseek-v4-pro）做一次 critique：
分析最近 N 个 tool_name+args+result，判断计划是否在轨道、是否该换工具/换方向。

设计原则：
- **失败永远降级**: LLM 调用失败、配置关闭 → 静默返回 None，绝不阻塞主流程
- **可观测**: 所有路径走 TraceContext + metrics（沿用 ④ 任务契约）
- **唯一合法通道**: critique 文本通过 event.result 拼接返回给主模型
  （见 chat.py POST_TOOL_USE hook 的 result 改写）

挂接点: POST_TOOL_USE hook（core/hooks.py），priority=40（低于 syntax_guard=80、test_guard=60）。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


__all__ = ["CRITIQUE_PROMPT", "ReflectionEngine"]


# 反思 prompt：让辅助模型分析最近工具调用，给出方向性建议
CRITIQUE_PROMPT = """你是一个智能体反思助手。分析以下最近几次工具调用的记录，判断：

1. **计划是否在轨道**: 当前工具调用序列是否在有效推进用户目标？
2. **是否有更优工具选择**: 是否该换用其他工具或调整参数？
3. **是否陷入循环**: 是否在重复相同的失败调用？
4. **下一步建议**: 给出一句简短的方向性建议。

工具调用记录（error 标记的优先关注）:
{context}

请用 2-3 句话给出反思和建议（中文），聚焦"下一步该怎么做"。不要复述记录。
"""


class ReflectionEngine:
    """反思引擎：每 N 次工具调用触发一次 LLM critique。

    线程安全说明：单实例在 hook_manager.fire() 同步调用链中使用，
    无并发问题（POST_TOOL_USE hook 是同步串行的）。
    """

    def __init__(
        self,
        client: Any = None,
        model: str = "deepseek-v4-pro",
        interval: int = 5,
        enabled: bool = True,
        max_recent: int = 10,
    ) -> None:
        self._client = client
        self._model = model
        self._interval = max(1, interval)
        self._enabled = enabled
        self._max_recent = max(1, max_recent)
        self._counter = 0
        self._recent_calls: list[dict] = []  # {tool, args, result, error}

    def record_call(
        self,
        tool_name: str,
        args_summary: str,
        result_summary: str,
        is_error: bool = False,
    ) -> None:
        """记录一次工具调用（供下次 critique 分析）。"""
        entry = {
            "tool": tool_name,
            "args": args_summary[:200] if isinstance(args_summary, str) else str(args_summary)[:200],
            "result": result_summary[:300] if isinstance(result_summary, str) else str(result_summary)[:300],
            "error": bool(is_error),
        }
        self._recent_calls.append(entry)
        # 只保留最近 max_recent 条
        if len(self._recent_calls) > self._max_recent:
            self._recent_calls = self._recent_calls[-self._max_recent :]

    def maybe_critique(self) -> str | None:
        """每 N 次调用触发一次反思，返回 critique 文本或 None。

        返回的文本格式: "\\n[反思] {critique}"（供拼接到 event.result）。
        LLM 失败或未到触发点时返回 None。
        """
        self._counter += 1

        # 未到触发点
        if not self._enabled or self._counter % self._interval != 0:
            return None

        # 无 client 或无记录 → 跳过
        if self._client is None or not self._recent_calls:
            return None

        try:
            from core.observability import TraceContext
            from core.observability import metrics as _m
        except ImportError:
            _m = None
            TraceContext = None  # type: ignore[assignment]

        try:
            if _m:
                _m.increment("reflection_runs")
                with TraceContext("reflection"):  # type: ignore[misc]
                    critique = self._call_llm()
            else:
                critique = self._call_llm()

            if critique:
                # 清空已分析的记录，避免重复 critique
                self._recent_calls.clear()
                return f"\n[反思] {critique.strip()}"
            return None
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as e:
            # 降级：LLM 失败不阻塞主流程，但保留日志便于排查
            logger.warning("reflection critique failed (%s: %s)", type(e).__name__, e)
            if _m:
                _m.increment("reflection_skipped")
            return None

    def _call_llm(self) -> str:
        """调用辅助模型做 critique（内部方法，失败由调用方捕获）。"""
        context = self._build_context()
        prompt = CRITIQUE_PROMPT.format(context=context)
        response = self._client.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        return response["choices"][0]["message"]["content"]

    def _build_context(self) -> str:
        """拼接最近工具调用记录，error 优先排列。"""
        if not self._recent_calls:
            return "(无记录)"

        # error=True 的调用排在前面，便于反思聚焦失败
        sorted_calls = sorted(
            self._recent_calls,
            key=lambda c: 0 if c.get("error") else 1,
        )

        lines = []
        for i, call in enumerate(sorted_calls, 1):
            err_tag = " [错误]" if call.get("error") else ""
            lines.append(
                f"{i}. 工具: {call.get('tool', '?')}{err_tag}\n"
                f"   参数: {call.get('args', '')}\n"
                f"   结果: {call.get('result', '')}"
            )
        return "\n".join(lines)

    # ── 状态查询（供测试和调试）──

    @property
    def counter(self) -> int:
        return self._counter

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def recent_calls_count(self) -> int:
        return len(self._recent_calls)

    def reset(self) -> None:
        """重置计数器和记录（供测试隔离）。"""
        self._counter = 0
        self._recent_calls.clear()
