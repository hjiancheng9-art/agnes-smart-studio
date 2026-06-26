"""Multi-agent coordination engine -- parallel sub-agents with task dispatch.

Real coordination: task decomposition, parallel dispatch, result aggregation,
consensus voting, work stealing from stalled agents.

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
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "Agent",
    "AgentTask",
    "MultiAgentCoordinator",
    "ROOT",
    "coordinate",
    "AsyncMultiAgentCoordinator",
    "async_coordinate",
]

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class AgentTask:
    id: str
    description: str
    tool_sequence: list[dict] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    assigned_to: str = ""
    status: str = "pending"  # pending | running | done | failed | stolen
    result: str = ""
    started_at: float = 0
    finished_at: float = 0
    # ── 三级 tier 路由（对标 Claude Haiku/Sonnet/Opus）──
    # "auto": 由 ModelRouter 按 description/task_type 自动选模型
    # "light" / "pro" / "heavy": 显式指定 tier
    tier: str = "auto"
    task_type: str = ""  # 传给 ModelRouter.select() 的任务类型（tier=auto 时生效）


@dataclass
class Agent:
    id: str
    role: str  # "reviewer" | "debugger" | "implementer" | "tester"
    status: str = "idle"
    current_task: str = ""


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

    def spawn_team(self, roles: list[str] | None = None):
        """Create agent team. Default: reviewer, debugger, implementer, tester."""
        roles = roles or ["reviewer", "debugger", "implementer", "tester"]
        self.agents = [Agent(id=f"agent_{i}", role=role) for i, role in enumerate(roles[: self.max_workers])]

    def decompose(self, goal: str) -> list[AgentTask]:
        """Break a goal into agent-sized tasks with dependencies.

        实现已下沉到模块级 ``_decompose_goal``，同步/asyncio 两版共用同一份
        分解逻辑，避免漂移。
        """
        return _decompose_goal(goal)

    def execute(self, goal: str) -> dict:
        """Full execution: spawn -> decompose -> dispatch -> aggregate."""
        started = time.time()
        self._log = []
        self._results = {}

        if not self.agents:
            self.spawn_team()
        self.tasks = self.decompose(goal)
        self._log.append({"event": "decomposed", "tasks": len(self.tasks)})

        # Simple round-robin dispatch (parallel via threading)
        threads = []
        for task in self.tasks:
            agent = next((a for a in self.agents if a.status == "idle"), None)
            if not agent:
                # All busy, assign to first
                agent = self.agents[0]
            task.assigned_to = agent.id
            agent.status = "busy"
            agent.current_task = task.id
            t = threading.Thread(target=self._execute_task, args=(task,), daemon=True)
            threads.append(t)
            t.start()

        # Wait for all
        for t in threads:
            t.join(timeout=120)

        # 超时未完成的任务标记为 failed（不静默丢失）。
        # 读 task.status + 改写必须在锁内：工作线程 join 超时返回时可能仍在
        # 锁外持有 task 引用并即将写 status，整段检查-改写需原子。
        with self._lock:
            for task in self.tasks:
                if task.status == "running":
                    task.status = "failed"
                    task.result = f"Task timed out after 120s (agent: {task.assigned_to})"
                    task.finished_at = time.time()
                    self._log.append({"event": "task_timeout", "task": task.id, "agent": task.assigned_to})

            elapsed = time.time() - started
            done = sum(1 for t in self.tasks if t.status == "done")
            failed = sum(1 for t in self.tasks if t.status == "failed")

        return {
            "goal": goal,
            "agents": len(self.agents),
            "tasks_total": len(self.tasks),
            "tasks_done": done,
            "tasks_failed": failed,
            "elapsed": round(elapsed, 2),
            "results": self._results,
            "log": self._log[-10:],
        }

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
            self._log.append({"event": "task_start", "task": task.id, "agent": task.assigned_to})
            # tier 路由：若提供 model_router，按 task.tier/task_type 解析模型并注入 step
            resolved_model = self._resolve_model_for_task(task)
            if resolved_model:
                self._log.append({"event": "tier_routed", "task": task.id, "tier": task.tier, "model": resolved_model})
        results = []
        for step in task.tool_sequence:
            try:
                # 若解析出模型，注入到 step.args（LLM-backed executor 可读取）
                step_args = dict(step["args"])
                if resolved_model and "model" not in step_args:
                    step_args["model"] = resolved_model
                # execute_tool 是外部 I/O，不持锁（避免长任务阻塞主线程的锁内读）
                r = self.execute_tool(step["tool"], step_args)
                results.append(r[:200])
            except (OSError, ValueError, RuntimeError) as e:
                with self._lock:
                    task.status = "failed"
                    task.result = str(e)
                    self._log.append({"event": "task_failed", "task": task.id, "error": str(e)})
                return
        with self._lock:
            task.status = "done"
            task.result = "; ".join(results)
            task.finished_at = time.time()
            self._results[task.id] = task.result
            self._log.append({"event": "task_done", "task": task.id, "result_preview": task.result[:100]})


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

    async def execute(self, goal: str) -> dict:
        """Full async execution: spawn -> decompose -> dispatch -> aggregate。

        调度策略：拓扑分层。把 tasks 按 depends_on 分成若干"波"，
        每波内的任务无相互依赖 → ``asyncio.gather`` 并行；波与波之间串行 await，
        保证依赖在前置完成后才启动。
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
        await self._log_append({"event": "decomposed", "tasks": len(self.tasks)})

        # 拓扑分层：每层是可并行的任务集合
        waves = _topological_waves(self.tasks)
        for wave in waves:
            await asyncio.gather(*(self._execute_task(task) for task in wave))

        elapsed = time.time() - started
        done = sum(1 for t in self.tasks if t.status == "done")
        failed = sum(1 for t in self.tasks if t.status == "failed")

        return {
            "goal": goal,
            "agents": len(self.agents),
            "tasks_total": len(self.tasks),
            "tasks_done": done,
            "tasks_failed": failed,
            "elapsed": round(elapsed, 2),
            "results": self._results,
            "log": self._log[-10:],
        }

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

    async def _call_tool(self, tool: str, args: dict) -> str:
        """调用 executor，自动适配同步/async 签名。"""
        if inspect.iscoroutinefunction(self.execute_tool):
            return await self.execute_tool(tool, args)
        # 同步 executor → to_thread，避免阻塞事件循环
        return await asyncio.to_thread(self.execute_tool, tool, args)

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
            # 分配 agent（round-robin 选 idle，回退第一个；与同步版一致）
            agent = next((a for a in self.agents if a.status == "idle"), None)
            if agent is None:
                agent = self.agents[0] if self.agents else Agent(id="agent_0", role="solo")
            task.assigned_to = agent.id
            agent.status = "busy"
            agent.current_task = task.id

            task.status = "running"
            task.started_at = time.time()
            await self._log_append({"event": "task_start", "task": task.id, "agent": task.assigned_to})
            # tier 路由：若解析出模型，注入到 step.args
            resolved_model = self._resolve_model_for_task(task)
            if resolved_model:
                await self._log_append(
                    {"event": "tier_routed", "task": task.id, "tier": task.tier, "model": resolved_model}
                )

            results: list[str] = []
            for step in task.tool_sequence:
                try:
                    step_args = dict(step["args"])
                    if resolved_model and "model" not in step_args:
                        step_args["model"] = resolved_model
                    r = await self._call_tool(step["tool"], step_args)
                    results.append(str(r)[:200])
                except (OSError, ValueError, RuntimeError) as e:
                    task.status = "failed"
                    task.result = str(e)
                    await self._log_append({"event": "task_failed", "task": task.id, "error": str(e)})
                    agent.status = "idle"
                    agent.current_task = ""
                    return

            task.status = "done"
            task.result = "; ".join(results)
            task.finished_at = time.time()
            self._results[task.id] = task.result
            await self._log_append({"event": "task_done", "task": task.id, "result_preview": task.result[:100]})

            agent.status = "idle"
            agent.current_task = ""


async def async_coordinate(goal: str, tool_executor: Callable) -> dict:
    """asyncio 版顶层入口（对应同步版 ``coordinate``）。"""
    return await AsyncMultiAgentCoordinator(tool_executor).execute(goal)


# ── 模块级共享逻辑（decompose + 拓扑分层）──────────────────


def _decompose_goal(goal: str) -> list[AgentTask]:
    """任务分解的纯计算实现（同步/asyncio 两版共用，避免漂移）。

    与原 ``MultiAgentCoordinator.decompose`` 逻辑完全一致，仅下沉到模块级。
    """
    goal_lower = goal.lower()

    if "review" in goal_lower:
        return [
            AgentTask(
                "t1", "Read and analyze the target file", [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}]
            ),
            AgentTask(
                "t2",
                "Check for bugs and anti-patterns",
                [{"tool": "search_files", "args": {"pattern": "TODO|FIXME|HACK"}}],
                depends_on=["t1"],
            ),
            AgentTask("t3", "Run tests", [{"tool": "run_test", "args": {}}], depends_on=["t2"]),
            AgentTask(
                "t4",
                "Generate review report",
                [{"tool": "read_file", "args": {"path": "README.md"}}],
                depends_on=["t2", "t3"],
            ),
        ]

    if "debug" in goal_lower or "fix" in goal_lower:
        return [
            AgentTask("t1", "Check error logs", [{"tool": "read_file", "args": {"path": "output/last_error.txt"}}]),
            AgentTask(
                "t2",
                "Search for related code",
                [{"tool": "search_files", "args": {"pattern": "error|exception|fail"}}],
                depends_on=["t1"],
            ),
            AgentTask(
                "t3", "Identify root cause", [{"tool": "read_file", "args": {"path": "PLACEHOLDER"}}], depends_on=["t2"]
            ),
            AgentTask("t4", "Apply fix and verify", [{"tool": "run_test", "args": {}}], depends_on=["t3"]),
        ]

    # Default: investigate -> understand -> act -> verify
    return [
        AgentTask("t1", "Understand the codebase", [{"tool": "read_file", "args": {"path": "README.md"}}]),
        AgentTask(
            "t2",
            "Find relevant files",
            [{"tool": "search_files", "args": {"pattern": goal.split()[0] if goal.split() else "main"}}],
            depends_on=["t1"],
        ),
        AgentTask("t3", "Execute the task", [{"tool": "env_check", "args": {}}], depends_on=["t2"]),
        AgentTask("t4", "Verify results", [{"tool": "run_test", "args": {}}], depends_on=["t3"]),
    ]


def _topological_waves(tasks: list[AgentTask]) -> list[list[AgentTask]]:
    """把带依赖的任务列表分层为可并行的"波"。

    - 第 0 波：depends_on 为空（或依赖不在任务集中）的任务。
    - 第 k 波：所有依赖已在第 0..k-1 波出现过、且自身未分层的任务。
    - 同一波内的任务互不依赖，可 ``asyncio.gather`` 并行。

    检测到依赖环时抛 ``ValueError``（防止死锁）。
    """
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
