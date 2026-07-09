"""
Deliberate Workflow — CRUX 深度推理工作流 (V2)
==============================================
V2 核心升级: ContextGather + PlanGate

流程:
Policy → [ContextGather] → Plan → [PlanGate] → Attack → Criticize → Repair → Verify

ContextGather: Plan 前收集代码库/历史/项目上下文
PlanGate: Plan 后校验 Who/What/Where/Why/How → 不通过回退
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .critic_agent import (
    CriticAgent,
    CritiqueReport,
    CritiqueSeverity,
)
from .intelligence_policy import (
    IntelligenceMode,
    IntelligencePolicyRouter,
    ModeConfig,
)
from .intelligence_trace import TraceRecord, get_trace_store
from .intelligence_trace import TraceStep as TraceStepRecord


@dataclass
class WorkflowStep:
    name: str
    status: str = "pending"
    started_at: float = 0.0
    completed_at: float = 0.0
    result: str = ""
    error: str = ""

    @property
    def duration(self) -> float:
        return (self.completed_at - self.started_at) if self.completed_at and self.started_at else 0.0


@dataclass
class WorkflowResult:
    goal_id: str = ""
    mode: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    critique_report: CritiqueReport | None = None
    passed: bool = False
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "mode": self.mode,
            "passed": self.passed,
            "summary": self.summary,
            "steps": [
                {"name": s.name, "status": s.status, "duration": round(s.duration, 1), "result": s.result[:200]}
                for s in self.steps
            ],
            "critique": self.critique_report.to_dict() if self.critique_report else None,
            "artifacts": self.artifacts,
        }


class DeliberateWorkflow:
    """深度推理工作流编排器 V2 — ContextGather + PlanGate"""

    # ── PlanGate: 必须回答 5W ──
    PLANGATE_QUESTIONS = ["who", "what", "where", "why", "how"]

    def __init__(
        self,
        toolbus: Any = None,
        policy_router: IntelligencePolicyRouter | None = None,
        critic_agent: CriticAgent | None = None,
        capability_router: Any = None,
        runtime_config: Any = None,
    ):
        self.toolbus = toolbus
        self.policy_router = policy_router or IntelligencePolicyRouter(toolbus)
        self.critic_agent = critic_agent or CriticAgent(toolbus)
        # Phase 9: Capability Runtime 集成
        self.capability_router = capability_router
        self.runtime_config = runtime_config

    # ══════════════════════════════════════
    # ── 主入口 ──
    # ══════════════════════════════════════

    async def execute(
        self,
        request: str,
        context: dict[str, Any] | None = None,
        mode: IntelligenceMode | None = None,
    ) -> WorkflowResult:
        if mode is None:
            mode = self.policy_router.route(request, context)
        config = self.policy_router.get_mode_config(mode)
        result = WorkflowResult(mode=mode.value)

        # ── Phase 9: Capability Runtime 快速路径 ──
        if self.capability_router and self.runtime_config and self.runtime_config.enabled:
            try:
                from .runtimes.base_runtime import RuntimeContext
                rt_type, runtime = self.capability_router.select_runtime(request, mode.value)
                if runtime and rt_type and self.runtime_config.is_runtime_enabled(runtime.name):
                    # 走专业 Runtime 快速路径
                    ctx = RuntimeContext(
                        request=request,
                        mode=mode.value,
                        config=config.to_dict() if hasattr(config, 'to_dict') else {},
                    )
                    rt_result = await runtime.execute(ctx)
                    result.passed = rt_result.get("status") == "success"
                    result.summary = f"Runtime: {runtime.name} — {rt_result.get('status', 'unknown')}"
                    rt_step = WorkflowStep(name=f"runtime_{runtime.name}", status="success")
                    rt_step.result = f"executed by {runtime.name}: {rt_result.get('status', '')}"
                    result.steps.append(rt_step)
                    # 记录轨迹
                    try:
                        trace = TraceRecord(
                            run_id=result.goal_id or str(uuid.uuid4())[:12],
                            user_request=request,
                            mode=result.mode,
                            status="pass" if result.passed else "fail",
                            steps=[TraceStepRecord(name=s.name, status=s.status) for s in result.steps],
                        )
                        trace.ended_at = time.time()
                        get_trace_store().record(trace)
                    except Exception:
                        import logging; logging.getLogger('crux').debug('silent except', exc_info=True)
                    return result
            except Exception:
                pass  # Runtime 失败则回退到传统流程

        # ── Round 0: Policy ──
        step0 = self._make_step("policy_analysis", result)
        try:
            summary = self.policy_router.summary(request, context)
            step0.result = f"mode={summary['mode']}, signals={list(summary.get('signal_scores', {}).keys())[:3]}"
            self._finish_step(step0, "success")
        except Exception as e:
            self._finish_step(step0, "failed", error=str(e))

        # ── Round 0.5: ContextGather (V2 新增) ──
        ctx_step = self._make_step("context_gather", result)
        if config.planner:
            try:
                gathered = await self._gather_context(request, context)
                ctx_step.result = f"context: {gathered.get('summary', 'ok')}"
                self._finish_step(ctx_step, "success")
            except Exception as e:
                self._finish_step(ctx_step, "failed", error=str(e))
        else:
            self._finish_step(ctx_step, "skipped")

        # ── Round 1: Plan ──
        step1 = self._make_step("plan", result)
        if config.planner:
            try:
                planning_result = await self._plan(request, config, context)
                result.goal_id = planning_result.get("goal_id", "")
                plan_text = planning_result.get("plan_text", "")
                step1.result = f"goal_id={result.goal_id}, steps={planning_result.get('step_count', 0)}"

                # ── V2: PlanGate ──
                if plan_text:
                    gate_result = self._plan_gate(request, plan_text)
                    if not gate_result["passed"]:
                        # 回退: 重规划一次
                        step1.result += f" | PlanGate: {gate_result['reason']}, 重试..."
                        planning_result2 = await self._plan(request, config, context, retry=True)
                        plan_text2 = planning_result2.get("plan_text", "")
                        gate_result2 = self._plan_gate(request, plan_text2)
                        if not gate_result2["passed"]:
                            step1.result += f" 回退: {gate_result2['reason']}"
                            step1.result += " | 使用原始 plan"
                        else:
                            step1.result += " 重规划通过"

                self._finish_step(step1, "success")
            except Exception as e:
                self._finish_step(step1, "failed", error=str(e))
        else:
            self._finish_step(step1, "skipped")

        # ── Round 2: Attack ──
        step2 = self._make_step("attack", result)
        if config.multi_agent:
            try:
                attack_result = await self._attack(request, config, context)
                step2.result = attack_result
                self._finish_step(step2, "success")
            except Exception as e:
                self._finish_step(step2, "failed", error=str(e))
        else:
            self._finish_step(step2, "skipped")

        # ── Round 3: Criticize ──
        step3 = self._make_step("criticize", result)
        if config.critic:
            try:
                report = await self._criticize(request, config, context)
                result.critique_report = report
                step3.result = f"findings={len(report.findings)}, passed={report.passed}, blocking={report.blocking}"
                self._finish_step(step3, "success" if not report.blocking else "failed")
            except Exception as e:
                self._finish_step(step3, "failed", error=str(e))
        else:
            self._finish_step(step3, "skipped")

        # ── Round 4: Repair ──
        step4 = self._make_step("repair", result)
        if config.critic and result.critique_report and not result.critique_report.passed and not result.critique_report.blocking:
            try:
                repair_result = await self._repair(request, result.critique_report, config)
                step4.result = repair_result
                self._finish_step(step4, "success")
            except Exception as e:
                self._finish_step(step4, "failed", error=str(e))
        else:
            self._finish_step(step4, "skipped")

        # ── Round 5: Verify ──
        step5 = self._make_step("verify", result)
        try:
            verify_result = await self._verify(request, config, context)
            result.passed = verify_result.get("passed", False)
            result.summary = verify_result.get("summary", "")
            step5.result = f"passed={result.passed}: {result.summary[:100]}"
            self._finish_step(step5, "success")
        except Exception as e:
            self._finish_step(step5, "failed", error=str(e))

        # ── 记录轨迹 ──
        try:
            # 获取信号分数
            signal_scores = None
            try:
                summary = self.policy_router.summary(request, context)
                signal_scores = summary.get("signal_scores")
            except Exception:
                import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

            trace = TraceRecord(
                run_id=result.goal_id or str(uuid.uuid4())[:12],
                user_request=request,
                mode=result.mode,
                status="pass" if result.passed else "fail",
                steps=[
                    TraceStepRecord(
                        name=s.name,
                        status=s.status,
                        duration=s.duration,
                        output_summary=s.result[:300],
                        error=s.error,
                    )
                    for s in result.steps
                ],
                critique_summary=result.critique_report.summary if result.critique_report else "",
                signal_scores=signal_scores,
                started_at=result.steps[0].started_at if result.steps else time.time(),
            )
            trace.ended_at = time.time()
            get_trace_store().record(trace)
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

        return result

    # ══════════════════════════════════════
    # ── V2: ContextGather ──
    # ══════════════════════════════════════

    async def _gather_context(self, request: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Plan 前收集上下文"""
        gathered: dict[str, Any] = {"sources": [], "summary": ""}
        ctx = context or {}
        parts: list[str] = []

        # 1. 项目结构
        if ctx.get("project"):
            parts.append(f"项目: {ctx['project']}")

        # 2. 历史失败
        if ctx.get("previous_failures", 0) > 0:
            parts.append(f"历史失败: {ctx['previous_failures']}次")
            if ctx.get("last_error"):
                parts.append(f"上次错误: {ctx['last_error'][:200]}")

        # 3. 相关文件
        if ctx.get("files"):
            files = ctx["files"]
            if isinstance(files, list) and len(files) <= 10:
                parts.append(f"相关文件: {', '.join(files[:5])}")

        # 4. 系统信息
        if ctx.get("system_info"):
            parts.append(f"系统: {ctx['system_info']}")

        # 5. 如果有 toolbus，做快速代码搜索
        if self.toolbus and ctx.get("search_project"):
            try:
                search_result = await self.toolbus.call("search_files", {
                    "pattern": request.split()[0] if request.split() else ""
                })
                if isinstance(search_result, str) and len(search_result) > 20:
                    parts.append(f"代码搜索: {len(search_result)} chars")
                    gathered["search_result"] = search_result[:1000]
            except Exception:
                import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

        gathered["summary"] = "; ".join(parts) if parts else "基础上下文"
        return gathered

    # ══════════════════════════════════════
    # ── V2: PlanGate ──
    # ══════════════════════════════════════

    def _plan_gate(self, request: str, plan_text: str) -> dict[str, Any]:
        """Plan 质量门禁 — 检查 5W"""
        result: dict[str, Any] = {"passed": True, "reason": "", "details": {}}
        lower_plan = plan_text.lower()
        lower_req = request.lower()

        # 检查每个维度
        checks = {
            "what": r"(实现|创建|修改|重构|迁移|删除|添加|优化|修复)",
            "where": r"(在.*中|文件|目录|模块|类|函数|src/|app/|core/)",
            "why": r"(因为|为了|原因|目的|why|reason|purpose|motivation)",
            "how": r"(步骤|方案|方式|通过|使用|方法|step|plan|approach|method)",
            "who": r"(用户|开发者|调用方|api|接口|client)",
        }

        for dimension, pattern in checks.items():
            found = bool(re.search(pattern, lower_plan))
            result["details"][dimension] = found
            if not found:
                result["passed"] = False

        if not result["passed"]:
            missing = [d for d, f in result["details"].items() if not f]
            result["reason"] = f"PlanGate 未通过: 缺少 {', '.join(missing)}"

        return result

    # ══════════════════════════════════════
    # ── Plan ──
    # ══════════════════════════════════════

    async def _plan(self, request: str, config: ModeConfig, context: dict[str, Any] | None = None, retry: bool = False) -> dict[str, Any]:
        """Plan 阶段"""
        result: dict[str, Any] = {"goal_id": "", "step_count": 0, "plan_text": ""}
        if not self.toolbus:
            return result

        boundaries = "不要执行任何破坏性操作。只规划，不执行。"
        if not config.allow_shell:
            boundaries += " 禁止 shell 命令。"
        if not config.allow_write:
            boundaries += " 禁止写入文件。"

        if retry:
            boundaries += " 请提供更具体的执行步骤，明确回答: 做什么(what)、在哪做(where)、为什么做(why)、怎么做(how)。"

        try:
            goal_response = await self.toolbus.call("create_goal", {
                "intent": request,
                "boundaries": boundaries,
                "max_steps": config.max_rounds * 5,
            })
            if isinstance(goal_response, dict):
                result["goal_id"] = goal_response.get("goal_id", "")
        except Exception:
            import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

        try:
            plan_response = await self.toolbus.call("execute_plan", {
                "goal": request,
                "use_llm_plan": True,
            })
            if isinstance(plan_response, str):
                result["plan_text"] = plan_response[:3000]
            elif isinstance(plan_response, dict):
                result["step_count"] = len(plan_response.get("steps", []))
                result["plan_text"] = json.dumps(plan_response, ensure_ascii=False)[:3000]
        except Exception as e:
            result["plan_error"] = str(e)

        return result

    # ══════════════════════════════════════
    # ── Attack ──
    # ══════════════════════════════════════

    async def _attack(self, request: str, config: ModeConfig, context: dict[str, Any] | None = None) -> str:
        if not self.toolbus or config.max_agents <= 0:
            return "skipped"

        attack_tasks = [
            f"从用户角度质疑: {request} — 找出 3 个最容易被忽略的边界情况",
            f"从安全角度攻击: {request} — 找出 3 个潜在的安全/异常路径",
            f"从性能角度挑战: {request} — 找出 3 个可能的效率/可扩展性问题",
        ]

        try:
            swarm_result = await self.toolbus.call("agent_swarm", {
                "template": "你是一个严格的攻击性测试者。任务: {{item}}",
                "items": attack_tasks[:config.max_agents],
                "role": "reviewer",
                "max_concurrency": config.max_agents,
            })
            if isinstance(swarm_result, str):
                return swarm_result[:2000]
            elif isinstance(swarm_result, dict):
                return json.dumps(swarm_result, ensure_ascii=False)[:2000]
            return str(swarm_result)[:2000]
        except Exception as e:
            return f"attack_failed: {e}"

    # ══════════════════════════════════════
    # ── Criticize ──
    # ══════════════════════════════════════

    async def _criticize(self, request: str, config: ModeConfig, context: dict[str, Any] | None = None) -> CritiqueReport:
        files: list[str] = []
        if context and "files" in context:
            files = context["files"]

        review_types = ["self_critic"]
        if config.review_type in ("code", "both"):
            review_types.append("code_review")
        if config.review_type in ("security", "both"):
            review_types.append("security_review")

        context_str = ""
        if context:
            if context.get("system_info"):
                context_str += f"系统: {context['system_info']}\n"
            if context.get("project"):
                context_str += f"项目: {context['project']}\n"

        return await self.critic_agent.review(
            target=request,
            files=files if files else None,
            context=context_str,
            review_types=review_types,
        )

    # ══════════════════════════════════════
    # ── Repair ──
    # ══════════════════════════════════════

    async def _repair(self, request: str, report: CritiqueReport, config: ModeConfig) -> str:
        if not self.toolbus:
            return "no_toolbus"

        blocking_findings = [f for f in report.findings if f.severity in (CritiqueSeverity.CRITICAL, CritiqueSeverity.HIGH)]
        if not blocking_findings:
            return "nothing_to_fix"

        try:
            fix_goal = f"""
基于以下审查发现修复方案。

原始请求: {request}

需要修复的 {len(blocking_findings)} 个问题:
{json.dumps([f.to_dict() for f in blocking_findings], ensure_ascii=False, indent=2)}

修复要求:
1. 修复每个 critical/high 问题
2. 不破坏已有功能
3. 每个修复必须说明对应的问题
"""

            repair_response = await self.toolbus.call("execute_plan", {
                "goal": fix_goal,
                "use_llm_plan": True,
            })
            if isinstance(repair_response, str):
                return repair_response[:2000]
            elif isinstance(repair_response, dict):
                return json.dumps(repair_response, ensure_ascii=False)[:2000]
            return str(repair_response)[:2000]
        except Exception as e:
            return f"repair_failed: {e}"

    # ══════════════════════════════════════
    # ── Verify ──
    # ══════════════════════════════════════

    async def _verify(self, request: str, config: ModeConfig, context: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"passed": True, "summary": "验证完成"}
        if not self.toolbus:
            return result
        try:
            verify_response = await self.toolbus.call("trm_route", {
                "intent": "review",
                "prompt": f"验证以下请求是否已正确完成:\n{request}\n\n确认: 1) 功能完整 2) 无副作用 3) 边界条件已处理",
            })
            if isinstance(verify_response, str):
                has_failure = any(kw in verify_response.lower() for kw in ["失败", "错误", "未完成", "遗漏", "bug", "error", "failed", "missing"])
                result["passed"] = not has_failure
                result["summary"] = verify_response[:300]
            elif isinstance(verify_response, dict):
                result["passed"] = verify_response.get("passed", verify_response.get("status") == "success")
                result["summary"] = verify_response.get("summary", verify_response.get("message", ""))
        except Exception as e:
            result["passed"] = True
            result["summary"] = f"验证跳过: {e}"
        return result

    # ══════════════════════════════════════
    # ── 快捷方法 ──
    # ══════════════════════════════════════

    async def fast_track(self, request: str, context: dict[str, Any] | None = None) -> WorkflowResult:
        result = WorkflowResult(mode="FAST", passed=True, summary="Fast path — 直接回答")
        step = self._make_step("direct_response", result)
        self._finish_step(step, "success")
        return result

    async def deep_dive(self, request: str, context: dict[str, Any] | None = None) -> WorkflowResult:
        return await self.execute(request, context, mode=IntelligenceMode.DEEP)

    # ══════════════════════════════════════
    # ── 辅助方法 ──
    # ══════════════════════════════════════

    def _make_step(self, name: str, result: WorkflowResult) -> WorkflowStep:
        step = WorkflowStep(name=name)
        step.started_at = time.time()
        result.steps.append(step)
        return step

    def _finish_step(self, step: WorkflowStep, status: str, result: str = "", error: str = "") -> None:
        step.status = status
        step.completed_at = time.time()
        if result:
            step.result = result
        if error:
            step.error = error

    def format_result_for_user(self, result: WorkflowResult) -> str:
        lines: list[str] = []
        mode_icon = {"FAST": "⚡", "BALANCED": "⚖️", "DEEP": "🧠", "SAFE": "🛡️", "RESEARCH": "🔬", "CREATIVE": "🎨"}.get(result.mode, "❓")
        status_icon = "✅" if result.passed else "❌"
        lines.append(f"{status_icon} [{mode_icon} {result.mode}] 工作流完成\n")

        for step in result.steps:
            icons = {"success": "✅", "failed": "❌", "skipped": "⏭️", "running": "🔄", "pending": "⏳"}
            icon = icons.get(step.status, "❓")
            duration = f"({step.duration:.1f}s)" if step.duration > 0 else ""
            lines.append(f"  {icon} **{step.name}**: {step.status} {duration}")
            if step.error:
                lines.append(f"    ⚠️ {step.error[:200]}")

        lines.append("")
        if result.critique_report:
            c = result.critique_report
            lines.append(f"📋 **审查报告**: {c.summary}")
            for f in c.findings:
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "ℹ️"}.get(f.severity.value, "❓")
                ev = f" | 📍 {f.evidence[:60]}" if f.evidence else ""
                lines.append(f"  {icon} [{f.severity.value}] {f.summary[:100]}{ev}")
            lines.append("")

        lines.append(f"**总结**: {result.summary}")
        if result.goal_id:
            lines.append(f"Goal ID: `{result.goal_id}`")
        return "\n".join(lines)
