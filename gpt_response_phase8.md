Phase 8 的目标不是把 DeliberateWorkflow 推翻，而是把它降级成 总调度壳，让专业 Runtime 接管不同任务的最佳实践。

最终结构：

ChatSession
  ↓
IntelligenceHook
  ↓
DeliberateWorkflow
  ↓
CapabilityRuntimeRouter
  ↓
DebugAnalyzeRuntime / CodeRefactorRuntime / ArchitectureDesignRuntime / ResearchRuntime / CreativeRuntime / SecurityRuntime
  ↓
EvidenceGate / Trace / Eval / Learning / Arena
1. 核心 Runtime 列表

Phase 8 先拆 7 个 Runtime：

1. GeneralRuntime
   - 默认兜底
   - 保留当前 DeliberateWorkflow 旧逻辑

2. DebugAnalyzeRuntime
   - bug 排查、根因分析、复现路径、测试通过但真实失败
   - 默认不写文件
   - 输出 root_cause / probes / fix_plan / verification_plan

3. CodePatchRuntime
   - 小范围代码修复
   - 允许最小补丁
   - 强制 diff + test evidence

4. CodeRefactorRuntime
   - 多文件重构、模块拆分、架构内代码迁移
   - 强制 rollback / test matrix / scope guard

5. ArchitectureDesignRuntime
   - 架构方案、技术路线、模块设计
   - 默认不执行写操作
   - 强制 tradeoff / migration plan / risk table

6. ResearchRuntime
   - 最新文档、API、版本、联网事实
   - 强制 web evidence pack

7. CreativeRuntime
   - 图片、视频、prompt、分镜、风格锁
   - 强制 style lock + quality score

8. SecurityRuntime
   - token、secret、权限、删除、shell、生产配置
   - SAFE 模式优先
   - 强制 security_review + approval gate

最小可落地版本先做这 4 个：

GeneralRuntime
DebugAnalyzeRuntime
CodeRefactorRuntime
ArchitectureDesignRuntime
2. 文件清单

新增：

core/runtime/
  __init__.py
  schemas.py
  base_runtime.py
  runtime_router.py
  runtime_registry.py
  general_runtime.py
  debug_analyze_runtime.py
  code_patch_runtime.py
  code_refactor_runtime.py
  architecture_design_runtime.py
  research_runtime.py
  creative_runtime.py
  security_runtime.py

测试：

tests/test_runtime_router.py
tests/test_base_runtime.py
tests/test_debug_analyze_runtime.py
tests/test_code_refactor_runtime.py
tests/test_runtime_integration.py

修改：

core/deliberate_workflow.py
core/intelligence_policy.py
core/intelligence_trace.py
3. Runtime 核心 Schema
core/runtime/schemas.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class CapabilityRuntimeType(str, Enum):
    GENERAL = "general"
    DEBUG_ANALYZE = "debug_analyze"
    CODE_PATCH = "code_patch"
    CODE_REFACTOR = "code_refactor"
    ARCHITECTURE_DESIGN = "architecture_design"
    RESEARCH = "research"
    CREATIVE = "creative"
    SECURITY = "security"


class RuntimeStatus(str, Enum):
    PASS = "pass"
    NEEDS_FIX = "needs_fix"
    BLOCK = "block"
    ERROR = "error"


@dataclass
class RuntimeContext:
    request: str
    goal: dict[str, Any]
    policy: Any
    session_context: dict[str, Any] = field(default_factory=dict)
    trace_run_id: str | None = None
    context_pack: dict[str, Any] = field(default_factory=dict)
    budget: Any | None = None
    cancellation: Any | None = None

    def policy_dict(self) -> dict[str, Any]:
        if hasattr(self.policy, "to_dict"):
            return self.policy.to_dict()
        if isinstance(self.policy, dict):
            return self.policy
        return {"policy": str(self.policy)}


@dataclass
class RuntimeResult:
    runtime: CapabilityRuntimeType
    status: RuntimeStatus
    content: str
    goal: dict[str, Any]
    context_pack: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] | None = None
    attack_report: dict[str, Any] | None = None
    critique_report: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    evidence_gate: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runtime"] = self.runtime.value
        data["status"] = self.status.value
        return data
4. BaseRuntime
core/runtime/base_runtime.py
Python
运行
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
    RuntimeStatus,
)


class BaseCapabilityRuntime(ABC):
    runtime_type: CapabilityRuntimeType = CapabilityRuntimeType.GENERAL

    def __init__(
        self,
        *,
        toolbus: Any,
        trace_store: Any,
        evidence_gate: Any,
        critic_agent: Any,
        plan_gate: Any | None = None,
    ) -> None:
        self.toolbus = toolbus
        self.trace_store = trace_store
        self.evidence_gate = evidence_gate
        self.critic_agent = critic_agent
        self.plan_gate = plan_gate

    @abstractmethod
    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        raise NotImplementedError

    async def gather_context(self, ctx: RuntimeContext) -> dict[str, Any]:
        return {}

    async def build_plan(self, ctx: RuntimeContext, context_pack: dict[str, Any]) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
        })

    async def attack(self, ctx: RuntimeContext, plan: dict[str, Any], context_pack: dict[str, Any]) -> dict[str, Any]:
        return await self.toolbus.call("multi_agent", {
            "mode": "parallel_attack",
            "goal": ctx.goal,
            "plan": plan,
            "request": ctx.request,
            "context_pack": context_pack,
            "agents": [
                "AssumptionBreaker",
                "RegressionHunter",
                "TestGapFinder",
            ],
            "output_schema": "AttackReport",
        })

    async def criticize(
        self,
        ctx: RuntimeContext,
        plan: dict[str, Any],
        context_pack: dict[str, Any],
        attack_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.critic_agent.review(
            goal=ctx.goal,
            plan=plan,
            attack_report=attack_report,
            context_pack=context_pack,
            policy=ctx.policy_dict(),
        )

    async def execute(
        self,
        ctx: RuntimeContext,
        plan: dict[str, Any],
        context_pack: dict[str, Any],
        critique_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "execute",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "critique_report": critique_report,
            "policy": ctx.policy_dict(),
        })

    def evaluate_evidence(
        self,
        ctx: RuntimeContext,
        result: dict[str, Any],
        critique_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = self.evidence_gate.evaluate(
            goal=ctx.goal,
            result=result,
            policy=ctx.policy_dict(),
            critique_report=critique_report or {},
        )
        return report.to_dict() if hasattr(report, "to_dict") else report

    def record_trace(
        self,
        ctx: RuntimeContext,
        *,
        phase: str,
        status: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        if not ctx.trace_run_id:
            return

        self.trace_store.record(
            ctx.trace_run_id,
            phase=phase,
            status=status,
            message=message,
            data={
                "runtime": self.runtime_type.value,
                **(data or {}),
            },
        )

    def _status_from_evidence(self, evidence: dict[str, Any]) -> RuntimeStatus:
        status = evidence.get("status")

        if status == "pass":
            return RuntimeStatus.PASS

        if status == "block":
            return RuntimeStatus.BLOCK

        if status == "needs_fix":
            return RuntimeStatus.NEEDS_FIX

        return RuntimeStatus.PASS
5. GeneralRuntime：保留旧逻辑兜底
core/runtime/general_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class GeneralRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.GENERAL

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="GeneralRuntime selected")

        context_pack = await self.gather_context(ctx)
        plan = await self.build_plan(ctx, context_pack)
        attack_report = await self.attack(ctx, plan, context_pack)
        critique_report = await self.criticize(ctx, plan, context_pack, attack_report)

        result = await self.execute(ctx, plan, context_pack, critique_report)
        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            attack_report=attack_report,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "trace_run_id": ctx.trace_run_id,
            },
        )
6. DebugAnalyzeRuntime

职责边界：

输入：
- bug
- 间歇性问题
- 测试通过但真实失败
- 报错堆栈
- 根因排查

输出：
- root_cause_hypotheses
- probes
- fix_plan
- verification_plan

默认：
- 不写文件
- 不执行破坏性 shell
- 优先搜索本地代码、日志、调用链
core/runtime/debug_analyze_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
    RuntimeStatus,
)


class DebugAnalyzeRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.DEBUG_ANALYZE

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="DebugAnalyzeRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "debug_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
            "require_repro": True,
            "require_probe_plan": True,
            "require_test_gap_analysis": True,
        })

        attack_report = await self.toolbus.call("multi_agent", {
            "mode": "debug_attack",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "agents": [
                "RootCauseHunter",
                "ReproDesigner",
                "RegressionHunter",
                "TestRealityMismatchHunter",
                "ProbeDesigner",
            ],
            "output_schema": "DebugAttackReport",
        })

        critique_report = await self.criticize(
            ctx=ctx,
            plan=plan,
            context_pack=context_pack,
            attack_report=attack_report,
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "debug_analyze",
            "goal": ctx.goal,
            "plan": plan,
            "attack_report": attack_report,
            "critique_report": critique_report,
            "context_pack": context_pack,
            "allow_write": False,
            "allow_shell": False,
            "output_contract": {
                "required_sections": [
                    "root_cause_hypotheses",
                    "evidence",
                    "probe_plan",
                    "minimal_fix_plan",
                    "verification_plan",
                ]
            },
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            attack_report=attack_report,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "no_write": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        local = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": ctx.request,
            "goal": ctx.goal,
            "focus": [
                "stack traces",
                "error logs",
                "call chains",
                "tests",
                "recent edits",
                "UI event handlers",
                "runtime state",
            ],
            "max_results": 16,
        })

        return {
            "local": local,
            "debug_mode": True,
            "requires_repro": True,
        }
7. CodeRefactorRuntime

职责边界：

输入：
- 重构
- 多文件拆分
- 模块边界调整
- service/repository/router 分层
- 架构内代码迁移

输出：
- refactor_plan
- affected_files
- invariants
- rollback_plan
- test_matrix
- diff evidence

强制：
- snapshot/rollback
- tests
- scope guard
- security review if touching auth/config/secret
core/runtime/code_refactor_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class CodeRefactorRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.CODE_REFACTOR

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="CodeRefactorRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "refactor_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
            "require_affected_files": True,
            "require_invariants": True,
            "require_test_matrix": True,
            "require_rollback_plan": True,
            "require_scope_guard": True,
        })

        gate = self._refactor_plan_gate(plan)

        if gate["status"] == "block":
            plan = await self.toolbus.call("execute_plan", {
                "mode": "revise_plan_only",
                "goal": ctx.goal,
                "previous_plan": plan,
                "gate_failures": gate["failures"],
                "context_pack": context_pack,
                "allow_write": False,
                "allow_shell": False,
            })

        attack_report = await self.toolbus.call("multi_agent", {
            "mode": "refactor_attack",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "agents": [
                "ScopeCreepHunter",
                "RegressionHunter",
                "InvariantChecker",
                "TestMatrixReviewer",
                "RollbackReviewer",
            ],
            "output_schema": "RefactorAttackReport",
        })

        critique_report = await self.criticize(
            ctx=ctx,
            plan=plan,
            context_pack=context_pack,
            attack_report=attack_report,
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "refactor_execute",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "attack_report": attack_report,
            "critique_report": critique_report,
            "policy": ctx.policy_dict(),
            "require_snapshot": True,
            "require_diff": True,
            "require_tests": True,
            "require_rollback_plan": True,
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            attack_report=attack_report,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "requires_diff": True,
                "requires_tests": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        repo = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": ctx.request,
            "goal": ctx.goal,
            "focus": [
                "module boundaries",
                "imports",
                "call graph",
                "tests",
                "configuration",
                "public APIs",
                "current file ownership",
            ],
            "max_results": 24,
        })

        return {
            "repo": repo,
            "refactor_mode": True,
        }

    def _refactor_plan_gate(self, plan: dict) -> dict:
        text = str(plan).lower()
        failures = []

        required = [
            ("affected", "missing affected files"),
            ("invariant", "missing invariants"),
            ("test", "missing test matrix"),
            ("rollback", "missing rollback plan"),
        ]

        for needle, msg in required:
            if needle not in text:
                failures.append(msg)

        return {
            "status": "block" if failures else "pass",
            "failures": failures,
        }
8. ArchitectureDesignRuntime

职责边界：

输入：
- 架构路线
- 模块设计
- Phase 规划
- 技术选型
- 工程系统设计

输出：
- problem framing
- architecture options
- recommendation
- implementation plan
- risks
- migration path
- acceptance criteria

默认：
- 不写文件
- 不跑 shell
- 不改配置
core/runtime/architecture_design_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
    RuntimeStatus,
)


class ArchitectureDesignRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.ARCHITECTURE_DESIGN

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="ArchitectureDesignRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "architecture_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
            "require_tradeoffs": True,
            "require_migration_plan": True,
            "require_acceptance_criteria": True,
        })

        attack_report = await self.toolbus.call("multi_agent", {
            "mode": "architecture_review",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "agents": [
                "OverEngineeringCritic",
                "ScalabilityCritic",
                "MigrationRiskCritic",
                "TestingStrategyCritic",
                "MaintainabilityCritic",
            ],
            "output_schema": "ArchitectureReviewReport",
        })

        critique_report = await self.criticize(
            ctx=ctx,
            plan=plan,
            context_pack=context_pack,
            attack_report=attack_report,
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "architecture_answer",
            "goal": ctx.goal,
            "plan": plan,
            "attack_report": attack_report,
            "critique_report": critique_report,
            "context_pack": context_pack,
            "allow_write": False,
            "allow_shell": False,
            "output_contract": {
                "required_sections": [
                    "current_state",
                    "options",
                    "recommended_architecture",
                    "implementation_steps",
                    "risks",
                    "acceptance_criteria",
                ]
            },
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            attack_report=attack_report,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "no_write": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        local = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": ctx.request,
            "goal": ctx.goal,
            "focus": [
                "existing architecture",
                "core modules",
                "previous phases",
                "tests",
                "constraints",
                "known failure modes",
            ],
            "max_results": 20,
        })

        return {
            "local": local,
            "architecture_mode": True,
        }
9. CodePatchRuntime
core/runtime/code_patch_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class CodePatchRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.CODE_PATCH

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="CodePatchRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "patch_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
            "require_files_to_modify": True,
            "require_tests": True,
            "require_minimal_patch": True,
        })

        critique_report = await self.criticize(ctx, plan, context_pack)

        result = await self.toolbus.call("execute_plan", {
            "mode": "patch_execute",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "critique_report": critique_report,
            "require_diff": True,
            "require_tests": True,
            "minimal_patch_only": True,
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "requires_diff": True,
                "requires_tests": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        repo = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": ctx.request,
            "goal": ctx.goal,
            "focus": [
                "target files",
                "related tests",
                "call sites",
                "error logs",
            ],
            "max_results": 12,
        })

        return {
            "repo": repo,
            "patch_mode": True,
        }
10. ResearchRuntime
core/runtime/research_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class ResearchRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.RESEARCH

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="ResearchRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "research_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "require_sources": True,
            "require_citations": True,
            "allow_write": False,
        })

        critique_report = await self.criticize(ctx, plan, context_pack)

        result = await self.toolbus.call("execute_plan", {
            "mode": "research_answer",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "critique_report": critique_report,
            "require_web_sources": True,
            "require_source_attribution": True,
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "requires_web_sources": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        web = await self.toolbus.call("web_search", {
            "query": ctx.request,
            "goal": ctx.goal,
            "max_results": 8,
        })

        evidence_pack = await self.toolbus.call("trm_route", {
            "intent": "review",
            "task": "Build evidence pack from web search results.",
            "goal": ctx.goal,
            "search_result": web,
            "output_schema": "EvidencePack",
        })

        return {
            "web": web,
            "evidence_pack": evidence_pack,
            "research_mode": True,
        }
11. CreativeRuntime
core/runtime/creative_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class CreativeRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.CREATIVE

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="CreativeRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "creative_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "require_style_lock": True,
            "require_negative_constraints": True,
            "allow_write": False,
        })

        critique_report = await self.criticize(ctx, plan, context_pack)

        result = await self.toolbus.call("execute_plan", {
            "mode": "creative_generate",
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "critique_report": critique_report,
            "require_style_lock": True,
            "require_quality_score": True,
            "require_dimension_table": True,
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "requires_style_lock": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        return {
            "creative_mode": True,
            "style_memory": ctx.session_context.get("style_memory", {}),
            "asset_context": ctx.session_context.get("asset_context", {}),
        }
12. SecurityRuntime
core/runtime/security_runtime.py
Python
运行
from __future__ import annotations

from core.runtime.base_runtime import BaseCapabilityRuntime
from core.runtime.schemas import (
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeResult,
)


class SecurityRuntime(BaseCapabilityRuntime):
    runtime_type = CapabilityRuntimeType.SECURITY

    async def run(self, ctx: RuntimeContext) -> RuntimeResult:
        self.record_trace(ctx, phase="runtime", status="ok", message="SecurityRuntime selected")

        context_pack = await self.gather_context(ctx)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "security_plan_only",
            "goal": ctx.goal,
            "request": ctx.request,
            "context_pack": context_pack,
            "policy": ctx.policy_dict(),
            "allow_write": False,
            "allow_shell": False,
            "require_risk_assessment": True,
            "require_approval_gate": True,
        })

        security_report = await self.toolbus.call("security_review", {
            "goal": ctx.goal,
            "plan": plan,
            "context_pack": context_pack,
            "focus": [
                "secret leakage",
                "destructive actions",
                "shell execution",
                "path traversal",
                "unsafe file writes",
                "privilege risk",
            ],
            "output_schema": "SecurityReviewReport",
        })

        critique_report = await self.criticize(
            ctx=ctx,
            plan=plan,
            context_pack=context_pack,
            attack_report={"security_report": security_report},
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "security_response",
            "goal": ctx.goal,
            "plan": plan,
            "security_report": security_report,
            "critique_report": critique_report,
            "allow_write": False,
            "allow_shell": False,
            "require_safe_recommendation": True,
        })

        evidence = self.evaluate_evidence(ctx, result, critique_report)

        return RuntimeResult(
            runtime=self.runtime_type,
            status=self._status_from_evidence(evidence),
            content=str(result.get("content") or result.get("final") or result),
            goal=ctx.goal,
            context_pack=context_pack,
            plan=plan,
            critique_report=critique_report,
            execution_result=result,
            evidence_gate=evidence,
            metadata={
                "runtime": self.runtime_type.value,
                "safe_mode": True,
                "trace_run_id": ctx.trace_run_id,
            },
        )

    async def gather_context(self, ctx: RuntimeContext) -> dict:
        local = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": ctx.request,
            "goal": ctx.goal,
            "focus": [
                "secrets",
                ".env",
                "auth",
                "permissions",
                "shell calls",
                "file writes",
                "config",
            ],
            "max_results": 20,
        })

        return {
            "local": local,
            "security_mode": True,
        }
13. RuntimeRegistry
core/runtime/runtime_registry.py
Python
运行
from __future__ import annotations

from typing import Any

from core.runtime.schemas import CapabilityRuntimeType
from core.runtime.general_runtime import GeneralRuntime
from core.runtime.debug_analyze_runtime import DebugAnalyzeRuntime
from core.runtime.code_patch_runtime import CodePatchRuntime
from core.runtime.code_refactor_runtime import CodeRefactorRuntime
from core.runtime.architecture_design_runtime import ArchitectureDesignRuntime
from core.runtime.research_runtime import ResearchRuntime
from core.runtime.creative_runtime import CreativeRuntime
from core.runtime.security_runtime import SecurityRuntime


class RuntimeRegistry:
    def __init__(
        self,
        *,
        toolbus: Any,
        trace_store: Any,
        evidence_gate: Any,
        critic_agent: Any,
        plan_gate: Any | None = None,
    ) -> None:
        kwargs = {
            "toolbus": toolbus,
            "trace_store": trace_store,
            "evidence_gate": evidence_gate,
            "critic_agent": critic_agent,
            "plan_gate": plan_gate,
        }

        self._runtimes = {
            CapabilityRuntimeType.GENERAL: GeneralRuntime(**kwargs),
            CapabilityRuntimeType.DEBUG_ANALYZE: DebugAnalyzeRuntime(**kwargs),
            CapabilityRuntimeType.CODE_PATCH: CodePatchRuntime(**kwargs),
            CapabilityRuntimeType.CODE_REFACTOR: CodeRefactorRuntime(**kwargs),
            CapabilityRuntimeType.ARCHITECTURE_DESIGN: ArchitectureDesignRuntime(**kwargs),
            CapabilityRuntimeType.RESEARCH: ResearchRuntime(**kwargs),
            CapabilityRuntimeType.CREATIVE: CreativeRuntime(**kwargs),
            CapabilityRuntimeType.SECURITY: SecurityRuntime(**kwargs),
        }

    def get(self, runtime_type: CapabilityRuntimeType):
        return self._runtimes.get(runtime_type) or self._runtimes[CapabilityRuntimeType.GENERAL]

    def all(self):
        return dict(self._runtimes)
14. CapabilityRuntimeRouter

这里不要重新做一套路由系统。直接复用现有 policy.mode、Router V2 信号、PolicyMemory 结果。

core/runtime/runtime_router.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.runtime.schemas import CapabilityRuntimeType


@dataclass
class RuntimeRouteDecision:
    runtime_type: CapabilityRuntimeType
    confidence: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_type": self.runtime_type.value,
            "confidence": self.confidence,
            "reasons": self.reasons,
        }


class CapabilityRuntimeRouter:
    """
    Runtime Router 只决定专业运行时。
    不决定 FAST/DEEP/SAFE，不决定模型。
    """

    def route(
        self,
        *,
        request: str,
        goal: dict[str, Any],
        policy: Any,
        route_features: dict[str, Any] | None = None,
    ) -> RuntimeRouteDecision:
        text = request.lower()
        policy_dict = policy.to_dict() if hasattr(policy, "to_dict") else dict(policy or {})
        mode = self._mode(policy)

        # SAFE 永远优先
        if mode == "SAFE" or self._has_security_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.SECURITY,
                confidence=1.0,
                reasons=["SAFE mode or security signal detected"],
            )

        if mode == "RESEARCH" or self._has_research_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.RESEARCH,
                confidence=0.95,
                reasons=["RESEARCH mode or external evidence required"],
            )

        if mode == "CREATIVE" or self._has_creative_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.CREATIVE,
                confidence=0.95,
                reasons=["CREATIVE mode or visual/prompt generation signal detected"],
            )

        if self._has_debug_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.DEBUG_ANALYZE,
                confidence=0.90,
                reasons=["debug/root-cause/test-reality mismatch signal detected"],
            )

        if self._has_refactor_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.CODE_REFACTOR,
                confidence=0.90,
                reasons=["multi-file refactor or architecture-level code change detected"],
            )

        if self._has_patch_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.CODE_PATCH,
                confidence=0.80,
                reasons=["small code patch signal detected"],
            )

        if self._has_architecture_signal(text):
            return RuntimeRouteDecision(
                runtime_type=CapabilityRuntimeType.ARCHITECTURE_DESIGN,
                confidence=0.85,
                reasons=["architecture/design/planning signal detected"],
            )

        return RuntimeRouteDecision(
            runtime_type=CapabilityRuntimeType.GENERAL,
            confidence=0.60,
            reasons=["fallback to GeneralRuntime"],
        )

    def _mode(self, policy: Any) -> str:
        if hasattr(policy, "mode"):
            mode = getattr(policy, "mode")
            return mode.value if hasattr(mode, "value") else str(mode)

        if isinstance(policy, dict):
            mode = policy.get("mode")
            return mode.value if hasattr(mode, "value") else str(mode)

        return "BALANCED"

    def _has_security_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "token", "secret", ".env", "密码", "密钥",
            "权限", "越权", "漏洞", "注入", "删除", "清空", "重置",
        ])

    def _has_research_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "最新", "当前", "官方文档", "联网", "web", "版本", "api 文档",
        ])

    def _has_creative_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "图片", "视频", "分镜", "镜头", "prompt", "风格", "生图", "生视频",
        ])

    def _has_debug_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "bug", "报错", "不工作", "不生效", "卡住", "根因", "排查",
            "复现", "traceback", "测试通过但", "真实", "偶尔", "间歇",
        ])

    def _has_refactor_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "重构", "多文件", "模块拆分", "分层", "service", "repository",
            "router", "迁移", "解耦", "架构内代码",
        ])

    def _has_patch_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "修复", "改一下", "实现", "补一个", "新增函数",
            "代码", "python", "class", "方法",
        ])

    def _has_architecture_signal(self, text: str) -> bool:
        return any(k in text for k in [
            "架构", "设计", "方案", "路线", "phase", "pipeline",
            "workflow", "系统", "模块", "能力", "runtime",
        ])
15. 与 DeliberateWorkflow 共存

不要一次性重写 DeliberateWorkflow。加一个 runtime delegation 开关：

ENABLE_CAPABILITY_RUNTIME = true
修改 core/deliberate_workflow.py

新增依赖：

Python
运行
from core.runtime.schemas import RuntimeContext
from core.runtime.runtime_router import CapabilityRuntimeRouter
from core.runtime.runtime_registry import RuntimeRegistry

构造函数：

Python
运行
class DeliberateWorkflow:
    def __init__(
        self,
        *,
        toolbus,
        policy_router,
        critic_agent,
        trace_store,
        evidence_gate,
        runtime_registry=None,
        runtime_router=None,
        enable_capability_runtime: bool = True,
        **kwargs,
    ):
        self.toolbus = toolbus
        self.policy_router = policy_router
        self.critic_agent = critic_agent
        self.trace_store = trace_store
        self.evidence_gate = evidence_gate
        self.enable_capability_runtime = enable_capability_runtime

        self.runtime_router = runtime_router or CapabilityRuntimeRouter()
        self.runtime_registry = runtime_registry or RuntimeRegistry(
            toolbus=toolbus,
            trace_store=trace_store,
            evidence_gate=evidence_gate,
            critic_agent=critic_agent,
        )

        # 保留旧字段
        ...

在原来的主流程里，goal 和 policy 创建后插入：

Python
运行
async def execute(self, request: str, context: dict | None = None, policy=None) -> dict:
    context = context or {}

    if policy is None:
        policy = await self.policy_router.route(request, context)

    run = self.trace_store.start_run(
        request,
        mode=self._mode(policy),
        metadata={"capability_runtime_enabled": self.enable_capability_runtime},
    )

    run_id = run.run_id

    goal = await self.toolbus.call("create_goal", {
        "request": request,
        "policy": policy.to_dict() if hasattr(policy, "to_dict") else policy,
    })

    if self.enable_capability_runtime:
        try:
            return await self._execute_with_runtime(
                request=request,
                context=context,
                policy=policy,
                goal=goal,
                trace_run_id=run_id,
            )
        except Exception as exc:
            self.trace_store.record(
                run_id,
                phase="runtime",
                status="error",
                message="Capability runtime failed; falling back to legacy deliberate workflow",
                data={"error": repr(exc)},
            )

    # 旧逻辑保留
    return await self._execute_legacy(
        request=request,
        context=context,
        policy=policy,
        goal=goal,
        trace_run_id=run_id,
    )

新增：

Python
运行
async def _execute_with_runtime(
    self,
    *,
    request: str,
    context: dict,
    policy,
    goal: dict,
    trace_run_id: str,
) -> dict:
    decision = self.runtime_router.route(
        request=request,
        goal=goal,
        policy=policy,
        route_features=getattr(policy, "features", None),
    )

    self.trace_store.record(
        trace_run_id,
        phase="runtime_route",
        status="ok",
        message=f"Selected runtime: {decision.runtime_type.value}",
        data=decision.to_dict(),
    )

    runtime = self.runtime_registry.get(decision.runtime_type)

    ctx = RuntimeContext(
        request=request,
        goal=goal,
        policy=policy,
        session_context=context,
        trace_run_id=trace_run_id,
    )

    result = await runtime.run(ctx)

    payload = result.to_dict()
    payload.setdefault("metadata", {})
    payload["metadata"]["trace_run_id"] = trace_run_id
    payload["metadata"]["runtime_route"] = decision.to_dict()

    self.trace_store.end_run(
        trace_run_id,
        status=result.status.value,
        metadata={
            "runtime": result.runtime.value,
            "runtime_status": result.status.value,
        },
    )

    return payload

保留旧逻辑：

Python
运行
async def _execute_legacy(
    self,
    *,
    request: str,
    context: dict,
    policy,
    goal: dict,
    trace_run_id: str,
) -> dict:
    # 这里放你当前 Phase 1-7 的 DeliberateWorkflow 原流程
    ...

辅助：

Python
运行
def _mode(self, policy) -> str:
    if hasattr(policy, "mode"):
        mode = policy.mode
        return mode.value if hasattr(mode, "value") else str(mode)
    if isinstance(policy, dict):
        return str(policy.get("mode", "unknown"))
    return "unknown"
16. Runtime 逐步迁移策略

不要一次性把所有模式迁过去。用开关控制：

Python
运行
CAPABILITY_RUNTIME_ROLLOUT = {
    "debug_analyze": True,
    "architecture_design": True,
    "code_refactor": True,
    "code_patch": False,
    "research": False,
    "creative": False,
    "security": False,
}

在 router 选中后加：

Python
运行
if not self.runtime_rollout.get(decision.runtime_type.value, False):
    decision.runtime_type = CapabilityRuntimeType.GENERAL
    decision.reasons.append("runtime not rolled out; fallback to GeneralRuntime")

Phase 8 MVP 只启用：

debug_analyze = True
architecture_design = True
code_refactor = True
17. 测试
tests/test_runtime_router.py
Python
运行
from core.runtime.runtime_router import CapabilityRuntimeRouter
from core.runtime.schemas import CapabilityRuntimeType


class FakePolicy:
    def __init__(self, mode="DEEP"):
        self.mode = mode

    def to_dict(self):
        return {"mode": self.mode}


def test_routes_debug_runtime():
    router = CapabilityRuntimeRouter()

    decision = router.route(
        request="测试通过但真实 TUI 鼠标滚动不生效，帮我排查根因",
        goal={},
        policy=FakePolicy("DEEP"),
    )

    assert decision.runtime_type == CapabilityRuntimeType.DEBUG_ANALYZE


def test_routes_refactor_runtime():
    router = CapabilityRuntimeRouter()

    decision = router.route(
        request="重构认证模块，拆分 router service repository，并补测试",
        goal={},
        policy=FakePolicy("DEEP"),
    )

    assert decision.runtime_type == CapabilityRuntimeType.CODE_REFACTOR


def test_routes_architecture_runtime():
    router = CapabilityRuntimeRouter()

    decision = router.route(
        request="设计 Phase 8 Capability Runtime 架构方案",
        goal={},
        policy=FakePolicy("DEEP"),
    )

    assert decision.runtime_type == CapabilityRuntimeType.ARCHITECTURE_DESIGN


def test_safe_overrides_everything():
    router = CapabilityRuntimeRouter()

    decision = router.route(
        request="删除配置前检查 token 泄漏风险",
        goal={},
        policy=FakePolicy("SAFE"),
    )

    assert decision.runtime_type == CapabilityRuntimeType.SECURITY
tests/test_debug_analyze_runtime.py
Python
运行
import pytest

from core.runtime.debug_analyze_runtime import DebugAnalyzeRuntime
from core.runtime.schemas import RuntimeContext


class FakeToolbus:
    async def call(self, name, payload):
        if name == "trm_route":
            return {"results": ["fake call chain", "fake test"]}
        if name == "execute_plan":
            if payload["mode"] == "debug_plan_only":
                return {"plan": ["inspect", "probe", "verify"]}
            return {
                "content": "root cause hypotheses + verification plan",
                "tool_results": [
                    {
                        "summary": "debug analysis generated",
                        "success": True,
                        "supports": ["root cause"],
                    }
                ],
            }
        if name == "multi_agent":
            return {"findings": ["possible focus issue"]}
        raise AssertionError(name)


class FakeTrace:
    def record(self, *args, **kwargs):
        pass


class FakeEvidenceGate:
    def evaluate(self, **kwargs):
        return {
            "status": "pass",
            "score": 1.0,
        }


class FakeCritic:
    async def review(self, **kwargs):
        return {"status": "pass", "findings": []}


class FakePolicy:
    mode = "DEEP"

    def to_dict(self):
        return {"mode": "DEEP"}


@pytest.mark.asyncio
async def test_debug_runtime_runs_without_write():
    runtime = DebugAnalyzeRuntime(
        toolbus=FakeToolbus(),
        trace_store=FakeTrace(),
        evidence_gate=FakeEvidenceGate(),
        critic_agent=FakeCritic(),
    )

    result = await runtime.run(
        RuntimeContext(
            request="测试通过但真实 TUI 不工作",
            goal={"finish_line": ["root cause"]},
            policy=FakePolicy(),
            trace_run_id="run_1",
        )
    )

    assert result.runtime.value == "debug_analyze"
    assert result.status.value == "pass"
    assert result.metadata["no_write"] is True
tests/test_runtime_integration.py
Python
运行
import pytest

from core.runtime.schemas import CapabilityRuntimeType


@pytest.mark.asyncio
async def test_deliberate_workflow_delegates_to_runtime(fake_deliberate_workflow):
    result = await fake_deliberate_workflow.execute(
        "测试通过但真实 TUI 鼠标滚动不生效，帮我排查根因",
        context={},
    )

    assert result["runtime"] == CapabilityRuntimeType.DEBUG_ANALYZE.value
    assert result["metadata"]["runtime_route"]["runtime_type"] == "debug_analyze"
18. 最小可落地版本

MVP 只做这些：

core/runtime/schemas.py
core/runtime/base_runtime.py
core/runtime/runtime_router.py
core/runtime/runtime_registry.py
core/runtime/general_runtime.py
core/runtime/debug_analyze_runtime.py
core/runtime/code_refactor_runtime.py
core/runtime/architecture_design_runtime.py

先不启用：

ResearchRuntime
CreativeRuntime
SecurityRuntime
CodePatchRuntime

但文件骨架可以先放进去，rollout 关掉。

19. Phase 8 验收标准
1. RuntimeRouter 能把 debug/refactor/architecture 三类任务稳定分流
2. DeliberateWorkflow 可以通过 feature flag 启用/关闭 Capability Runtime
3. Runtime 失败时自动 fallback 到 legacy DeliberateWorkflow
4. 每个 Runtime 都写入 trace：runtime_route + runtime
5. RuntimeResult 统一 schema
6. DebugAnalyzeRuntime 默认不写文件
7. CodeRefactorRuntime 强制 affected_files / invariants / tests / rollback
8. ArchitectureDesignRuntime 默认不写文件、不跑 shell
9. 现有 174/174 测试不回退
10. 新增 Runtime 测试后总测试数达到 195+
20. 推荐落地顺序
Step 1:
加 schemas.py / base_runtime.py / runtime_router.py / runtime_registry.py

Step 2:
实现 GeneralRuntime，确保它能兜底旧逻辑

Step 3:
实现 DebugAnalyzeRuntime
先把 debug 类请求从 DeliberateWorkflow 拆出去

Step 4:
实现 ArchitectureDesignRuntime
把方案设计类请求拆出去

Step 5:
实现 CodeRefactorRuntime
把高风险多文件重构拆出去

Step 6:
DeliberateWorkflow 增加 _execute_with_runtime()
feature flag 默认打开 debug/architecture/refactor 三类

Step 7:
补 Runtime trace + Runtime eval case

Step 8:
再逐步打开 Research / Creative / Security / CodePatch
最终建议

Phase 8 不要追求一次拆完。第一版只拆：

DebugAnalyzeRuntime
ArchitectureDesignRuntime
CodeRefactorRuntime

这三类最值得拆，因为它们的工作流差异最大：

DebugAnalyze：先找根因，不应急着改代码
ArchitectureDesign：只做设计，不应执行写操作
CodeRefactor：高风险修改，必须强制 tests + rollback

一句话：

Phase 8 的核心是把 DeliberateWorkflow 从“万能大脑”降级成“运行时调度器”，让每类任务进入自己的专业推理流水线。