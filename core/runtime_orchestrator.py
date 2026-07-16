"""CRUX Runtime Orchestrator — 量身定制的全功能运行编排引擎.

基于 MasterOrchestrator 的六阶段闭环，叠加全部 CRUX 能力系统：
  DNA 人格 · 七兽协奏 · A/B/C/D 分级 · 白虎自愈 · 流式进度
  事件发射 · 暂停恢复 · Dry-Run · 真实费用 · 技能注入 · 插件工具
  Agent 角色路由 · ChatSession 集成 · 能力热刷新

用法:
    from core.runtime_orchestrator import execute, execute_stream, preview

    result = execute("重构支付模块")
    for event in execute_stream("重构支付模块"):
        print(event.to_tui())
    plan = preview("设计架构")  # dry-run
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.orchestrator")
ROOT = Path(__file__).parent.parent


# ═══════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════

# TaskComplexity is now the canonical classifier — imported from core.task_complexity
from core.task_complexity import TaskClassification, TaskComplexity, classify_task  # noqa: E402

class DNAProfile(Enum):
    CRUX = "crux"; CLAUDE = "claude"; CODEBUDDY = "codebuddy"
    CODEX = "codex"; KIMI = "kimi"; ZCODE = "zcode"

class BeastRole(Enum):
    BAIHU = "baihu"; XUANWU = "xuanwu"; QINGLONG = "qinglong"
    ZHUQUE = "zhuque"; QILIN = "qilin"; TENGSHE = "tengshe"; YINGLONG = "yinglong"

class OrchestrationMode(Enum):
    AUTO = "auto"; FULL = "full"; FAST = "fast"; DRY_RUN = "dry_run"


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class OrchestrationError:
    phase: str = ""; step: int = 0; code: str = "UNKNOWN"
    message: str = ""; recoverable: bool = True; suggestion: str = ""


@dataclass
class OrchestrationProgress:
    trace_id: str = ""; phase: str = ""; phase_index: int = 0
    total_phases: int = 6; step: int = 0; total_steps: int = 0
    message: str = ""; level: str = "info"; beast: str = ""
    elapsed_ms: float = 0.0

    def to_tui(self) -> tuple[str, str]:
        prefix = f"[{self.beast}]" if self.beast else f"({self.phase})"
        return (f"class:activity-{self.level}", f"{prefix} {self.message}")


@dataclass
class OrchestrationResult:
    trace_id: str = ""; goal: str = ""; grade: str = "B"; dna: str = "crux"
    mode: str = "auto"; verdict: str = "unknown"; model_tier: str = ""
    complexity: str = ""; phases_completed: list[str] = field(default_factory=list)
    steps_executed: int = 0; steps_failed: int = 0
    total_duration_ms: float = 0.0; cost_estimate_usd: float = 0.0
    recovery_attempts: int = 0
    artifacts: list[str] = field(default_factory=list)
    errors: list[OrchestrationError] = field(default_factory=list)
    plan_preview: list[dict] = field(default_factory=list)
    raw_result: dict = field(default_factory=dict)


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
    "架构": DNAProfile.CLAUDE, "architecture": DNAProfile.CLAUDE, "设计": DNAProfile.CLAUDE, "design": DNAProfile.CLAUDE,
    "实现": DNAProfile.CODEBUDDY, "implement": DNAProfile.CODEBUDDY,
    "审查": DNAProfile.CODEX, "review": DNAProfile.CODEX, "审计": DNAProfile.CODEX, "audit": DNAProfile.CODEX,
    "修复": DNAProfile.CRUX, "fix": DNAProfile.CRUX, "重构": DNAProfile.CRUX, "refactor": DNAProfile.CRUX,
    "推理": DNAProfile.KIMI, "analyze": DNAProfile.KIMI,
    "工具": DNAProfile.ZCODE, "tool": DNAProfile.ZCODE,
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
    OrchestrationMode.AUTO: set(), OrchestrationMode.FULL: set(),
    OrchestrationMode.FAST: {"context", "verify"}, OrchestrationMode.DRY_RUN: {"execute", "verify", "close"},
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
    "implementer": "Implementer", "architect": "Architecture-Documenter",
    "reviewer": "Code-Reviewer", "debugger": "Debugger", "tester": "Implementer-Test",
    "refactor": "Implementer-Refactor", "security": "Security-Auditor",
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

class _StreamStop(Exception):
    """内部: 携带结果结束流式生成器."""
    def __init__(self, result: OrchestrationResult):
        self.result = result


class RuntimeOrchestrator:
    """CRUX 量身定制 · 全能力编排器."""

    def __init__(
        self, tool_executor: Callable | None = None, model_router: Callable | None = None,
        *, mode: OrchestrationMode | str = OrchestrationMode.AUTO,
        callbacks: OrchestrationCallbacks | None = None,
        max_recovery: int = 3, max_concurrent: int = 8,
        skills: list[str] | None = None, cost_budget_usd: float = 5.0,
    ) -> None:
        self._tool_executor = tool_executor; self._model_router = model_router
        self.mode = mode if isinstance(mode, OrchestrationMode) else OrchestrationMode(mode)
        self.callbacks = callbacks or OrchestrationCallbacks()
        self.max_recovery = max_recovery; self.max_concurrent = max_concurrent
        self.skills = skills or []; self.cost_budget_usd = cost_budget_usd
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
        result = None
        for _ in self.execute_stream(goal, **overrides):
            pass
        raise RuntimeError("execute_stream should have raised _StreamStop")

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
            raise _StreamStop(result)
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
                raise _StreamStop(result)

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
                try: self.callbacks.on_complete(result)
                except Exception: pass

            yield self._emit(p, "info", f"CLOSE → {result.verdict} | {result.total_duration_ms:.0f}ms | \${result.cost_estimate_usd:.4f}")

        except KeyboardInterrupt:
            result.verdict = "cancelled"
            yield self._emit(p, "warn", "用户中断")
            raise _StreamStop(result)
        except _StreamStop:
            raise
        except Exception as e:
            result.verdict = "fail"
            err = OrchestrationError(phase=p.phase, code=type(e).__name__, message=str(e)[:200])
            result.errors.append(err)
            yield self._emit(p, "error", str(e)[:120])
            raise _StreamStop(result)
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
            return [{"trace_id": tid, "goal": i["goal"][:60], "elapsed_ms": (time.monotonic() - i["started_at"]) * 1000}
                    for tid, i in self._active_runs.items()]

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
                name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
                role_match = re.search(r'^role:\s*(.+)$', content, re.MULTILINE)
                if name_match:
                    name = name_match.group(1).strip().lower().replace(" ", "-")
                    role = role_match.group(1).strip().lower() if role_match else name
                    self._agent_roles[name] = name_match.group(1).strip()
                    self._agent_roles[role] = name_match.group(1).strip()
            except Exception:
                pass

    def _load_model_pricing(self) -> None:
        """从 models.json 和 provider 获取实际定价."""
        try:
            # 默认定价 ($/1M tokens, 转为 $/1K)
            defaults = {
                "deepseek": 0.00028,   # deepseek-v4: $0.28/M input
                "crux": 0.0005,
                "zhipu": 0.0,          # free tier
                "claude": 0.003,       # claude sonnet: $3/M
                "openai": 0.002,       # gpt-4o-mini: $2/M
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
            DNAProfile.CRUX: "implementer", DNAProfile.CLAUDE: "architect",
            DNAProfile.CODEBUDDY: "implementer", DNAProfile.CODEX: "reviewer",
            DNAProfile.KIMI: "debugger", DNAProfile.ZCODE: "implementer-refactor",
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
                result.plan_preview = [{"step": i + 1, "action": t.get("description", f"Step {i+1}"),
                                         "tool": t.get("tool", "auto")} for i, t in enumerate(tasks)]
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
        self, trace_id: str, goal: str, grade: TaskComplexity,
        executor: Callable, p: OrchestrationProgress, result: OrchestrationResult,
    ) -> Generator[OrchestrationProgress, None, None]:
        raw = self._run_master(trace_id, goal, executor, grade)
        self._parse_raw_result(raw, result)
        self._compute_verdict(result)
        yield self._emit(p, "info", f"执行完成: {result.steps_executed} 步骤")

    def _execute_multi_agent(
        self, trace_id: str, goal: str, grade: TaskComplexity, dna: DNAProfile,
        executor: Callable, p: OrchestrationProgress, result: OrchestrationResult,
    ) -> Generator[OrchestrationProgress, None, None]:
        try:
            from core.multi_agent_decompose import SmartDecomposer
            from core.multi_agent_swarm import AgentSwarm

            decomposer = SmartDecomposer()
            tasks = decomposer.decompose(goal, max_tasks=8)
            steps = [t.get("description", f"Step {i+1}") for i, t in enumerate(tasks)]
            role = self._select_agent_role(dna)

            yield self._emit(p, "info", f"Multi-Agent: {len(steps)} 任务 · 角色 {role}")

            swarm = AgentSwarm(execute_tool=executor, model_router=self._model_router,
                               max_workers=min(len(steps), self.max_concurrent))
            swarm_result = swarm.dispatch("{{item}}", steps, role=role)

            result.steps_executed = len(steps)
            result.verdict = "pass" if swarm_result and "error" not in str(swarm_result).lower() else "needs_fix"
            yield self._emit(p, "info", f"Multi-Agent 完成: {result.steps_executed} 任务")
        except (ImportError, Exception) as e:
            logger.info("[%s] Multi-agent 不可用 (%s)，降级 MasterOrchestrator", trace_id, e)
            yield from self._execute_via_master(trace_id, goal, grade, executor, p, result)

    def _run_master(self, trace_id: str, goal: str, executor: Callable, grade: TaskComplexity) -> dict:
        from core.orchestration import MasterOrchestrator, ExecutionBudget

        def _on_phase(phase: str, action: str, details: dict | None) -> None:
            if self.callbacks.on_phase_start and action == "start":
                try: self.callbacks.on_phase_start(phase, str(details or ""))
                except Exception: pass
            if self.callbacks.on_phase_done and action == "done":
                try: self.callbacks.on_phase_done(phase, 0)
                except Exception: pass
            self._emit_event(f"orchestration:phase:{action}", {"trace_id": trace_id, "phase": phase, "details": details})

        budget = ExecutionBudget(
            total_timeout_s=600.0, per_task_timeout_s=180.0,
            max_retries=2 if grade != TaskComplexity.CRITICAL else 0, max_consecutive_failures=3,
        )
        orch = MasterOrchestrator(tool_executor=executor, model_router=self._model_router,
                                   budget=budget, phase_callback=_on_phase)
        return orch.run(goal)

    def _build_executor(self, trace_id: str) -> Callable:
        """构建能力感知执行器 — 插件 > TRM > ToolRegistry."""
        plugin_tools = {}
        try:
            from core.plugin_system import PluginManager
            for name, handler in getattr(PluginManager(), '_tool_handlers', {}).items():
                plugin_tools[name] = handler
        except Exception:
            pass

        # 技能上下文 — 注入到工具调用的 kwargs
        skill_ctx = {}
        if self.skills:
            skill_ctx["_skills"] = self.skills

        def _exec(name: str, args: dict) -> str:
            args_with_skills = {**args, **skill_ctx}
            if name in plugin_tools:
                try: return str(plugin_tools[name](**args_with_skills))
                except Exception as e: return f"[插件错误] {name}: {e}"
            try:
                from core.tool_registry_mesh import ToolRegistryMesh
                trm = ToolRegistryMesh()
                trm.discover_all()
                if name in trm._function_map:
                    r = trm._call_tool(name, args_with_skills)
                    if r is not None: return str(r)
            except Exception: pass
            try:
                from core.tools import get_registry
                registry = get_registry()
                if name in registry._executors:
                    return str(registry._executors[name](**args_with_skills))
            except Exception: pass
            return f"[错误] 工具不可用: {name}"
        return _exec

    # ── Internal: Helpers ───────────────────────────────────

    def _resolve_params(self, goal: str, overrides: dict) -> tuple[TaskComplexity, DNAProfile, OrchestrationMode]:
        grade = overrides.get("grade"); dna_p = overrides.get("dna_profile") or overrides.get("dna")
        mode = overrides.get("mode") or overrides.get("mode_override") or self.mode
        if isinstance(grade, str):
            try: grade = TaskComplexity[grade]
            except (KeyError, TypeError): grade = None
        if isinstance(dna_p, str):
            try: dna_p = DNAProfile(dna_p)
            except ValueError: dna_p = None
        if isinstance(mode, str):
            try: mode = OrchestrationMode(mode)
            except ValueError: mode = self.mode
        classification = classify_task(goal)
        auto_grade = classification.complexity
        auto_dna = _resolve_dna(goal)
        if grade is None: grade = auto_grade
        if dna_p is None: dna_p = auto_dna
        if not isinstance(mode, OrchestrationMode): mode = self.mode
        if mode == OrchestrationMode.AUTO:
            mode = _COMPLEXITY_DEFAULT_MODE.get(grade, OrchestrationMode.AUTO)
        return grade, dna_p, mode

    def _should_skip(self, phase: str, mode: OrchestrationMode) -> bool:
        return phase in _MODE_SKIP.get(mode, set())

    def _run_phase(self, p: OrchestrationProgress, phase: str, mode: OrchestrationMode) -> Generator[OrchestrationProgress, None, None]:
        p.phase = phase; p.phase_index = _PHASE_INDEX.get(phase, 0)
        if self._should_skip(phase, mode):
            yield self._emit(p, "info", f"{phase.upper()} → 跳过")
        else:
            yield self._emit(p, "info", f"{phase.upper()} → 开始")
            yield self._emit(p, "info", f"{phase.upper()} → 完成")

    def _dry_run_phase(self, goal: str, grade: TaskComplexity, dna: DNAProfile,
                        p: OrchestrationProgress, result: OrchestrationResult) -> Generator[OrchestrationProgress, None, None]:
        yield self._emit(p, "info", f"DRY-RUN → {grade.name}级 · DNA {dna.value}")
        try:
            from core.multi_agent_decompose import SmartDecomposer
            decomposer = SmartDecomposer()
            tasks = decomposer.decompose(goal, max_tasks=8)
            result.plan_preview = [{"step": i + 1, "action": t.get("description", f"Step {i+1}"),
                                     "tool": t.get("tool", "auto")} for i, t in enumerate(tasks)]
        except Exception:
            result.plan_preview = [{"step": 1, "action": goal, "tool": "auto"}]
        result.verdict = "dry_run"
        for step in result.plan_preview:
            yield self._emit(p, "info", f"  步骤 {step['step']}: {step['action'][:80]}")

    def _parse_raw_result(self, raw: dict, result: OrchestrationResult) -> None:
        result.raw_result = raw; result.model_tier = raw.get("model_tier", "")
        result.complexity = raw.get("complexity", "")
        if raw.get("error"):
            result.errors.append(OrchestrationError(phase="execute", code="MASTER_ERROR", message=raw["error"][:200]))
        exec_data = raw.get("execution", {})
        result.steps_executed = exec_data.get("completed", 0); result.steps_failed = exec_data.get("failed", 0)

    def _compute_verdict(self, result: OrchestrationResult) -> None:
        if result.errors: result.verdict = "needs_fix" if result.steps_executed > 0 else "fail"
        elif result.steps_failed == 0 and result.steps_executed > 0: result.verdict = "pass"
        elif result.steps_executed > 0: result.verdict = "needs_fix"
        else: result.verdict = "pass"

    def _estimate_cost(self, result: OrchestrationResult) -> float:
        rate = self._model_pricing.get("default", 0.001)  # $/1K tokens
        est_tokens = result.steps_executed * 10000  # ~10K tokens/step
        return round(est_tokens * rate / 1000, 6)

    def _archive_replay(self, trace_id: str, goal: str, grade: str, dna: str, result: OrchestrationResult) -> None:
        try:
            from core.run_replay import save_run_replay
            save_run_replay(trace_id, {"goal": goal, "grade": grade, "dna": dna, "verdict": result.verdict,
                                        "cost_usd": result.cost_estimate_usd, "duration_ms": result.total_duration_ms},
                            [{"phase": e.phase, "code": e.code, "message": e.message} for e in result.errors], [])
            result.artifacts.append(f"output/replays/{trace_id}.json")
        except Exception as e:
            logger.debug("[%s] 复盘失败: %s", trace_id, e)

    def _emit_event(self, name: str, data: Any) -> None:
        try:
            from core.event_bus import bus
            bus.emit(name, data=data)
        except Exception: pass

    def _emit(self, p: OrchestrationProgress, level: str, message: str) -> OrchestrationProgress:
        p.level = level; p.message = message
        if self.callbacks.on_progress:
            try: self.callbacks.on_progress(p)
            except Exception: pass
        return p

    def _emit_beast(self, p: OrchestrationProgress, beast: BeastRole) -> OrchestrationProgress:
        p.beast = beast.value; p.level = "beast"
        p.message = _BEAST_MSGS.get(beast, str(beast))
        if self.callbacks.on_beast_activate:
            try: self.callbacks.on_beast_activate(beast.value, p.message)
            except Exception: pass
        return p


# ═══════════════════════════════════════════════════════════════
# ChatSession Integration
# ═══════════════════════════════════════════════════════════════

class OrchestrationMixin:
    """混入 ChatSession — 编排器接入对话流."""

    def _init_orchestrator(self) -> None:
        self._orchestrator = RuntimeOrchestrator(callbacks=OrchestrationCallbacks(
            on_progress=self._orch_on_progress,
            on_phase_start=self._orch_on_phase,
            on_complete=self._orch_on_complete,
        ))

    def _orch_on_progress(self, event: OrchestrationProgress) -> None:
        style, text = event.to_tui()
        if hasattr(self, 'message_pane'):
            self.message_pane.append_message("system", text)

    def _orch_on_phase(self, phase: str, message: str) -> None:
        pass

    def _orch_on_complete(self, result: OrchestrationResult) -> None:
        if hasattr(self, 'message_pane'):
            summary = (f"[编排完成] {result.verdict.upper()} | {result.grade}级·{result.dna} | "
                       f"{result.steps_executed}步骤 | {result.total_duration_ms:.0f}ms | \${result.cost_estimate_usd:.4f}")
            self.message_pane.append_message("system", summary)

    def orchestrate(self, goal: str, **kwargs) -> OrchestrationResult:
        if not hasattr(self, '_orchestrator'): self._init_orchestrator()
        return self._orchestrator.execute(goal, **kwargs)

    def orchestrate_stream(self, goal: str, **kwargs):
        if not hasattr(self, '_orchestrator'): self._init_orchestrator()
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
            if _instance is None: _instance = RuntimeOrchestrator(**kwargs)
    return _instance

def execute(goal: str, **kwargs) -> OrchestrationResult:
    try:
        for _ in get_orchestrator().execute_stream(goal, **kwargs):
            pass
    except _StreamStop as e:
        return e.result
    return OrchestrationResult(goal=goal, verdict="fail")

def execute_stream(goal: str, **kwargs):
    return get_orchestrator().execute_stream(goal, **kwargs)

def preview(goal: str, **kwargs) -> OrchestrationResult:
    return get_orchestrator().preview(goal, **kwargs)
