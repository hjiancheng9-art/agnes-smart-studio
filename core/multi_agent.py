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


from core.multi_agent_modes import (
    AgentMode,
    AgentModeResult,
    SessionContext,
    _agent_mode_history,
    ambiguity_score,
    build_context_state,
    compute_agent_mode,
    decomposability_score,
    failure_score,
    file_scope_score,
    get_mode_statistics,
    keyword_score,
    length_score,
    record_agent_mode_result,
    risk_score,
    should_use_multi_agent,
    simplicity_score,
)


import logging

from core.error_sink import catch

logger = logging.getLogger("crux.multi_agent")
import asyncio

# 跨模块 trace 上下文：供 cost_tracker 等下游模块读取当前 root_trace_id
import contextvars as _crux_ctx
import inspect
import json
import threading
import time
import uuid
from collections.abc import Callable

from core.multi_agent_models import ROOT, Agent, AgentTask

_current_root_trace_id = _crux_ctx.ContextVar("crux_root_trace_id", default="")
_current_trace_id = _crux_ctx.ContextVar("crux_trace_id", default="")


def get_current_root_trace_id() -> str:
    """获取当前执行的 root_trace_id，供下游模块（cost_tracker/observability）使用。"""
    return _current_root_trace_id.get()


def get_current_trace_id() -> str:
    """获取当前 AgentTask 的 trace_id，供下游模块使用。"""
    return _current_trace_id.get()


__all__ = [
    "AGENT_SWARM_TOOL_DEF",
    "ROOT",
    "Agent",
    "AgentMode",
    "AgentModeResult",
    "AgentSwarm",
    "AgentTask",
    "AsyncMultiAgentCoordinator",
    "MultiAgentCoordinator",
    "SmartDecomposer",
    "_exec_agent_swarm",
    "ambiguity_score",
    "async_coordinate",
    "build_context_state",
    "compute_agent_mode",
    "coordinate",
    "failure_score",
    "file_scope_score",
    "get_mode_statistics",
    "keyword_score",
    "length_score",
    "record_agent_mode_result",
    "risk_score",
    "should_use_multi_agent",
    "simplicity_score",
]


# ── 同步版（threading + Lock，保留兼容）─────────────────────


class MultiAgentCoordinator:
    """Orchestrates multiple agents to solve a complex task (threading 版).

    .. deprecated::
        仅保留向后兼容。``coordinate()`` 现已委托给 ``AsyncMultiAgentCoordinator``
        （拓扑排序 + DAG 依赖感知）。新代码应直接使用 ``async_coordinate()``。
        此类忽略 ``depends_on``，仅做 round-robin 调度。
    """

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
                agent.context_history.append(
                    {
                        "ts": time.time(),
                        "event": "new_goal",
                        "goal": new_goal,
                    }
                )
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
        agent.context_history.append(
            {
                "ts": time.time(),
                "event": "spawned",
                "goal": goal,
            }
        )

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
                            self._log.append(
                                {
                                    "event": "task_failed",
                                    "task": task.id,
                                    "trace_id": task.trace_id,
                                    "root_trace_id": task.root_trace_id,
                                    "error": error_str,
                                    "failure_type": ftype,
                                    "suggestion": suggestion,
                                    "consecutive_failures": sum(1 for t in self.tasks if t.status == "failed"),
                                }
                            )
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
                agent.context_history.append(
                    {
                        "ts": time.time(),
                        "event": "completed",
                        "goal": goal,
                    }
                )
        except Exception as e:
            with self._lock:
                agent.status = "failed"
                agent.context_history.append(
                    {
                        "ts": time.time(),
                        "event": "error",
                        "error": str(e),
                    }
                )

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
        for task, t in zip(self.tasks, threads, strict=False):
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
                    self._log.append(
                        {
                            "event": "task_timeout",
                            "task": task.id,
                            "trace_id": task.trace_id,
                            "root_trace_id": task.root_trace_id,
                            "agent": task.assigned_to,
                            "timeout": to,
                        }
                    )

            # ── DAG runtime guard ────────────────────────────────────
            _propagate_failed_deps(self.tasks, root_trace_id=root_id)
            deadlock_msg = _check_dag_deadlock(self.tasks, root_trace_id=root_id)
            if deadlock_msg:
                self._log.append({"event": "dag_deadlock", "deadlock": deadlock_msg, "root_trace_id": root_id})

            time.time() - started
            sum(1 for t in self.tasks if t.status == "done")
            sum(1 for t in self.tasks if t.status == "failed")

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
            self._log.append(
                {
                    "event": "task_start",
                    "task": task.id,
                    "agent": task.assigned_to,
                    "trace_id": task.trace_id,
                    "root_trace_id": task.root_trace_id,
                }
            )
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
                        self._log.append(
                            {
                                "event": "task_failed",
                                "task": task.id,
                                "error": error_str,
                                "failure_type": ftype,
                                "suggestion": suggestion,
                            }
                        )
                    except ImportError:
                        self._log.append({"event": "task_failed", "task": task.id, "error": error_str})
                return
        with self._lock:
            task.status = "done"
            task.result = "; ".join(results)
            task.finished_at = time.time()
            self._results[task.id] = task.result
            self._log.append(
                {
                    "event": "task_done",
                    "task": task.id,
                    "trace_id": task.trace_id,
                    "root_trace_id": task.root_trace_id,
                    "result_preview": task.result[:100],
                }
            )


def coordinate(goal: str, tool_executor: Callable) -> dict:
    """Sync entry point — delegates to AsyncMultiAgentCoordinator for DAG-aware scheduling.

    The old sync MultiAgentCoordinator only did round-robin and ignored task
    dependencies. This wrapper runs the async version (which does proper
    topological scheduling) via asyncio.run(), so callers get better scheduling
    without changing their sync API.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
        # Already in an event loop — run in a separate thread to avoid nested loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, async_coordinate(goal, tool_executor)).result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        return asyncio.run(async_coordinate(goal, tool_executor))


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

    _AUTO_TASK_TIMEOUT = 240  # seconds per task — prevents infinite-hang deadlock in multi-agent waves
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
                    await self._log_append(
                        {
                            "event": "task_timeout",
                            "task": task.id,
                            "trace_id": task.trace_id,
                            "root_trace_id": task.root_trace_id,
                            "timeout": task_timeout,
                            "wave": _wave_idx,
                        }
                    )

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

        time.time() - started
        sum(1 for t in self.tasks if t.status == "done")
        sum(1 for t in self.tasks if t.status == "failed")

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
                await self._log_append(
                    {
                        "event": "task_start",
                        "task": task.id,
                        "agent": task.assigned_to,
                        "trace_id": task.trace_id,
                        "root_trace_id": task.root_trace_id,
                    }
                )
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
                        r = await self._call_tool(
                            step["tool"], step_args, trace_id=task.trace_id, root_trace_id=task.root_trace_id
                        )
                        results.append(str(r)[:200])
                    except Exception as e:
                        task.status = "failed"
                        task.result = str(e)
                        await self._log_append(
                            {
                                "event": "task_failed",
                                "task": task.id,
                                "trace_id": task.trace_id,
                                "root_trace_id": task.root_trace_id,
                                "error": str(e),
                            }
                        )
                        agent.current_task = ""
                        return

                task.status = "done"
                task.result = "; ".join(results)
                task.finished_at = time.time()
                self._results[task.id] = task.result
                await self._log_append(
                    {
                        "event": "task_done",
                        "task": task.id,
                        "trace_id": task.trace_id,
                        "root_trace_id": task.root_trace_id,
                        "result_preview": task.result[:100],
                    }
                )

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


from core.multi_agent_decompose import (
    SmartDecomposer,
    _build_run_summary,
    _check_dag_deadlock,
    _decompose_goal,
    _keyword_decompose,
    _propagate_failed_deps,
    _topological_waves,
)


from core.multi_agent_swarm import (
    AGENT_SWARM_TOOL_DEF,
    AgentSwarm,
    _exec_agent_swarm,
)


