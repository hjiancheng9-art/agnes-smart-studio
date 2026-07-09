下面直接按 CRUX 可落地代码架构 给方案。核心改法是：

不要把 DEEP 模式做成“一个超长 prompt”。
要把它做成一个可执行的 orchestration runtime：

create_goal
→ plan_only execute_plan
→ multi_agent / agent_swarm 做攻击性探测
→ think_deep + DeepSeek self-critic + code_review 做混合审查
→ execute_plan 修复
→ goal_evaluate 裁决
问题 1：DEEP 四轮怎么映射到已有 CRUX 工具

你的映射方向基本对，但要改一个关键点：

Plan 阶段不要直接让 execute_plan 执行。Plan 阶段只能 plan-only / dry-run。

否则 DEEP 模式第一轮就可能开始写文件、跑命令、改状态，后面 Attack / Criticize 就失去意义。

推荐最终映射
Round 0：Policy
- IntelligencePolicyRouter
- trm_route

Round 1：Plan
- create_goal
- trm_route(intent="think")
- execute_plan(plan_only=True / dry_run=True)

Round 2：Attack
- multi_agent
- agent_swarm
- web_search / web_fetch，仅在需要实时事实时启用
- trm_route(intent="search" / "review" / "think")

Round 3：Criticize
- think_deep
- DeepSeek self-critic
- code_review
- security_review
- goal_evaluate(precheck)

Round 4：Repair
- execute_plan
- goal_evaluate
- execute_plan(repair=True)
- goal_evaluate(final)
更精确的工具分工
Plan 阶段

使用：

create_goal + trm_route(intent="think") + execute_plan(plan_only=True)

目的：

把用户模糊请求变成：
- finish_line
- constraints
- success_criteria
- plan_steps
- allowed_tools
- forbidden_actions

Plan 阶段输出不要是自然语言散文，而是结构化对象。

JSON
{
  "goal_id": "g_20260709_xxx",
  "finish_line": [
    "完成代码修改",
    "通过现有测试",
    "新增回归测试",
    "解释风险和回滚"
  ],
  "constraints": [
    "不得删除用户文件",
    "不得重构无关模块",
    "所有写文件操作必须有 diff"
  ],
  "plan": [
    {
      "id": "inspect",
      "intent": "search",
      "tool": "trm_route",
      "depends_on": []
    },
    {
      "id": "patch",
      "intent": "execute",
      "tool": "execute_plan",
      "depends_on": ["inspect"]
    },
    {
      "id": "verify",
      "intent": "review",
      "tool": "goal_evaluate",
      "depends_on": ["patch"]
    }
  ]
}
Attack 阶段

Attack 不是执行子任务，而是 攻击计划、攻击假设、攻击边界条件。

使用：

multi_agent
agent_swarm
trm_route(intent="think")
trm_route(intent="search")
web_search / web_fetch

每个攻击 Agent 不要泛泛评价，固定角色：

1. AssumptionBreaker
   找隐含假设

2. EdgeCaseHunter
   找边界条件

3. RegressionHunter
   找可能破坏的旧功能

4. ToolRiskAnalyst
   找工具调用风险

5. EvidenceChecker
   判断哪些信息需要联网确认

6. TestDesigner
   反推必须新增哪些测试

Attack 阶段输出：

JSON
{
  "attacks": [
    {
      "agent": "RegressionHunter",
      "finding": "方案只修改 mouse_handler，但 keyboard binding 可能仍被 input buffer 抢焦点",
      "severity": "high",
      "evidence": "现象包含鼠标和键盘同时失效",
      "required_fix": "检查 focus / key binding 作用域"
    }
  ],
  "must_fix_before_execution": [],
  "must_test": []
}
Criticize 阶段

Criticize 是对 计划、补丁、证据、测试结果 做审查。

使用：

think_deep
DeepSeek self-critic
code_review
security_review
goal_evaluate(precheck)

这里不要只用 think_deep。正确设计是 混合评审：

think_deep：独立弱模型反方，负责多样性和盲点
DeepSeek self-critic：强模型自审，负责语义和架构质量
code_review：代码质量、bug、测试缺口
security_review：危险操作、安全风险
goal_evaluate：是否满足 finish_line

最终 Criticize 输出一个统一的 CritiqueReport。

Repair 阶段

使用：

execute_plan(repair=True)
goal_evaluate

Repair 阶段必须吃进去：

- 原始 goal
- 原始 plan
- attack findings
- critique report
- failed finish_line
- failed tests

修复不是“重新回答”，而是：

只修 failed criteria
只修 high severity issue
只改最小必要范围
最终 DEEP 工作流伪代码
Python
运行
async def run_deep_mode(user_request: str) -> dict:
    policy = await intelligence_policy_router.route(user_request)

    goal = await create_goal({
        "request": user_request,
        "mode": policy.mode,
        "require_finish_line": True,
        "require_constraints": True,
        "require_success_criteria": True,
    })

    plan = await execute_plan({
        "goal": goal,
        "mode": "plan_only",
        "dry_run": True,
        "allow_write": False,
        "allow_shell": False,
    })

    attack_report = await multi_agent({
        "goal": goal,
        "plan": plan,
        "agents": [
            "AssumptionBreaker",
            "EdgeCaseHunter",
            "RegressionHunter",
            "ToolRiskAnalyst",
            "TestDesigner",
        ],
        "output_schema": "AttackReport",
    })

    critique_report = await critic_agent.review({
        "goal": goal,
        "plan": plan,
        "attack_report": attack_report,
    })

    revised_plan = await execute_plan({
        "goal": goal,
        "previous_plan": plan,
        "critique": critique_report,
        "mode": "revise_plan_only",
        "dry_run": True,
        "allow_write": False,
    })

    result = await execute_plan({
        "goal": goal,
        "plan": revised_plan,
        "mode": "execute",
        "allow_write": policy.allow_write,
        "allow_shell": policy.allow_shell,
        "max_retries": policy.max_repair_rounds,
    })

    evaluation = await goal_evaluate({
        "goal": goal,
        "result": result,
        "finish_line": goal["finish_line"],
    })

    repair_round = 0
    while evaluation["status"] == "needs_fix" and repair_round < policy.max_repair_rounds:
        repair_round += 1

        repair_plan = await execute_plan({
            "goal": goal,
            "result": result,
            "evaluation": evaluation,
            "mode": "repair_plan_only",
            "dry_run": True,
        })

        result = await execute_plan({
            "goal": goal,
            "plan": repair_plan,
            "mode": "repair_execute",
            "allow_write": policy.allow_write,
            "allow_shell": policy.allow_shell,
        })

        evaluation = await goal_evaluate({
            "goal": goal,
            "result": result,
            "finish_line": goal["finish_line"],
        })

    return {
        "goal": goal,
        "policy": policy.to_dict(),
        "plan": revised_plan,
        "attack_report": attack_report,
        "critique_report": critique_report,
        "result": result,
        "evaluation": evaluation,
    }
问题 2：IntelligencePolicyRouter Python 类骨架

建议新增：

core/intelligence_policy.py
core/deliberate_workflow.py
core/critic_agent.py

下面给你可直接改造成项目代码的骨架。

core/intelligence_policy.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Awaitable, Literal


class IntelligenceMode(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"
    SAFE = "SAFE"
    RESEARCH = "RESEARCH"
    CREATIVE = "CREATIVE"


@dataclass
class RiskProfile:
    complexity: int = 1
    ambiguity: int = 1
    code_risk: int = 1
    tool_risk: int = 1
    factual_volatility: int = 1
    security_risk: int = 1
    creative_load: int = 1
    destructive_risk: int = 1

    @property
    def total(self) -> int:
        return (
            self.complexity
            + self.ambiguity
            + self.code_risk
            + self.tool_risk
            + self.factual_volatility
            + self.security_risk
            + self.creative_load
            + self.destructive_risk
        )


@dataclass
class ToolChainPolicy:
    use_create_goal: bool = False
    use_execute_plan: bool = False
    use_multi_agent: bool = False
    use_agent_swarm: bool = False
    use_think_deep: bool = False
    use_goal_evaluate: bool = False
    use_code_review: bool = False
    use_security_review: bool = False
    use_web_search: bool = False
    use_cdp_browser: bool = False


@dataclass
class IntelligencePolicy:
    mode: IntelligenceMode
    risk: RiskProfile
    toolchain: ToolChainPolicy

    max_rounds: int = 1
    max_repair_rounds: int = 0
    max_plan_candidates: int = 1
    max_agents: int = 0

    allow_write: bool = False
    allow_shell: bool = False
    allow_network: bool = False
    require_goal_contract: bool = False
    require_attack_round: bool = False
    require_critic_round: bool = False
    require_evidence_pack: bool = False
    require_tests: bool = False
    require_user_approval_for_destructive_ops: bool = True

    context_budget_tokens: int = 16_000
    skill_budget_tokens: int = 2_000

    trm_intents: list[str] = field(default_factory=list)
    selected_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        return data


class IntelligencePolicyRouter:
    """
    上层智能策略路由器。

    职责：
    1. 输入用户请求
    2. 估计任务风险
    3. 调用 trm_route 获取底层工具意图
    4. 输出 IntelligencePolicy
    """

    def __init__(
        self,
        trm_route: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> None:
        self.trm_route = trm_route

    async def route(self, user_request: str, context: dict[str, Any] | None = None) -> IntelligencePolicy:
        context = context or {}

        risk = self._score_risk(user_request, context)
        trm_result = await self._route_with_trm(user_request, risk, context)
        mode = self._select_mode(user_request, risk, trm_result)
        policy = self._build_policy(mode, risk, trm_result, user_request)

        return policy

    async def _route_with_trm(
        self,
        user_request: str,
        risk: RiskProfile,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        使用已有 trm_route 做底层 intent 推荐。
        这里不让 trm_route 决定 FAST/DEEP/SAFE，只让它提供工具意图。
        """
        payload = {
            "request": user_request,
            "risk_profile": asdict(risk),
            "available_intents": [
                "search",
                "review",
                "execute",
                "think",
                "generate",
                "status",
            ],
            "context": context,
        }

        return await self.trm_route(payload)

    def _score_risk(self, text: str, context: dict[str, Any]) -> RiskProfile:
        lower = text.lower()
        length = len(text)

        risk = RiskProfile()

        # 复杂度
        if length > 800:
            risk.complexity += 1
        if length > 2000:
            risk.complexity += 1
        if any(k in lower for k in [
            "架构", "architecture", "多文件", "重构", "refactor",
            "debug", "排查", "根因", "pipeline", "workflow",
            "agent", "router", "compiler",
        ]):
            risk.complexity += 2

        # 歧义
        if any(k in lower for k in [
            "不行", "炸了", "偶尔", "间歇", "有时候",
            "可能", "不知道", "帮我看看", "怎么回事",
        ]):
            risk.ambiguity += 2

        # 代码风险
        if any(k in lower for k in [
            "代码", "python", "typescript", "javascript",
            "class", "function", "bug", "traceback",
            "单元测试", "测试", "pytest", "修复",
        ]):
            risk.code_risk += 2

        # 工具风险
        if any(k in lower for k in [
            "执行", "运行", "shell", "cmd", "powershell",
            "写文件", "删除", "修改", "patch", "apply",
            "浏览器", "cdp", "playwright",
        ]):
            risk.tool_risk += 2

        # 实时事实风险
        if any(k in lower for k in [
            "最新", "现在", "当前", "today", "latest",
            "官方文档", "api", "版本", "价格", "新闻",
            "搜索", "联网", "web",
        ]):
            risk.factual_volatility += 3

        # 安全风险
        if any(k in lower for k in [
            "token", "key", "secret", "密码", "权限",
            "注入", "越权", "security", "漏洞",
        ]):
            risk.security_risk += 3

        # 破坏性风险
        if any(k in lower for k in [
            "删除", "覆盖", "重置", "清空", "rm -rf",
            "格式化", "迁移数据库", "drop table",
        ]):
            risk.destructive_risk += 4

        # 创意负载
        if any(k in lower for k in [
            "图片", "视频", "prompt", "分镜", "镜头",
            "风格", "文案", "剧本", "视觉", "生成图",
        ]):
            risk.creative_load += 3

        return self._clamp_risk(risk)

    def _clamp_risk(self, risk: RiskProfile) -> RiskProfile:
        for field_name in risk.__dataclass_fields__:
            value = getattr(risk, field_name)
            setattr(risk, field_name, max(1, min(5, value)))
        return risk

    def _select_mode(
        self,
        user_request: str,
        risk: RiskProfile,
        trm_result: dict[str, Any],
    ) -> IntelligenceMode:
        lower = user_request.lower()
        intents = set(trm_result.get("intents", []))

        if risk.destructive_risk >= 4 or risk.security_risk >= 4:
            return IntelligenceMode.SAFE

        if risk.factual_volatility >= 4 or "search" in intents:
            return IntelligenceMode.RESEARCH

        if risk.creative_load >= 4 and risk.code_risk <= 2:
            return IntelligenceMode.CREATIVE

        if (
            risk.complexity >= 4
            or risk.code_risk >= 4
            or risk.tool_risk >= 4
            or risk.total >= 20
            or "execute" in intents
        ):
            return IntelligenceMode.DEEP

        if risk.total >= 12:
            return IntelligenceMode.BALANCED

        return IntelligenceMode.FAST

    def _build_policy(
        self,
        mode: IntelligenceMode,
        risk: RiskProfile,
        trm_result: dict[str, Any],
        user_request: str,
    ) -> IntelligencePolicy:
        intents = trm_result.get("intents", [])
        selected_skills = trm_result.get("skills", [])

        if mode == IntelligenceMode.FAST:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(),
                max_rounds=1,
                max_repair_rounds=0,
                trm_intents=intents,
                selected_skills=selected_skills[:1],
                context_budget_tokens=12_000,
                skill_budget_tokens=1_000,
            )

        if mode == IntelligenceMode.BALANCED:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(
                    use_create_goal=True,
                    use_goal_evaluate=True,
                ),
                max_rounds=2,
                max_repair_rounds=1,
                require_goal_contract=True,
                require_tests=risk.code_risk >= 3,
                trm_intents=intents,
                selected_skills=selected_skills[:3],
                context_budget_tokens=32_000,
                skill_budget_tokens=3_000,
            )

        if mode == IntelligenceMode.DEEP:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(
                    use_create_goal=True,
                    use_execute_plan=True,
                    use_multi_agent=True,
                    use_think_deep=True,
                    use_goal_evaluate=True,
                    use_code_review=risk.code_risk >= 2,
                ),
                max_rounds=4,
                max_repair_rounds=3,
                max_plan_candidates=3,
                max_agents=5,
                allow_write=True,
                allow_shell=True,
                require_goal_contract=True,
                require_attack_round=True,
                require_critic_round=True,
                require_tests=risk.code_risk >= 2,
                trm_intents=intents,
                selected_skills=selected_skills[:5],
                context_budget_tokens=96_000,
                skill_budget_tokens=8_000,
            )

        if mode == IntelligenceMode.SAFE:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(
                    use_create_goal=True,
                    use_execute_plan=True,
                    use_multi_agent=True,
                    use_think_deep=True,
                    use_goal_evaluate=True,
                    use_code_review=risk.code_risk >= 2,
                    use_security_review=True,
                ),
                max_rounds=5,
                max_repair_rounds=2,
                max_plan_candidates=3,
                max_agents=6,
                allow_write=True,
                allow_shell=False,
                require_goal_contract=True,
                require_attack_round=True,
                require_critic_round=True,
                require_tests=True,
                require_user_approval_for_destructive_ops=True,
                trm_intents=intents,
                selected_skills=selected_skills[:6],
                context_budget_tokens=128_000,
                skill_budget_tokens=10_000,
            )

        if mode == IntelligenceMode.RESEARCH:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(
                    use_create_goal=True,
                    use_execute_plan=True,
                    use_multi_agent=True,
                    use_think_deep=True,
                    use_goal_evaluate=True,
                    use_web_search=True,
                    use_cdp_browser=True,
                ),
                max_rounds=4,
                max_repair_rounds=2,
                max_plan_candidates=2,
                max_agents=4,
                allow_network=True,
                require_goal_contract=True,
                require_attack_round=True,
                require_critic_round=True,
                require_evidence_pack=True,
                trm_intents=list(set(intents + ["search", "think", "review"])),
                selected_skills=selected_skills[:5],
                context_budget_tokens=96_000,
                skill_budget_tokens=8_000,
            )

        if mode == IntelligenceMode.CREATIVE:
            return IntelligencePolicy(
                mode=mode,
                risk=risk,
                toolchain=ToolChainPolicy(
                    use_create_goal=True,
                    use_multi_agent=True,
                    use_think_deep=True,
                    use_goal_evaluate=True,
                ),
                max_rounds=3,
                max_repair_rounds=2,
                max_plan_candidates=3,
                max_agents=4,
                require_goal_contract=True,
                require_attack_round=True,
                require_critic_round=True,
                trm_intents=list(set(intents + ["generate", "review"])),
                selected_skills=selected_skills[:5],
                context_budget_tokens=64_000,
                skill_budget_tokens=8_000,
            )

        raise ValueError(f"Unhandled intelligence mode: {mode}")
core/deliberate_workflow.py

这个模块把四轮真正串起来。

Python
运行
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.intelligence_policy import IntelligencePolicy, IntelligenceMode
from core.critic_agent import CriticAgent


@dataclass
class WorkflowResult:
    status: str
    goal: dict[str, Any]
    policy: dict[str, Any]
    plan: dict[str, Any] | None
    attack_report: dict[str, Any] | None
    critique_report: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    evaluation: dict[str, Any] | None


class DeliberateWorkflow:
    def __init__(
        self,
        toolbus: Any,
        policy_router: Any,
        critic_agent: CriticAgent,
    ) -> None:
        self.toolbus = toolbus
        self.policy_router = policy_router
        self.critic_agent = critic_agent

    async def run(self, user_request: str, context: dict[str, Any] | None = None) -> WorkflowResult:
        context = context or {}
        policy: IntelligencePolicy = await self.policy_router.route(user_request, context)

        if policy.mode == IntelligenceMode.FAST:
            return await self._run_fast(user_request, policy, context)

        if policy.mode == IntelligenceMode.BALANCED:
            return await self._run_balanced(user_request, policy, context)

        return await self._run_deliberate(user_request, policy, context)

    async def _run_fast(
        self,
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> WorkflowResult:
        result = await self.toolbus.call("trm_route", {
            "intent": "generate",
            "request": user_request,
            "context": context,
            "policy": policy.to_dict(),
        })

        return WorkflowResult(
            status="done",
            goal={},
            policy=policy.to_dict(),
            plan=None,
            attack_report=None,
            critique_report=None,
            execution_result=result,
            evaluation=None,
        )

    async def _run_balanced(
        self,
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> WorkflowResult:
        goal = await self._create_goal(user_request, policy, context)

        result = await self.toolbus.call("trm_route", {
            "intent": "think",
            "request": user_request,
            "goal": goal,
            "context": context,
            "policy": policy.to_dict(),
        })

        evaluation = await self._evaluate(goal, result)

        if evaluation.get("status") == "needs_fix" and policy.max_repair_rounds > 0:
            result = await self.toolbus.call("trm_route", {
                "intent": "generate",
                "request": user_request,
                "goal": goal,
                "previous_result": result,
                "evaluation": evaluation,
                "instruction": "Fix only the failed criteria.",
            })
            evaluation = await self._evaluate(goal, result)

        return WorkflowResult(
            status=evaluation.get("status", "done"),
            goal=goal,
            policy=policy.to_dict(),
            plan=None,
            attack_report=None,
            critique_report=None,
            execution_result=result,
            evaluation=evaluation,
        )

    async def _run_deliberate(
        self,
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> WorkflowResult:
        # Round 1: Plan
        goal = await self._create_goal(user_request, policy, context)
        plan = await self._plan_only(goal, user_request, policy, context)

        # Optional research evidence
        evidence_pack = None
        if policy.require_evidence_pack:
            evidence_pack = await self._build_evidence_pack(goal, user_request, policy, context)

        # Round 2: Attack
        attack_report = await self._attack(goal, plan, user_request, policy, context, evidence_pack)

        # Round 3: Criticize
        critique_report = await self.critic_agent.review(
            goal=goal,
            plan=plan,
            attack_report=attack_report,
            evidence_pack=evidence_pack,
            context=context,
            policy=policy.to_dict(),
        )

        # Revise plan before execution
        revised_plan = await self._revise_plan(
            goal=goal,
            plan=plan,
            attack_report=attack_report,
            critique_report=critique_report,
            policy=policy,
            context=context,
        )

        # Round 4: Execute / Repair
        execution_result = await self._execute(revised_plan, goal, policy, context)
        evaluation = await self._evaluate(goal, execution_result)

        repair_round = 0
        while evaluation.get("status") == "needs_fix" and repair_round < policy.max_repair_rounds:
            repair_round += 1

            repair_plan = await self._repair_plan(
                goal=goal,
                plan=revised_plan,
                execution_result=execution_result,
                evaluation=evaluation,
                critique_report=critique_report,
                policy=policy,
                context=context,
            )

            execution_result = await self._execute(repair_plan, goal, policy, context)
            evaluation = await self._evaluate(goal, execution_result)

        return WorkflowResult(
            status=evaluation.get("status", "unknown"),
            goal=goal,
            policy=policy.to_dict(),
            plan=revised_plan,
            attack_report=attack_report,
            critique_report=critique_report,
            execution_result=execution_result,
            evaluation=evaluation,
        )

    async def _create_goal(
        self,
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("create_goal", {
            "request": user_request,
            "context": context,
            "mode": policy.mode.value,
            "require_finish_line": True,
            "require_constraints": True,
            "require_success_criteria": True,
            "require_forbidden_actions": True,
        })

    async def _plan_only(
        self,
        goal: dict[str, Any],
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "plan_only",
            "dry_run": True,
            "allow_write": False,
            "allow_shell": False,
            "goal": goal,
            "request": user_request,
            "context": context,
            "policy": policy.to_dict(),
            "max_plan_candidates": policy.max_plan_candidates,
        })

    async def _build_evidence_pack(
        self,
        goal: dict[str, Any],
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        search_result = await self.toolbus.call("web_search", {
            "query": user_request,
            "goal": goal,
            "max_results": 5,
        })

        # 让 trm_route 或专用 summarizer 把搜索结果压成 evidence pack
        evidence_pack = await self.toolbus.call("trm_route", {
            "intent": "review",
            "task": "Build an evidence pack from web search results.",
            "goal": goal,
            "search_result": search_result,
            "output_schema": "EvidencePack",
        })

        return evidence_pack

    async def _attack(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        user_request: str,
        policy: IntelligencePolicy,
        context: dict[str, Any],
        evidence_pack: dict[str, Any] | None,
    ) -> dict[str, Any]:
        agents = [
            {
                "name": "AssumptionBreaker",
                "mission": "Find hidden assumptions and unsupported claims in the plan.",
            },
            {
                "name": "EdgeCaseHunter",
                "mission": "Find edge cases likely to break the plan.",
            },
            {
                "name": "RegressionHunter",
                "mission": "Find existing behavior that the plan may accidentally break.",
            },
            {
                "name": "ToolRiskAnalyst",
                "mission": "Find unsafe, unnecessary, or wrong tool usage.",
            },
            {
                "name": "TestDesigner",
                "mission": "Derive concrete tests required to validate the plan.",
            },
        ][: policy.max_agents]

        return await self.toolbus.call("multi_agent", {
            "mode": "parallel_attack",
            "goal": goal,
            "plan": plan,
            "request": user_request,
            "context": context,
            "evidence_pack": evidence_pack,
            "agents": agents,
            "output_schema": "AttackReport",
        })

    async def _revise_plan(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        attack_report: dict[str, Any],
        critique_report: dict[str, Any],
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "revise_plan_only",
            "dry_run": True,
            "allow_write": False,
            "allow_shell": False,
            "goal": goal,
            "previous_plan": plan,
            "attack_report": attack_report,
            "critique_report": critique_report,
            "policy": policy.to_dict(),
            "context": context,
            "instruction": (
                "Revise the plan to fix high-severity critique items. "
                "Do not add unrelated scope."
            ),
        })

    async def _execute(
        self,
        plan: dict[str, Any],
        goal: dict[str, Any],
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "execute",
            "goal": goal,
            "plan": plan,
            "context": context,
            "allow_write": policy.allow_write,
            "allow_shell": policy.allow_shell,
            "allow_network": policy.allow_network,
            "require_tests": policy.require_tests,
            "max_retries": 1,
        })

    async def _repair_plan(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        execution_result: dict[str, Any],
        evaluation: dict[str, Any],
        critique_report: dict[str, Any],
        policy: IntelligencePolicy,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("execute_plan", {
            "mode": "repair_plan_only",
            "dry_run": True,
            "allow_write": False,
            "allow_shell": False,
            "goal": goal,
            "previous_plan": plan,
            "execution_result": execution_result,
            "evaluation": evaluation,
            "critique_report": critique_report,
            "context": context,
            "instruction": (
                "Generate a minimal repair plan. "
                "Only address failed finish_line items and high-severity issues."
            ),
        })

    async def _evaluate(
        self,
        goal: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("goal_evaluate", {
            "goal": goal,
            "result": result,
            "finish_line": goal.get("finish_line", []),
            "success_criteria": goal.get("success_criteria", []),
        })
问题 3：CriticAgent 具体实现

你的思路对，但要改成 三审合一，不要押宝 think_deep。

设计决策

这样做：

think_deep 不负责“比 DeepSeek 更聪明”。
think_deep 负责“独立视角、低成本反对票、发现明显矛盾”。

DeepSeek self-critic 负责“强语义审查”。
code_review / security_review 负责“工具化审查”。
CriticAgent 负责聚合裁决。

最终结构：

CriticAgent
   ├── ThinkDeepCritic
   ├── SelfCritic / DeepSeekCritic
   ├── CodeReviewCritic
   ├── SecurityReviewCritic
   └── CritiqueAggregator
为什么 think_deep 仍然有价值

本地 llama.cpp 模型即使不如 DeepSeek，也有三个价值：

1. 独立采样路径
   它犯错方式和 DeepSeek 不同，能打破同模型自嗨。

2. 反方任务更简单
   “找 3 个漏洞”比“完整解决任务”难度低很多。

3. 低成本多轮
   可以让它反复跑 checklist，不消耗主 API。

但不要让它做开放式评价。要给它极窄的审查任务。

错误用法：

请评价这个方案好不好。

正确用法：

只找以下 6 类问题：
1. 目标不一致
2. 隐含假设
3. 缺少验证
4. 工具调用风险
5. 修改范围过大
6. 可能破坏旧功能

每类最多 2 条。
每条必须包含 evidence / severity / required_fix。
core/critic_agent.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CritiqueFinding:
    source: str
    category: str
    severity: Severity
    finding: str
    evidence: str
    required_fix: str
    blocks_execution: bool = False


@dataclass
class CritiqueReport:
    status: str
    findings: list[CritiqueFinding]
    blocking_findings: list[CritiqueFinding]
    repair_instructions: list[str]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [
                {
                    **asdict(f),
                    "severity": f.severity.value,
                }
                for f in self.findings
            ],
            "blocking_findings": [
                {
                    **asdict(f),
                    "severity": f.severity.value,
                }
                for f in self.blocking_findings
            ],
            "repair_instructions": self.repair_instructions,
            "confidence": self.confidence,
        }


class CriticAgent:
    def __init__(self, toolbus: Any) -> None:
        self.toolbus = toolbus

    async def review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        attack_report: dict[str, Any] | None = None,
        evidence_pack: dict[str, Any] | None = None,
        patch: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        policy = policy or {}

        review_jobs = []

        review_jobs.append(self._think_deep_review(
            goal=goal,
            plan=plan,
            attack_report=attack_report,
            evidence_pack=evidence_pack,
            patch=patch,
            context=context,
        ))

        review_jobs.append(self._self_critic_review(
            goal=goal,
            plan=plan,
            attack_report=attack_report,
            evidence_pack=evidence_pack,
            patch=patch,
            context=context,
        ))

        if self._looks_like_code_task(goal, plan, patch, context):
            review_jobs.append(self._code_review(
                goal=goal,
                plan=plan,
                patch=patch,
                context=context,
            ))

        if self._needs_security_review(goal, plan, patch, context, policy):
            review_jobs.append(self._security_review(
                goal=goal,
                plan=plan,
                patch=patch,
                context=context,
            ))

        raw_reports = []
        for job in review_jobs:
            try:
                raw_reports.append(await job)
            except Exception as exc:
                raw_reports.append({
                    "source": "critic_runtime",
                    "status": "error",
                    "error": repr(exc),
                    "findings": [{
                        "category": "critic_failure",
                        "severity": "medium",
                        "finding": "A critic backend failed.",
                        "evidence": repr(exc),
                        "required_fix": "Do not rely solely on the failed critic. Continue with remaining critics.",
                        "blocks_execution": False,
                    }]
                })

        report = self._aggregate(raw_reports)
        return report.to_dict()

    async def _think_deep_review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        attack_report: dict[str, Any] | None,
        evidence_pack: dict[str, Any] | None,
        patch: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = self._build_think_deep_prompt(
            goal=goal,
            plan=plan,
            attack_report=attack_report,
            evidence_pack=evidence_pack,
            patch=patch,
        )

        return await self.toolbus.call("think_deep", {
            "prompt": prompt,
            "temperature": 0.2,
            "max_tokens": 1800,
            "output_schema": "CritiqueFindings",
        })

    async def _self_critic_review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        attack_report: dict[str, Any] | None,
        evidence_pack: dict[str, Any] | None,
        patch: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("trm_route", {
            "intent": "review",
            "review_type": "self_critic",
            "goal": goal,
            "plan": plan,
            "attack_report": attack_report,
            "evidence_pack": evidence_pack,
            "patch": patch,
            "context": context,
            "instruction": self._self_critic_instruction(),
            "output_schema": "CritiqueFindings",
        })

    async def _code_review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        patch: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("code_review", {
            "goal": goal,
            "plan": plan,
            "patch": patch,
            "context": context,
            "focus": [
                "correctness",
                "regression risk",
                "missing tests",
                "unrelated changes",
                "error handling",
                "API misuse",
            ],
            "output_schema": "CritiqueFindings",
        })

    async def _security_review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        patch: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.toolbus.call("security_review", {
            "goal": goal,
            "plan": plan,
            "patch": patch,
            "context": context,
            "focus": [
                "secret leakage",
                "destructive operations",
                "shell injection",
                "path traversal",
                "unsafe file writes",
                "network exfiltration",
            ],
            "output_schema": "CritiqueFindings",
        })

    def _build_think_deep_prompt(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        attack_report: dict[str, Any] | None,
        evidence_pack: dict[str, Any] | None,
        patch: dict[str, Any] | None,
    ) -> str:
        return f"""
你是 CRUX Studio 的独立反方审查器。

你的任务不是解决问题，不是重写方案。
你的任务是找出方案中最可能导致失败的漏洞。

只检查以下 6 类问题：
1. goal_mismatch：方案是否偏离用户目标或 finish_line
2. hidden_assumption：是否存在未证明的隐含假设
3. missing_verification：是否缺少测试、证据或验收方式
4. tool_risk：是否存在错误、危险或不必要的工具调用
5. over_scope：是否修改范围过大或引入无关重构
6. regression_risk：是否可能破坏已有功能

输出 JSON，格式必须是：
{{
  "source": "think_deep",
  "status": "pass | needs_fix | block",
  "findings": [
    {{
      "category": "goal_mismatch | hidden_assumption | missing_verification | tool_risk | over_scope | regression_risk",
      "severity": "low | medium | high | critical",
      "finding": "具体问题",
      "evidence": "来自 goal/plan/attack_report/evidence_pack/patch 的证据",
      "required_fix": "必须怎样修",
      "blocks_execution": true/false
    }}
  ]
}}

规则：
- 最多输出 8 条 findings。
- 不要空泛建议。
- 每条 finding 必须有 evidence。
- 如果没有发现严重问题，输出 status="pass" 和空 findings。
- 不要输出 Markdown。
- 不要输出解释性散文。

[GOAL]
{goal}

[PLAN]
{plan}

[ATTACK_REPORT]
{attack_report}

[EVIDENCE_PACK]
{evidence_pack}

[PATCH]
{patch}
""".strip()

    def _self_critic_instruction(self) -> str:
        return """
你是主模型自审查器。你的任务是从强语义和工程正确性角度审查方案。

重点检查：
1. 方案是否真的满足 finish_line
2. 是否遗漏用户的硬约束
3. 是否需要联网证据但没有证据
4. 是否计划执行顺序错误
5. 是否测试不足
6. 是否存在更小修复路径
7. 是否存在明显过度工程

输出 CritiqueFindings JSON。
每条 finding 必须包含 severity、evidence、required_fix、blocks_execution。
""".strip()

    def _aggregate(self, raw_reports: list[dict[str, Any]]) -> CritiqueReport:
        findings: list[CritiqueFinding] = []

        for report in raw_reports:
            source = report.get("source", "unknown")
            for item in report.get("findings", []) or []:
                severity = self._parse_severity(item.get("severity", "medium"))

                finding = CritiqueFinding(
                    source=source,
                    category=item.get("category", "unknown"),
                    severity=severity,
                    finding=item.get("finding", ""),
                    evidence=item.get("evidence", ""),
                    required_fix=item.get("required_fix", ""),
                    blocks_execution=bool(item.get("blocks_execution", False)),
                )

                if finding.finding:
                    findings.append(finding)

        findings = self._dedupe_findings(findings)

        blocking = [
            f for f in findings
            if f.blocks_execution or f.severity in {Severity.CRITICAL}
        ]

        high = [
            f for f in findings
            if f.severity in {Severity.HIGH, Severity.CRITICAL}
        ]

        if blocking:
            status = "block"
        elif high:
            status = "needs_fix"
        else:
            status = "pass"

        repair_instructions = self._make_repair_instructions(findings)

        confidence = self._estimate_confidence(raw_reports, findings)

        return CritiqueReport(
            status=status,
            findings=findings,
            blocking_findings=blocking,
            repair_instructions=repair_instructions,
            confidence=confidence,
        )

    def _parse_severity(self, value: str) -> Severity:
        value = str(value).lower()
        if value == "critical":
            return Severity.CRITICAL
        if value == "high":
            return Severity.HIGH
        if value == "low":
            return Severity.LOW
        return Severity.MEDIUM

    def _dedupe_findings(self, findings: list[CritiqueFinding]) -> list[CritiqueFinding]:
        seen: set[tuple[str, str]] = set()
        deduped: list[CritiqueFinding] = []

        for f in findings:
            key = (
                f.category.lower().strip(),
                f.finding.lower().strip()[:120],
            )
            if key in seen:
                continue

            seen.add(key)
            deduped.append(f)

        # 高严重度优先
        severity_rank = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }

        deduped.sort(key=lambda x: severity_rank[x.severity])
        return deduped

    def _make_repair_instructions(self, findings: list[CritiqueFinding]) -> list[str]:
        instructions: list[str] = []

        for f in findings:
            if f.severity in {Severity.HIGH, Severity.CRITICAL} or f.blocks_execution:
                instructions.append(
                    f"[{f.severity.value}/{f.category}] {f.required_fix}"
                )

        # 限制数量，避免 repair prompt 被噪声污染
        return instructions[:8]

    def _estimate_confidence(
        self,
        raw_reports: list[dict[str, Any]],
        findings: list[CritiqueFinding],
    ) -> float:
        successful = [
            r for r in raw_reports
            if r.get("status") != "error"
        ]

        if not raw_reports:
            return 0.0

        backend_score = len(successful) / len(raw_reports)

        if not findings:
            return round(0.65 * backend_score, 2)

        evidence_count = sum(1 for f in findings if f.evidence)
        evidence_score = evidence_count / max(1, len(findings))

        return round((backend_score * 0.5) + (evidence_score * 0.5), 2)

    def _looks_like_code_task(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        patch: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> bool:
        blob = f"{goal} {plan} {patch} {context}".lower()
        return any(k in blob for k in [
            "code", "python", "typescript", "javascript",
            "class", "function", "pytest", "traceback",
            "diff", "patch", ".py", ".ts", ".js",
        ])

    def _needs_security_review(
        self,
        goal: dict[str, Any],
        plan: dict[str, Any],
        patch: dict[str, Any] | None,
        context: dict[str, Any],
        policy: dict[str, Any],
    ) -> bool:
        if policy.get("mode") == "SAFE":
            return True

        blob = f"{goal} {plan} {patch} {context}".lower()

        return any(k in blob for k in [
            "token", "secret", "password", "key",
            "shell", "subprocess", "powershell", "cmd",
            "delete", "remove", "rm -rf",
            "权限", "密码", "密钥", "删除",
        ])
Repair 阶段如何吃掉 Critique

你需要让 execute_plan 在 repair 模式下严格消费 repair_instructions。

Python
运行
async def repair_with_critique(toolbus, goal, plan, result, critique_report, evaluation):
    return await toolbus.call("execute_plan", {
        "mode": "repair_execute",
        "goal": goal,
        "previous_plan": plan,
        "previous_result": result,
        "evaluation": evaluation,
        "repair_instructions": critique_report["repair_instructions"],
        "blocking_findings": critique_report["blocking_findings"],
        "rules": [
            "Only fix failed finish_line items.",
            "Only fix high/critical critique findings.",
            "Do not introduce unrelated refactors.",
            "Do not repeat a rejected plan.",
            "Run tests after patch.",
        ],
    })
DeepSeek self-critic 的具体 prompt

把这个做成常量：

Python
运行
SELF_CRITIC_PROMPT = """
你是 CRUX Studio 的主模型审查器。
你正在审查另一个模型生成的计划或补丁。

你的目标不是礼貌评价，而是找出会导致任务失败的具体问题。

检查维度：
1. 是否满足用户真实目标
2. 是否满足 finish_line
3. 是否违反 constraints
4. 是否存在未经验证的事实
5. 是否存在计划顺序错误
6. 是否缺少测试
7. 是否有过度工程
8. 是否有更小、更稳的修复路径
9. 是否有安全或破坏性风险
10. 是否需要浏览器或官方文档证据

输出 JSON：
{
  "source": "deepseek_self_critic",
  "status": "pass | needs_fix | block",
  "findings": [
    {
      "category": "...",
      "severity": "low | medium | high | critical",
      "finding": "...",
      "evidence": "...",
      "required_fix": "...",
      "blocks_execution": true/false
    }
  ]
}

规则：
- 不要输出 Markdown。
- 不要重写完整方案。
- 每条 finding 必须具体。
- 没有 evidence 的 finding 不要输出。
"""
think_deep 的最佳使用方式

不要让 think_deep 做这件事：

“你觉得这个方案怎么样？”

让它做这件事：

“只找 3-8 个会导致失败的具体漏洞。”

更好的 think_deep 调用策略：

Python
运行
async def run_think_deep_attack(toolbus, goal, plan):
    return await toolbus.call("think_deep", {
        "temperature": 0.1,
        "max_tokens": 1200,
        "prompt": f"""
你是一个保守的软件审计员。
只做失败分析，不做方案生成。

请找出下面计划中最可能失败的 5 个点。
每个点必须包含：
- 问题
- 为什么会失败
- 需要什么证据验证
- 最小修复建议

[GOAL]
{goal}

[PLAN]
{plan}
"""
    })

参数建议：

temperature: 0.1 - 0.3
max_tokens: 1200 - 2000
top_p: 0.8
repeat_penalty: 1.1

不要让本地模型输出太长。长了会胡。

是否应该用 DeepSeek 自己当 Critic？

答案：要用，但不能只用。

最终决策：

默认 DEEP：
- think_deep critic：开启
- DeepSeek self-critic：开启
- code_review：代码任务开启
- security_review：SAFE 模式开启

FAST：
- 不开 critic

BALANCED：
- 只开 goal_evaluate
- 代码任务开轻量 code_review

SAFE：
- 全部开启

原因：

只用 think_deep：
- 容易漏掉复杂语义问题

只用 DeepSeek self-critic：
- 容易和原方案同源偏见，自我认可

只用 code_review：
- 无法审查目标偏移和产品层风险

混合审查：
- 成本可控
- 视角互补
- 能聚合成 blocking / needs_fix / pass
推荐的最终目录结构
core/
  intelligence_policy.py
  deliberate_workflow.py
  critic_agent.py
  critique_schema.py
  task_contract.py
  repair_loop.py

core/reviewer/
  think_deep_reviewer.py
  self_critic_reviewer.py
  code_reviewer_adapter.py
  security_reviewer_adapter.py

core/policy/
  risk_keywords.py
  mode_config.json
最小可落地版本

你先不要一次写太大。第一版只做这 4 个文件：

core/intelligence_policy.py
core/critic_agent.py
core/deliberate_workflow.py
tests/test_intelligence_policy.py

MVP 目标：

1. 用户请求进入 IntelligencePolicyRouter
2. 自动判定 FAST / BALANCED / DEEP / SAFE / RESEARCH
3. DEEP 自动走 create_goal → execute_plan(plan_only)
4. think_deep + self_critic 生成 CritiqueReport
5. execute_plan 根据 CritiqueReport 修复
6. goal_evaluate 裁决 pass / needs_fix / fail
一句话结论

你的原始映射接近正确，但要这样修正：

Plan 阶段：create_goal + execute_plan(plan_only)，不执行
Attack 阶段：multi_agent / agent_swarm 攻击假设，不改代码
Criticize 阶段：think_deep + DeepSeek self-critic + code_review/security_review 混合审查
Repair 阶段：execute_plan 只修失败项，goal_evaluate 做最终裁决

这就是 CRUX 的“穷人 o1/o3”核心骨架。