"""Agent Swarm — 模板化大规模并行子智能体分派.

Extracted from core/multi_agent.py (P2 refactor). Contains:
- AgentSwarm: template-based parallel agent dispatch
- AGENT_SWARM_TOOL_DEF: tool definition for /tools registry
- _exec_agent_swarm: executor function for tool integration
- _get_coordinator: coordinator singleton (lazy-imports MultiAgentCoordinator)
"""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

from core.multi_agent_models import ROOT, Agent, AgentTask  # noqa: F401  # re-exported

if TYPE_CHECKING:
    from collections.abc import Callable

    from core.multi_agent import MultiAgentCoordinator

logger = logging.getLogger("crux.multi_agent")

# ── AgentSwarm: 模板化批量并行分派 ──────────────────────────


class AgentSwarm:
    """模板化大规模并行子智能体分派。

    用法:
        swarm = AgentSwarm(tool_executor)
        results = swarm.dispatch(
            template="Review {{item}} for bugs and security issues",
            items=["src/auth.py", "src/db.py", "src/api.py"],
            role="reviewer",
        )
    """

    def __init__(
        self,
        tool_executor: Callable,
        max_workers: int = 8,
        model_router=None,
    ) -> None:
        self.execute_tool = tool_executor
        self.max_workers = max_workers
        self.model_router = model_router
        self._results: dict[str, str] = {}
        self._lock = threading.Lock()

    def dispatch(
        self,
        template: str,
        items: list[str],
        role: str = "implementer",
        max_concurrency: int | None = None,
        *,
        review: bool = False,
    ) -> dict:
        """使用模板并行分派 N 个同类型子智能体。

        Args:
            template: 提示模板，{{item}} 占位符会被替换为 items 中的值
            items: 每个 item 启动一个子智能体
            role: 子智能体角色
            max_concurrency: 最大并发数，默认 min(len(items), max_workers)
            review: 若 True，所有 worker 完成后自动派 1 个 reviewer
                    交叉审查结果的完整性和一致性

        Returns:
            dict: {item: result_str}，如果 review 启用则额外包含 _review 键
        """

        concurrency = min(max_concurrency or self.max_workers, len(items))
        sem = threading.Semaphore(concurrency)
        threads: list[threading.Thread] = []
        results: dict[str, str] = {}

        def _work(item: str):
            if not sem.acquire(timeout=300):
                with self._lock:
                    results[item] = "error: semaphore timeout"
                return
            try:
                from core.multi_agent import MultiAgentCoordinator

                goal = template.replace("{{item}}", item)
                coordinator = MultiAgentCoordinator(
                    tool_executor=self.execute_tool,
                    max_workers=1,
                    model_router=self.model_router,
                )
                coordinator.spawn_team([role])
                r = coordinator.execute(goal)
                with self._lock:
                    results[item] = (
                        f"done={r.get('tasks_done', '?')}/{r.get('tasks_total', '?')} "
                        f"failed={r.get('tasks_failed', '?')} "
                        f"elapsed={r.get('elapsed_ms', 0) / 1000:.1f}s"
                    )
            except Exception as e:
                with self._lock:
                    results[item] = f"error: {type(e).__name__}: {e}"
            finally:
                sem.release()

        for item in items:
            t = threading.Thread(target=_work, args=(item,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=300)

        # ── Cross-review: verify completeness and consistency ──
        if review and len(results) > 1:
            review_result = self._review_results(template, items, role, results)
            results["_review"] = review_result

        return results

    def _review_results(self, template: str, items: list[str], role: str, results: dict[str, str]) -> str:
        """Spawn a reviewer agent to cross-check worker results.

        The reviewer checks for:
        - Internal consistency across results
        - Obvious errors or incomplete outputs
        - Items that may need rework
        """
        error_items = {k: v for k, v in results.items() if v.startswith("error:")}
        ok_items = {k: v for k, v in results.items() if not v.startswith("error:")}

        review_prompt = (
            f"Cross-review the following parallel {role} results.\n\n"
            f"Template: {template}\n"
            f"Items processed: {len(items)}\n"
            f"Successful: {len(ok_items)}\n"
            f"Failed: {len(error_items)}\n\n"
        )
        if ok_items:
            review_prompt += "--- Successful results ---\n"
            for item, result in list(ok_items.items())[:5]:
                review_prompt += f"[{item}]: {result[:200]}\n"
        if error_items:
            review_prompt += "--- Failed items ---\n"
            for item, result in list(error_items.items())[:5]:
                review_prompt += f"[{item}]: {result[:200]}\n"

        review_prompt += (
            "\nYour task: check these results for consistency and completeness. "
            "Are there any contradictions between results? "
            "Are any results clearly incomplete or nonsensical? "
            "Should any items be re-run? "
            "Respond with: PASS (all good) or REWORK: <specific items to redo>"
        )

        try:
            from core.multi_agent import MultiAgentCoordinator

            coordinator = MultiAgentCoordinator(
                tool_executor=self.execute_tool,
                max_workers=1,
                model_router=self.model_router,
            )
            coordinator.spawn_team(["reviewer"])
            r = coordinator.execute(review_prompt)
            return (
                f"review_ok={r.get('tasks_done', '?')}/{r.get('tasks_total', '?')} "
                f"failed={r.get('tasks_failed', '?')} "
                f"elapsed={r.get('elapsed_ms', 0) / 1000:.1f}s"
            )
        except Exception as e:
            return f"review_error: {type(e).__name__}: {e}"


# ── Coordination entry points (backward-compatible) ──────────

_coordinator: MultiAgentCoordinator | None = None
_coordinator_lock = threading.Lock()


def _get_coordinator(tool_executor: Callable):
    global _coordinator
    if _coordinator is None:
        with _coordinator_lock:
            if _coordinator is None:
                from core.multi_agent import MultiAgentCoordinator

                _coordinator = MultiAgentCoordinator(tool_executor=tool_executor)
    else:
        _coordinator.execute_tool = tool_executor
    return _coordinator


# coordinate() removed (duplicate of line 351)


# ── Agent Swarm tool definition ──

AGENT_SWARM_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "agent_swarm",
        "description": (
            "大规模并行子智能体分派。使用模板将同一提示应用于多个目标，"
            "并行执行并汇总结果。适用于批量审查、批量重构、批量测试等场景。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "description": "提示模板，使用 {{item}} 作为占位符",
                },
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "每个 item 启动一个子智能体",
                },
                "role": {
                    "type": "string",
                    "description": "子智能体角色: reviewer/debugger/implementer/tester",
                },
                "max_concurrency": {
                    "type": "integer",
                    "description": "最大并发数，默认 8",
                },
                "review": {
                    "type": "boolean",
                    "description": "完成后自动派 reviewer 交叉审查结果完整性和一致性（默认 false）",
                },
            },
            "required": ["template", "items"],
        },
    },
}


def _exec_agent_swarm(**kwargs) -> str:
    """执行 AgentSwarm 分派。"""
    # tool_executor 需要从外部注入（caller 闭包）
    # 这里使用 import 级别的默认 executor
    from core.tools import get_registry

    registry = get_registry()

    def _exec(tool: str, args: dict) -> str:
        if registry.has(tool):
            return registry.execute(tool, args)
        return f"[agent_swarm] 工具 {tool} 不可用"

    swarm = AgentSwarm(
        tool_executor=_exec,
        model_router=getattr(registry, "model_router", None),
    )
    do_review = kwargs.get("review", kwargs.get("cross_review", False))
    results = swarm.dispatch(
        template=kwargs["template"],
        items=kwargs["items"],
        role=kwargs.get("role", "implementer"),
        max_concurrency=kwargs.get("max_concurrency"),
        review=bool(do_review),
    )
    return json.dumps(results, ensure_ascii=False, indent=2)
