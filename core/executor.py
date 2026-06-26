"""Autonomous task executor -- plan, execute, verify loop.

The engine that turns a natural-language task into a sequence of tool calls
with dependency tracking, error recovery, and verification gates.

Lifecycle:
    1. PLAN   — decompose task into ordered steps with dependencies
    2. EXECUTE — run each step with its tool, track state, recover from errors
    3. VERIFY  — run tests / syntax checks, confirm the goal is met
    4. REPORT  — return structured result with evidence

两条实现共存：
- ``TaskExecutor`` / ``run`` —— **同步版**（顺序执行，保留兼容）。
- ``AsyncTaskExecutor`` / ``arun`` —— **asyncio 原生版**（Phase 6.3 新增）。
  独立步骤并行执行（``asyncio.Semaphore`` 限并发），按 ``depends_on``
  拓扑调度，同步 executor 自动 ``asyncio.to_thread`` 包装。

两版共享 ``Step`` / ``Task`` 数据类（纯数据，无 I/O）。
"""

from __future__ import annotations

import asyncio
import datetime
import inspect
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

__all__ = [
    "ROOT",
    "Step",
    "Task",
    "TaskExecutor",
    "AsyncTaskExecutor",
    "Goal",
    "GoalManager",
    "quick_plan",
    "execute_plan_tool",
    "async_execute_plan_tool",
    "create_goal_tool",
    "get_goal_tool",
    "set_goal_budget_tool",
    "update_goal_tool",
]

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Step:
    id: str
    description: str
    tool: str
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    verify: str | None = None  # "syntax" | "test" | None
    status: str = "pending"  # pending | running | done | failed | skipped
    result: str = ""
    error: str = ""


@dataclass
class Task:
    id: str
    goal: str
    steps: list[Step] = field(default_factory=list)
    status: str = "pending"
    errors_allowed: int = 0


class TaskExecutor:
    """Executes a decomposed task with dependency tracking and verification."""

    def __init__(self, tool_executor: Callable, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.execute_tool = tool_executor  # (tool_name, args) -> result_str
        self._log: list[dict] = []

    def run(self, task: Task) -> dict:
        """Run all steps in dependency order. Returns final report."""
        start_ts = time.time()
        task.status = "running"
        errors = 0

        for step in task.steps:
            # ── Goal 预算门 ──
            try:
                from core.executor import _get_goal_manager as _gm
                if not _gm().record_step():
                    step.status = "skipped"
                    step.error = "Goal budget exhausted (max steps reached)"
                    continue
            except (ImportError, OSError):
                pass

            ready = all(any(s.id == dep and s.status == "done" for s in task.steps) for dep in step.depends_on)
            if not ready:
                step.status = "skipped"
                step.error = f"Dependencies not met: {step.depends_on}"
                continue

            step.status = "running"
            self._log.append({"ts": time.time(), "step": step.id, "event": "start"})
            try:
                result = self.execute_tool(step.tool, step.args)
                step.result = result[:500]
                step.status = "done"
                # ── Goal 工具调用计数 ──
                try:
                    from core.executor import _get_goal_manager as _gm2
                    _gm2().record_tool_call()
                except (ImportError, OSError):
                    pass
                self._log.append({"ts": time.time(), "step": step.id, "event": "done", "result_preview": result[:100]})
            except (OSError, ValueError, RuntimeError) as e:
                step.error = f"{type(e).__name__}: {e}"
                step.status = "failed"
                errors += 1
                self._log.append({"ts": time.time(), "step": step.id, "event": "failed", "error": step.error})
                if errors > task.errors_allowed:
                    break

            # Verification
            if step.verify == "syntax":
                try:
                    import ast

                    # 限制范围: 只检查 core/ 和相关目录, 不扫描全项目
                    _scan_dirs = [
                        d for d in (self.root / "core", self.root / "engines", self.root / "pipeline")
                        if d.exists()
                    ]
                    if not _scan_dirs:
                        _scan_dirs = [self.root / "core"]
                    for sd in _scan_dirs:
                        for pf in sd.rglob("*.py"):
                            if "__pycache__" not in pf.parts:
                                ast.parse(pf.read_text(encoding="utf-8"))
                    self._log.append({"ts": time.time(), "step": step.id, "event": "verify_syntax_ok"})
                except SyntaxError as se:
                    step.status = "failed"
                    step.error = f"Syntax check failed: {se}"
                    errors += 1
                    break
            elif step.verify and step.verify.startswith("test"):
                # test 或 test:<target_path> 格式
                target = step.verify.split(":", 1)[1] if ":" in step.verify else "tests/"
                from core.pytest_runner import run_pytest_safe

                r = run_pytest_safe(test_target=target, timeout=30, cwd=self.root)
                # 用 exit_code 判断，比字符串匹配更可靠
                if r.returncode != 0:
                    out = r.stdout or r.stderr or ""
                    step.status = "failed"
                    step.error = f"Tests failed (exit={r.returncode}): {out[-200:]}"
                    errors += 1
                    break
                self._log.append({"ts": time.time(), "step": step.id, "event": "verify_tests_ok"})

        elapsed = time.time() - start_ts
        all_done = all(s.status == "done" for s in task.steps)
        task.status = "done" if all_done else "failed" if errors > 0 else "partial"

        return {
            "goal": task.goal,
            "status": task.status,
            "elapsed": round(elapsed, 2),
            "steps_total": len(task.steps),
            "steps_done": sum(1 for s in task.steps if s.status == "done"),
            "steps_failed": sum(1 for s in task.steps if s.status == "failed"),
            "steps_skipped": sum(1 for s in task.steps if s.status == "skipped"),
            "details": [
                {"id": s.id, "status": s.status, "error": s.error, "result_preview": s.result[:100]}
                for s in task.steps
                if s.status != "done"
            ],
            "log": self._log[-10:],
        }


class AsyncTaskExecutor:
    """asyncio 原生版 TaskExecutor — 独立步骤并行执行 + 拓扑依赖调度。

    与同步版 TaskExecutor 共享 Step/Task 数据类。差异：
    - 独立步骤（无 depends_on 或依赖已满足）使用 asyncio.Semaphore 并行调度
    - 同步 tool_executor 自动 asyncio.to_thread 包装
    - 异步 tool_executor 直接 await
    - verify 步骤走 asyncio.to_thread（run_pytest_safe 是同步 subprocess）
    """

    def __init__(
        self,
        tool_executor: Callable,
        root: Path | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.root = root or ROOT
        self.execute_tool = tool_executor  # sync or async (tool_name, args) -> result_str
        self._log: list[dict] = []
        self._sem = asyncio.Semaphore(max_concurrency)
        self._is_async = inspect.iscoroutinefunction(tool_executor)
        self._lock = asyncio.Lock()  # protects _log + error count
        self._break_event = asyncio.Event()

    async def _call_tool(self, tool: str, args: dict) -> str:
        """调用 tool executor，自动区分同步/异步。"""
        if self._is_async:
            return await self.execute_tool(tool, args)
        return await asyncio.to_thread(self.execute_tool, tool, args)

    async def _run_step(self, step: Step, task: Task) -> None:
        """执行单个 step（含依赖检查、验证门、错误计数）。"""
        # 依赖检查
        ready = all(any(s.id == dep and s.status == "done" for s in task.steps) for dep in step.depends_on)
        if not ready:
            step.status = "skipped"
            step.error = f"Dependencies not met: {step.depends_on}"
            async with self._lock:
                self._log.append({"ts": time.time(), "step": step.id, "event": "skipped", "reason": step.error})
            return

        if self._break_event.is_set():
            step.status = "skipped"
            step.error = "Pipeline terminated due to error budget exceeded"
            return

        step.status = "running"
        async with self._lock:
            self._log.append({"ts": time.time(), "step": step.id, "event": "start"})

        async with self._sem:
            try:
                result = await self._call_tool(step.tool, step.args)
                step.result = result[:500]
                step.status = "done"
                async with self._lock:
                    self._log.append(
                        {"ts": time.time(), "step": step.id, "event": "done", "result_preview": result[:100]}
                    )
            except (OSError, ValueError, RuntimeError) as e:
                step.error = f"{type(e).__name__}: {e}"
                step.status = "failed"
                async with self._lock:
                    self._log.append({"ts": time.time(), "step": step.id, "event": "failed", "error": step.error})
                return  # don't verify on failure

        # Verification (outside semaphore — gate checks are lightweight)
        if step.verify == "syntax":
            await self._verify_syntax(step)
        elif step.verify == "test":
            await self._verify_tests(step)

    async def _verify_syntax(self, step: Step) -> None:
        """在 asyncio.to_thread 中做 ast.parse 语法验证（限制范围）。"""
        try:

            def _check():
                import ast

                _scan_dirs = [
                    d for d in (self.root / "core", self.root / "engines", self.root / "pipeline")
                    if d.exists()
                ]
                if not _scan_dirs:
                    _scan_dirs = [self.root / "core"]
                # Also scan root-level .py files
                _root_pys = list(self.root.glob("*.py"))
                for pf in _root_pys:
                    if "__pycache__" not in pf.parts:
                        ast.parse(pf.read_text(encoding="utf-8"))
                for sd in _scan_dirs:
                    for pf in sd.rglob("*.py"):
                        if "__pycache__" not in pf.parts:
                            ast.parse(pf.read_text(encoding="utf-8"))

            await asyncio.to_thread(_check)
            async with self._lock:
                self._log.append({"ts": time.time(), "step": step.id, "event": "verify_syntax_ok"})
        except SyntaxError as se:
            step.status = "failed"
            step.error = f"Syntax check failed: {se}"
            async with self._lock:
                self._log.append(
                    {"ts": time.time(), "step": step.id, "event": "verify_syntax_failed", "error": step.error}
                )

    async def _verify_tests(self, step: Step) -> None:
        """在 asyncio.to_thread 中调用 run_pytest_safe。支持 test:<target> 格式。"""
        from core.pytest_runner import run_pytest_safe

        verify = step.verify or ""
        target = verify.split(":", 1)[1] if ":" in verify else "tests/"

        r = await asyncio.to_thread(
            run_pytest_safe,
            test_target=target,
            timeout=30,
            cwd=self.root,
        )
        if r.returncode != 0:
            out = r.stdout or r.stderr or ""
            step.status = "failed"
            step.error = f"Tests failed (exit={r.returncode}): {out[-200:]}"
            async with self._lock:
                self._log.append(
                    {"ts": time.time(), "step": step.id, "event": "verify_tests_failed", "error": step.error}
                )
        else:
            async with self._lock:
                self._log.append({"ts": time.time(), "step": step.id, "event": "verify_tests_ok"})

    async def arun(self, task: Task) -> dict:
        """并行执行所有步骤（拓扑依赖感知），返回结构化报告。

        执行策略：将所有 step 提交为 asyncio.Task，依赖检查在每个
        task 内部完成。通过 _break_event 在错误预算耗尽时提前终止
        尚未启动的 step。
        """
        start_ts = time.time()
        task.status = "running"
        self._break_event.clear()
        errors = 0

        async def _exec_step(step: Step) -> None:
            nonlocal errors
            await self._run_step(step, task)
            if step.status == "failed":
                async with self._lock:
                    errors += 1
                    if errors > task.errors_allowed:
                        self._break_event.set()

        # 拓扑 waves：按依赖层级分批，同层并行，层间串行
        # 比 fire-all-happen 更安全：保证同层 step 看到一致的依赖状态
        executed: set[str] = set()
        remaining = list(task.steps)
        waves: list[list[Step]] = []

        while remaining:
            wave = []
            still_remaining = []
            for step in remaining:
                deps = set(step.depends_on)
                if deps.issubset(executed):
                    wave.append(step)
                else:
                    still_remaining.append(step)
            if not wave:
                # 无法继续：剩余 step 的依赖无法满足（循环依赖或缺失）
                for step in still_remaining:
                    step.status = "skipped"
                    step.error = f"Unresolvable dependencies: {step.depends_on}"
                break
            waves.append(wave)
            executed.update(s.id for s in wave)
            remaining = still_remaining

        for wave in waves:
            if self._break_event.is_set():
                for step in wave:
                    step.status = "skipped"
                    step.error = "Pipeline terminated due to error budget exceeded"
                break
            await asyncio.gather(*[_exec_step(s) for s in wave])
            # wave 完成后检查 break
            if self._break_event.is_set():
                continue

        elapsed = time.time() - start_ts
        all_done = all(s.status == "done" for s in task.steps)
        task.status = "done" if all_done else "failed" if errors > 0 else "partial"

        return {
            "goal": task.goal,
            "status": task.status,
            "elapsed": round(elapsed, 2),
            "steps_total": len(task.steps),
            "steps_done": sum(1 for s in task.steps if s.status == "done"),
            "steps_failed": sum(1 for s in task.steps if s.status == "failed"),
            "steps_skipped": sum(1 for s in task.steps if s.status == "skipped"),
            "details": [
                {"id": s.id, "status": s.status, "error": s.error, "result_preview": s.result[:100]}
                for s in task.steps
                if s.status != "done"
            ],
            "log": self._log[-10:],
        }


def quick_plan(goal: str) -> Task:
    """Generate a simple plan for common task patterns (no LLM needed)."""
    goal_lower = goal.lower()
    steps = []

    # Pattern: fix bug
    if "fix" in goal_lower or "bug" in goal_lower or "repair" in goal_lower:
        steps = [
            Step("1_read_error", "Read error log", "read_file", {"path": "output/last_error.txt"}),
            Step(
                "2_search_code",
                "Search for related code",
                "search_files",
                {"pattern": goal.split()[-1] if goal.split() else "TODO"},
            ),
            Step(
                "3_fix",
                "Apply fix",
                "edit_file",
                {"path": "PLACEHOLDER", "old_text": "PLACEHOLDER", "new_text": "PLACEHOLDER"},
                depends_on=["2_search_code"],
            ),
            Step("4_verify", "Verify syntax", "env_check", {}, verify="syntax", depends_on=["3_fix"]),
        ]

    # Pattern: audit / check
    if "audit" in goal_lower or "check" in goal_lower or "scan" in goal_lower:
        steps = [
            Step("1_audit", "Run self-audit", "env_check", {}),
            Step("2_tests", "Run tests", "run_test", {}, verify="test", depends_on=["1_audit"]),
        ]

    # Pattern: test
    if "test" in goal_lower:
        steps = [
            Step("1_test", "Run test suite", "run_test", {}, verify="test"),
        ]

    if not steps:
        steps = [
            Step("1_understand", "Analyze the goal", "read_file", {"path": "README.md"}),
            Step("2_verify", "Verify environment", "env_check", {}),
        ]

    return Task(id=f"task_{int(time.time())}", goal=goal, steps=steps, errors_allowed=1)


def execute_plan_tool(goal: str, steps: str, root: str | None = None) -> str:
    """tools.json 适配入口：接受 JSON steps 字符串，构造 Task 并执行。

    LLM 在 agent 模式下通过 execute_plan 工具调用此函数，传入结构化计划，
    由 TaskExecutor 自主跑完所有步骤（依赖排序、错误追踪、语法/测试校验门）
    并返回结构化报告。不需要 LLM 自己逐个调工具。
    """
    import json

    from core.tools import get_registry

    registry = get_registry()
    registry.load(mcp=True)

    step_list = [Step(**s) for s in json.loads(steps)]
    task = Task(id=f"plan_{int(time.time())}", goal=goal, steps=step_list, errors_allowed=1)
    executor = TaskExecutor(
        tool_executor=lambda name, args: registry.execute(name, args),
        root=Path(root) if root else ROOT,
    )
    result = executor.run(task)
    return json.dumps(result, ensure_ascii=False, indent=2)


async def async_execute_plan_tool(goal: str, steps: str, root: str | None = None) -> str:
    """tools.json 适配入口 — asyncio 原生版。

    与 execute_plan_tool 对应，使用 AsyncTaskExecutor 实现并行步骤执行。
    供 AsyncChatSession / asyncio runtime 直接 await。
    """
    import json

    from core.tools import get_registry

    registry = get_registry()
    registry.load(mcp=True)

    step_list = [Step(**s) for s in json.loads(steps)]
    task = Task(id=f"plan_{int(time.time())}", goal=goal, steps=step_list, errors_allowed=1)
    executor = AsyncTaskExecutor(
        tool_executor=lambda name, args: registry.execute(name, args),
        root=Path(root) if root else ROOT,
    )
    result = await executor.arun(task)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════
# Goal Mode — 借鉴 Kimi Code Goal Mode
# 将模糊意图转化为明确完成契约，含预算管理 + 停止规则
# ═══════════════════════════════════════════════════════════════════

_GOALS_FILE = ROOT / "output" / "goals.json"


@dataclass
class Goal:
    """A goal-mode task with clear finish line, boundaries, and budget."""

    id: str
    intent: str
    finish_line: str = ""
    boundaries: str = ""
    status: str = "active"  # active | paused | completed | cancelled
    max_steps: int = 20
    max_tool_calls: int = 100
    max_duration_seconds: int = 0  # 0 = unlimited
    steps_executed: int = 0
    tool_calls_made: int = 0
    created_at: str = ""
    updated_at: str = ""
    evidence: str = ""

    def is_budget_exhausted(self) -> bool:
        return self.steps_executed >= self.max_steps or self.tool_calls_made >= self.max_tool_calls

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        return cls(**data)


class GoalManager:
    """Persistent goal manager backed by a JSON file.

    借鉴 Kimi Code 的 CreateGoal / GetGoal / SetGoalBudget / UpdateGoal 理念，
    用 Python dataclass + JSON 实现，与 task_manager 风格一致。
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _GOALS_FILE
        self._goals: dict[str, Goal] = {}
        self._active_goal_id: str = ""
        self._next_id: int = 1
        self._lock = threading.RLock()
        self._load()

    def create(self, intent: str, finish_line: str = "", boundaries: str = "", max_steps: int = 20) -> Goal:
        with self._lock:
            gid = f"goal-{self._next_id:03d}"
            self._next_id += 1
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            goal = Goal(
                id=gid,
                intent=intent,
                finish_line=finish_line,
                boundaries=boundaries,
                max_steps=max_steps,
                created_at=now,
                updated_at=now,
            )
            self._goals[gid] = goal
            if not self._active_goal_id:
                self._active_goal_id = gid
            self._save()
            return goal

    def get(self, goal_id: str = "") -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            return self._goals.get(gid)

    def set_budget(
        self,
        goal_id: str = "",
        max_steps: int | None = None,
        max_tool_calls: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            goal = self._goals.get(gid)
            if goal is None:
                return None
            if max_steps is not None:
                goal.max_steps = max_steps
            if max_tool_calls is not None:
                goal.max_tool_calls = max_tool_calls
            if max_duration_seconds is not None:
                goal.max_duration_seconds = max_duration_seconds
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return goal

    def update(self, goal_id: str = "", status: str = "", evidence: str = "") -> Goal | None:
        with self._lock:
            gid = goal_id or self._active_goal_id
            goal = self._goals.get(gid)
            if goal is None:
                return None
            if status:
                goal.status = status
            if evidence:
                goal.evidence = evidence
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return goal

    def record_step(self) -> bool:
        """Record a step execution; returns True if budget still available."""
        with self._lock:
            goal = self._goals.get(self._active_goal_id)
            if goal is None:
                return True
            goal.steps_executed += 1
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return not goal.is_budget_exhausted()

    def record_tool_call(self) -> bool:
        """Record a tool call; returns True if budget still available."""
        with self._lock:
            goal = self._goals.get(self._active_goal_id)
            if goal is None:
                return True
            goal.tool_calls_made += 1
            goal.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._save()
            return not goal.is_budget_exhausted()

    def _save(self) -> None:
        data = {
            "goals": [g.to_dict() for g in self._goals.values()],
            "active_goal_id": self._active_goal_id,
            "next_id": self._next_id,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        self._next_id = data.get("next_id", 1)
        self._active_goal_id = data.get("active_goal_id", "")
        for gd in data.get("goals", []):
            try:
                goal = Goal.from_dict(gd)
                self._goals[goal.id] = goal
            except (TypeError, KeyError):
                continue


# ── Module-level singleton ──────────────────────────────────

_goal_manager: GoalManager | None = None


def _get_goal_manager() -> GoalManager:
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager


# ── Tool-calling entry points (tools.json 引用) ─────────────


def create_goal_tool(
    intent: str,
    finish_line: str = "",
    boundaries: str = "",
    max_steps: int = 20,
) -> str:
    """Create a new goal-mode task. 借鉴 Kimi Code CreateGoal."""
    mgr = _get_goal_manager()
    goal = mgr.create(intent, finish_line, boundaries, max_steps)
    return json.dumps(
        {"ok": True, "goal_id": goal.id, "intent": goal.intent, "max_steps": goal.max_steps},
        ensure_ascii=False,
    )


def get_goal_tool(goal_id: str = "") -> str:
    """Get full goal status. 借鉴 Kimi Code GetGoal."""
    mgr = _get_goal_manager()
    goal = mgr.get(goal_id)
    if goal is None:
        return json.dumps({"ok": False, "error": "Goal not found"}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "goal": goal.to_dict(),
            "budget_remaining": {
                "steps": goal.max_steps - goal.steps_executed,
                "tool_calls": goal.max_tool_calls - goal.tool_calls_made,
                "exhausted": goal.is_budget_exhausted(),
            },
        },
        ensure_ascii=False,
    )


def set_goal_budget_tool(
    goal_id: str = "",
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
    max_duration_seconds: int | None = None,
) -> str:
    """Set or adjust goal budget. 借鉴 Kimi Code SetGoalBudget."""
    mgr = _get_goal_manager()
    goal = mgr.set_budget(goal_id, max_steps, max_tool_calls, max_duration_seconds)
    if goal is None:
        return json.dumps({"ok": False, "error": "Goal not found"}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "goal_id": goal.id,
            "budget": {
                "max_steps": goal.max_steps,
                "max_tool_calls": goal.max_tool_calls,
                "max_duration_seconds": goal.max_duration_seconds,
            },
        },
        ensure_ascii=False,
    )


def update_goal_tool(goal_id: str = "", status: str = "", evidence: str = "") -> str:
    """Update goal status. 借鉴 Kimi Code UpdateGoal."""
    mgr = _get_goal_manager()
    goal = mgr.update(goal_id, status, evidence)
    if goal is None:
        return json.dumps({"ok": False, "error": "Goal not found"}, ensure_ascii=False)
    return json.dumps(
        {"ok": True, "goal_id": goal.id, "status": goal.status, "evidence": goal.evidence},
        ensure_ascii=False,
    )
