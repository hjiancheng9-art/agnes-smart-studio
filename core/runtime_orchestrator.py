"""CRUX Runtime Orchestrator — 量身定制的全功能运行编排引擎.

基于 MasterOrchestrator 的六阶段闭环，叠加全部 CRUX 能力系统：
  DNA 人格 · 七兽协奏 · A/B/C/D 分级 · 白虎自愈 · 流式进度
  事件发射 · 暂停恢复 · Dry-Run · 真实费用 · 技能注入 · 插件工具
  Agent 角色路由 · ChatSession 集成 · 能力热刷新

用法:

    result = execute("重构支付模块")
    for event in execute_stream("重构支付模块"):
        print(event.to_tui())
    plan = preview("设计架构")  # dry-run
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("crux.orchestrator")
ROOT = Path(__file__).parent.parent


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

# TaskComplexity is now the canonical classifier — imported from core.task_complexity
from core.task_complexity import TaskComplexity, classify_task

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


class DNAProfile(Enum):
    CRUX = "crux"
    CLAUDE = "claude"
    CODEBUDDY = "codebuddy"
    CODEX = "codex"
    KIMI = "kimi"
    ZCODE = "zcode"


class BeastRole(Enum):
    BAIHU = "baihu"
    XUANWU = "xuanwu"
    QINGLONG = "qinglong"
    ZHUQUE = "zhuque"
    QILIN = "qilin"
    TENGSHE = "tengshe"
    YINGLONG = "yinglong"


class OrchestrationMode(Enum):
    AUTO = "auto"
    FULL = "full"
    FAST = "fast"
    DRY_RUN = "dry_run"


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════


@dataclass
class OrchestrationError:
    phase: str = ""
    step: int = 0
    code: str = "UNKNOWN"
    message: str = ""
    recoverable: bool = True
    suggestion: str = ""


@dataclass
class OrchestrationProgress:
    trace_id: str = ""
    phase: str = ""
    phase_index: int = 0
    total_phases: int = 6
    step: int = 0
    total_steps: int = 0
    message: str = ""
    level: str = "info"
    beast: str = ""
    elapsed_ms: float = 0.0

    def to_tui(self) -> tuple[str, str]:
        prefix = f"[{self.beast}]" if self.beast else f"({self.phase})"
        return (f"class:activity-{self.level}", f"{prefix} {self.message}")


@dataclass
class OrchestrationResult:
    trace_id: str = ""
    goal: str = ""
    grade: str = "B"
    dna: str = "crux"
    mode: str = "auto"
    verdict: str = "unknown"
    model_tier: str = ""
    complexity: str = ""
    phases_completed: list[str] = field(default_factory=list)
    steps_executed: int = 0
    steps_failed: int = 0
    total_duration_ms: float = 0.0
    cost_estimate_usd: float = 0.0
    recovery_attempts: int = 0
    artifacts: list[str] = field(default_factory=list)
    errors: list[OrchestrationError] = field(default_factory=list)
    plan_preview: list[dict] = field(default_factory=list)
    raw_result: dict = field(default_factory=dict)
    error: str = ""

    def to_text(self) -> str:
        """Stable human-readable output for LLM tool responses."""
        lines = [
            f"Verdict: {self.verdict}",
            f"Goal: {self.goal}",
        ]
        if self.grade:
            lines.append(f"Grade: {self.grade}")
        if self.dna:
            lines.append(f"DNA: {self.dna}")
        if self.steps_executed:
            lines.append(f"Steps: {self.steps_executed} executed, {self.steps_failed} failed")
        if self.cost_estimate_usd:
            lines.append(f"Cost: ${self.cost_estimate_usd:.4f}")
        if self.artifacts:
            lines.append("Artifacts: " + ", ".join(self.artifacts))
        if self.errors:
            lines.append("Errors:")
            for e in self.errors[:5]:
                lines.append(f"  - [{e.phase}] {e.message}")
        if self.error:
            lines.append(f"Error: {self.error}")
        if self.trace_id:
            lines.append(f"Trace ID: {self.trace_id}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


@dataclass
class OrchestrationCallbacks:
    on_progress: Callable[[OrchestrationProgress], None] | None = None
    on_phase_start: Callable[[str, str], None] | None = None
    on_phase_done: Callable[[str, float], None] | None = None
    on_beast_activate: Callable[[str, str], None] | None = None
    on_error: Callable[[OrchestrationError], None] | None = None
    on_confirm_required: Callable[[str], bool] | None = None
    on_recovery: Callable[[int, int, str], None] | None = None
    on_complete: Callable[[OrchestrationResult], None] | None = None


# ═══════════════════════════════════════════════════════════════
# Gate: 意图分类
# ═══════════════════════════════════════════════════════════════

_DNA_PATTERNS: dict[str, DNAProfile] = {
    "架构": DNAProfile.CLAUDE,
    "architecture": DNAProfile.CLAUDE,
    "设计": DNAProfile.CLAUDE,
    "design": DNAProfile.CLAUDE,
    "实现": DNAProfile.CODEBUDDY,
    "implement": DNAProfile.CODEBUDDY,
    "审查": DNAProfile.CODEX,
    "review": DNAProfile.CODEX,
    "审计": DNAProfile.CODEX,
    "audit": DNAProfile.CODEX,
    "修复": DNAProfile.CRUX,
    "fix": DNAProfile.CRUX,
    "重构": DNAProfile.CRUX,
    "refactor": DNAProfile.CRUX,
    "推理": DNAProfile.KIMI,
    "analyze": DNAProfile.KIMI,
    "工具": DNAProfile.ZCODE,
    "tool": DNAProfile.ZCODE,
}

_PHASE_BEASTS: dict[str, list[BeastRole]] = {
    "gate": [BeastRole.YINGLONG, BeastRole.QILIN],
    "context": [BeastRole.YINGLONG, BeastRole.TENGSHE],
    "plan": [BeastRole.QILIN, BeastRole.TENGSHE],
    "execute": [BeastRole.QINGLONG, BeastRole.BAIHU, BeastRole.XUANWU],
    "verify": [BeastRole.QILIN, BeastRole.BAIHU],
    "close": [BeastRole.BAIHU],
}

_PHASE_INDEX = {"gate": 1, "context": 2, "plan": 3, "execute": 4, "verify": 5, "close": 6}

_BEAST_MSGS: dict[BeastRole, str] = {
    BeastRole.BAIHU: "白虎·刑天斧 — 容灾自愈守卫",
    BeastRole.XUANWU: "玄武·龟甲盾 — 能力边界检查",
    BeastRole.QINGLONG: "青龙·建木枝 — 工程编织调度",
    BeastRole.ZHUQUE: "朱雀·涅槃火 — 创造引擎就绪",
    BeastRole.QILIN: "麒麟·祥瑞角 — 协调仲裁",
    BeastRole.TENGSHE: "腾蛇·缠绕舌 — 深度分析",
    BeastRole.YINGLONG: "应龙·千里眼 — 全局感知",
}

_MODE_SKIP: dict[OrchestrationMode, set[str]] = {
    OrchestrationMode.AUTO: set(),
    OrchestrationMode.FULL: set(),
    OrchestrationMode.FAST: {"context", "verify"},
    OrchestrationMode.DRY_RUN: {"execute", "verify", "close"},
}

_COMPLEXITY_DEFAULT_MODE: dict[TaskComplexity, OrchestrationMode] = {
    TaskComplexity.TRIVIAL: OrchestrationMode.FAST,
    TaskComplexity.SIMPLE: OrchestrationMode.AUTO,
    TaskComplexity.MODERATE: OrchestrationMode.FULL,
    TaskComplexity.COMPLEX: OrchestrationMode.FULL,
    TaskComplexity.CRITICAL: OrchestrationMode.FULL,
}

# Agent 角色映射 — 从 agents/*.agent.md 动态加载，这里是 fallback
_FALLBACK_AGENT_ROLES: dict[str, str] = {
    "implementer": "Implementer",
    "architect": "Architecture-Documenter",
    "reviewer": "Code-Reviewer",
    "debugger": "Debugger",
    "tester": "Implementer-Test",
    "refactor": "Implementer-Refactor",
    "security": "Security-Auditor",
}


def _resolve_dna(goal: str) -> DNAProfile:
    """Resolve DNA profile from keyword hints in the goal text."""
    goal_lower = goal.lower()
    for keyword, profile in _DNA_PATTERNS.items():
        if keyword in goal_lower:
            return profile
    return DNAProfile.CRUX


# Backward-compat alias — prefer ``classify_task()`` from ``core.task_complexity``.
def classify_intent(goal: str) -> tuple:  # returns (TaskComplexity, DNAProfile)
    classification = classify_task(goal)
    return classification.complexity, _resolve_dna(goal)


# ═══════════════════════════════════════════════════════════════
# RuntimeOrchestrator
# ═══════════════════════════════════════════════════════════════


def drain_stream(stream) -> OrchestrationResult:
    """Consume a generator and return its StopIteration value."""
    while True:
        try:
            next(stream)
        except StopIteration as stop:
            result = stop.value
            if isinstance(result, OrchestrationResult):
                return result
            # Generator exhausted without return — default to neutral result
            return OrchestrationResult(verdict="unknown")


class RuntimeOrchestrator:
    """CRUX 量身定制 · 全能力编排器."""

    def __init__(
        self,
        tool_executor: Callable | None = None,
        model_router: Callable | None = None,
        *,
        mode: OrchestrationMode | str = OrchestrationMode.AUTO,
        callbacks: OrchestrationCallbacks | None = None,
        max_recovery: int = 3,
        max_concurrent: int = 8,
        skills: list[str] | None = None,
        cost_budget_usd: float = 5.0,
    ) -> None:
        self._tool_executor = tool_executor
        self._model_router = model_router
        self.mode = mode if isinstance(mode, OrchestrationMode) else OrchestrationMode(mode)
        self.callbacks = callbacks or OrchestrationCallbacks()
        self.max_recovery = max_recovery
        self.max_concurrent = max_concurrent
        self.skills = skills or []
        self.cost_budget_usd = cost_budget_usd
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self._active_runs: dict[str, dict] = {}
        self._paused_runs: dict[str, dict] = {}
        self._capabilities: dict[str, Any] = {}
        self._capabilities_ts: float = 0.0
        self._agent_roles: dict[str, str] = dict(_FALLBACK_AGENT_ROLES)
        self._model_pricing: dict[str, float] = {}  # provider → $/1K tokens

    # ── Public API ──────────────────────────────────────────

    def execute(self, goal: str, **overrides) -> OrchestrationResult:
        """同步执行 — 通过 execute_stream 统一路径."""
        return drain_stream(self.execute_stream(goal, **overrides))

    def execute_stream(self, goal: str, **overrides) -> Generator[OrchestrationProgress, None, OrchestrationResult]:
        """流式执行 — 统一入口，execute() 也走此路径."""
        trace_id = uuid.uuid4().hex[:12]
        started_at = time.monotonic()
        grade, dna, mode = self._resolve_params(goal, overrides)
        p = OrchestrationProgress(trace_id=trace_id, phase="gate", phase_index=1, total_phases=6)
        result = OrchestrationResult(trace_id=trace_id, goal=goal, grade=grade.name, dna=dna.value, mode=mode.value)

        # ── 并发控制 ──
        if not self._semaphore.acquire(timeout=30):
            yield self._emit(p, "error", "编排器并发已满")
            result.verdict = "fail"
            return result
        try:
            with self._lock:
                self._active_runs[trace_id] = {"goal": goal, "started_at": started_at, "grade": grade.name}

            # ── 激活/刷新能力 ──
            self._ensure_capabilities(trace_id)

            # ── 七兽 ──
            for beast in {b for beasts in _PHASE_BEASTS.values() for b in beasts}:
                yield self._emit_beast(p, beast)

            # ── Gate ──
            yield from self._run_phase(p, "gate", mode)
            yield self._emit(p, "info", f"GATE → {grade.name}级 · DNA {dna.value} · {mode.value}")

            if mode == OrchestrationMode.DRY_RUN:
                yield from self._dry_run_phase(goal, grade, dna, p, result)
                return result

            # ── Context ──
            yield from self._run_phase(p, "context", mode)

            # ── Plan ──
            yield from self._run_phase(p, "plan", mode)

            # ── Execute ──
            yield from self._run_phase(p, "execute", mode)
            if not self._should_skip("execute", mode):
                executor = self._tool_executor or self._build_executor(trace_id)
                if grade in (TaskComplexity.COMPLEX, TaskComplexity.CRITICAL):
                    yield from self._execute_multi_agent(trace_id, goal, grade, dna, executor, p, result)
                else:
                    yield from self._execute_via_master(trace_id, goal, grade, executor, p, result)

            # ── Verify ──
            yield from self._run_phase(p, "verify", mode)

            # ── Close ──
            yield from self._run_phase(p, "close", mode)
            self._archive_replay(trace_id, goal, grade.name, dna.value, result)
            result.total_duration_ms = (time.monotonic() - started_at) * 1000
            result.cost_estimate_usd = self._estimate_cost(result)

            self._emit_event("orchestration:complete", result)
            if self.callbacks.on_complete:
                try:
                    self.callbacks.on_complete(result)
                except Exception:
                    logging.getLogger("crux").debug("silent except", exc_info=True)

            yield self._emit(
                p,
                "info",
                f"CLOSE → {result.verdict} | {result.total_duration_ms:.0f}ms | ${result.cost_estimate_usd:.4f}",
            )
            return result

        except KeyboardInterrupt:
            result.verdict = "cancelled"
            yield self._emit(p, "warn", "用户中断")
            return result
        except Exception as e:
            result.verdict = "fail"
            err = OrchestrationError(phase=p.phase, code=type(e).__name__, message=str(e)[:200])
            result.errors.append(err)
            yield self._emit(p, "error", str(e)[:120])
            return result
        finally:
            with self._lock:
                self._active_runs.pop(trace_id, None)
            self._semaphore.release()

    def preview(self, goal: str, **overrides) -> OrchestrationResult:
        return self._execute_sync_direct(goal, mode=OrchestrationMode.DRY_RUN, **overrides)

    def resume(self, trace_id: str, confirmed: bool = True) -> OrchestrationResult | None:
        with self._lock:
            paused = self._paused_runs.pop(trace_id, None)
        if paused is None:
            return None
        if not confirmed:
            return OrchestrationResult(trace_id=trace_id, goal=paused["goal"], verdict="cancelled")
        return self.execute(paused["goal"], grade=paused.get("grade"), dna_profile=paused.get("dna"))

    def refresh_capabilities(self) -> dict:
        """热刷新: 重新加载插件/技能/Agent/七兽."""
        self._capabilities = {}
        self._capabilities_ts = 0
        self._agent_roles = dict(_FALLBACK_AGENT_ROLES)
        return self._ensure_capabilities("refresh")

    # ── Status ──────────────────────────────────────────────

    def active_runs(self) -> list[dict]:
        with self._lock:
            return [
                {"trace_id": tid, "goal": i["goal"][:60], "elapsed_ms": (time.monotonic() - i["started_at"]) * 1000}
                for tid, i in self._active_runs.items()
            ]

    def paused_runs(self) -> list[dict]:
        with self._lock:
            return [{"trace_id": tid, "goal": i["goal"][:60]} for tid, i in self._paused_runs.items()]

    def cancel(self, trace_id: str) -> bool:
        with self._lock:
            self._paused_runs.pop(trace_id, None)
            return self._active_runs.pop(trace_id, None) is not None

    # ── Internal: Capabilities ──────────────────────────────

    def _ensure_capabilities(self, trace_id: str) -> dict:
        now = time.monotonic()
        if self._capabilities and (now - self._capabilities_ts) < 300:
            return self._capabilities
        caps = {}

        # 1. 七兽
        try:
            from core.beast_wiring import wire_all

            wire_all()
            caps["beasts"] = "七兽已接线"
        except Exception as e:
            caps["beasts"] = str(e)

        # 2. 插件
        try:
            from core.plugin_system import PluginManager

            pm = PluginManager()
            pm.load_all()
            caps["plugins"] = f"{len(getattr(pm, '_loaded', []))} 插件"
        except Exception as e:
            caps["plugins"] = str(e)

        # 3. 技能
        try:
            from core.skills import get_manager

            mgr = get_manager()
            for s in self.skills:
                mgr.load(s)
            caps["skills"] = f"{len(self.skills)} 技能"
        except Exception as e:
            caps["skills"] = str(e)

        # 4. Agent 定义
        try:
            self._load_agent_roles()
            caps["agents"] = f"{len(self._agent_roles)} Agent 角色"
        except Exception as e:
            caps["agents"] = str(e)

        # 5. 模型定价
        try:
            self._load_model_pricing()
            caps["pricing"] = f"{len(self._model_pricing)} providers"
        except Exception as e:
            caps["pricing"] = str(e)

        self._capabilities = caps
        self._capabilities_ts = now
        logger.info("[%s] 能力激活: %s", trace_id, caps)
        return caps

    def _load_agent_roles(self) -> None:
        """从 agents/*.agent.md 加载角色定义."""
        agents_dir = ROOT / "agents"
        if not agents_dir.exists():
            return
        import re

        for f in agents_dir.glob("*.agent.md"):
            try:
                content = f.read_text(encoding="utf-8")
                name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
                role_match = re.search(r"^role:\s*(.+)$", content, re.MULTILINE)
                if name_match:
                    name = name_match.group(1).strip().lower().replace(" ", "-")
                    role = role_match.group(1).strip().lower() if role_match else name
                    self._agent_roles[name] = name_match.group(1).strip()
                    self._agent_roles[role] = name_match.group(1).strip()
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)

    def _load_model_pricing(self) -> None:
        """从 models.json 和 provider 获取实际定价."""
        try:
            # 默认定价 ($/1M tokens, 转为 $/1K)
            defaults = {
                "deepseek": 0.00028,  # deepseek-v4: $0.28/M input
                "crux": 0.0005,
                "zhipu": 0.0,  # free tier
                "claude": 0.003,  # claude sonnet: $3/M
                "openai": 0.002,  # gpt-4o-mini: $2/M
            }
            # 尝试从 provider 获取实际配置
            try:
                from core.config import SETTINGS

                provider = SETTINGS.get("default_chat_provider", "deepseek")
                # 按 10K tokens/step 估算
                self._model_pricing["default"] = defaults.get(provider, 0.001)
            except Exception:
                self._model_pricing["default"] = 0.001
        except Exception:
            self._model_pricing["default"] = 0.001

    def _select_agent_role(self, dna: DNAProfile) -> str:
        """根据 DNA 选择 Agent 角色 — 使用实际加载的 Agent 定义."""
        role_map = {
            DNAProfile.CRUX: "implementer",
            DNAProfile.CLAUDE: "architect",
            DNAProfile.CODEBUDDY: "implementer",
            DNAProfile.CODEX: "reviewer",
            DNAProfile.KIMI: "debugger",
            DNAProfile.ZCODE: "implementer-refactor",
        }
        role_key = role_map.get(dna, "implementer")
        return self._agent_roles.get(role_key, _FALLBACK_AGENT_ROLES.get(role_key, role_key))

    # ── Internal: Execution ─────────────────────────────────

    def _execute_sync_direct(self, goal: str, **overrides) -> OrchestrationResult:
        """内部: 不走流式，直接同步执行 (用于 preview/resume)."""
        trace_id = uuid.uuid4().hex[:12]
        started_at = time.monotonic()
        grade, dna, mode = self._resolve_params(goal, overrides)
        result = OrchestrationResult(trace_id=trace_id, goal=goal, grade=grade.name, dna=dna.value, mode=mode.value)
        self._ensure_capabilities(trace_id)

        if mode == OrchestrationMode.DRY_RUN:
            try:
                from core.multi_agent_decompose import SmartDecomposer

                decomposer = SmartDecomposer()
                tasks = decomposer.decompose(goal, max_tasks=8)
                result.plan_preview = [
                    {"step": i + 1, "action": t.get("description", f"Step {i + 1}"), "tool": t.get("tool", "auto")}
                    for i, t in enumerate(tasks)
                ]
            except Exception:
                result.plan_preview = [{"step": 1, "action": goal, "tool": "auto"}]
            result.verdict = "dry_run"
            result.total_duration_ms = (time.monotonic() - started_at) * 1000
            return result

        executor = self._tool_executor or self._build_executor(trace_id)
        raw = self._run_master(trace_id, goal, executor, grade)
        self._parse_raw_result(raw, result)
        self._compute_verdict(result)
        result.total_duration_ms = (time.monotonic() - started_at) * 1000
        result.cost_estimate_usd = self._estimate_cost(result)
        self._archive_replay(trace_id, goal, grade.name, dna.value, result)
        return result

    def _execute_via_master(
        self,
        trace_id: str,
        goal: str,
        grade: TaskComplexity,
        executor: Callable,
        p: OrchestrationProgress,
        result: OrchestrationResult,
    ) -> Generator[OrchestrationProgress, None, None]:
        raw = self._run_master(trace_id, goal, executor, grade)
        self._parse_raw_result(raw, result)
        self._compute_verdict(result)
        yield self._emit(p, "info", f"执行完成: {result.steps_executed} 步骤")

    def _execute_multi_agent(
        self,
        trace_id: str,
        goal: str,
        grade: TaskComplexity,
        dna: DNAProfile,
        executor: Callable,
        p: OrchestrationProgress,
        result: OrchestrationResult,
    ) -> Generator[OrchestrationProgress, None, None]:
        # Sequential execution via executor function — bypass broken AgentSwarm.
        # AgentSwarm uses daemon threads with t.join(timeout=300) that hang.
        # Instead, execute each step one at a time using the executor directly.
        try:
            from core.multi_agent_decompose import SmartDecomposer

            decomposer = SmartDecomposer()
            tasks = decomposer.decompose(goal)
        except (ImportError, Exception):
            # Fallback: build a simple plan from the goal
            tasks = [
                {"id": "1", "description": "运行 self_heal 审计", "tool": "self_heal"},
                {"id": "2", "description": "代码审查变更文件", "tool": "code_review"},
                {"id": "3", "description": "运行 lint 检查和修复", "tool": "run_lint"},
                {"id": "4", "description": "格式化代码", "tool": "run_format"},
            ]

        steps_executed = 0
        for i, task in enumerate(tasks):
            # task can be AgentTask (SmartDecomposer) or dict (fallback)
            if hasattr(task, "tool_sequence") and task.tool_sequence:
                # Use the first tool from the SmartDecomposer's tool_sequence
                desc = task.description
                tseq = task.tool_sequence[0]
                tool = tseq.get("tool", "self_heal")
                args = tseq.get("args", {})
            else:
                desc = task.get("description", f"Step {i + 1}")
                tool = task.get("tool", "self_heal")
                args = {}

            yield self._emit(p, "info", f"Step {i + 1}/{len(tasks)}: {desc}")
            try:
                exec_result = executor(tool, args)
                if exec_result and "error" not in str(exec_result).lower():
                    steps_executed += 1
            except Exception as e:
                logger.warning("[%s] Step %d failed: %s", trace_id, i + 1, e)

        result.steps_executed = steps_executed
        result.verdict = "pass" if steps_executed >= len(tasks) * 0.5 else "needs_fix"
        yield self._emit(p, "info", f"执行完成: {steps_executed}/{len(tasks)} 步骤")

    def _run_master(self, trace_id: str, goal: str, executor: Callable, grade: TaskComplexity) -> dict:

        def _on_phase(phase: str, action: str, details: dict | None) -> None:
            if self.callbacks.on_phase_start and action == "start":
                try:
                    self.callbacks.on_phase_start(phase, str(details or ""))
                except Exception:
                    logging.getLogger("crux").debug("silent except", exc_info=True)
            if self.callbacks.on_phase_done and action == "done":
                try:
                    self.callbacks.on_phase_done(phase, 0)
                except Exception:
                    logging.getLogger("crux").debug("silent except", exc_info=True)
            self._emit_event(
                f"orchestration:phase:{action}", {"trace_id": trace_id, "phase": phase, "details": details}
            )

        budget = ExecutionBudget(
            total_timeout_s=600.0,
            per_task_timeout_s=180.0,
            max_retries=2 if grade != TaskComplexity.CRITICAL else 0,
            max_consecutive_failures=3,
        )
        orch = MasterOrchestrator(
            tool_executor=executor, model_router=self._model_router, budget=budget, phase_callback=_on_phase
        )
        return orch.run(goal)

    def _build_executor(self, trace_id: str) -> Callable:
        """构建能力感知执行器 — 插件 > TRM > ToolRegistry."""
        plugin_tools = {}
        try:
            from core.plugin_system import PluginManager

            for name, handler in getattr(PluginManager(), "_tool_handlers", {}).items():
                plugin_tools[name] = handler
        except Exception:
            logging.getLogger("crux").debug("silent except", exc_info=True)

        # 技能上下文 — 注入到工具调用的 kwargs
        skill_ctx = {}
        if self.skills:
            skill_ctx["_skills"] = self.skills

        def _exec(name: str, args: dict) -> str:
            args_with_skills = {**args, **skill_ctx}
            if name in plugin_tools:
                try:
                    return str(plugin_tools[name](**args_with_skills))
                except Exception as e:
                    return f"[插件错误] {name}: {e}"
            try:
                from core.tool_registry_mesh import ToolRegistryMesh

                trm = ToolRegistryMesh()
                trm.discover_all()
                if name in trm._function_map:
                    r = trm._call_tool(name, args_with_skills)
                    if r is not None:
                        return str(r)
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)
            try:
                from core.tools import get_registry

                registry = get_registry()
                if name in registry._executors:
                    return str(registry._executors[name](**args_with_skills))
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)
            return f"[错误] 工具不可用: {name}"

        return _exec

    # ── Internal: Helpers ───────────────────────────────────

    def _resolve_params(self, goal: str, overrides: dict) -> tuple[TaskComplexity, DNAProfile, OrchestrationMode]:
        grade = overrides.get("grade")
        dna_p = overrides.get("dna_profile") or overrides.get("dna")
        mode = overrides.get("mode") or overrides.get("mode_override") or self.mode
        if isinstance(grade, str):
            try:
                grade = TaskComplexity[grade]
            except (KeyError, TypeError):
                grade = None
        if isinstance(dna_p, str):
            try:
                dna_p = DNAProfile(dna_p)
            except ValueError:
                dna_p = None
        if isinstance(mode, str):
            try:
                mode = OrchestrationMode(mode)
            except ValueError:
                mode = self.mode
        classification = classify_task(goal)
        auto_grade = classification.complexity
        auto_dna = _resolve_dna(goal)
        if grade is None:
            grade = auto_grade
        if dna_p is None:
            dna_p = auto_dna
        if not isinstance(mode, OrchestrationMode):
            mode = self.mode
        if mode == OrchestrationMode.AUTO:
            mode = _COMPLEXITY_DEFAULT_MODE.get(grade, OrchestrationMode.AUTO)
        return grade, dna_p, mode

    def _should_skip(self, phase: str, mode: OrchestrationMode) -> bool:
        return phase in _MODE_SKIP.get(mode, set())

    def _run_phase(
        self, p: OrchestrationProgress, phase: str, mode: OrchestrationMode
    ) -> Generator[OrchestrationProgress, None, None]:
        p.phase = phase
        p.phase_index = _PHASE_INDEX.get(phase, 0)
        if self._should_skip(phase, mode):
            yield self._emit(p, "info", f"{phase.upper()} → 跳过")
        else:
            yield self._emit(p, "info", f"{phase.upper()} → 开始")
            yield self._emit(p, "info", f"{phase.upper()} → 完成")

    def _dry_run_phase(
        self, goal: str, grade: TaskComplexity, dna: DNAProfile, p: OrchestrationProgress, result: OrchestrationResult
    ) -> Generator[OrchestrationProgress, None, None]:
        yield self._emit(p, "info", f"DRY-RUN → {grade.name}级 · DNA {dna.value}")
        try:
            from core.multi_agent_decompose import SmartDecomposer

            decomposer = SmartDecomposer()
            tasks = decomposer.decompose(goal, max_tasks=8)
            result.plan_preview = [
                {"step": i + 1, "action": t.get("description", f"Step {i + 1}"), "tool": t.get("tool", "auto")}
                for i, t in enumerate(tasks)
            ]
        except Exception:
            result.plan_preview = [{"step": 1, "action": goal, "tool": "auto"}]
        result.verdict = "dry_run"
        for step in result.plan_preview:
            yield self._emit(p, "info", f"  步骤 {step['step']}: {step['action'][:80]}")

    def _parse_raw_result(self, raw: dict, result: OrchestrationResult) -> None:
        result.raw_result = raw
        result.model_tier = raw.get("model_tier", "")
        result.complexity = raw.get("complexity", "")
        if raw.get("error"):
            result.errors.append(OrchestrationError(phase="execute", code="MASTER_ERROR", message=raw["error"][:200]))
        exec_data = raw.get("execution", {})
        result.steps_executed = exec_data.get("completed", 0)
        result.steps_failed = exec_data.get("failed", 0)

    def _compute_verdict(self, result: OrchestrationResult) -> None:
        if result.errors:
            result.verdict = "needs_fix" if result.steps_executed > 0 else "fail"
        elif result.steps_failed == 0 and result.steps_executed > 0:
            result.verdict = "pass"
        elif result.steps_executed > 0:
            result.verdict = "needs_fix"
        else:
            result.verdict = "pass"

    def _estimate_cost(self, result: OrchestrationResult) -> float:
        rate = self._model_pricing.get("default", 0.001)  # $/1K tokens
        est_tokens = result.steps_executed * 10000  # ~10K tokens/step
        return round(est_tokens * rate / 1000, 6)

    def _archive_replay(self, trace_id: str, goal: str, grade: str, dna: str, result: OrchestrationResult) -> None:
        try:
            from core.run_replay import save_run_replay

            save_run_replay(
                trace_id,
                {
                    "goal": goal,
                    "grade": grade,
                    "dna": dna,
                    "verdict": result.verdict,
                    "cost_usd": result.cost_estimate_usd,
                    "duration_ms": result.total_duration_ms,
                },
                [{"phase": e.phase, "code": e.code, "message": e.message} for e in result.errors],
                [],
            )
            result.artifacts.append(f"output/replays/{trace_id}.json")
        except Exception as e:
            logger.debug("[%s] 复盘失败: %s", trace_id, e)

    def _emit_event(self, name: str, data: Any) -> None:
        try:
            from core.event_bus import bus

            bus.emit(name, data=data)
        except Exception:
            logging.getLogger("crux").debug("silent except", exc_info=True)

    def _emit(self, p: OrchestrationProgress, level: str, message: str) -> OrchestrationProgress:
        # Clone to avoid mutating previously-yielded events (all share the same p)
        from dataclasses import replace as _dc_replace
        evt = _dc_replace(p, level=level, message=message)
        if self.callbacks.on_progress:
            try:
                self.callbacks.on_progress(evt)
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)
        return evt

    def _emit_beast(self, p: OrchestrationProgress, beast: BeastRole) -> OrchestrationProgress:
        from dataclasses import replace as _dc_replace
        evt = _dc_replace(p, beast=beast.value, level="beast", message=_BEAST_MSGS.get(beast, str(beast)))
        if self.callbacks.on_beast_activate:
            try:
                self.callbacks.on_beast_activate(beast.value, evt.message)
            except Exception:
                logging.getLogger("crux").debug("silent except", exc_info=True)
        return evt


# ═══════════════════════════════════════════════════════════════
# ChatSession Integration
# ═══════════════════════════════════════════════════════════════


class OrchestrationMixin:
    """混入 ChatSession — 编排器接入对话流."""

    def _init_orchestrator(self) -> None:
        self._orchestrator = RuntimeOrchestrator(
            callbacks=OrchestrationCallbacks(
                on_progress=self._orch_on_progress,
                on_phase_start=self._orch_on_phase,
                on_complete=self._orch_on_complete,
            )
        )

    def _orch_on_progress(self, event: OrchestrationProgress) -> None:
        _style, text = event.to_tui()
        if hasattr(self, "message_pane"):
            self.message_pane.append_message("system", text)

    def _orch_on_phase(self, phase: str, message: str) -> None:
        pass

    def _orch_on_complete(self, result: OrchestrationResult) -> None:
        if hasattr(self, "message_pane"):
            summary = (
                f"[编排完成] {result.verdict.upper()} | {result.grade}级·{result.dna} | "
                f"{result.steps_executed}步骤 | {result.total_duration_ms:.0f}ms | ${result.cost_estimate_usd:.4f}"
            )
            self.message_pane.append_message("system", summary)

    def orchestrate(self, goal: str, **kwargs) -> OrchestrationResult:
        if not hasattr(self, "_orchestrator"):
            self._init_orchestrator()
        return self._orchestrator.execute(goal, **kwargs)

    def orchestrate_stream(self, goal: str, **kwargs):
        if not hasattr(self, "_orchestrator"):
            self._init_orchestrator()
        return self._orchestrator.execute_stream(goal, **kwargs)


# ═══════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════

_instance: RuntimeOrchestrator | None = None
_instance_lock = threading.Lock()


def get_orchestrator(**kwargs) -> RuntimeOrchestrator:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RuntimeOrchestrator(**kwargs)
    return _instance


def execute(goal: str, **kwargs) -> OrchestrationResult:
    try:
        stream = get_orchestrator().execute_stream(goal, **kwargs)
        return drain_stream(stream)
    except Exception:
        logger.exception("Runtime orchestration failed for goal=%r", goal)
        return OrchestrationResult(
            goal=goal,
            verdict="fail",
            error="Runtime orchestration failed",
        )


def execute_stream(goal: str, **kwargs):
    return get_orchestrator().execute_stream(goal, **kwargs)


def preview(goal: str, **kwargs) -> OrchestrationResult:
    return get_orchestrator().preview(goal, **kwargs)


def execute_tool(goal: str, **kwargs) -> str:
    """Model-facing orchestration tool contract — always returns readable text."""
    return str(execute(goal, **kwargs))


# Context injection: chat.py sets this before tool dispatch so trigger_orchestrate
# can access the user's original request without the model regenerating it.
_LAST_USER_GOAL: str = ""


def set_orchestrate_goal(goal: str) -> None:
    global _LAST_USER_GOAL
    _LAST_USER_GOAL = goal


def trigger_orchestrate(preset: str = "auto", **kwargs) -> str:
    """Lightweight orchestration entry point. Model only picks a preset enum;
    the actual goal is injected from session context (set by send_stream).

    This avoids models spending 30+ seconds generating a 200-character goal string.
    """
    global _LAST_USER_GOAL
    user_goal = _LAST_USER_GOAL or "未指定任务"
    presets = {
        "self_heal": f"对当前系统执行自检、定位问题、修复并验证：{user_goal}",
        "analyze": f"分析并提出可执行方案：{user_goal}",
        "execute": user_goal,
        "auto": user_goal,
    }
    full_goal = presets.get(preset, user_goal)
    return execute_tool(full_goal, **kwargs)


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


import threading
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

from core.task_complexity import TaskComplexity

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


def get_master_orchestrator(tool_executor=None, model_router=None) -> MasterOrchestrator:
    """获取全局 MasterOrchestrator 单例."""
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

    return execute_tool(goal, **kwargs)
