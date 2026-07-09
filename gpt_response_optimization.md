我先说明一个限制：我没有在 File Library 里检索到 core/intelligence_policy.py、core/critic_agent.py、core/deliberate_flow.py、core/intelligence_hook.py 这 4 个新文件本体，所以不能做逐行代码审查。下面是基于你描述的实现、CRUX 现有方法论和架构文档给出的代码级审查与补丁方案。CRUX 自己的文档已经明确了 A/B/C/D 任务分级、复杂任务必须 Plan、验证结果才算证据、读可以并行但写必须隔离，这正好应该成为 Intelligence Pipeline 的硬规则底座。

METHODOLOGY

 

AGENTS

A. 当前实现审查结论
A1. IntelligencePolicyRouter：关键词路由一定太粗糙

结论：关键词路由可以作为第一版，但不能作为最终路由真源。现在最危险的是误报 RESEARCH / CREATIVE / SAFE，以及漏报 DEEP。

典型误报：

“帮我生成 Python 代码” 
→ 可能被 “生成” 打到 CREATIVE
→ 实际应该是 DEEP/BALANCED code task

“搜索项目里的 xxx”
→ 可能被 “搜索” 打到 RESEARCH
→ 实际是 local repo search，不该联网

“清理一下文案”
→ 可能被 “清理/删除” 打到 SAFE
→ 实际可能只是文本改写

“不要联网，按已有代码分析”
→ 如果只看 “联网/搜索/最新” 关键词，可能仍触发 RESEARCH

典型漏报：

“这个偶尔不响应”
→ 没有明显代码词，但这是复杂 debug，应该 DEEP

“测试都过了但真实 TUI 不工作”
→ 这是强烈 DEEP 信号，因为单测与真实行为不一致

“帮我看看这个设计有没有问题”
→ 如果没触发代码关键词，可能走 BALANCED，但架构审查应该 DEEP

“这里是不是有安全问题”
→ 如果没有 token/secret/delete 等词，可能漏掉 SAFE/security_review

你现在应该把 IntelligencePolicyRouter 从“关键词命中”升级成 信号评分 + 硬规则门禁 + 置信度追踪。

A2. CriticAgent：Self-Critic 需要从“评价”改成“可执行阻塞审查”

如果现在的 self-critic prompt 只是：

请审查这个方案，指出问题。

不够。

应该改成：

只输出 blocking / needs_fix / pass。
每条 finding 必须绑定：
- finish_line
- evidence
- risk
- required_fix
- blocks_execution

Critic 不能只是“提出建议”，它必须能直接喂给 Repair 阶段。

你的 CriticAgent 输出应该统一成这个 schema：

Python
运行
class CritiqueStatus(str, Enum):
    PASS = "pass"
    NEEDS_FIX = "needs_fix"
    BLOCK = "block"


@dataclass
class CritiqueFinding:
    id: str
    source: str
    category: str
    severity: str
    evidence: str
    finding: str
    required_fix: str
    blocks_execution: bool
    related_finish_line: str | None = None
    related_plan_step: str | None = None

关键点：没有 evidence 的 finding 直接丢弃。

CRUX 文档里也强调“报告不是证据，命令输出、测试结果、构建结果才算证据”，所以 CriticAgent 也必须遵守这个原则。

AGENTS

A3. DeliberateWorkflow：五轮设计对，但少了两个门

你现在是：

Plan → Attack → Criticize → Repair → Verify

方向对，但要加两个关键环节：

ContextGather → Plan → PlanGate → Attack → Criticize → Repair → Verify → EvidenceReport

缺的第一个环节：ContextGather

Plan 前必须先收集上下文。否则 Plan 只是拍脑袋。

代码任务：repo search / read relevant files / recent errors
研究任务：web evidence pack
创意任务：style lock / existing asset context
debug 任务：error log / repro / call chain

缺的第二个环节：PlanGate

Plan 生成后不能直接进入 Attack。先验证 Plan 自身是否合格：

- 有没有 finish_line
- 有没有 constraints
- 有没有 allowed_tools / forbidden_tools
- 有没有 tests_to_run
- 有没有 rollback_plan
- 有没有 write isolation
- 是否把 local search 错当 web search
A4. Wire 层最大风险：send_stream() 集成不要破坏流式协议

CRUX 文档说明 ChatSession.send_stream() 的协议是 yield (kind, payload) 元组，再交给 StreamingRenderer.render_stream() 分发到 message pane。

AGENTS

所以 core/intelligence_hook.py 最大风险不是算法，而是 wire 层：

1. hook 内部再次调用 send_stream，造成递归
2. DEEP workflow 阻塞 UI streaming，用户看起来像卡死
3. workflow 失败后没有 fallback 到原始聊天路径
4. Plan/Attack/Criticize 的中间状态被当成最终 assistant message 渲染
5. cancellation / Ctrl+C 不能终止子任务
6. execute_plan 写文件时和 multi_agent 并行写冲突

你应该强制 hook 只做三件事：

1. policy 判断
2. 发 phase/status 事件
3. 返回最终 assistant payload

不要在 hook 里直接做渲染逻辑。

B. 下一步最应该做的 3 件事
P0：重写 core/intelligence_policy.py 为 Router V2

目标：从关键词路由升级为信号评分路由。

新增：

core/routing_signals.py
tests/test_intelligence_policy_golden.py

保留原来的 6 模式，但路由逻辑改成：

Explicit Override
→ Hard Safety Guard
→ Signal Extraction
→ Mode Scoring
→ TRM Intent Overlay
→ Confidence / Margin
→ Final Policy
直接加这个文件：core/routing_signals.py
Python
运行
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re


class RouteMode(str, Enum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    DEEP = "DEEP"
    SAFE = "SAFE"
    RESEARCH = "RESEARCH"
    CREATIVE = "CREATIVE"


@dataclass
class RouteSignal:
    name: str
    mode: RouteMode
    weight: float
    evidence: str
    hard: bool = False


@dataclass
class RouteFeatures:
    text: str
    text_wo_code: str
    has_code_block: bool = False
    has_stacktrace: bool = False
    has_file_path: bool = False
    has_url: bool = False
    has_explicit_web: bool = False
    has_explicit_no_web: bool = False
    has_local_search: bool = False
    has_write_action: bool = False
    has_destructive_action: bool = False
    has_security_term: bool = False
    has_debug_symptom: bool = False
    has_test_mismatch: bool = False
    has_architecture_term: bool = False
    has_creative_term: bool = False
    has_simple_chat: bool = False
    explicit_mode: RouteMode | None = None


class SignalExtractor:
    CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
    FILE_PATH_RE = re.compile(
        r"(\b[\w./\\-]+\.(py|ts|tsx|js|jsx|json|md|yaml|yml|toml|ini|css|html)\b)"
    )
    URL_RE = re.compile(r"https?://\S+")

    def extract(self, text: str) -> RouteFeatures:
        lower = text.lower()
        code_blocks = self.CODE_FENCE_RE.findall(text)
        text_wo_code = self.CODE_FENCE_RE.sub(" ", text)

        f = RouteFeatures(
            text=text,
            text_wo_code=text_wo_code,
            has_code_block=bool(code_blocks),
            has_file_path=bool(self.FILE_PATH_RE.search(text)),
            has_url=bool(self.URL_RE.search(text)),
        )

        f.explicit_mode = self._explicit_mode(lower)

        f.has_explicit_no_web = any(x in lower for x in [
            "不要联网", "别联网", "不用联网", "no web", "without web",
            "不要搜索网页", "只看本地", "只看项目", "local only",
        ])

        f.has_explicit_web = any(x in lower for x in [
            "联网", "搜索网页", "web_search", "web fetch", "web_fetch",
            "官方文档", "最新", "current", "latest", "browse", "查一下",
        ]) and not f.has_explicit_no_web

        f.has_local_search = any(x in lower for x in [
            "搜索项目", "搜代码", "grep", "ripgrep", "rg ",
            "查仓库", "查项目", "本地代码", "repo search",
        ])

        f.has_stacktrace = any(x in text for x in [
            "Traceback (most recent call last):",
            "Exception",
            "Error:",
            "TypeError:",
            "ValueError:",
            "IndentationError:",
            "SyntaxError:",
        ])

        f.has_write_action = any(x in lower for x in [
            "修改", "修复", "实现", "新增", "删除", "重构",
            "patch", "write", "edit", "apply", "refactor",
        ])

        f.has_destructive_action = any(x in lower for x in [
            "删除文件", "清空", "覆盖", "重置", "drop table",
            "rm -rf", "格式化磁盘", "迁移数据库", "生产环境", "部署",
        ])

        f.has_security_term = any(x in lower for x in [
            "token", "secret", "password", "密码", "密钥",
            ".env", "鉴权", "权限", "越权", "注入", "漏洞",
            "security", "xss", "csrf", "sql injection",
        ])

        f.has_debug_symptom = any(x in lower for x in [
            "不工作", "不生效", "炸了", "报错", "卡住",
            "偶尔", "间歇", "复现", "根因", "排查",
            "doesn't work", "not working", "flaky", "intermittent",
        ])

        f.has_test_mismatch = any(x in lower for x in [
            "测试通过但", "tests pass but", "单测通过但",
            "真实", "实际不行", "real tui", "线上不行",
        ])

        f.has_architecture_term = any(x in lower for x in [
            "架构", "编排", "pipeline", "workflow", "router",
            "agent", "多智能体", "重构", "多文件", "系统设计",
            "architecture", "orchestration",
        ])

        f.has_creative_term = any(x in lower for x in [
            "图片", "视频", "分镜", "镜头", "prompt", "风格",
            "生图", "生视频", "剧本", "文案", "storyboard",
        ])

        f.has_simple_chat = len(text.strip()) <= 80 and not any([
            f.has_code_block,
            f.has_stacktrace,
            f.has_file_path,
            f.has_write_action,
            f.has_explicit_web,
            f.has_local_search,
        ])

        return f

    def _explicit_mode(self, lower: str) -> RouteMode | None:
        mapping = {
            "/fast": RouteMode.FAST,
            "/balanced": RouteMode.BALANCED,
            "/deep": RouteMode.DEEP,
            "/safe": RouteMode.SAFE,
            "/research": RouteMode.RESEARCH,
            "/creative": RouteMode.CREATIVE,
        }
        for key, mode in mapping.items():
            if lower.strip().startswith(key):
                return mode
        return None


class SignalScorer:
    def score(self, f: RouteFeatures) -> tuple[RouteMode, dict[str, float], list[RouteSignal], float]:
        scores = {m.value: 0.0 for m in RouteMode}
        signals: list[RouteSignal] = []

        def add(mode: RouteMode, weight: float, name: str, evidence: str, hard: bool = False):
            scores[mode.value] += weight
            signals.append(RouteSignal(name=name, mode=mode, weight=weight, evidence=evidence, hard=hard))

        if f.explicit_mode:
            add(f.explicit_mode, 100.0, "explicit_mode", f.explicit_mode.value, hard=True)

        if f.has_destructive_action:
            add(RouteMode.SAFE, 100.0, "destructive_action", "destructive keyword", hard=True)

        if f.has_security_term:
            add(RouteMode.SAFE, 12.0, "security_term", "security keyword")

        if f.has_explicit_web:
            add(RouteMode.RESEARCH, 12.0, "explicit_web", "web/freshness keyword")

        if f.has_local_search:
            add(RouteMode.DEEP, 5.0, "local_search", "repo/local search keyword")
            scores[RouteMode.RESEARCH.value] -= 4.0

        if f.has_stacktrace:
            add(RouteMode.DEEP, 10.0, "stacktrace", "stacktrace detected")

        if f.has_debug_symptom:
            add(RouteMode.DEEP, 7.0, "debug_symptom", "debug symptom")

        if f.has_test_mismatch:
            add(RouteMode.DEEP, 10.0, "test_reality_mismatch", "tests pass but real behavior fails")

        if f.has_architecture_term:
            add(RouteMode.DEEP, 8.0, "architecture_term", "architecture/workflow/router term")

        if f.has_code_block or f.has_file_path:
            add(RouteMode.BALANCED, 4.0, "code_context", "code block or file path")
            add(RouteMode.DEEP, 3.0, "code_context_deep", "code block or file path")

        if f.has_write_action:
            add(RouteMode.BALANCED, 3.0, "write_action", "write/edit/fix keyword")
            add(RouteMode.DEEP, 4.0, "write_action_deep", "write/edit/fix keyword")

        if f.has_creative_term:
            add(RouteMode.CREATIVE, 8.0, "creative_term", "creative generation keyword")

        # “生成代码”不是 CREATIVE，要压回代码模式
        if f.has_creative_term and any(x in f.text.lower() for x in ["生成代码", "code", "python", "函数", "class"]):
            scores[RouteMode.CREATIVE.value] -= 6.0
            add(RouteMode.BALANCED, 5.0, "code_generation_not_creative", "generate code")

        if f.has_simple_chat:
            add(RouteMode.FAST, 5.0, "simple_chat", "short simple request")

        # no-web 是硬约束：除非 explicit /research，否则压制 RESEARCH
        if f.has_explicit_no_web and f.explicit_mode != RouteMode.RESEARCH:
            scores[RouteMode.RESEARCH.value] -= 50.0
            add(RouteMode.BALANCED, 3.0, "explicit_no_web", "user forbids web")

        sorted_scores = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best_name, best_score = sorted_scores[0]
        second_score = sorted_scores[1][1]
        margin = best_score - second_score
        confidence = max(0.0, min(1.0, margin / 12.0))

        return RouteMode(best_name), scores, signals, confidence

然后在 core/intelligence_policy.py 里改成：

Python
运行
from core.routing_signals import SignalExtractor, SignalScorer, RouteMode


class IntelligencePolicyRouter:
    def __init__(self, trm_route=None):
        self.trm_route = trm_route
        self.extractor = SignalExtractor()
        self.scorer = SignalScorer()

    async def route(self, user_request: str, context: dict | None = None) -> IntelligencePolicy:
        context = context or {}

        features = self.extractor.extract(user_request)
        mode, scores, signals, confidence = self.scorer.score(features)

        trm = await self._safe_trm_route(user_request, features, context)
        mode = self._overlay_trm(mode, scores, trm, features)

        # 低置信度不要冒进。默认升到 BALANCED，不直接 FAST。
        if confidence < 0.25 and mode == RouteMode.FAST:
            mode = RouteMode.BALANCED

        policy = self._policy_for_mode(mode, features, scores, signals, trm, confidence)

        return policy

    async def _safe_trm_route(self, user_request, features, context):
        if not self.trm_route:
            return {}

        try:
            return await self.trm_route({
                "request": user_request,
                "features": features.__dict__,
                "context": context,
            })
        except Exception as exc:
            return {"error": repr(exc), "intents": []}

    def _overlay_trm(self, mode, scores, trm, features):
        intents = set(trm.get("intents", []))

        # TRM 只能增强，不能绕过安全硬规则
        if features.has_destructive_action or features.has_security_term:
            return RouteMode.SAFE

        if "search" in intents and not features.has_explicit_no_web:
            if features.has_explicit_web:
                return RouteMode.RESEARCH

        if "execute" in intents and mode in {RouteMode.FAST, RouteMode.BALANCED}:
            return RouteMode.DEEP

        if "review" in intents and features.has_code_block:
            return RouteMode.BALANCED

        return mode
加黄金测试：tests/test_intelligence_policy_golden.py
Python
运行
import pytest

from core.intelligence_policy import IntelligencePolicyRouter
from core.routing_signals import RouteMode


class DummyRouter:
    async def __call__(self, payload):
        return {"intents": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [
    ("你好", RouteMode.FAST),
    ("解释一下这个函数是什么意思", RouteMode.BALANCED),
    ("请不要联网，只看本地代码分析这个 bug", RouteMode.DEEP),
    ("搜索项目里的 send_stream 调用链", RouteMode.DEEP),
    ("请查最新官方文档", RouteMode.RESEARCH),
    ("测试都通过但真实 TUI 不能滚动", RouteMode.DEEP),
    ("删除 output 目录并重置配置", RouteMode.SAFE),
    ("检查这个 token 是否有泄漏风险", RouteMode.SAFE),
    ("帮我生成 Python 路由器代码", RouteMode.BALANCED),
    ("做一个电影级视频分镜 prompt", RouteMode.CREATIVE),
])
async def test_router_golden_cases(text, expected):
    router = IntelligencePolicyRouter(trm_route=DummyRouter())
    policy = await router.route(text)
    assert policy.mode.value == expected.value
P0：在 core/deliberate_flow.py 加 ContextGather 和 PlanGate

现在五轮前面必须补一轮：

ContextGather → Plan → PlanGate → Attack → Criticize → Repair → Verify
直接加代码
Python
运行
class DeliberateWorkflow:
    async def run(self, request: str, context: dict | None = None):
        context = context or {}
        policy = await self.policy_router.route(request, context)

        goal = await self.toolbus.call("create_goal", {
            "request": request,
            "policy": policy.to_dict(),
        })

        context_pack = await self._gather_context(request, goal, policy, context)

        plan = await self.toolbus.call("execute_plan", {
            "mode": "plan_only",
            "request": request,
            "goal": goal,
            "context_pack": context_pack,
            "allow_write": False,
            "allow_shell": False,
        })

        gate = self._plan_gate(goal, plan, policy, context_pack)
        if gate["status"] == "block":
            plan = await self.toolbus.call("execute_plan", {
                "mode": "revise_plan_only",
                "goal": goal,
                "previous_plan": plan,
                "gate_failures": gate["failures"],
                "context_pack": context_pack,
                "allow_write": False,
                "allow_shell": False,
            })

        attack = await self._attack(request, goal, plan, policy, context_pack)

        critique = await self.critic.review(
            goal=goal,
            plan=plan,
            attack_report=attack,
            context_pack=context_pack,
            policy=policy.to_dict(),
        )

        if critique["status"] == "block":
            plan = await self.toolbus.call("execute_plan", {
                "mode": "revise_plan_only",
                "goal": goal,
                "previous_plan": plan,
                "critique": critique,
                "context_pack": context_pack,
                "allow_write": False,
            })

        result = await self.toolbus.call("execute_plan", {
            "mode": "execute",
            "goal": goal,
            "plan": plan,
            "context_pack": context_pack,
            "allow_write": policy.allow_write,
            "allow_shell": policy.allow_shell,
            "require_tests": policy.require_tests,
        })

        evaluation = await self.toolbus.call("goal_evaluate", {
            "goal": goal,
            "result": result,
            "finish_line": goal.get("finish_line", []),
        })

        return await self._repair_until_pass(
            goal=goal,
            plan=plan,
            result=result,
            evaluation=evaluation,
            critique=critique,
            policy=policy,
            context_pack=context_pack,
        )
新增 _gather_context
Python
运行
async def _gather_context(self, request, goal, policy, context):
    context_pack = {
        "local": None,
        "web": None,
        "history": None,
        "risk": policy.risk.__dict__ if hasattr(policy, "risk") else {},
    }

    # 本地代码任务：先走 trm_route(search)，不是 web_search
    if policy.mode.value in {"BALANCED", "DEEP", "SAFE"}:
        context_pack["local"] = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": request,
            "goal": goal,
            "max_results": 12,
        })

    # RESEARCH 才联网
    if policy.mode.value == "RESEARCH" or getattr(policy, "require_evidence_pack", False):
        context_pack["web"] = await self.toolbus.call("web_search", {
            "query": request,
            "max_results": 6,
        })

    return context_pack
新增 _plan_gate
Python
运行
def _plan_gate(self, goal, plan, policy, context_pack):
    failures = []

    if not goal.get("finish_line"):
        failures.append("missing finish_line")

    if not goal.get("constraints"):
        failures.append("missing constraints")

    if not plan:
        failures.append("empty plan")

    plan_text = str(plan).lower()

    if policy.mode.value in {"DEEP", "SAFE"} and "test" not in plan_text and "pytest" not in plan_text:
        failures.append("DEEP/SAFE plan missing tests")

    if policy.mode.value == "RESEARCH" and not context_pack.get("web"):
        failures.append("RESEARCH mode missing web evidence pack")

    if policy.mode.value in {"DEEP", "SAFE"} and not context_pack.get("local"):
        failures.append("DEEP/SAFE mode missing local context pack")

    if policy.mode.value == "SAFE" and "rollback" not in plan_text and "回滚" not in plan_text:
        failures.append("SAFE plan missing rollback strategy")

    return {
        "status": "block" if failures else "pass",
        "failures": failures,
    }
P1：加 Router Replay / 真实路由评测

你现在 68/68 通过只能证明“代码没有坏”，不能证明“路由准”。

新增：

core/router_replay.py
data/router_golden_cases.jsonl
tests/test_router_replay.py
data/router_golden_cases.jsonl
JSON
{"text":"你好","expected":"FAST","why":"simple chat"}
{"text":"请搜索项目里的 send_stream 调用链","expected":"DEEP","why":"local repo search, not web"}
{"text":"查一下 prompt_toolkit 3.0.52 官方文档","expected":"RESEARCH","why":"fresh external API"}
{"text":"测试通过但真实 TUI 不滚动","expected":"DEEP","why":"test/reality mismatch"}
{"text":"删除所有缓存并重置配置","expected":"SAFE","why":"destructive operation"}
{"text":"帮我生成 Python 代码","expected":"BALANCED","why":"code generation, not creative"}
{"text":"给我写 5 个电影级分镜 prompt","expected":"CREATIVE","why":"visual prompt task"}
core/router_replay.py
Python
运行
import json
from pathlib import Path


async def replay_router(router, path: str = "data/router_golden_cases.jsonl"):
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))

    results = []
    for case in cases:
        policy = await router.route(case["text"])
        got = policy.mode.value
        ok = got == case["expected"]
        results.append({
            "ok": ok,
            "text": case["text"],
            "expected": case["expected"],
            "got": got,
            "why": case.get("why", ""),
        })

    passed = sum(1 for r in results if r["ok"])
    total = len(results)

    return {
        "passed": passed,
        "total": total,
        "accuracy": passed / total if total else 0,
        "failures": [r for r in results if not r["ok"]],
    }

目标：路由准确率先做到 90%+，再谈智能。

C. 真实 CRUX 架构问题：关键词路由怎么升级
C1. 不要让 LLM 做主分类器

答案：不要用 DeepSeek 做主路由。

这样做：

硬规则主判
信号评分排序
TRM intent 叠加
LLM 只做低置信度 tie-breaker

原因：

1. 路由必须稳定、便宜、可测、可回放
2. DeepSeek 分类会受 prompt、上下文、温度影响
3. 路由错误会级联导致错误工具链
4. LLM 分类适合补盲，不适合当安全门

只在这种情况调用 LLM classifier：

Python
运行
if confidence < 0.25 and top_two_modes_are_close:
    mode = await llm_tiebreak_classify(...)

而且 LLM classifier 不能覆盖 SAFE：

Python
运行
if hard_guard_mode == "SAFE":
    return SAFE
C2. _auto_route 应该叠加逻辑层，但不要混成一个路由器

答案：应该叠加，但要分两层。

现在应该形成两个独立决策：

Model Route：用哪个模型 / tier
Workflow Route：走 FAST / BALANCED / DEEP / SAFE / RESEARCH / CREATIVE

不要让 _auto_route() 同时决定模型和工作流，否则以后会变成一坨。

新结构
Python
运行
@dataclass
class RoutingDecision:
    workflow_mode: str
    model_tier: str
    model_id: str | None
    provider: str | None
    tool_policy: dict
    reason: dict
ChatSession.send_stream() 里这样接
Python
运行
async def send_stream(self, user_message: str):
    decision = await self.route_intelligence(user_message)

    if decision.workflow_mode in {"DEEP", "SAFE", "RESEARCH", "CREATIVE"}:
        async for event in self.intelligence_hook.run_stream(user_message, decision):
            yield event
        return

    # 原有路径
    async for event in self._send_stream_normal(user_message, decision):
        yield event
route_intelligence
Python
运行
async def route_intelligence(self, user_message: str) -> RoutingDecision:
    workflow_policy = await self.intelligence_policy_router.route(user_message, {
        "code_mode": self.code_mode,
        "agent_mode": self.agent_mode,
        "loaded_skills": self.loaded_skills,
    })

    model_route = self._auto_route(
        user_message,
        workflow_mode=workflow_policy.mode.value,
    )

    return RoutingDecision(
        workflow_mode=workflow_policy.mode.value,
        model_tier=model_route.tier,
        model_id=model_route.model_id,
        provider=model_route.provider,
        tool_policy=workflow_policy.to_dict(),
        reason={
            "workflow": workflow_policy.to_dict(),
            "model": model_route.to_dict(),
        },
    )
_auto_route 的新职责
只决定模型：
- flash / pro / heavy
- local / api
- provider fallback
IntelligencePolicyRouter 的职责
只决定流程：
- FAST / BALANCED / DEEP / SAFE / RESEARCH / CREATIVE
- 工具链
- 轮数
- 是否 critic
- 是否 evidence
- 是否 tests
C3. 不需要 LLM 的硬规则系统：这样做

你要加一个 Action × Object × Risk Matrix。

core/risk_matrix.py
Python
运行
from dataclasses import dataclass
from enum import Enum


class ActionType(str, Enum):
    READ = "read"
    SEARCH = "search"
    EXPLAIN = "explain"
    REVIEW = "review"
    GENERATE = "generate"
    MODIFY = "modify"
    EXECUTE = "execute"
    DELETE = "delete"
    DEPLOY = "deploy"


class ObjectType(str, Enum):
    TEXT = "text"
    CODE = "code"
    REPO = "repo"
    CONFIG = "config"
    SECRET = "secret"
    DATABASE = "database"
    BROWSER = "browser"
    IMAGE_VIDEO = "image_video"
    UNKNOWN = "unknown"


@dataclass
class RiskDecision:
    action: ActionType
    object_type: ObjectType
    base_mode: str
    requires_context: bool
    requires_plan: bool
    requires_tests: bool
    requires_review: bool
    requires_approval: bool


MATRIX: dict[tuple[ActionType, ObjectType], RiskDecision] = {
    (ActionType.EXPLAIN, ObjectType.TEXT): RiskDecision(
        ActionType.EXPLAIN, ObjectType.TEXT,
        "FAST", False, False, False, False, False,
    ),
    (ActionType.REVIEW, ObjectType.CODE): RiskDecision(
        ActionType.REVIEW, ObjectType.CODE,
        "BALANCED", True, False, False, True, False,
    ),
    (ActionType.MODIFY, ObjectType.CODE): RiskDecision(
        ActionType.MODIFY, ObjectType.CODE,
        "DEEP", True, True, True, True, False,
    ),
    (ActionType.DELETE, ObjectType.REPO): RiskDecision(
        ActionType.DELETE, ObjectType.REPO,
        "SAFE", True, True, True, True, True,
    ),
    (ActionType.MODIFY, ObjectType.SECRET): RiskDecision(
        ActionType.MODIFY, ObjectType.SECRET,
        "SAFE", True, True, True, True, True,
    ),
    (ActionType.SEARCH, ObjectType.REPO): RiskDecision(
        ActionType.SEARCH, ObjectType.REPO,
        "BALANCED", True, False, False, False, False,
    ),
    (ActionType.SEARCH, ObjectType.UNKNOWN): RiskDecision(
        ActionType.SEARCH, ObjectType.UNKNOWN,
        "RESEARCH", False, False, False, False, False,
    ),
    (ActionType.GENERATE, ObjectType.IMAGE_VIDEO): RiskDecision(
        ActionType.GENERATE, ObjectType.IMAGE_VIDEO,
        "CREATIVE", True, True, False, True, False,
    ),
}
Action/Object 抽取器
Python
运行
class ActionObjectDetector:
    def detect(self, text: str) -> tuple[ActionType, ObjectType]:
        lower = text.lower()

        action = ActionType.EXPLAIN
        if any(k in lower for k in ["删除", "remove", "delete", "清空"]):
            action = ActionType.DELETE
        elif any(k in lower for k in ["执行", "运行", "run", "execute"]):
            action = ActionType.EXECUTE
        elif any(k in lower for k in ["修改", "修复", "实现", "改", "patch", "edit"]):
            action = ActionType.MODIFY
        elif any(k in lower for k in ["审查", "review", "检查"]):
            action = ActionType.REVIEW
        elif any(k in lower for k in ["搜索", "查找", "grep", "search"]):
            action = ActionType.SEARCH
        elif any(k in lower for k in ["生成", "写一个", "create", "generate"]):
            action = ActionType.GENERATE

        obj = ObjectType.UNKNOWN
        if any(k in lower for k in [".py", ".ts", ".js", "代码", "函数", "class", "traceback"]):
            obj = ObjectType.CODE
        elif any(k in lower for k in ["项目", "仓库", "repo", "目录", "文件"]):
            obj = ObjectType.REPO
        elif any(k in lower for k in [".env", "token", "secret", "密码", "密钥"]):
            obj = ObjectType.SECRET
        elif any(k in lower for k in ["数据库", "migration", "sql", "table"]):
            obj = ObjectType.DATABASE
        elif any(k in lower for k in ["浏览器", "网页", "cdp", "playwright"]):
            obj = ObjectType.BROWSER
        elif any(k in lower for k in ["图片", "视频", "分镜", "prompt", "生图", "生视频"]):
            obj = ObjectType.IMAGE_VIDEO
        elif any(k in lower for k in ["文案", "段落", "文本", "翻译"]):
            obj = ObjectType.TEXT

        return action, obj

然后在 Router 里：

Python
运行
action, obj = self.action_object_detector.detect(user_request)
matrix_decision = MATRIX.get((action, obj))

if matrix_decision:
    mode = max_mode(mode, matrix_decision.base_mode)
    policy.require_goal_contract |= matrix_decision.requires_plan
    policy.require_tests |= matrix_decision.requires_tests
    policy.require_critic_round |= matrix_decision.requires_review
    policy.require_user_approval_for_destructive_ops |= matrix_decision.requires_approval
CriticAgent 直接改进版 Prompt

把 self-critic prompt 换成这个：

Python
运行
SELF_CRITIC_PROMPT = """
你是 CRUX Studio 的阻塞式审查器，不是建议者。

你的任务：
审查 PLAN / PATCH / ATTACK_REPORT 是否足以满足 GOAL.finish_line。
你只能输出 JSON，不输出 Markdown。

审查维度：
1. goal_mismatch：是否偏离用户目标
2. missing_context：是否缺少必要代码/日志/文档上下文
3. missing_test：是否缺少测试或验证命令
4. unsupported_claim：是否把猜测当事实
5. unsafe_action：是否有危险写入、删除、shell、网络、secret 风险
6. over_scope：是否修改范围过大
7. regression_risk：是否可能破坏已有功能
8. weak_repair：修复是否只修表面症状

输出格式：
{
  "source": "self_critic",
  "status": "pass | needs_fix | block",
  "findings": [
    {
      "id": "F001",
      "category": "missing_test",
      "severity": "low | medium | high | critical",
      "finding": "具体问题",
      "evidence": "必须引用 goal/plan/patch/attack_report 中的具体内容",
      "related_finish_line": "对应的 finish_line，没有则 null",
      "related_plan_step": "对应的 plan step，没有则 null",
      "required_fix": "最小修复动作",
      "blocks_execution": true
    }
  ]
}

硬规则：
- 没有 evidence 的 finding 禁止输出。
- 不要泛泛说“需要更多测试”，必须说需要什么测试。
- 如果发现危险写入/删除/secret/生产配置风险，status 必须是 block。
- 如果 finish_line 没有验证路径，status 至少是 needs_fix。
- 如果只是风格建议，禁止输出。
"""

再加一个 finding 过滤器：

Python
运行
def normalize_findings(raw_findings: list[dict]) -> list[dict]:
    cleaned = []
    for f in raw_findings:
        if not f.get("finding"):
            continue
        if not f.get("evidence"):
            continue
        if not f.get("required_fix"):
            continue
        cleaned.append(f)

    return cleaned[:8]
intelligence_hook.py 的正确 wire 方式

重点：不要破坏 (kind, payload) 协议。

Python
运行
class IntelligenceHook:
    def __init__(self, workflow, fallback_send_stream):
        self.workflow = workflow
        self.fallback_send_stream = fallback_send_stream

    async def send_stream(self, session, user_message: str):
        try:
            policy = await self.workflow.policy_router.route(user_message, {
                "code_mode": getattr(session, "code_mode", False),
                "agent_mode": getattr(session, "agent_mode", False),
                "loaded_skills": getattr(session, "loaded_skills", []),
            })

            if policy.mode.value == "FAST":
                async for event in self.fallback_send_stream(user_message):
                    yield event
                return

            yield ("status", {
                "phase": "intelligence_policy",
                "mode": policy.mode.value,
                "message": f"CRUX Intelligence Pipeline: {policy.mode.value}",
            })

            async for event in self.workflow.run_stream(user_message, policy=policy):
                # event 必须已经是 (kind, payload)
                yield event

        except Exception as exc:
            yield ("status", {
                "phase": "intelligence_fallback",
                "message": f"Intelligence Pipeline failed, fallback to normal chat: {exc!r}",
            })

            async for event in self.fallback_send_stream(user_message):
                yield event

workflow.run_stream() 里面按阶段发状态：

Python
运行
async def run_stream(self, request: str, policy):
    yield ("status", {"phase": "context_gather", "message": "Collecting context"})
    context_pack = await self._gather_context(...)

    yield ("status", {"phase": "plan", "message": "Building plan"})
    plan = await self._plan(...)

    yield ("status", {"phase": "critic", "message": "Reviewing plan"})
    critique = await self.critic.review(...)

    result = await self._execute_or_repair(...)

    yield ("assistant", {
        "content": self._render_final(result),
        "metadata": {
            "mode": policy.mode.value,
            "verified": result.get("evaluation", {}).get("status"),
        },
    })
最终优先级表
优先级	文件	直接改什么
P0	core/intelligence_policy.py + core/routing_signals.py	从关键词改成信号评分、硬规则、TRM overlay、confidence
P0	core/deliberate_flow.py	在 Plan 前加 ContextGather，在 Plan 后加 PlanGate
P0	core/critic_agent.py	self-critic 改成 blocking schema，丢弃无 evidence finding
P1	core/intelligence_hook.py	确保只 yield (kind, payload)，失败 fallback，避免递归 send_stream
P1	data/router_golden_cases.jsonl + core/router_replay.py	建 50-100 条真实路由黄金集，跑准确率
P2	core/policy_memory.py	把历史失败路由写入 memory，做 route calibration
最终判断

你现在的 Intelligence Pipeline 已经过了“能跑”的阶段，下一步不要继续堆 Agent。下一步要做的是：

1. 路由可解释
2. Plan 有门禁
3. Critic 有证据
4. Hook 不破坏流式协议
5. 路由准确率可回放评测

一句话：

CRUX 现在最该补的不是更多推理轮次，而是 Router V2 + PlanGate + Evidence-based Critic。