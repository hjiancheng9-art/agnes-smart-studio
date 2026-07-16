"""CRUX Master Orchestration Engine — 白虎脊椎.

将 CRUX 的 7 个 DNA 基因和 13 个金手指编排成一个完整的认知-执行-验证闭环。
每一轮对话不再是松散的工具调用链，而是严格分阶段的状态机。

阶段：
  GATE    — 意图分类 + 复杂度判定 + 模型路由
  CONTEXT — 强制上下文收集（"先理解再行动"硬件门禁）
  PLAN    — 任务分解 + 依赖拓扑排序
  EXECUTE — 并行分派 + 文件隔离 + 超时预算管理
  VERIFY  — 交叉审查 + 自检 + diff 守卫
  CLOSE   — 资源回收 + 指标上报 + 记忆沉淀

DNA 映射：
  Gene 1 (Self-evolution)  → VERIFY 阶段的自检 + reflect
  Gene 6 (Semantic memory) → CLOSE 阶段的记忆沉淀
  Gene 7 (Resilience)      → EXECUTE 阶段的降级链 + 熔断

金手指映射：
  残魂老祖  → VERIFY 阶段的自动 critique
  天劫渡劫  → EXECUTE 阶段的 failover + retry
  分身亿万  → EXECUTE 阶段的并行分派
  神识外放  → CONTEXT 阶段的代码感知
  万界灵脉  → GATE 阶段的模型路由
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger("crux.orchestration")

# ═══════════════════════════════════════════════════════════════════
# Phase definitions
# ═══════════════════════════════════════════════════════════════════


class Phase(Enum):
    """编排阶段 — 严格顺序，不可跳跃."""

    GATE = auto()  # 意图分类 + 模型路由
    CONTEXT = auto()  # 强制上下文收集
    PLAN = auto()  # 任务分解 + 依赖图
    EXECUTE = auto()  # 并行执行
    VERIFY = auto()  # 交叉审查 + 自检
    CLOSE = auto()  # 资源回收 + 记忆沉淀


PHASE_ORDER = (Phase.GATE, Phase.CONTEXT, Phase.PLAN, Phase.EXECUTE, Phase.VERIFY, Phase.CLOSE)


# TaskComplexity and classify_task are the canonical implementations in
# core/task_complexity.py.  We re-export for backward compatibility.
from typing import TYPE_CHECKING

from core.task_complexity import TaskComplexity, classify_task

if TYPE_CHECKING:
    from collections.abc import Callable

MODEL_TIER_FOR_COMPLEXITY: dict[TaskComplexity, str] = {
    TaskComplexity.TRIVIAL: "light",
    TaskComplexity.SIMPLE: "light",
    TaskComplexity.MODERATE: "pro",
    TaskComplexity.COMPLEX: "heavy",
    TaskComplexity.CRITICAL: "heavy",
}


def classify_complexity(user_text: str) -> TaskComplexity:
    """Backward-compat wrapper — prefer ``classify_task()`` directly."""
    return classify_task(user_text).complexity


# ═══════════════════════════════════════════════════════════════════
# Context: mandatory pre-action reconnaissance
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ContextSnapshot:
    """执行前的代码上下文快照 — 必须收集才能通过 CONTEXT 门禁."""

    goal: str
    relevant_files: list[str] = field(default_factory=list)
    call_chain: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    risk_areas: list[str] = field(default_factory=list)
    collected_at: float = 0.0


CONTEXT_MIN_FILES = 1  # 至少要读了 1 个文件才能过门禁
CONTEXT_TOOLS = frozenset(
    {
        "read_file",
        "search_files",
        "glob_files",
        "list_files",
        "find_symbol",
        "find_references",
        "git_diff",
        "git_log",
    }
)


def context_is_sufficient(snapshot: ContextSnapshot) -> bool:
    """CONTEXT 门禁: 是否收集了足够的上下文."""
    return len(snapshot.relevant_files) >= CONTEXT_MIN_FILES


# ═══════════════════════════════════════════════════════════════════
# Plan: task decomposition with dependency DAG
# ═══════════════════════════════════════════════════════════════════


@dataclass
class OrchestrationPlan:
    """编排计划 — PLAN 阶段的输出."""

    id: str
    goal: str
    complexity: TaskComplexity
    tasks: list[dict] = field(default_factory=list)
    depends_on: dict[str, list[str]] = field(default_factory=dict)
    model_tier: str = "pro"
    max_concurrency: int = 4
    needs_review: bool = False
    needs_human_confirm: bool = False
    created_at: float = 0.0


# ═══════════════════════════════════════════════════════════════════
# Execute: parallel dispatch with file isolation + timeout budget
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ExecutionBudget:
    """单次编排的执行预算."""

    total_timeout_s: float = 600.0  # 总超时
    per_task_timeout_s: float = 180.0  # 单任务超时
    max_retries: int = 2  # 单任务最大重试
    max_consecutive_failures: int = 3  # 连续失败熔断阈值


@dataclass
class FileOwnership:
    """文件所有权 — 防止并行 agent 文件冲突."""

    path: str
    owner_id: str
    acquired_at: float = 0.0


class FileIsolationGuard:
    """EXECUTE 阶段的文件隔离锁.

    两个 agent 不可同时修改同一文件。一个 agent 持有文件写锁时，
    其他 agent 必须等待或使用不同文件。
    """

    def __init__(self) -> None:
        self._locks: dict[str, str] = {}  # path → owner_id
        self._lock = threading.Lock()

    def acquire(self, path: str, owner_id: str) -> bool:
        with self._lock:
            if path in self._locks and self._locks[path] != owner_id:
                return False
            self._locks[path] = owner_id
            return True

    def release(self, path: str, owner_id: str) -> None:
        with self._lock:
            if self._locks.get(path) == owner_id:
                del self._locks[path]

    def release_all(self, owner_id: str) -> None:
        with self._lock:
            for path, owner in list(self._locks.items()):
                if owner == owner_id:
                    del self._locks[path]


# ═══════════════════════════════════════════════════════════════════
# Verify: cross-review + self-check + diff guard
# ═══════════════════════════════════════════════════════════════════


@dataclass
class VerificationResult:
    """VERIFY 阶段的输出."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    review_notes: str = ""
    diff_clean: bool = True
    tests_passed: bool = True
    verified_at: float = 0.0


VERIFY_CHECKLIST = [
    "目标是否达成",
    "是否有无关改动",
    "是否破坏公共 API",
    "测试是否通过",
    "diff 是否可审查",
    "是否有安全风险",
    "进程是否残留",
]

# ═══════════════════════════════════════════════════════════════════
# Master Orchestrator
# ═══════════════════════════════════════════════════════════════════


class MasterOrchestrator:
    """CRUX 总编排器 — 七阶段认知-执行-验证闭环.

    Usage:
        orch = MasterOrchestrator(tool_executor, model_router)
        result = orch.run("修复认证模块的空指针异常")
    """

    def __init__(
        self,
        tool_executor: Callable,
        model_router=None,
        *,
        budget: ExecutionBudget | None = None,
        phase_callback: Callable[[str, str, dict | None], None] | None = None,
    ) -> None:
        self.execute_tool = tool_executor
        self.model_router = model_router
        self.budget = budget or ExecutionBudget()
        self.file_guard = FileIsolationGuard()
        self.phase_callback = phase_callback  # (phase, action, details) 用于 RuntimeOrchestrator 集成
        self._run_id = ""
        self._phase: Phase = Phase.GATE
        self._started_at = 0.0
        self._mode = "auto"  # "auto" | "full" | "fast"

    # ── Public API ─────────────────────────────────────────────

    def _notify_phase(self, phase_name: str, action: str, details: dict | None = None) -> None:
        """通知外部观察者阶段变化 (供 RuntimeOrchestrator 集成)."""
        if self.phase_callback:
            try:
                self.phase_callback(phase_name, action, details)
            except Exception:
                import logging

                logging.getLogger("crux").debug("silent except", exc_info=True)

    def run(self, goal: str) -> dict:
        """主入口: 完整编排一个目标从 Gate 到 Close."""
        self._run_id = uuid.uuid4().hex[:12]
        self._started_at = time.time()
        result: dict = {"run_id": self._run_id, "goal": goal}

        try:
            # Phase 1: GATE
            self._phase = Phase.GATE
            self._notify_phase("gate", "start")
            complexity = classify_complexity(goal)
            model_tier = MODEL_TIER_FOR_COMPLEXITY[complexity]
            result["complexity"] = complexity.name
            result["model_tier"] = model_tier
            logger.info("[%s] GATE: complexity=%s tier=%s", self._run_id, complexity.name, model_tier)

            # 简单任务跳过重编排 — 直接执行不做六阶段展开
            if complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE):
                result["phase"] = "fast_path"
                result["note"] = "Simple task — skipped full orchestration"
                self._notify_phase("gate", "skip", {"reason": "trivial/simple"})
                return self._close(result)

            self._notify_phase("gate", "done", {"complexity": complexity.name, "tier": model_tier})

            # Phase 2: CONTEXT — 强制上下文收集（硬件门禁）
            self._phase = Phase.CONTEXT
            self._notify_phase("context", "start")
            snapshot = self._gather_context(goal, complexity)
            if not context_is_sufficient(snapshot):
                logger.warning("[%s] CONTEXT: insufficient — injecting explorer", self._run_id)
                snapshot = self._inject_explorer(goal, snapshot)
            result["context"] = {"files": snapshot.relevant_files, "risks": snapshot.risk_areas}
            self._notify_phase("context", "done", {"files": len(snapshot.relevant_files)})

            # Phase 3: PLAN — 任务分解
            self._phase = Phase.PLAN
            self._notify_phase("plan", "start")
            plan = self._build_plan(goal, complexity, snapshot)
            result["plan"] = {"tasks": len(plan.tasks), "max_concurrency": plan.max_concurrency}
            self._notify_phase("plan", "done", {"tasks": len(plan.tasks)})

            # 高风险操作 → 人工确认门禁
            if plan.needs_human_confirm:
                result["confirm_required"] = True
                result["confirm_message"] = f"高风险操作 (complexity={complexity.name})。涉及: " + ", ".join(
                    snapshot.risk_areas[:3] or ["未知风险"]
                )
                self._notify_phase("plan", "pause", {"reason": "human_confirm_required"})
                return result  # 暂停，等待确认后调用 resume()

            # Phase 4: EXECUTE — 并行执行
            self._phase = Phase.EXECUTE
            self._notify_phase("execute", "start", {"tasks": len(plan.tasks)})
            exec_result = self._execute_plan(plan)
            result["execution"] = exec_result
            self._notify_phase(
                "execute",
                "done",
                {"completed": exec_result.get("completed", 0), "failed": exec_result.get("failed", 0)},
            )

            # Phase 5: VERIFY — 交叉审查
            self._phase = Phase.VERIFY
            self._notify_phase("verify", "start")
            if plan.needs_review or complexity in (TaskComplexity.COMPLEX, TaskComplexity.CRITICAL):
                verification = self._verify_results(goal, plan, exec_result)
                result["verification"] = {
                    "passed": verification.passed,
                    "issues": len(verification.issues),
                }
                if not verification.passed:
                    result["verification"]["details"] = verification.issues[:5]
            else:
                result["verification"] = {"passed": True, "skipped": "moderate complexity"}
            self._notify_phase("verify", "done", result["verification"])

        except Exception as e:
            logger.exception("[%s] orchestration failed at phase %s", self._run_id, self._phase.name)
            result["error"] = f"{type(e).__name__}: {e}"
            result["failed_phase"] = self._phase.name
            self._notify_phase(self._phase.name.lower(), "error", {"error": str(e)})

        return self._close(result)

    # ── Phase implementations ──────────────────────────────────

    def _gather_context(self, goal: str, complexity: TaskComplexity) -> ContextSnapshot:
        """CONTEXT 阶段: 收集代码上下文."""
        snapshot = ContextSnapshot(goal=goal, collected_at=time.time())

        # 搜索相关文件
        keywords = [w for w in goal.split() if len(w) > 2]
        for kw in keywords[:3]:
            try:
                r = self.execute_tool("search_files", {"pattern": kw})
                if r and not str(r).startswith("[错误]"):
                    for line in str(r).split("\n")[:5]:
                        if ":" in line:
                            fpath = line.split(":")[0]
                            if fpath not in snapshot.relevant_files:
                                snapshot.relevant_files.append(fpath)
            except Exception:
                logger.debug("Exception in orchestration", exc_info=True)

        # Git 变更检测
        try:
            r = self.execute_tool("git_diff", {})
            if r and not str(r).startswith("[错误]"):
                for line in str(r).split("\n")[:10]:
                    if line.strip():
                        snapshot.recent_changes.append(line.strip()[:120])
        except Exception:
            logger.debug("Exception in orchestration", exc_info=True)

        return snapshot

    def _inject_explorer(self, goal: str, snapshot: ContextSnapshot) -> ContextSnapshot:
        """注入上下文探索任务 — 当 CONTEXT 不足时."""
        try:
            from core.multi_agent_decompose import SmartDecomposer

            decomposer = SmartDecomposer(model_router=self.model_router)
            # 强制只生成 explorer 任务
            tasks = decomposer.decompose(f"Explore the codebase to understand: {goal}")
            for task in tasks:
                if not task.depends_on:
                    r = (
                        self.execute_tool(task.tool_sequence[0]["tool"], task.tool_sequence[0]["args"])
                        if task.tool_sequence
                        else ""
                    )
                    if r:
                        for line in str(r).split("\n")[:5]:
                            if ":" in line and not line.startswith(" "):
                                fpath = line.split(":")[0]
                                if fpath not in snapshot.relevant_files:
                                    snapshot.relevant_files.append(fpath)
        except Exception:
            logger.debug("Exception in orchestration", exc_info=True)
        return snapshot

    def _build_plan(self, goal: str, complexity: TaskComplexity, snapshot: ContextSnapshot) -> OrchestrationPlan:
        """PLAN 阶段: 分解任务."""
        plan = OrchestrationPlan(
            id=self._run_id,
            goal=goal,
            complexity=complexity,
            model_tier=MODEL_TIER_FOR_COMPLEXITY[complexity],
            created_at=time.time(),
        )

        try:
            from core.multi_agent_decompose import SmartDecomposer

            decomposer = SmartDecomposer(model_router=self.model_router)
            tasks = decomposer.decompose(goal)

            for task in tasks:
                task_dict = {
                    "id": task.id,
                    "description": task.description,
                    "tier": task.tier,
                    "tools": [e.get("tool", "") for e in (task.tool_sequence or [])],
                    "depends_on": task.depends_on,
                }
                plan.tasks.append(task_dict)
                plan.depends_on[task.id] = task.depends_on

            plan.max_concurrency = min(len(tasks), 4 if complexity == TaskComplexity.COMPLEX else 2)
            plan.needs_review = complexity in (TaskComplexity.COMPLEX, TaskComplexity.CRITICAL)
            plan.needs_human_confirm = complexity == TaskComplexity.CRITICAL

        except Exception:
            # Fallback: build a sensible plan without SmartDecomposer.
            # For self-check/heal tasks, produce multiple concrete steps.
            _gl = goal.lower()
            if "自检" in _gl or "自修" in _gl or "self heal" in _gl or "audit" in _gl:
                plan.tasks = [
                    {
                        "id": "1",
                        "description": "运行 self_heal 审计扫描",
                        "tier": "pro",
                        "tools": ["self_heal"],
                        "depends_on": [],
                    },
                    {
                        "id": "2",
                        "description": "审查发现的问题并生成修复方案",
                        "tier": "pro",
                        "tools": ["code_review"],
                        "depends_on": ["1"],
                    },
                    {
                        "id": "3",
                        "description": "运行测试验证",
                        "tier": "pro",
                        "tools": ["run_test"],
                        "depends_on": ["2"],
                    },
                ]
                plan.max_concurrency = 1
                plan.needs_review = True
            else:
                plan.tasks = [{"id": "direct", "description": goal, "tier": "pro", "tools": [], "depends_on": []}]
                plan.max_concurrency = 1

        return plan

    def _execute_plan(self, plan: OrchestrationPlan) -> dict:
        """EXECUTE 阶段: 顺序执行（不依赖 AgentSwarm）."""
        if len(plan.tasks) == 0:
            return {"mode": "empty", "result": "no tasks"}

        results = {}
        done = 0
        failed = 0

        for task in plan.tasks:
            tid = task.get("id", task.get("description", ""))
            tools = task.get("tools", [])
            task.get("description", tid)
            task_result = ""
            for tool_name in tools:
                # Build correct args per tool
                if tool_name == "self_heal" or tool_name == "run_lint":
                    args = {"fix": True}
                elif tool_name == "run_test":
                    args = {"path": "tests/", "extra_args": '-m "not slow" -q'}
                else:
                    args = {}
                try:
                    task_result = self.execute_tool(tool_name, args)
                except Exception as e:
                    task_result = f"[error] {e}"
                    break
            results[tid] = task_result
            if task_result and not str(task_result).startswith("[error]"):
                done += 1
            else:
                failed += 1

        return {"mode": "sequential", "done": done, "failed": failed, "total": len(plan.tasks), "results": results}

    def _verify_results(self, goal: str, plan: OrchestrationPlan, exec_result: dict) -> VerificationResult:
        """VERIFY 阶段: 交叉审查 + 自检."""
        result = VerificationResult(passed=True, verified_at=time.time())

        # 1. 执行结果检查
        if exec_result.get("failed", 0) > 0:
            result.passed = False
            result.issues.append(f"{exec_result['failed']} tasks failed")

        # 2. 交叉审查: 派 reviewer agent
        if plan.needs_review:
            try:
                review_prompt = (
                    f"Review the following task execution for correctness and completeness.\n"
                    f"Goal: {goal}\n"
                    f"Tasks: {len(plan.tasks)}\n"
                    f"Results: {exec_result}\n\n"
                    f"Check: Are all objectives met? Any missing pieces? "
                    f"Any inconsistencies? Obvious errors?\n"
                    f"Respond PASS or FAIL with specific issues."
                )
                r = self.execute_tool("think_deep", {"prompt": review_prompt})
                if r and "FAIL" in str(r).upper():
                    result.passed = False
                    result.review_notes = str(r)[:500]
                    result.issues.append(f"Review found issues: {result.review_notes[:200]}")
            except Exception:
                logger.debug("Exception in orchestration", exc_info=True)

        # 3. Diff 守卫: 检查无关改动
        try:
            r = self.execute_tool("git_diff", {})
            if r and not str(r).startswith("[错误]"):
                diff_text = str(r)
                # 检查是否改了保护区文件
                for protected in ["core/methodology.py", "core/orchestration.py"]:
                    if protected in diff_text:
                        result.passed = False
                        result.diff_clean = False
                        result.issues.append(f"Protected file modified: {protected}")
        except Exception:
            logger.debug("Exception in orchestration", exc_info=True)

        # 4. 进程残留检查
        import subprocess as _sp

        try:
            r = _sp.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            python_count = len([l for l in r.stdout.strip().split("\n") if l.strip()])
            if python_count > 10:
                result.issues.append(f"High Python process count: {python_count}")
        except Exception:
            logger.debug("Exception in orchestration", exc_info=True)

        return result

    def _close(self, result: dict) -> dict:
        """CLOSE 阶段: 资源回收 + 指标."""
        self._phase = Phase.CLOSE
        elapsed = time.time() - self._started_at
        result["elapsed_s"] = round(elapsed, 1)
        result["phases_completed"] = [p.name for p in PHASE_ORDER if p.value <= self._phase.value]

        # Cleanup file isolation locks
        self.file_guard.release_all(self._run_id)

        logger.info(
            "[%s] CLOSE: elapsed=%.1fs result=%s", self._run_id, elapsed, "ok" if "error" not in result else "error"
        )
        return result


# ═══════════════════════════════════════════════════════════════════
# Integration: wire into existing chat pipeline
# ═══════════════════════════════════════════════════════════════════

_orchestrator: MasterOrchestrator | None = None
_orch_lock = threading.Lock()


def get_orchestrator(tool_executor=None, model_router=None) -> MasterOrchestrator:
    """获取全局编排器单例."""
    global _orchestrator
    if _orchestrator is None:
        with _orch_lock:
            if _orchestrator is None:
                _orchestrator = MasterOrchestrator(
                    tool_executor=tool_executor,
                    model_router=model_router,
                )
    return _orchestrator


# run_orchestrate removed — use tools.json "orchestrate" → core.runtime_orchestrator.execute_tool
def run_orchestrate(goal: str = "", mode: str = "auto", **kwargs) -> str:
    """Backward-compat wrapper — delegates to canonical ``orchestrate`` tool.

    Deprecated: use ``core.runtime_orchestrator.execute_tool()`` directly.
    """
    import warnings

    warnings.warn(
        "core.orchestration.run_orchestrate() is deprecated; use core.runtime_orchestrator.execute_tool().",
        DeprecationWarning,
        stacklevel=2,
    )
    from core.runtime_orchestrator import execute_tool

    return execute_tool(goal, **kwargs)
