"""Multi-agent coordination engine -- parallel sub-agents with task dispatch.

Real coordination: task decomposition, parallel dispatch, result aggregation,
consensus voting, work stealing from stalled agents.

Usage:
    from core.multi_agent import MultiAgentOrchestra, should_use_multi_agent

    orchestra = MultiAgentOrchestra()
    result = orchestra.run(goal="Refactor payment module")

两条实现共存：
- ``MultiAgentCoordinator`` / ``coordinate`` —— **同步版**（threading + Lock）。
  保留以兼容既有调用方与 tests/test_multi_agent.py。
- ``AsyncMultiAgentCoordinator`` / ``async_coordinate`` —— **asyncio 原生版**
  （Phase 4 新增）。用 ``asyncio.Semaphore`` 限并发、``asyncio.gather`` 并行、
  ``asyncio.to_thread`` 包装同步 executor，并**真正按 ``depends_on`` 拓扑调度**
  （同步版只做 round-robin，忽略依赖）。

两版共享 ``AgentTask`` / ``Agent`` / ``decompose``（纯计算，无 I/O）。
asyncio 版的 executor 既支持同步 ``Callable``（自动 to_thread 包装），
也支持 async ``Callable``（直接 await），便于嵌入事件循环。

⚠ AsyncMultiAgentCoordinator 已接通 asyncio runtime（M5 async_render /
AsyncChatSession 可直接 await ``execute``）。同步版仍标记 EXPERIMENTAL，
未接 ChatSession runtime。

优化（ChatGPT评审建议 v5.0）：
    默认单智能体运行，仅在高复杂度任务时启用多智能体。
    判断标准见 should_use_multi_agent()。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from dataclasses import dataclass
from typing import Any


@dataclass
class SessionContext:
    """多智能体决策上下文"""
    recent_failures: int = 0
    files_touched: int = 0
    tools_used: int = 0
    error_repeated: bool = False
    task_continuation: bool = False
    previous_plan_exists: bool = False

    @staticmethod
    def from_dict(d: dict) -> "SessionContext":
        return SessionContext(
            recent_failures=d.get("recent_failures", 0),
            files_touched=d.get("files_touched", 0),
            tools_used=d.get("tools_used", 0),
            error_repeated=d.get("error_repeated", False),
        )


# ═══════════════════════════════════════════════════════════
# AgentMode 4-tier system — weighted multi-factor scoring
# ═══════════════════════════════════════════════════════════

class AgentMode(Enum):
    """4-tier agent orchestration mode, selected by weighted multi-factor scoring."""
    SINGLE = "single"                       # score < 3
    SINGLE_WITH_REVIEWER = "single_with_reviewer"  # score >= 3
    PLAN_EXECUTE = "plan_execute"           # score >= 5
    SWARM = "swarm"                         # score >= 8


@dataclass
class AgentModeResult:
    """Record of a completed agent mode execution for long-term learning."""
    mode: AgentMode
    task_type: str
    success: bool
    latency: float
    user_correction: bool = False
    timestamp: float = field(default_factory=lambda: __import__("time", fromlist=["time"]).time())


# ─── Weighted trigger keywords ───

_TRIGGERS: dict[str, list[tuple[str, float]]] = {
    "high_complexity": [
        ("refactor", 3.0), ("重构", 3.0), ("migrate", 3.0), ("迁移", 3.0),
        ("architecture", 3.0), ("架构", 3.0), ("audit", 2.5), ("审计", 2.5),
        ("review entire", 3.0), ("审查整个", 3.0), ("review whole", 3.0),
        ("batch", 2.0), ("批量", 2.0), ("parallel", 2.5), ("并行", 2.5),
        ("simultaneous", 2.5), ("同时处理", 2.5), ("multi-module", 2.5), ("多模块", 2.5),
        ("cross-file", 2.5), ("跨文件", 2.5), ("entire project", 3.0), ("全项目", 3.0),
    ],
    "multi_perspective": [
        ("compare", 2.0), ("对比", 2.0), ("comparison", 2.0), ("比较", 2.0),
        ("pros and cons", 2.5), ("正反", 2.5), ("multi-angle", 2.5), ("多角度", 2.5),
    ],
    "coordination": [
        ("orchestrate", 3.0), ("coordinate", 2.5), ("协同", 2.5),
        ("multiple agents", 3.5), ("多智能体", 3.5), ("swarm", 3.5),
        ("team", 2.0), ("团队", 2.0),
    ],
}

_SIMPLICITY_BLOCKERS: list[tuple[str, float]] = [
    ("simple", 2.0), ("简单", 2.0), ("quick", 1.5), ("快速", 1.5),
    ("immediate", 2.0), ("立即", 2.0), ("direct", 2.0), ("直接", 2.0),
    ("single step", 3.0), ("单步", 3.0), ("one word", 3.0), ("一句话", 3.0),
    ("简答", 3.0), ("brief", 1.5), ("tiny", 2.0),
    ("just", 1.0), ("只", 1.0), ("only", 1.0),
]

_DESTRUCTIVE_ACTIONS: list[tuple[str, float]] = [
    ("delete", 4.0), ("clean", 4.0), ("migrate", 4.0),
    ("reset", 4.0), ("drop", 4.0), ("truncate", 4.0),
    ("purge", 4.0), ("rm ", 4.0), ("remove all", 4.0),
    ("destroy", 4.0), ("wipe", 4.0), ("nuke", 4.0),
    ("删除", 4.0), ("清理", 4.0), ("重置", 4.0), ("销毁", 4.0),
]

_FUZZY_INTENT: list[tuple[str, float]] = [
    ("maybe", 1.0), ("perhaps", 1.0), ("possibly", 1.0),
    ("大概", 1.0), ("也许", 1.0), ("可能", 1.0), ("或许", 1.0),
    ("unsure", 1.5), ("不确定", 1.5), ("not sure", 1.5),
    ("something like", 1.5), ("之类", 1.5),
    ("看看", 0.5), ("试试", 0.5), ("explore", 0.5),
    ("不好用", 2.0), ("不对劲", 2.0), ("还是不行", 2.0),
]


def _match_weighted(text: str, patterns: list[tuple[str, float]]) -> tuple[float, list[str]]:
    """Return (total_score, matched_patterns) for weighted pattern matching."""
    tl = text.lower()
    total = 0.0
    matched: list[str] = []
    for pat, weight in patterns:
        if pat in tl:
            total += weight
            matched.append(pat)
    return total, matched


# ─── Individual scoring functions ───

def keyword_score(goal: str) -> tuple[float, list[str]]:
    """Weighted keyword score from _TRIGGERS dict.

    Returns:
        (total_score, matched_keywords)
    """
    total = 0.0
    all_matched: list[str] = []
    for _cat, patterns in _TRIGGERS.items():
        s, m = _match_weighted(goal, patterns)
        total += s
        all_matched.extend(m)
    return total, all_matched


def length_score(goal: str) -> float:
    """Score based on task description length (complexity proxy).

    Longer tasks signal more complex requirements.
    """
    ln = len(goal)
    if ln > 2000:
        return 3.0
    if ln > 1000:
        return 2.5
    if ln > 500:
        return 1.5
    if ln > 200:
        return 0.5
    return 0.0


def file_scope_score(session: dict[str, Any]) -> float:
    """Score based on context features: breadth of files touched in session.

    More files touched → broader impact → more agents may help.
    """
    files = session.get("files_touched", 0)
    if files > 20:
        return 3.0
    if files > 10:
        return 2.0
    if files > 5:
        return 1.0
    if files > 2:
        return 0.5
    return 0.0


def failure_score(session: dict[str, Any]) -> float:
    """Score from recent failures and error repetition signals.

    Repeated failures suggest the current approach isn't working —
    more agents or perspectives may break the deadlock.
    """
    score = 0.0
    recent = session.get("recent_failures", 0)
    if recent >= 3:
        score += 3.0
    elif recent >= 2:
        score += 2.0
    elif recent >= 1:
        score += 1.0
    if session.get("error_repeated", False):
        score += 2.0
    return score


def risk_score(goal: str) -> tuple[float, list[str]]:
    """Risk score for destructive actions. Each match adds +4.

    Destructive operations warrant extra review — SWARM or PLAN_EXECUTE.
    """
    return _match_weighted(goal, _DESTRUCTIVE_ACTIONS)


def ambiguity_score(goal: str) -> tuple[float, list[str]]:
    """Ambiguity/fuzzy-intent score — unclear tasks benefit from multi-agent exploration.

    Fuzzy intent means the user hasn't specified exact steps, so multi-agent
    exploration or planning helps clarify before execution.
    """
    return _match_weighted(goal, _FUZZY_INTENT)


def simplicity_score(goal: str) -> tuple[float, list[str]]:
    """Negative weight from simplicity blockers.

    Returns positive values that are SUBTRACTED from the total.
    These are not hard stops — they reduce the score but don't block multi-agent.
    """
    return _match_weighted(goal, _SIMPLICITY_BLOCKERS)


def decomposability_score(goal: str) -> tuple[float, list[str]]:
    """DAG decomposability estimation (v6.0).

    智谱清言建议：预判任务是否能拆解为独立并行子任务。
    可分解性高的任务 → 有并行叶子节点 → 适合 SWARM。
    """
    patterns: list[tuple[str, float]] = [
        ("并且", 3.0), ("同时", 3.0), ("分别", 3.0),
        ("先", 1.5), ("再", 1.5), ("然后", 1.5),
        ("前端", 2.0), ("后端", 2.0), ("前后端", 3.0),
        ("数据库", 2.0), ("API", 2.0),
        ("同时生成", 4.0), ("并行处理", 4.0),
        ("分别处理", 3.0), ("各自", 2.0),
        ("多维度", 2.0), ("多个方面", 2.0), ("多角度", 2.0),
        ("提取", 1.5), ("转换", 1.5), ("合并", 1.5),
    ]
    return _match_weighted(goal, patterns)


# ─── Context state features ───

def build_context_state(
    recent_failures: int = 0,
    files_touched: int = 0,
    tools_used: int = 0,
    error_repeated: bool = False,
    task_continuation: bool = False,
) -> dict[str, Any]:
    """Build a context state features dict consumed by scoring functions.

    All values default to 0/False — callers incrementally populate from
    session state (recent tool calls, error counts, touched files, etc.).
    """
    return {
        "recent_failures": recent_failures,
        "files_touched": files_touched,
        "tools_used": tools_used,
        "error_repeated": error_repeated,
        "task_continuation": task_continuation,
    }


# ─── Main scoring + mode selection ───

def compute_agent_mode(
    goal: str,
    session: dict[str, Any] | None = None,
) -> tuple[AgentMode, float, dict[str, Any]]:
    """Compute the optimal agent mode via weighted multi-factor scoring.

    Scoring dimensions:
        keyword_score   — weighted trigger keywords (complexity/coordination/perspective)
        length_score    — task description length as complexity proxy
        file_scope_score — breadth of files touched in session
        failure_score   — recent failures + error repetition signals
        risk_score      — destructive action detection (+4 per danger match)
        ambiguity_score — fuzzy intent signals benefit from exploration
        simplicity_score — blocker words (subtracted, not hard stop)

    Thresholds:
        score >= 8  → SWARM
        score >= 5  → PLAN_EXECUTE
        score >= 3  → SINGLE_WITH_REVIEWER
        score <  3  → SINGLE

    Returns:
        (AgentMode, final_score, breakdown dict with per-dimension details)
    """
    ctx = session or {}

    kw, kw_matched = keyword_score(goal)
    ln = length_score(goal)
    fs = file_scope_score(ctx)
    ff = failure_score(ctx)
    rk, rk_matched = risk_score(goal)
    am, am_matched = ambiguity_score(goal)
    sp, sp_matched = simplicity_score(goal)
    dg, dg_matched = decomposability_score(goal)

    total = kw + ln + fs + ff + rk + am - sp + dg

    if total >= 8:
        mode = AgentMode.SWARM
    elif total >= 5:
        mode = AgentMode.PLAN_EXECUTE
    elif total >= 3:
        mode = AgentMode.SINGLE_WITH_REVIEWER
    else:
        mode = AgentMode.SINGLE

    breakdown: dict[str, Any] = {
        "keyword": {"score": kw, "matched": kw_matched},
        "length": {"score": ln, "chars": len(goal)},
        "file_scope": {
            "score": fs,
            "files_touched": ctx.get("files_touched", 0),
        },
        "failure": {
            "score": ff,
            "recent_failures": ctx.get("recent_failures", 0),
            "error_repeated": ctx.get("error_repeated", False),
        },
        "risk": {"score": rk, "matched": rk_matched},
        "ambiguity": {"score": am, "matched": am_matched},
        "simplicity": {"score": sp, "matched": sp_matched, "subtracted": True},
        "decomposability": {"score": dg, "matched": dg_matched},
        "total": round(total, 2),
        "mode": mode.value,
    }
    return mode, total, breakdown


# ─── Backward-compatible wrapper ───

def should_use_multi_agent(goal: str) -> tuple[bool, str]:
    """Backward-compatible wrapper — delegates to compute_agent_mode().

    Preserves the original (should_use: bool, reason: str) return type
    for existing callers.

    Mapping:
        SINGLE / SINGLE_WITH_REVIEWER → False (no multi-agent)
        PLAN_EXECUTE / SWARM           → True  (use multi-agent)
    """
    mode, score, _breakdown = compute_agent_mode(goal)
    should = mode in (AgentMode.PLAN_EXECUTE, AgentMode.SWARM)
    reason = f"AgentMode={mode.value} score={score:.1f}"
    return should, reason


# ─── Long-term learning ───

_agent_mode_history: list[AgentModeResult] = []


def record_agent_mode_result(result: AgentModeResult) -> None:
    """Record an agent mode execution result for long-term learning.

    Stored in-memory as _agent_mode_history. Over time, the distribution
    of success/failure per mode can inform threshold tuning.

    Args:
        result: An AgentModeResult with mode, task_type, success, latency,
                and optional user_correction.
    """
    _agent_mode_history.append(result)
    # Keep bounded — drop oldest 200 when exceeding 1000
    if len(_agent_mode_history) > 1000:
        del _agent_mode_history[:200]


def get_mode_statistics() -> dict[str, dict[str, Any]]:
    """Return success/failure statistics per AgentMode from recorded history.

    Returns:
        Dict keyed by mode value (e.g. "single", "swarm") with:
        total, success, failure, corrections, total_latency,
        success_rate, correction_rate, avg_latency.
        Empty dict if no history recorded.
    """
    if not _agent_mode_history:
        return {}

    stats: dict[str, dict[str, Any]] = {}
    for r in _agent_mode_history:
        key = r.mode.value
        if key not in stats:
            stats[key] = {
                "total": 0, "success": 0, "failure": 0,
                "corrections": 0, "total_latency": 0.0,
            }
        s = stats[key]
        s["total"] += 1
        if r.success:
            s["success"] += 1
        else:
            s["failure"] += 1
        if r.user_correction:
            s["corrections"] += 1
        s["total_latency"] += r.latency

    for s in stats.values():
        n = s["total"]
        s["success_rate"] = round(s["success"] / n, 3) if n > 0 else 0.0
        s["correction_rate"] = round(s["corrections"] / n, 3) if n > 0 else 0.0
        s["avg_latency"] = round(s["total_latency"] / n, 3) if n > 0 else 0.0

    return stats


from core.error_sink import catch
import logging

logger = logging.getLogger("crux.multi_agent")
import asyncio
import inspect
import json
import threading
import time
import uuid
from collections.abc import Callable

from core.multi_agent_models import ROOT, Agent, AgentTask  # noqa: F401

# 跨模块 trace 上下文：供 cost_tracker 等下游模块读取当前 root_trace_id
import contextvars as _crux_ctx
_current_root_trace_id = _crux_ctx.ContextVar("crux_root_trace_id", default="")
_current_trace_id = _crux_ctx.ContextVar("crux_trace_id", default="")


def get_current_root_trace_id() -> str:
    """获取当前执行的 root_trace_id，供下游模块（cost_tracker/observability）使用。"""
    return _current_root_trace_id.get()


def get_current_trace_id() -> str:
    """获取当前 AgentTask 的 trace_id，供下游模块使用。"""
    return _current_trace_id.get()


__all__ = [
    "Agent",
    "AgentTask",
    "AgentMode",
    "AgentModeResult",
    "MultiAgentCoordinator",
    "ROOT",
    "SmartDecomposer",
    "coordinate",
    "AsyncMultiAgentCoordinator",
    "async_coordinate",
    "AgentSwarm",
    "AGENT_SWARM_TOOL_DEF",
    "_exec_agent_swarm",
    "compute_agent_mode",
    "should_use_multi_agent",
    "keyword_score",
    "length_score",
    "file_scope_score",
    "failure_score",
    "risk_score",
    "ambiguity_score",
    "simplicity_score",
    "build_context_state",
    "record_agent_mode_result",
    "get_mode_statistics",
]


# ── 同步版（threading + Lock，保留兼容）─────────────────────


class MultiAgentCoordinator:
    """Orchestrates multiple agents to solve a complex task (threading 版)."""

    def __init__(self, tool_executor: Callable, max_workers: int = 4, model_router=None) -> None:
        self.execute_tool = tool_executor
        self.max_workers = max_workers
        self.agents: list[Agent] = []
        self.tasks: list[AgentTask] = []
        self._lock = threading.Lock()
        self._results: dict[str, str] = {}
        self._log: list[dict] = []
        # 可选 ModelRouter — 当 tool_executor 是 LLM-backed 时，按 task.tier 选模型
        # None 时退回原行为（tool_executor 内部自决模型），完全向后兼容
        self.model_router = model_router
        # 持久化智能体注册表（agent_id → Agent）
        self._agent_registry: dict[str, Agent] = {}
        # 后台任务线程追踪
        self._background_threads: dict[str, threading.Thread] = {}

    def spawn_team(self, roles: list[str] | None = None):
        """Create agent team. Default: reviewer, debugger, implementer, tester."""
        roles = roles or ["reviewer", "debugger", "implementer", "tester"]
        self.agents = [Agent(id=f"agent_{i}", role=role) for i, role in enumerate(roles[: self.max_workers])]
        # 注册到持久化注册表
        with self._lock:
            for agent in self.agents:
                agent.created_at = time.time()
                self._agent_registry[agent.id] = agent

    def resume(self, agent_id: str, new_goal: str | None = None) -> Agent | None:
        """恢复持久化智能体实例，可选注入新目标。

        Args:
            agent_id: 智能体 ID
            new_goal: 可选，新的执行目标（追加到 context_history）

        Returns:
            Agent 实例，未找到返回 None
        """
        with self._lock:
            agent = self._agent_registry.get(agent_id)
            if agent is None:
                return None
            if new_goal:
                agent.context_history.append({
                    "ts": time.time(),
                    "event": "new_goal",
                    "goal": new_goal,
                })
            # 确保 agent 在活跃列表中
            if agent not in self.agents:
                self.agents.append(agent)
            agent.status = "idle"
            return agent

    def spawn_background(self, goal: str, role: str = "implementer") -> Agent:
        """在后台异步执行目标，返回 Agent 实例。

        Args:
            goal: 执行目标
            role: 智能体角色

        Returns:
            Agent 实例（含 agent_id 用于后续 resume）
        """

        agent_id = f"bg_{uuid.uuid4().hex[:8]}"
        agent = Agent(
            id=agent_id,
            role=role,
            status="busy",
            created_at=time.time(),
        )
        agent.context_history.append({
            "ts": time.time(),
            "event": "spawned",
            "goal": goal,
        })

        with self._lock:
            self._agent_registry[agent_id] = agent
            self.agents.append(agent)

        # 在后台线程执行
        t = threading.Thread(
            target=self._execute_background,
            args=(agent, goal),
            daemon=True,
        )
        t.start()

        with self._lock:
            self._background_threads[agent_id] = t

        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        """获取持久化的智能体实例。"""
        return self._agent_registry.get(agent_id)

    def list_agents(self) -> list[Agent]:
        """列出所有持久化智能体。"""
        return list(self._agent_registry.values())

    def _execute_background(self, agent: Agent, goal: str) -> None:
        """后台执行目标（用于 spawn_background）。"""

        try:
            tasks = self.decompose(goal)
            agent.current_task = goal
            for task in tasks:
                task.assigned_to = agent.id
                with self._lock:
                    task.status = "running"
                    task.started_at = time.time()
                results = []
                for step in task.tool_sequence:
                    try:
                        step_args = dict(step["args"])
                        # contextvar (_current_root_trace_id / _current_trace_id) 已自动传播
                        r = self.execute_tool(step["tool"], step_args)
                        results.append(r[:200])
                    except Exception as e:
                        error_str = f"{type(e).__name__}: {e}"
                        with self._lock:
                            task.status = "failed"
                            task.result = f"Failed at step {step['tool']}: {error_str}"
                            task.finished_at = time.time()
                        # ── 方法论: 子Agent失败分类与路由建议 ──
                        try:
                            from core.methodology import classify_failure, get_methodology_state
                            ftype, suggestion = classify_failure(error_str)
                            get_methodology_state()
                            self._log.append({
                                "event": "task_failed",
                                "task": task.id,
                                "trace_id": task.trace_id,
                                "root_trace_id": task.root_trace_id,
                                "error": error_str,
                                "failure_type": ftype,
                                "suggestion": suggestion,
                                "consecutive_failures": sum(
                                    1 for t in self.tasks if t.status == "failed"
                                ),
                            })
                        except ImportError:
                            pass
                        break
                else:
                    with self._lock:
                        task.status = "done"
                        task.result = "; ".join(results) if results else "completed"
                        task.finished_at = time.time()

            with self._lock:
                agent.status = "idle"
                agent.total_tasks_completed += 1
                agent.context_history.append({
                    "ts": time.time(),
                    "event": "completed",
                    "goal": goal,
                })
        except Exception as e:
            with self._lock:
                agent.status = "failed"
                agent.context_history.append({
                    "ts": time.time(),
                    "event": "error",
                    "error": str(e),
                })

    def decompose(self, goal: str) -> list[AgentTask]:
        """Break a goal into agent-sized tasks with dependencies.

        实现已下沉到模块级 ``_decompose_goal``，同步/asyncio 两版共用同一份
        分解逻辑，避免漂移。若 coordinator 有 model_router，传递给分解器以选最优模型。
        """
        return _decompose_goal(goal, model_router=self.model_router)

    def execute(self, goal: str) -> dict:
        """Full execution: spawn -> decompose -> dispatch -> aggregate."""
        started = time.time()
        self._log = []
        self._results = {}

        if not self.agents:
            self.spawn_team()
        self.tasks = self.decompose(goal)
        # 统一 root_trace_id：一次 execute 的所有 task 共享同一 root
        root_id = uuid.uuid4().hex[:16]
        _current_root_trace_id.set(root_id)
        for t in self.tasks:
            t.root_trace_id = root_id
        _current_root_trace_id.set(root_id)
        self._log.append({"event": "decomposed", "tasks": len(self.tasks), "root_trace_id": root_id})

        # Simple round-robin dispatch (parallel via threading)
        threads = []
        with self._lock:
            for task in self.tasks:
                agent = next((a for a in self.agents if a.status == "idle"), None)
                if not agent:
                    # All busy, assign to first
                    agent = self.agents[0]
                task.assigned_to = agent.id
                agent.status = "busy"
                agent.current_task = task.id
        for task in self.tasks:
            t = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
            threads.append(t)
            t.start()

        # Wait for all (use per-task timeout, default 120s)
        for task, t in zip(self.tasks, threads):
            to = task.timeout_seconds if task.timeout_seconds > 0 else 120
            t.join(timeout=to)

        # 超时未完成的任务标记为 failed（不静默丢失）。
        # 读 task.status + 改写必须在锁内：工作线程 join 超时返回时可能仍在
        # 锁外持有 task 引用并即将写 status，整段检查-改写需原子。
        with self._lock:
            for task in self.tasks:
                if task.status == "running":
                    task.status = "failed"
                    task.result = f"Task timed out (agent: {task.assigned_to})"
                    task.finished_at = time.time()
                    self._log.append({"event": "task_timeout", "task": task.id, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id, "agent": task.assigned_to, "timeout": to})

            # ── DAG runtime guard ────────────────────────────────────
            _propagate_failed_deps(self.tasks, root_trace_id=root_id)
            deadlock_msg = _check_dag_deadlock(self.tasks, root_trace_id=root_id)
            if deadlock_msg:
                self._log.append({"event": "dag_deadlock", "deadlock": deadlock_msg, "root_trace_id": root_id})

            elapsed = time.time() - started
            done = sum(1 for t in self.tasks if t.status == "done")
            failed = sum(1 for t in self.tasks if t.status == "failed")

        return _build_run_summary(goal, self.tasks, self._log, self.agents, started)

    def _resolve_model_for_task(self, task: AgentTask) -> str | None:
        """按 task.tier/task_type 解析模型（若提供 model_router）。

        - tier="auto" + task_type 非空 → ModelRouter.select(task_type=...)
        - tier in (light/pro/heavy) → ModelRouter.select_for_tier(tier)
        - 其他（默认 auto 无 task_type）→ None（不注入，executor 自决）
        """
        if not self.model_router:
            return None
        if task.tier in ("light", "pro", "heavy"):
            return self.model_router.select_for_tier(task.tier)
        if task.tier == "auto" and task.task_type:
            return self.model_router.select(task_type=task.task_type)
        return None

    def _execute_task(self, task: AgentTask):
        # task.status / task.result / task.started_at / task.finished_at 是与主线程
        # 共享的可变状态（主线程在 join 后读 status、超时时改写 status），所有读写
        # 必须在 self._lock 内，避免 TOCTOU 竞态。
        with self._lock:
            task.status = "running"
            task.started_at = time.time()
            self._log.append({"event": "task_start", "task": task.id, "agent": task.assigned_to, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id})
            # tier 路由：若提供 model_router，按 task.tier/task_type 解析模型并注入 step
            resolved_model = self._resolve_model_for_task(task)
            if resolved_model:
                self._log.append({"event": "tier_routed", "task": task.id, "tier": task.tier, "model": resolved_model})
        # 设置 trace 上下文
        _current_root_trace_id.set(task.root_trace_id)
        _current_trace_id.set(task.trace_id)
        results = []
        for step in task.tool_sequence:
            try:
                # 若解析出模型，注入到 step.args（LLM-backed executor 可读取）
                step_args = dict(step["args"])
                if resolved_model and "model" not in step_args:
                    step_args["model"] = resolved_model
                r = self.execute_tool(step["tool"], step_args)
                results.append(r[:200])
            except Exception as e:
                error_str = str(e)
                with self._lock:
                    task.status = "failed"
                    task.result = error_str
                    # ── 方法论: 失败分类
                    try:
                        from core.methodology import classify_failure
                        ftype, suggestion = classify_failure(error_str)
                        self._log.append({
                            "event": "task_failed", "task": task.id,
                            "error": error_str,
                            "failure_type": ftype, "suggestion": suggestion,
                        })
                    except ImportError:
                        self._log.append({"event": "task_failed", "task": task.id, "error": error_str})
                return
        with self._lock:
            task.status = "done"
            task.result = "; ".join(results)
            task.finished_at = time.time()
            self._results[task.id] = task.result
            self._log.append({"event": "task_done", "task": task.id, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id, "result_preview": task.result[:100]})


def coordinate(goal: str, tool_executor: Callable) -> dict:
    return MultiAgentCoordinator(tool_executor).execute(goal)


# ── asyncio 原生版（Phase 4）────────────────────────────────


class AsyncMultiAgentCoordinator:
    """asyncio 原生的多智能体协调器。

    与同步版 ``MultiAgentCoordinator`` 对应，提供完全 async 的协调能力：

    - **依赖感知调度**：按 ``AgentTask.depends_on`` 做拓扑分层，同一层内
      ``asyncio.gather`` 并行，层间串行等待（同步版只 round-robin，忽略依赖）。
    - **并发上限**：``asyncio.Semaphore(max_workers)`` 限制同时在途的任务数，
      避免一次性 gather 全部任务打爆下游。
    - **executor 双模**：``tool_executor`` 既可以是同步 ``Callable``（自动
      ``asyncio.to_thread`` 包装），也可以是 async ``Callable``（直接 await），
      由 ``inspect.iscoroutinefunction`` 自动检测。

    共享 ``AgentTask`` / ``Agent`` / ``decompose``（纯计算逻辑与同步版完全一致，
      复用同一份实现，避免两份 decompose 漂移）。
    """

    def __init__(self, tool_executor: Callable, max_workers: int = 4, model_router=None) -> None:
        self.execute_tool = tool_executor
        self.max_workers = max_workers
        self.agents: list[Agent] = []
        self.tasks: list[AgentTask] = []
        self._results: dict[str, str] = {}
        self._log: list[dict] = []
        # 可选 ModelRouter — 按 task.tier/task_type 选模型
        self.model_router = model_router
        # 运行时状态（_sem / _log_lock 绑定 event loop，必须惰性创建）
        self._sem: asyncio.Semaphore | None = None
        self._log_lock: asyncio.Lock | None = None
        self._running_tasks: set[str] = set()  # task.id set for cleanup

    def spawn_team(self, roles: list[str] | None = None) -> None:
        """Create agent team（与同步版语义一致）。"""
        roles = roles or ["reviewer", "debugger", "implementer", "tester"]
        self.agents = [Agent(id=f"agent_{i}", role=role) for i, role in enumerate(roles[: self.max_workers])]

    def decompose(self, goal: str) -> list[AgentTask]:
        """Break a goal into tasks（复用模块级 ``_decompose_goal``）。

        同步/asyncio 两版共用同一份分解逻辑，避免两份实现漂移。
        """
        return _decompose_goal(goal)

    def _ensure_runtime(self) -> None:
        """惰性初始化 loop-bound 运行时状态（_sem / _log_lock）。

        这些对象绑定当前 event loop。本方法在 ``_execute_task`` 入口兜底调用，
        保证单测可以直接 gather 单个任务而无需预先初始化。
        ``execute`` 每次都会显式重建它们（支持多次 execute + 跨 loop 复用）。
        """
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_workers)
        if self._log_lock is None:
            self._log_lock = asyncio.Lock()

    _AUTO_TASK_TIMEOUT = 240   # seconds per task — prevents infinite-hang deadlock in multi-agent waves
    _WAVE_DEADLOCK_TIMEOUT = 300  # seconds per wave — upper-bound on any single wave

    async def execute(self, goal: str) -> dict:
        """Full async execution: spawn -> decompose -> dispatch -> aggregate。

        调度策略：拓扑分层。把 tasks 按 depends_on 分成若干"波"，
        每波内的任务无相互依赖 → ``asyncio.gather`` 并行；波与波之间串行 await，
        保证依赖在前置完成后才启动。

        内建死锁防护：
        - 每任务有独立超时 _AUTO_TASK_TIMEOUT；
        - 每波有全局超时 _WAVE_DEADLOCK_TIMEOUT；
        - 拓扑分层自动检测循环依赖并抛 ValueError。
        """
        started = time.time()
        self._log = []
        self._results = {}
        # 重建 loop-bound 状态：支持多次 execute + 跨 event loop 复用 coordinator
        self._sem = asyncio.Semaphore(self.max_workers)
        self._log_lock = asyncio.Lock()

        if not self.agents:
            self.spawn_team()
        self.tasks = self.decompose(goal)
        # 统一 root_trace_id：一次 execute 的所有 task 共享同一 root
        root_id = uuid.uuid4().hex[:16]
        for t in self.tasks:
            t.root_trace_id = root_id
        await self._log_append({"event": "decomposed", "tasks": len(self.tasks), "root_trace_id": root_id})

        # 拓扑分层：每层是可并行的任务集合
        waves = _topological_waves(self.tasks)
        for wave_idx, wave in enumerate(waves):
            async def _run_task_safe(task: AgentTask, _wave_idx=wave_idx) -> None:
                """Wrap _execute_task with per-task timeout for deadlock prevention."""
                try:
                    task_timeout = task.timeout_seconds if task.timeout_seconds > 0 else self._AUTO_TASK_TIMEOUT
                    await asyncio.wait_for(
                        self._execute_task(task),
                        timeout=task_timeout,
                    )
                except asyncio.TimeoutError:
                    task.status = "failed"
                    task.result = f"[timeout] task exceeded {task_timeout}s"
                    await self._log_append({"event": "task_timeout", "task": task.id, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id, "timeout": task_timeout, "wave": _wave_idx})

            try:
                await asyncio.wait_for(
                    asyncio.gather(*[_run_task_safe(task) for task in wave]),
                    timeout=self._WAVE_DEADLOCK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                await self._log_append({"event": "wave_timeout", "wave": wave_idx, "tasks_remaining": len(wave)})
                # Mark remaining unfinished tasks as failed
                for t in wave:
                    if t.status not in ("done", "failed"):
                        t.status = "failed"
                        t.result = f"[deadlock] wave {wave_idx} global timeout after {self._WAVE_DEADLOCK_TIMEOUT}s"
            # ── DAG runtime guard ────────────────────────────────────
            _propagate_failed_deps(self.tasks, root_trace_id=root_id)
            deadlock_msg = _check_dag_deadlock(self.tasks, wave_idx=wave_idx, root_trace_id=root_id)
            if deadlock_msg:
                await self._log_append({"event": "dag_deadlock", "deadlock": deadlock_msg, "root_trace_id": root_id})

        elapsed = time.time() - started
        done = sum(1 for t in self.tasks if t.status == "done")
        failed = sum(1 for t in self.tasks if t.status == "failed")

        return _build_run_summary(goal, self.tasks, self._log, self.agents, started)

    async def _log_append(self, entry: dict) -> None:
        """线程安全地追加日志（_log 在并行任务间共享）。"""
        if self._log_lock is None:
            self._ensure_runtime()
        async with self._log_lock:  # type: ignore[union-attr]
            self._log.append(entry)

    def _resolve_model_for_task(self, task: AgentTask) -> str | None:
        """按 task.tier/task_type 解析模型（若提供 model_router）。

        与同步版 ``MultiAgentCoordinator._resolve_model_for_task`` 语义一致。
        """
        if not self.model_router:
            return None
        if task.tier in ("light", "pro", "heavy"):
            return self.model_router.select_for_tier(task.tier)
        if task.tier == "auto" and task.task_type:
            return self.model_router.select(task_type=task.task_type)
        return None

    async def _call_tool(self, tool: str, args: dict, timeout: float = 0) -> str:
        """调用 executor，自动适配同步/async 签名。通过 contextvar 传递 trace 上下文。"""
        call_args = dict(args)
        if inspect.iscoroutinefunction(self.execute_tool):
            if timeout > 0:
                return await asyncio.wait_for(self.execute_tool(tool, call_args), timeout=timeout)
            return await self.execute_tool(tool, call_args)
        # 同步 executor → to_thread，避免阻塞事件循环
        return await asyncio.to_thread(self.execute_tool, tool, call_args)

    async def _execute_task(self, task: AgentTask) -> None:
        """执行单个任务：拿 semaphore → 跑 tool_sequence → 记结果。

        与同步版 ``_execute_task`` 语义对齐：首个工具失败即标记 failed 并返回，
        不继续后续步骤。成功则拼接所有步骤结果。

        自包含：入口调 ``_ensure_runtime`` 保证 ``_sem`` 就绪，无需调用方
        预先初始化（便于单测直接 gather 单个任务）。
        """
        if self._sem is None:
            self._ensure_runtime()
        async with self._sem:  # type: ignore[union-attr]
            self._running_tasks.add(task.id)
            try:
                # 分配 agent（round-robin 选 idle，回退第一个；与同步版一致）
                agent = next((a for a in self.agents if a.status == "idle"), None)
                if agent is None:
                    agent = self.agents[0] if self.agents else Agent(id="agent_0", role="solo")
                task.assigned_to = agent.id
                agent.status = "busy"
                agent.current_task = task.id

                task.status = "running"
                task.started_at = time.time()
                await self._log_append({"event": "task_start", "task": task.id, "agent": task.assigned_to, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id})
                # tier 路由：若解析出模型，注入到 step.args
                resolved_model = self._resolve_model_for_task(task)
                if resolved_model:
                    await self._log_append(
                        {"event": "tier_routed", "task": task.id, "tier": task.tier, "model": resolved_model}
                    )

                results: list[str] = []
                # 设置 trace 上下文
                _current_root_trace_id.set(task.root_trace_id)
                _current_trace_id.set(task.trace_id)
                for step in task.tool_sequence:
                    try:
                        step_args = dict(step["args"])
                        if resolved_model and "model" not in step_args:
                            step_args["model"] = resolved_model
                        # contextvar 已自动传播，_call_tool 不再需显式传递
                        r = await self._call_tool(step["tool"], step_args,
                                                  trace_id=task.trace_id,
                                                  root_trace_id=task.root_trace_id)
                        results.append(str(r)[:200])
                    except Exception as e:
                        task.status = "failed"
                        task.result = str(e)
                        await self._log_append({"event": "task_failed", "task": task.id, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id, "error": str(e)})
                        agent.current_task = ""
                        return

                task.status = "done"
                task.result = "; ".join(results)
                task.finished_at = time.time()
                self._results[task.id] = task.result
                await self._log_append({"event": "task_done", "task": task.id, "trace_id": task.trace_id, "root_trace_id": task.root_trace_id, "result_preview": task.result[:100]})

                agent.status = "idle"
                agent.current_task = ""
            finally:
                self._running_tasks.discard(task.id)
                agent.status = "idle"
                agent.current_task = ""


async def async_coordinate(goal: str, tool_executor: Callable) -> dict:
    """asyncio 版顶层入口（对应同步版 ``coordinate``）。"""
    return await AsyncMultiAgentCoordinator(tool_executor).execute(goal)


# ── 模块级共享逻辑（decompose + 拓扑分层）──────────────────


# ── #4 Qoder-style: Smart Multi-Agent Decomposition ──

_SMART_DECOMPOSE_PROMPT = """你是多智能体任务规划专家。将用户目标分解为 3-5 个子任务，每个子任务分配给一个专门的 Agent。

可用工具：read_file, search_files, glob_files, code_analyze, find_symbol, find_references,
           graph_neighbors, graph_ancestors, graph_descendants, run_test, run_bash,
           run_python, edit_file, write_file, web_search, web_fetch, github_search

规则：
1. 每个子任务只做一件事，用 1-2 个工具
2. 标注依赖关系（depends_on）：B 需要 A 的结果时，B.depends_on = ["A的id"]
3. 第一波（无依赖）的任务至少 2 个，可以并行
4. 给每个任务分配 role: explorer(探索) | analyst(分析) | fixer(修改) | tester(验证)
5. 给每个任务分配 tier: light(简单搜索/读文件) | pro(分析/修改) | heavy(架构审查)
6. 返回纯 JSON 数组，每项含 id/description/role/tier/tools/depends_on 字段

目标：{goal}

只返回 JSON 数组，不要其他文字。"""


class SmartDecomposer:
    """LLM-driven task decomposition for multi-agent coordination.

    Qoder 理念：不再用关键词匹配暴力分解任务，而是让 LLM 理解意图后
    智能拆解，自动分配角色（explorer/analyst/fixer/tester）和
    模型层级（light/pro/heavy），失败时退回关键词匹配。

    Usage:
        decomposer = SmartDecomposer()
        tasks = decomposer.decompose("审查认证模块的安全性")
        # → 4-5 个带角色和 tier 的 AgentTask
    """

    def __init__(self, client=None, model: str | None = None, model_router=None) -> None:
        self._client = client
        self._model = model
        self._model_router = model_router

    def decompose(self, goal: str, tool_names: list[str] | None = None) -> list[AgentTask]:
        """Smart decompose with LLM, fallback to keyword matching."""
        try:
            return self._llm_decompose(goal, tool_names)
        except Exception:
            # Any LLM failure → fallback to keyword-based decomposition
            return _keyword_decompose(goal)

    def _llm_decompose(self, goal: str, tool_names: list[str] | None = None) -> list[AgentTask]:
        """Use LLM to decompose the goal into structured tasks.

        Model tier adapts to goal complexity: simple goals use light model,
        complex architecture/planning use heavy. Saves cost on routine tasks.

        Results are cached — repeated calls with the same goal skip the LLM.
        """
        # ── Check cache first ──
        from core.agent_cache import get_cache
        cache = get_cache()
        cached = cache.get_decomposition(goal, "decompose")
        if cached is not None:
            return cached

        prompt = _SMART_DECOMPOSE_PROMPT.format(goal=goal)

        # Resolve model via router: match tier to goal complexity
        model = self._model
        if not model and self._model_router:
            # Classify goal first → light goals don't need heavy-tier decomposition
            goal_tier = self._model_router.classify_prompt(goal)
            if goal_tier == "light":
                model = self._model_router.select(task_type="search")  # light tier
            elif goal_tier == "reasoner":
                model = self._model_router.select(task_type="planning")  # heavy tier
            else:
                model = self._model_router.select(task_type="tool_calling")  # pro tier

        # ── 方法论检查: Agent 路由约束 ──
        try:
            from core.methodology import check_agent_route

            resolved = model or "deepseek-v4-pro"
            if "planning" in (goal_tier if model else ""):
                allowed, msg = check_agent_route("architecture", resolved)
            elif goal_tier == "light" and "pro" in resolved:
                allowed, msg = check_agent_route("grep", resolved)
            else:
                allowed, msg = True, ""
            if not allowed:
                raise RuntimeError(f"Agent routing violation: {msg}")
        except (ImportError, RuntimeError):
            pass

        # Try via CruxClient if available, otherwise via raw chat
        raw = ""
        try:
            from core.client import CruxClient

            client = self._client or CruxClient()
            chat_model = model or "deepseek-v4-pro"
            resp = client.chat(chat_model, messages=[{"role": "user", "content": prompt}])
            raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "") if isinstance(resp, dict) else str(resp)
        except ImportError:
            # Last resort: try via run_bash calling a simple script
            raise RuntimeError("No LLM client available for SmartDecomposer") from None

        # Parse JSON from response
        tasks_json = _extract_json(raw)

        tasks: list[AgentTask] = []
        for item in tasks_json:
            tools = []
            for t in item.get("tools", []):
                tools.append({"tool": t.get("name", "read_file"), "args": t.get("args", {})})
            if not tools:
                tools = [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}]

            task = AgentTask(
                id=item.get("id", f"t{len(tasks)}"),
                description=item.get("description", ""),
                tool_sequence=tools,
                depends_on=item.get("depends_on", []),
                tier=item.get("tier", "auto"),
                task_type=item.get("role", ""),
            )
            tasks.append(task)

        # Ensure at least 2 independent tasks (wave 0)
        independent = [t for t in tasks if not t.depends_on]
        if len(independent) < 2 and len(tasks) >= 2:
            tasks[1].depends_on = []

        result = tasks if tasks else _keyword_decompose(goal)
        # Cache successful decompositions
        if tasks:
            cache.set_decomposition(goal, "decompose", result)
        return result


def _decompose_goal(goal: str, model_router=None) -> list[AgentTask]:
    """任务分解入口：优先智能分解，失败退回关键词匹配。

    所有调用方（MultiAgentCoordinator / AsyncMultiAgentCoordinator）通过
    此函数获得统一的行为，不需要关心内部是 LLM 还是关键词。
    """
    try:
        decomposer = SmartDecomposer(model_router=model_router)
        return decomposer.decompose(goal)
    except Exception:
        return _keyword_decompose(goal)


def _keyword_decompose(goal: str) -> list[AgentTask]:
    """关键词匹配的快速分解（LLM 不可用时的可靠降级）。

    保留原有逻辑：review / debug / default 三条路径。
    """
    goal_lower = goal.lower()

    if "review" in goal_lower or "审查" in goal_lower or "audit" in goal_lower:
        return [
            AgentTask(
                "t1", "探索并读取目标文件", [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}],
                tier="light", task_type="explorer"
            ),
            AgentTask(
                "t2", "搜索潜在问题和反模式",
                [{"tool": "search_files", "args": {"pattern": "TODO|FIXME|HACK|bug|error"}}],
                depends_on=["t1"], tier="light", task_type="explorer"
            ),
            AgentTask(
                "t3", "分析代码结构和依赖",
                [{"tool": "code_analyze", "args": {"file_path": "PLACEHOLDER"}}],
                depends_on=["t1"], tier="pro", task_type="analyst"
            ),
            AgentTask(
                "t4", "运行测试验证",
                [{"tool": "run_test", "args": {}}],
                depends_on=["t2", "t3"], tier="heavy", task_type="tester"
            ),
        ]

    if "debug" in goal_lower or "fix" in goal_lower or "调试" in goal_lower or "修复" in goal_lower:
        return [
            AgentTask(
                "t1", "检查错误日志", [{"tool": "search_files", "args": {"pattern": "error|exception|traceback"}}],
                tier="light", task_type="explorer"
            ),
            AgentTask(
                "t2", "全局搜索相关代码",
                [{"tool": "search_files", "args": {"pattern": "def |class "}}],
                tier="light", task_type="explorer"
            ),
            AgentTask(
                "t3", "定位根因并读取文件",
                [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}],
                depends_on=["t1", "t2"], tier="pro", task_type="analyst"
            ),
            AgentTask(
                "t4", "实施修复",
                [{"tool": "edit_file", "args": {"path": "PLACEHOLDER", "old_text": "", "new_text": ""}}],
                depends_on=["t3"], tier="pro", task_type="fixer"
            ),
            AgentTask(
                "t5", "验证修复并运行测试",
                [{"tool": "run_test", "args": {}}],
                depends_on=["t4"], tier="heavy", task_type="tester"
            ),
        ]

    # Default: investigate → understand → act → verify
    first_word = goal.split()[0] if goal.split() else "main"
    return [
        AgentTask(
            "t1", "探索项目结构", [{"tool": "list_files", "args": {}}],
            tier="light", task_type="explorer"
        ),
        AgentTask(
            "t2", "搜索相关文件",
            [{"tool": "search_files", "args": {"pattern": first_word}}],
            tier="light", task_type="explorer"
        ),
        AgentTask(
            "t3", "读取并分析关键文件",
            [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}],
            depends_on=["t2"], tier="pro", task_type="analyst"
        ),
        AgentTask(
            "t4", "执行操作并验证",
            [{"tool": "run_test", "args": {}}],
            depends_on=["t3"], tier="heavy", task_type="tester"
        ),
    ]


def _extract_json(raw: str) -> list[dict]:
    """Extract JSON array from LLM response."""
    import json as _json

    raw = raw.strip()
    # Try direct parse
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        pass
    # Try extracting from code blocks
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", raw)
    if m:
        try:
            return _json.loads(m.group(1))
        except _json.JSONDecodeError:
            pass
    # Try finding any array
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            return _json.loads(m.group(0))
        except _json.JSONDecodeError:
            pass
    return []




# ── DAG Runtime Deadlock Guard ──────────────────────────


def _build_run_summary(goal: str, tasks: list, log: list, agents: list, started: float) -> dict:
    """生成执行摘要：统计各状态任务数 + 事件计数。"""
    done = sum(1 for t in tasks if t.status == "done")
    failed = sum(1 for t in tasks if t.status == "failed")
    skipped = sum(1 for t in tasks if t.status == "skipped")
    timed_out = sum(1 for t in tasks if "[timeout]" in t.result or "[deadlock]" in t.result)
    cancelled = sum(1 for t in tasks if t.status == "pending")
    
    deadlock_count = sum(1 for e in log if e.get("event") == "dag_deadlock")
    fallback_count = sum(1 for e in log if e.get("event") in ("wave_timeout", "task_timeout"))
    timeout_count = sum(1 for e in log if e.get("event") == "task_timeout")
    
    # 提取 provider route 信息
    provider_route = ""
    for entry in log:
        if entry.get("event") == "tier_routed":
            provider_route = entry.get("model", "")
        if "provider" in entry:
            provider_route = entry.get("provider", provider_route)
    longest = max(tasks, key=lambda t: t.finished_at - t.started_at) if tasks else None
    longest_info = {}
    if longest and longest.finished_at > 0:
        longest_info = {"id": longest.id, "duration_ms": int((longest.finished_at - longest.started_at) * 1000), "status": longest.status}
    
    failure_reasons: dict[str, int] = {}
    for t in tasks:
        if t.status == "failed" and t.result:
            reason = t.result[:60]
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    
    root_id = tasks[0].root_trace_id if tasks else ""
    
    result = {
        "goal": goal,
        "root_trace_id": root_id,
        "elapsed_ms": int((time.time() - started) * 1000),
        "agents": len(agents),
        "tasks_total": len(tasks),
        "tasks_done": done,
        "tasks_failed": failed,
        "tasks_skipped": skipped,
        "tasks_timeout": timed_out,
        "tasks_cancelled": cancelled,
        "events": {"deadlocks": deadlock_count, "fallbacks": fallback_count, "timeouts": timeout_count},
        "longest_task": longest_info,
        "failure_reasons": failure_reasons,
        "provider_route": provider_route,
    }
    try:
        from core.run_summary import save_run
        from core.run_replay import save_run_replay
        from core.quality_gate import assess_quality
        from core.policy_gate import auto_recover
        from core.retry_budget import auto_retry_decision, record_retry_attempt
        quality = assess_quality(result)
        result.update(quality)
        policy = auto_recover(result)
        result.update({"policy_action": policy["action"], "policy_reason": policy["reason"]})
        retry = auto_retry_decision(result)
        result.update({"retry_budget": retry.get("budget", {}), "retry_decision": retry.get("should_retry", False), "retry_reason": retry.get("reason", "")})
        if retry.get("should_retry"):
            record_retry_attempt(root_id, "scheduled", "pending")
        save_run(result)
        try:
            from core.incident_classifier import classify_run
            from core.incident_store import save_incident, should_alert
            incident = classify_run(result, log)
            result.update({"incident": incident})
            try:
                from core.incident_playbook import auto_remediation
                cmds = auto_remediation(incident, root_id)
                if cmds:
                    result.update({"remediation_commands": cmds})
            except Exception as _es:
                catch(_es, "core.multi_agent", "swallowed")
            if incident.get("total_incidents", 0) > 0:
                try:
                    save_incident(incident)
                    alert = should_alert(incident)
                    result.update({"alert": alert})
                except Exception as _es:
                    catch(_es, "core.multi_agent", "swallowed")
        except Exception as _es:
            catch(_es, "core.multi_agent", "swallowed")
        try:
            tasks_dict = [{"id": t.id, "status": t.status, "trace_id": t.trace_id, "result": t.result, "started_at": t.started_at, "finished_at": t.finished_at} for t in tasks]
            save_run_replay(root_id, result, log, tasks_dict)
        except Exception as _es:
            catch(_es, "core.multi_agent", "swallowed")
    except Exception as _es:
        catch(_es, "core.multi_agent", "swallowed")
    return result

def _check_dag_deadlock(tasks: list[AgentTask], wave_idx: int = 0, root_trace_id: str = "") -> str | None:
    """检查 DAG 死锁条件。返回描述字符串或 None（无死锁）。

    死锁条件：
    - 存在 pending 任务，但没有 running 任务 → 不可进展
    - 所有 pending 任务的依赖都是 failed → 级联失败
    """
    pending = [t for t in tasks if t.status == "pending"]
    running = [t for t in tasks if t.status == "running"]
    failed_ids = {t.id for t in tasks if t.status == "failed"}

    if pending and not running:
        # 检查是否所有 pending 任务都依赖了已失败的 task
        stuck = []
        for t in pending:
            deps = t.depends_on
            if deps and all(d in failed_ids for d in deps):
                stuck.append(t.id)
        if stuck and len(stuck) == len(pending):
            return (
                f"DAG deadlock: {len(pending)} tasks stuck "
                f"(all deps failed: {stuck[:5]}{'...' if len(stuck) > 5 else ''}) "
                f"[wave={wave_idx}, trace={root_trace_id[:12]}...]"
            )
        if not running:
            # 有 pending 但没有 running，且至少一个 pending 的依赖不可满足
            for t in pending:
                deps = t.depends_on
                unknown = [d for d in deps if d not in {x.id for x in tasks}]
                if unknown:
                    return (
                        f"DAG deadlock: task '{t.id}' depends on unknown tasks {unknown} "
                        f"[wave={wave_idx}, trace={root_trace_id[:12]}...]"
                    )
    return None


def _propagate_failed_deps(tasks: list[AgentTask], root_trace_id: str = "") -> int:
    """将上游 failed 的 task 的下游标记为 skipped。

    返回被 skip 的数量。
    """
    skipped = 0
    failed_ids = {t.id for t in tasks if t.status in ("failed", "skipped")}
    if not failed_ids:
        return 0
    for t in tasks:
        if t.status != "pending":
            continue
        if t.depends_on and any(d in failed_ids for d in t.depends_on):
            t.status = "skipped"
            t.result = "[skipped] upstream task failed"
            skipped += 1
    return skipped


def _topological_waves(tasks: list[AgentTask]) -> list[list[AgentTask]]:
    """把带依赖的任务列表分层为可并行的"波"。

    - 第 0 波：depends_on 为空（或依赖不在任务集中）的任务。
    - 第 k 波：所有依赖已在第 0..k-1 波出现过、且自身未分层的任务。
    - 同一波内的任务互不依赖，可 ``asyncio.gather`` 并行。

    检测到依赖环时抛 ``ValueError``（防止死锁）。
    检测到重复 ID 时抛 ``ValueError``（防止误报为环）。
    """
    # 重复 ID 检测：SmartDecomposer 的 LLM 输出可能产生重复 ID
    if len({t.id for t in tasks}) != len(tasks):
        from collections import Counter
        dupes = [tid for tid, cnt in Counter(t.id for t in tasks).items() if cnt > 1]
        raise ValueError(f"Duplicate task IDs detected: {dupes}")
    by_id = {t.id: t for t in tasks}
    placed: set[str] = set()
    waves: list[list[AgentTask]] = []

    while len(placed) < len(tasks):
        # 当前波：未分层且所有（已知）依赖均已分层的任务
        wave = [t for t in tasks if t.id not in placed and all(d in placed or d not in by_id for d in t.depends_on)]
        if not wave:
            # 剩余任务都无法满足依赖 → 存在环
            remaining = [t.id for t in tasks if t.id not in placed]
            raise ValueError(f"任务依赖存在环或不可满足: {remaining}")
        waves.append(wave)
        placed.update(t.id for t in wave)

    return waves


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
    ) -> dict:
        """使用模板并行分派 N 个同类型子智能体。

        Args:
            template: 提示模板，{{item}} 占位符会被替换为 items 中的值
            items: 每个 item 启动一个子智能体
            role: 子智能体角色
            max_concurrency: 最大并发数，默认 min(len(items), max_workers)

        Returns:
            dict: {item: result_str}
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
                goal = template.replace("{{item}}", item)
                f"swarm_{uuid.uuid4().hex[:8]}"
                coordinator = MultiAgentCoordinator(
                    tool_executor=self.execute_tool,
                    max_workers=1,
                    model_router=self.model_router,
                )
                coordinator.spawn_team([role])
                r = coordinator.execute(goal)
                with self._lock:
                    results[item] = (
                        f"done={r['tasks_done']}/{r['tasks_total']} failed={r['tasks_failed']}"
                        f" elapsed={r['elapsed']}s"
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

        return results


# ── Coordination entry points (backward-compatible) ──────────

_coordinator: MultiAgentCoordinator | None = None
_coordinator_lock = threading.Lock()


def _get_coordinator(tool_executor: Callable) -> MultiAgentCoordinator:
    global _coordinator
    if _coordinator is None:
        with _coordinator_lock:
            if _coordinator is None:
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
    results = swarm.dispatch(
        template=kwargs["template"],
        items=kwargs["items"],
        role=kwargs.get("role", "implementer"),
        max_concurrency=kwargs.get("max_concurrency"),
    )
    return json.dumps(results, ensure_ascii=False, indent=2)
