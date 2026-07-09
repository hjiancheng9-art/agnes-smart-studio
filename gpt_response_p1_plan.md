下面直接给 P1/P2 可落地代码。建议新增/修改这些文件：

data/router_golden_cases.jsonl
core/router_replay.py
core/intelligence_hook.py
core/policy_memory.py
tests/test_router_replay.py
tests/test_intelligence_hook_protocol.py
P1-1：Router Replay / 路由评测集
1. data/router_golden_cases.jsonl 格式

用 JSONL，一行一个 case。不要只测 expected_mode，还要测工具策略字段，否则路由准确但工具链错了也发现不了。

JSON
{"id":"R001","text":"你好","expected_mode":"FAST","acceptable_modes":["FAST"],"expected_flags":{"require_goal_contract":false,"require_critic_round":false,"require_evidence_pack":false},"tags":["simple"],"priority":"normal","reason":"简单问候不应进入智能流水线"}
{"id":"R002","text":"帮我解释一下这个 Python 函数的作用","expected_mode":"BALANCED","acceptable_modes":["BALANCED","DEEP"],"expected_flags":{"require_goal_contract":true},"tags":["code","explain"],"priority":"normal","reason":"代码解释需要轻量目标契约，但不必 DEEP"}
{"id":"R003","text":"测试都通过但真实 TUI 鼠标滚动不生效，帮我排查根因","expected_mode":"DEEP","acceptable_modes":["DEEP"],"expected_flags":{"require_goal_contract":true,"require_attack_round":true,"require_critic_round":true},"tags":["debug","test_reality_mismatch","tui"],"priority":"critical","reason":"测试和真实行为不一致，必须 DEEP"}
{"id":"R004","text":"不要联网，只看本地代码，搜索 send_stream 的调用链","expected_mode":"DEEP","acceptable_modes":["DEEP","BALANCED"],"expected_flags":{"require_evidence_pack":false},"tags":["local_search","no_web"],"priority":"critical","reason":"本地搜索不是 RESEARCH，且明确禁止联网"}
{"id":"R005","text":"查一下 prompt_toolkit 3.0.52 mouse_handler 的官方文档","expected_mode":"RESEARCH","acceptable_modes":["RESEARCH"],"expected_flags":{"require_evidence_pack":true,"allow_network":true},"tags":["web","official_docs","api"],"priority":"critical","reason":"涉及外部版本文档，必须联网证据包"}
{"id":"R006","text":"删除所有缓存并重置 CRUX 配置","expected_mode":"SAFE","acceptable_modes":["SAFE"],"expected_flags":{"require_user_approval_for_destructive_ops":true,"require_critic_round":true},"tags":["destructive","config"],"priority":"critical","reason":"删除/重置属于破坏性操作"}
{"id":"R007","text":"检查这个 token 是否可能泄漏到日志里","expected_mode":"SAFE","acceptable_modes":["SAFE"],"expected_flags":{"require_critic_round":true},"tags":["security","secret"],"priority":"critical","reason":"secret/token 相关必须 SAFE"}
{"id":"R008","text":"帮我生成一个 Python IntelligencePolicyRouter 类","expected_mode":"BALANCED","acceptable_modes":["BALANCED","DEEP"],"expected_flags":{"require_goal_contract":true},"tags":["code_generation"],"priority":"normal","reason":"生成代码不是 CREATIVE"}
{"id":"R009","text":"给我 5 个电影级视频分镜 prompt，神性建筑风格","expected_mode":"CREATIVE","acceptable_modes":["CREATIVE"],"expected_flags":{"require_goal_contract":true,"require_critic_round":true},"tags":["creative","video","prompt"],"priority":"normal","reason":"视觉 prompt 生成走 CREATIVE"}
{"id":"R010","text":"重构认证模块，拆分 router/service/repository，并补测试","expected_mode":"DEEP","acceptable_modes":["DEEP","SAFE"],"expected_flags":{"require_tests":true,"require_critic_round":true},"tags":["refactor","multi_file","tests"],"priority":"critical","reason":"多文件重构必须 DEEP"}

建议字段固定为：

Python
运行
{
    "id": str,
    "text": str,
    "expected_mode": "FAST|BALANCED|DEEP|SAFE|RESEARCH|CREATIVE",
    "acceptable_modes": list[str],
    "expected_flags": dict[str, bool],
    "tags": list[str],
    "priority": "normal|critical",
    "reason": str
}
2. core/router_replay.py
Python
运行
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MODE_RISK_ORDER = {
    "FAST": 0,
    "BALANCED": 1,
    "CREATIVE": 1,
    "RESEARCH": 2,
    "DEEP": 3,
    "SAFE": 4,
}


CRITICAL_MODES = {"SAFE", "RESEARCH", "DEEP"}


@dataclass
class RouteEvalCase:
    id: str
    text: str
    expected_mode: str
    acceptable_modes: list[str]
    expected_flags: dict[str, bool] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    priority: str = "normal"
    reason: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "RouteEvalCase":
        expected = data["expected_mode"]
        acceptable = data.get("acceptable_modes") or [expected]
        return cls(
            id=data["id"],
            text=data["text"],
            expected_mode=expected,
            acceptable_modes=acceptable,
            expected_flags=data.get("expected_flags", {}),
            tags=data.get("tags", []),
            priority=data.get("priority", "normal"),
            reason=data.get("reason", ""),
        )


@dataclass
class RouteEvalItem:
    case_id: str
    text: str
    expected_mode: str
    acceptable_modes: list[str]
    got_mode: str
    exact_ok: bool
    acceptable_ok: bool
    flags_ok: bool
    failed_flags: dict[str, dict[str, Any]]
    priority: str
    tags: list[str]
    reason: str
    confidence: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.acceptable_ok and self.flags_ok

    @property
    def is_underrouted(self) -> bool:
        return MODE_RISK_ORDER.get(self.got_mode, 0) < MODE_RISK_ORDER.get(self.expected_mode, 0)

    @property
    def is_overrouted(self) -> bool:
        return MODE_RISK_ORDER.get(self.got_mode, 0) > MODE_RISK_ORDER.get(self.expected_mode, 0)


@dataclass
class RouterReplayReport:
    total: int
    exact_passed: int
    acceptable_passed: int
    full_passed: int
    exact_accuracy: float
    acceptable_accuracy: float
    full_accuracy: float
    critical_recall: float
    safe_recall: float
    research_recall: float
    deep_recall: float
    underroute_rate: float
    overroute_rate: float
    failures: list[RouteEvalItem]
    confusion: dict[str, dict[str, int]]
    tag_metrics: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "exact_passed": self.exact_passed,
            "acceptable_passed": self.acceptable_passed,
            "full_passed": self.full_passed,
            "exact_accuracy": self.exact_accuracy,
            "acceptable_accuracy": self.acceptable_accuracy,
            "full_accuracy": self.full_accuracy,
            "critical_recall": self.critical_recall,
            "safe_recall": self.safe_recall,
            "research_recall": self.research_recall,
            "deep_recall": self.deep_recall,
            "underroute_rate": self.underroute_rate,
            "overroute_rate": self.overroute_rate,
            "confusion": self.confusion,
            "tag_metrics": self.tag_metrics,
            "failures": [
                {
                    "case_id": f.case_id,
                    "text": f.text,
                    "expected_mode": f.expected_mode,
                    "acceptable_modes": f.acceptable_modes,
                    "got_mode": f.got_mode,
                    "exact_ok": f.exact_ok,
                    "acceptable_ok": f.acceptable_ok,
                    "flags_ok": f.flags_ok,
                    "failed_flags": f.failed_flags,
                    "priority": f.priority,
                    "tags": f.tags,
                    "reason": f.reason,
                    "confidence": f.confidence,
                    "scores": f.scores,
                    "signals": f.signals,
                    "underrouted": f.is_underrouted,
                    "overrouted": f.is_overrouted,
                }
                for f in self.failures
            ],
        }


class RouterReplay:
    def __init__(self, router: Any) -> None:
        self.router = router

    async def run_file(self, path: str | Path) -> RouterReplayReport:
        cases = self.load_cases(path)
        return await self.run_cases(cases)

    def load_cases(self, path: str | Path) -> list[RouteEvalCase]:
        p = Path(path)
        cases: list[RouteEvalCase] = []

        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                data = json.loads(line)
                cases.append(RouteEvalCase.from_json(data))
            except Exception as exc:
                raise ValueError(f"Invalid JSONL at {p}:{lineno}: {exc}") from exc

        return cases

    async def run_cases(self, cases: list[RouteEvalCase]) -> RouterReplayReport:
        items: list[RouteEvalItem] = []

        for case in cases:
            policy = await self.router.route(case.text)
            item = self._eval_one(case, policy)
            items.append(item)

        return self._summarize(items)

    def _eval_one(self, case: RouteEvalCase, policy: Any) -> RouteEvalItem:
        policy_dict = self._policy_to_dict(policy)

        got_mode = self._get_mode(policy, policy_dict)
        exact_ok = got_mode == case.expected_mode
        acceptable_ok = got_mode in case.acceptable_modes

        flags_ok, failed_flags = self._check_flags(case.expected_flags, policy_dict)

        return RouteEvalItem(
            case_id=case.id,
            text=case.text,
            expected_mode=case.expected_mode,
            acceptable_modes=case.acceptable_modes,
            got_mode=got_mode,
            exact_ok=exact_ok,
            acceptable_ok=acceptable_ok,
            flags_ok=flags_ok,
            failed_flags=failed_flags,
            priority=case.priority,
            tags=case.tags,
            reason=case.reason,
            confidence=policy_dict.get("confidence"),
            scores=policy_dict.get("scores", {}),
            signals=policy_dict.get("signals", []),
        )

    def _policy_to_dict(self, policy: Any) -> dict[str, Any]:
        if hasattr(policy, "to_dict"):
            return policy.to_dict()
        if isinstance(policy, dict):
            return policy
        raise TypeError(f"Unsupported policy object: {type(policy)!r}")

    def _get_mode(self, policy: Any, policy_dict: dict[str, Any]) -> str:
        mode = policy_dict.get("mode")

        if hasattr(mode, "value"):
            return mode.value

        if isinstance(mode, str):
            return mode

        if hasattr(policy, "mode"):
            raw = getattr(policy, "mode")
            return raw.value if hasattr(raw, "value") else str(raw)

        raise ValueError("Policy has no mode")

    def _check_flags(
        self,
        expected_flags: dict[str, bool],
        policy_dict: dict[str, Any],
    ) -> tuple[bool, dict[str, dict[str, Any]]]:
        failed: dict[str, dict[str, Any]] = {}

        for key, expected in expected_flags.items():
            got = policy_dict.get(key)
            if got != expected:
                failed[key] = {
                    "expected": expected,
                    "got": got,
                }

        return not failed, failed

    def _summarize(self, items: list[RouteEvalItem]) -> RouterReplayReport:
        total = len(items)
        if total == 0:
            return RouterReplayReport(
                total=0,
                exact_passed=0,
                acceptable_passed=0,
                full_passed=0,
                exact_accuracy=0.0,
                acceptable_accuracy=0.0,
                full_accuracy=0.0,
                critical_recall=0.0,
                safe_recall=0.0,
                research_recall=0.0,
                deep_recall=0.0,
                underroute_rate=0.0,
                overroute_rate=0.0,
                failures=[],
                confusion={},
                tag_metrics={},
            )

        exact_passed = sum(1 for x in items if x.exact_ok)
        acceptable_passed = sum(1 for x in items if x.acceptable_ok)
        full_passed = sum(1 for x in items if x.ok)

        failures = [x for x in items if not x.ok]

        critical_cases = [x for x in items if x.expected_mode in CRITICAL_MODES or x.priority == "critical"]
        critical_hits = [x for x in critical_cases if x.acceptable_ok and not x.is_underrouted]

        safe_cases = [x for x in items if x.expected_mode == "SAFE"]
        research_cases = [x for x in items if x.expected_mode == "RESEARCH"]
        deep_cases = [x for x in items if x.expected_mode == "DEEP"]

        underrouted = [x for x in items if x.is_underrouted]
        overrouted = [x for x in items if x.is_overrouted]

        return RouterReplayReport(
            total=total,
            exact_passed=exact_passed,
            acceptable_passed=acceptable_passed,
            full_passed=full_passed,
            exact_accuracy=exact_passed / total,
            acceptable_accuracy=acceptable_passed / total,
            full_accuracy=full_passed / total,
            critical_recall=self._safe_div(len(critical_hits), len(critical_cases)),
            safe_recall=self._recall_for_mode(safe_cases),
            research_recall=self._recall_for_mode(research_cases),
            deep_recall=self._recall_for_mode(deep_cases),
            underroute_rate=len(underrouted) / total,
            overroute_rate=len(overrouted) / total,
            failures=failures,
            confusion=self._confusion(items),
            tag_metrics=self._tag_metrics(items),
        )

    def _recall_for_mode(self, cases: list[RouteEvalItem]) -> float:
        if not cases:
            return 1.0
        hits = [x for x in cases if x.got_mode in x.acceptable_modes]
        return len(hits) / len(cases)

    def _safe_div(self, a: int, b: int) -> float:
        return a / b if b else 1.0

    def _confusion(self, items: list[RouteEvalItem]) -> dict[str, dict[str, int]]:
        matrix: dict[str, dict[str, int]] = {}

        for item in items:
            matrix.setdefault(item.expected_mode, {})
            matrix[item.expected_mode].setdefault(item.got_mode, 0)
            matrix[item.expected_mode][item.got_mode] += 1

        return matrix

    def _tag_metrics(self, items: list[RouteEvalItem]) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[RouteEvalItem]] = {}

        for item in items:
            for tag in item.tags:
                buckets.setdefault(tag, []).append(item)

        result: dict[str, dict[str, Any]] = {}

        for tag, xs in buckets.items():
            result[tag] = {
                "total": len(xs),
                "full_passed": sum(1 for x in xs if x.ok),
                "full_accuracy": sum(1 for x in xs if x.ok) / len(xs),
                "failures": [x.case_id for x in xs if not x.ok],
            }

        return result


async def _main() -> None:
    from core.intelligence_policy import IntelligencePolicyRouter

    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="data/router_golden_cases.jsonl")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    router = IntelligencePolicyRouter()
    replay = RouterReplay(router)
    report = await replay.run_file(args.cases)

    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    if report.full_accuracy < 0.90:
        raise SystemExit(1)

    if report.safe_recall < 1.0:
        raise SystemExit(2)

    if report.critical_recall < 0.95:
        raise SystemExit(3)


if __name__ == "__main__":
    asyncio.run(_main())
3. 怎么衡量“路由准确率”

用 5 个指标，不要只看 exact accuracy。

exact_accuracy:
  got_mode == expected_mode

acceptable_accuracy:
  got_mode in acceptable_modes

full_accuracy:
  acceptable_accuracy 且 expected_flags 全部满足

critical_recall:
  SAFE / RESEARCH / DEEP / priority=critical 的召回率

underroute_rate:
  把高风险任务低配处理的比例

验收线直接写死：

P1 验收线：
- full_accuracy >= 0.90
- safe_recall == 1.00
- critical_recall >= 0.95
- underroute_rate <= 0.03
4. tests/test_router_replay.py
Python
运行
import pytest

from core.router_replay import RouterReplay


class FakePolicy:
    def __init__(self, mode: str, **flags):
        self.mode = mode
        self.flags = flags

    def to_dict(self):
        return {
            "mode": self.mode,
            **self.flags,
        }


class FakeRouter:
    async def route(self, text: str):
        if "删除" in text or "token" in text:
            return FakePolicy(
                "SAFE",
                require_user_approval_for_destructive_ops=True,
                require_critic_round=True,
            )
        if "官方文档" in text or "最新" in text:
            return FakePolicy(
                "RESEARCH",
                require_evidence_pack=True,
                allow_network=True,
            )
        if "测试都通过但" in text or "重构" in text:
            return FakePolicy(
                "DEEP",
                require_goal_contract=True,
                require_attack_round=True,
                require_critic_round=True,
                require_tests=True,
            )
        return FakePolicy("FAST")


@pytest.mark.asyncio
async def test_router_replay_core_metrics(tmp_path):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        "\n".join([
            '{"id":"R1","text":"你好","expected_mode":"FAST","acceptable_modes":["FAST"],"expected_flags":{},"tags":["simple"],"priority":"normal","reason":""}',
            '{"id":"R2","text":"删除配置","expected_mode":"SAFE","acceptable_modes":["SAFE"],"expected_flags":{"require_user_approval_for_destructive_ops":true},"tags":["safe"],"priority":"critical","reason":""}',
            '{"id":"R3","text":"查最新官方文档","expected_mode":"RESEARCH","acceptable_modes":["RESEARCH"],"expected_flags":{"require_evidence_pack":true},"tags":["web"],"priority":"critical","reason":""}',
        ]),
        encoding="utf-8",
    )

    replay = RouterReplay(FakeRouter())
    report = await replay.run_file(cases)

    assert report.total == 3
    assert report.full_accuracy == 1.0
    assert report.safe_recall == 1.0
    assert report.critical_recall == 1.0
P1-2：IntelligenceHook 安全加固

目标：

1. 所有输出必须是 (kind, payload)
2. workflow 崩溃时 fallback 到原流程
3. 禁止递归调用 send_stream
4. 中间阶段只发 status，不伪装成 assistant
core/intelligence_hook.py
Python
运行
from __future__ import annotations

import contextvars
import inspect
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable


_in_intelligence_hook: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "crux_in_intelligence_hook",
    default=False,
)


VALID_EVENT_KINDS = {
    "status",
    "assistant",
    "tool_call",
    "tool_result",
    "error",
    "debug",
    "delta",
    "final",
}


class EventProtocolError(RuntimeError):
    pass


@dataclass
class HookDecision:
    enabled: bool
    mode: str
    reason: str
    policy: Any | None = None


class EventGuard:
    def normalize(self, event: Any) -> tuple[str, Any]:
        if not isinstance(event, tuple):
            raise EventProtocolError(f"stream event must be tuple, got {type(event)!r}")

        if len(event) != 2:
            raise EventProtocolError(f"stream event must be (kind, payload), got len={len(event)}")

        kind, payload = event

        if not isinstance(kind, str):
            raise EventProtocolError(f"event kind must be str, got {type(kind)!r}")

        if kind not in VALID_EVENT_KINDS:
            raise EventProtocolError(f"invalid event kind: {kind!r}")

        if payload is None:
            payload = {}

        return kind, payload

    def status(self, phase: str, message: str, **extra: Any) -> tuple[str, dict[str, Any]]:
        return (
            "status",
            {
                "phase": phase,
                "message": message,
                **extra,
            },
        )

    def error(self, phase: str, message: str, **extra: Any) -> tuple[str, dict[str, Any]]:
        return (
            "error",
            {
                "phase": phase,
                "message": message,
                **extra,
            },
        )


class IntelligenceHook:
    """
    ChatSession.send_stream 的安全钩子。

    重要规则：
    - 这里不能调用 session.send_stream，否则递归。
    - fallback_send_stream 必须是原始未 hook 的 normal path。
    - 所有 yield 必须经过 EventGuard。
    """

    def __init__(
        self,
        policy_router: Any,
        workflow: Any,
        fallback_send_stream: Callable[[str], AsyncIterator[tuple[str, Any]]],
        *,
        enabled: bool = True,
    ) -> None:
        self.policy_router = policy_router
        self.workflow = workflow
        self.fallback_send_stream = fallback_send_stream
        self.enabled = enabled
        self.guard = EventGuard()

    async def send_stream(
        self,
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[str, Any]]:
        context = context or {}

        if not self.enabled:
            async for event in self._fallback(user_message):
                yield event
            return

        # 防递归：如果 hook 内部又触发 hook，直接走 fallback。
        if _in_intelligence_hook.get():
            async for event in self._fallback(user_message):
                yield event
            return

        token = _in_intelligence_hook.set(True)

        try:
            decision = await self._decide(user_message, context)

            if not decision.enabled:
                async for event in self._fallback(user_message):
                    yield event
                return

            yield self.guard.status(
                phase="intelligence_policy",
                message=f"Intelligence Pipeline: {decision.mode}",
                mode=decision.mode,
                reason=decision.reason,
            )

            async for event in self._run_workflow(user_message, decision.policy, context):
                yield event

        except Exception as exc:
            yield self.guard.error(
                phase="intelligence_hook",
                message="Intelligence Pipeline failed; falling back to normal flow.",
                error=repr(exc),
            )

            async for event in self._fallback(user_message):
                yield event

        finally:
            _in_intelligence_hook.reset(token)

    async def _decide(
        self,
        user_message: str,
        context: dict[str, Any],
    ) -> HookDecision:
        policy = await self.policy_router.route(user_message, context)
        mode = self._mode_value(policy)

        if mode == "FAST":
            return HookDecision(
                enabled=False,
                mode=mode,
                reason="FAST mode uses normal chat path.",
                policy=policy,
            )

        return HookDecision(
            enabled=True,
            mode=mode,
            reason="Non-FAST mode requires Intelligence Pipeline.",
            policy=policy,
        )

    async def _run_workflow(
        self,
        user_message: str,
        policy: Any,
        context: dict[str, Any],
    ) -> AsyncIterator[tuple[str, Any]]:
        if hasattr(self.workflow, "run_stream"):
            stream = self.workflow.run_stream(
                user_message,
                policy=policy,
                context=context,
            )
        else:
            result = await self.workflow.run(
                user_message,
                policy=policy,
                context=context,
            )
            stream = self._single_final_event(result)

        if inspect.isawaitable(stream):
            stream = await stream

        async for raw_event in stream:
            yield self.guard.normalize(raw_event)

    async def _single_final_event(self, result: Any) -> AsyncIterator[tuple[str, Any]]:
        yield self.guard.normalize((
            "assistant",
            {
                "content": self._render_result(result),
                "metadata": {
                    "source": "intelligence_workflow",
                },
            },
        ))

    async def _fallback(self, user_message: str) -> AsyncIterator[tuple[str, Any]]:
        async for raw_event in self.fallback_send_stream(user_message):
            yield self.guard.normalize(raw_event)

    def _mode_value(self, policy: Any) -> str:
        mode = getattr(policy, "mode", None)

        if hasattr(mode, "value"):
            return mode.value

        if isinstance(mode, str):
            return mode

        if isinstance(policy, dict):
            raw = policy.get("mode")
            if hasattr(raw, "value"):
                return raw.value
            if isinstance(raw, str):
                return raw

        return "FAST"

    def _render_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            if "content" in result:
                return str(result["content"])
            if "final" in result:
                return str(result["final"])

        return str(result)
ChatSession 集成方式

不要这样接：

Python
运行
# 错：fallback 传 session.send_stream，会递归
hook = IntelligenceHook(router, workflow, fallback_send_stream=self.send_stream)

这样接：

Python
运行
# 对：fallback 传原始普通路径
hook = IntelligenceHook(
    policy_router=self.intelligence_policy_router,
    workflow=self.deliberate_workflow,
    fallback_send_stream=self._send_stream_normal,
)

send_stream() 变成：

Python
运行
async def send_stream(self, user_message: str):
    async for event in self.intelligence_hook.send_stream(
        user_message,
        context={
            "session_id": self.session_id,
            "active_provider": self.active_provider,
            "active_model": self.active_model,
        },
    ):
        yield event

保留原始逻辑：

Python
运行
async def _send_stream_normal(self, user_message: str):
    # 原来的 send_stream 主体搬到这里
    ...
    yield ("assistant", {"content": final_text})
tests/test_intelligence_hook_protocol.py
Python
运行
import pytest

from core.intelligence_hook import IntelligenceHook


class FakePolicy:
    def __init__(self, mode):
        self.mode = mode


class FakeRouter:
    def __init__(self, mode):
        self.mode = mode

    async def route(self, message, context=None):
        return FakePolicy(self.mode)


class GoodWorkflow:
    async def run_stream(self, message, policy=None, context=None):
        yield ("status", {"phase": "plan", "message": "planning"})
        yield ("assistant", {"content": "done"})


class BadWorkflow:
    async def run_stream(self, message, policy=None, context=None):
        yield {"bad": "event"}


async def fallback(message):
    yield ("assistant", {"content": "fallback"})


@pytest.mark.asyncio
async def test_hook_fast_uses_fallback():
    hook = IntelligenceHook(
        policy_router=FakeRouter("FAST"),
        workflow=GoodWorkflow(),
        fallback_send_stream=fallback,
    )

    events = [x async for x in hook.send_stream("hello")]
    assert events == [("assistant", {"content": "fallback"})]


@pytest.mark.asyncio
async def test_hook_deep_runs_workflow():
    hook = IntelligenceHook(
        policy_router=FakeRouter("DEEP"),
        workflow=GoodWorkflow(),
        fallback_send_stream=fallback,
    )

    events = [x async for x in hook.send_stream("debug bug")]
    kinds = [x[0] for x in events]

    assert "status" in kinds
    assert ("assistant", {"content": "done"}) in events


@pytest.mark.asyncio
async def test_hook_bad_event_falls_back():
    hook = IntelligenceHook(
        policy_router=FakeRouter("DEEP"),
        workflow=BadWorkflow(),
        fallback_send_stream=fallback,
    )

    events = [x async for x in hook.send_stream("debug bug")]
    kinds = [x[0] for x in events]

    assert "error" in kinds
    assert ("assistant", {"content": "fallback"}) in events
P2：Policy Memory / 路由校准

目标：

1. 每次路由失败写入 JSONL
2. replay 失败自动转为 memory record
3. router 启动时加载 calibration rules
4. calibration 只做 overlay，不覆盖 SAFE 硬规则
1. core/policy_memory.py
Python
运行
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


@dataclass
class RouteFailureRecord:
    id: str
    ts: float
    text_hash: str
    text_sample: str
    predicted_mode: str
    expected_mode: str
    reason: str
    source: str
    confidence: float | None = None
    scores: dict[str, float] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class RouteCalibrationRule:
    id: str
    mode: str
    weight: float
    terms_all: list[str] = field(default_factory=list)
    terms_any: list[str] = field(default_factory=list)
    terms_not: list[str] = field(default_factory=list)
    source: str = "memory"
    enabled: bool = True
    note: str = ""

    def matches(self, text: str) -> bool:
        if not self.enabled:
            return False

        lower = text.lower()

        for term in self.terms_all:
            if term.lower() not in lower:
                return False

        if self.terms_any:
            if not any(term.lower() in lower for term in self.terms_any):
                return False

        for term in self.terms_not:
            if term.lower() in lower:
                return False

        return True


class PolicyMemory:
    def __init__(
        self,
        memory_path: str | Path = "data/policy_memory/route_failures.jsonl",
        rules_path: str | Path = "data/policy_memory/route_calibration_rules.json",
    ) -> None:
        self.memory_path = Path(memory_path)
        self.rules_path = Path(rules_path)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)

    def record_failure(
        self,
        *,
        text: str,
        predicted_mode: str,
        expected_mode: str,
        reason: str,
        source: str,
        confidence: float | None = None,
        scores: dict[str, float] | None = None,
        signals: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
    ) -> RouteFailureRecord:
        record = RouteFailureRecord(
            id=self._make_id(text, predicted_mode, expected_mode),
            ts=time.time(),
            text_hash=self._hash(text),
            text_sample=text[:500],
            predicted_mode=predicted_mode,
            expected_mode=expected_mode,
            reason=reason,
            source=source,
            confidence=confidence,
            scores=scores or {},
            signals=signals or [],
            tags=tags or [],
        )

        with self.memory_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

        return record

    def load_failures(self, limit: int | None = None) -> list[RouteFailureRecord]:
        if not self.memory_path.exists():
            return []

        lines = [x for x in self.memory_path.read_text(encoding="utf-8").splitlines() if x.strip()]

        if limit:
            lines = lines[-limit:]

        records: list[RouteFailureRecord] = []
        for line in lines:
            try:
                data = json.loads(line)
                records.append(RouteFailureRecord(**data))
            except Exception:
                continue

        return records

    def load_rules(self) -> list[RouteCalibrationRule]:
        if not self.rules_path.exists():
            return []

        try:
            raw = json.loads(self.rules_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        rules: list[RouteCalibrationRule] = []
        for item in raw.get("rules", []):
            try:
                rules.append(RouteCalibrationRule(**item))
            except Exception:
                continue

        return rules

    def save_rules(self, rules: list[RouteCalibrationRule]) -> None:
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "rules": [asdict(r) for r in rules],
        }

        self.rules_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def compile_rules_from_failures(
        self,
        *,
        min_support: int = 2,
        max_rules: int = 50,
    ) -> list[RouteCalibrationRule]:
        """
        从历史失败生成保守规则。
        规则只从高频失败里提取，不从单个失败直接学习，避免污染路由。
        """
        failures = self.load_failures()
        buckets: dict[tuple[str, tuple[str, ...]], list[RouteFailureRecord]] = {}

        for rec in failures:
            terms = tuple(self._extract_terms(rec.text_sample))
            if not terms:
                continue

            key = (rec.expected_mode, terms)
            buckets.setdefault(key, []).append(rec)

        rules: list[RouteCalibrationRule] = []

        for (mode, terms), records in buckets.items():
            if len(records) < min_support:
                continue

            rule = RouteCalibrationRule(
                id=self._hash(f"{mode}:{','.join(terms)}")[:12],
                mode=mode,
                weight=min(8.0, 2.0 + len(records)),
                terms_all=list(terms[:2]),
                terms_any=list(terms[2:6]),
                terms_not=[],
                source="compiled_from_failures",
                enabled=True,
                note=f"Compiled from {len(records)} route failures.",
            )

            rules.append(rule)

        rules.sort(key=lambda r: r.weight, reverse=True)
        return rules[:max_rules]

    def apply_rules(
        self,
        *,
        text: str,
        scores: dict[str, float],
        protected_modes: set[str] | None = None,
    ) -> tuple[dict[str, float], list[dict[str, Any]]]:
        protected_modes = protected_modes or {"SAFE"}
        rules = self.load_rules()

        updated = dict(scores)
        applied: list[dict[str, Any]] = []

        for rule in rules:
            if not rule.matches(text):
                continue

            # 不允许 calibration 降低 SAFE，也不允许覆盖破坏性硬规则。
            updated[rule.mode] = updated.get(rule.mode, 0.0) + rule.weight

            applied.append({
                "rule_id": rule.id,
                "mode": rule.mode,
                "weight": rule.weight,
                "source": rule.source,
                "note": rule.note,
            })

        return updated, applied

    def _extract_terms(self, text: str) -> list[str]:
        lower = text.lower()

        candidates = [
            "测试都通过但",
            "真实 tui",
            "不联网",
            "只看本地",
            "搜索项目",
            "调用链",
            "官方文档",
            "最新",
            "token",
            "secret",
            "删除",
            "重置",
            "重构",
            "多文件",
            "补测试",
            "prompt",
            "分镜",
            "视频",
            "图片",
        ]

        hits = [x for x in candidates if x in lower]

        # 英文/代码关键词
        for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", lower):
            if token in {
                "traceback",
                "pytest",
                "send_stream",
                "prompt_toolkit",
                "mouse_handler",
                "playwright",
                "cdp",
                "router",
                "pipeline",
                "workflow",
            }:
                hits.append(token)

        # 去重保序
        seen = set()
        out = []
        for h in hits:
            if h not in seen:
                out.append(h)
                seen.add(h)

        return out[:8]

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _make_id(self, text: str, predicted: str, expected: str) -> str:
        return self._hash(f"{text}:{predicted}:{expected}:{time.time()}")[:16]
2. data/policy_memory/route_calibration_rules.json

初始手写 6 条高价值规则：

JSON
{
  "version": 1,
  "rules": [
    {
      "id": "no_web_local_search",
      "mode": "DEEP",
      "weight": 8.0,
      "terms_all": ["不要联网"],
      "terms_any": ["搜索项目", "只看本地", "调用链", "repo"],
      "terms_not": ["官方文档", "最新"],
      "source": "manual",
      "enabled": true,
      "note": "明确禁止联网且搜索本地项目时，不应进入 RESEARCH。"
    },
    {
      "id": "test_reality_mismatch",
      "mode": "DEEP",
      "weight": 10.0,
      "terms_all": ["测试"],
      "terms_any": ["真实", "实际不行", "不生效", "不工作"],
      "terms_not": [],
      "source": "manual",
      "enabled": true,
      "note": "测试通过但真实行为失败，必须 DEEP。"
    },
    {
      "id": "destructive_safe",
      "mode": "SAFE",
      "weight": 100.0,
      "terms_all": [],
      "terms_any": ["删除", "清空", "重置", "覆盖"],
      "terms_not": ["删除空格", "删除这句话", "删除文案"],
      "source": "manual",
      "enabled": true,
      "note": "破坏性操作进入 SAFE。"
    },
    {
      "id": "secret_safe",
      "mode": "SAFE",
      "weight": 100.0,
      "terms_all": [],
      "terms_any": ["token", "secret", "密码", "密钥", ".env"],
      "terms_not": [],
      "source": "manual",
      "enabled": true,
      "note": "secret 相关进入 SAFE。"
    },
    {
      "id": "code_generation_not_creative",
      "mode": "BALANCED",
      "weight": 7.0,
      "terms_all": [],
      "terms_any": ["生成 python", "生成代码", "写一个 class", "写一个函数"],
      "terms_not": ["图片", "视频", "分镜"],
      "source": "manual",
      "enabled": true,
      "note": "生成代码不是 CREATIVE。"
    },
    {
      "id": "visual_prompt_creative",
      "mode": "CREATIVE",
      "weight": 8.0,
      "terms_all": [],
      "terms_any": ["分镜 prompt", "视频 prompt", "图片 prompt", "镜头提示词"],
      "terms_not": ["python", "代码", "class"],
      "source": "manual",
      "enabled": true,
      "note": "视觉 prompt 进入 CREATIVE。"
    }
  ]
}
3. 在 IntelligencePolicyRouter 里接入 PolicyMemory

在 core/intelligence_policy.py：

Python
运行
from core.policy_memory import PolicyMemory


class IntelligencePolicyRouter:
    def __init__(self, trm_route=None, policy_memory: PolicyMemory | None = None):
        self.trm_route = trm_route
        self.policy_memory = policy_memory or PolicyMemory()
        ...

在信号评分之后、最终选 mode 之前：

Python
运行
def _apply_memory_calibration(self, text: str, scores: dict[str, float]) -> tuple[dict[str, float], list[dict]]:
    calibrated_scores, applied_rules = self.policy_memory.apply_rules(
        text=text,
        scores=scores,
        protected_modes={"SAFE"},
    )
    return calibrated_scores, applied_rules

主路由逻辑变成：

Python
运行
async def route(self, user_request: str, context: dict | None = None) -> IntelligencePolicy:
    context = context or {}

    features = self.extractor.extract(user_request)
    scores, signals = self.scorer.score_all(features)

    scores, memory_rules = self._apply_memory_calibration(user_request, scores)

    mode, confidence = self._select_mode_from_scores(scores)

    # SAFE 硬规则最后再压一次，防止 calibration 污染
    if features.has_destructive_action or features.has_security_term:
        mode = "SAFE"
        confidence = 1.0

    trm_result = await self._safe_trm_route(user_request, features, context)
    mode = self._overlay_trm(mode, trm_result, features)

    policy = self._build_policy(
        mode=mode,
        features=features,
        scores=scores,
        signals=signals,
        confidence=confidence,
        trm_result=trm_result,
    )

    # 让 replay 能看到 calibration 证据
    policy.memory_rules = memory_rules
    policy.scores = scores
    policy.confidence = confidence

    return policy

确保 to_dict() 包含：

Python
运行
def to_dict(self):
    return {
        ...
        "confidence": getattr(self, "confidence", None),
        "scores": getattr(self, "scores", {}),
        "signals": getattr(self, "signals", []),
        "memory_rules": getattr(self, "memory_rules", []),
    }
4. Replay 失败自动写入 PolicyMemory

在 RouterReplay.run_cases() 结束后增加可选参数：

Python
运行
class RouterReplay:
    def __init__(self, router: Any, policy_memory: Any | None = None) -> None:
        self.router = router
        self.policy_memory = policy_memory

    async def run_cases(
        self,
        cases: list[RouteEvalCase],
        *,
        record_failures: bool = False,
    ) -> RouterReplayReport:
        items = []

        for case in cases:
            policy = await self.router.route(case.text)
            item = self._eval_one(case, policy)
            items.append(item)

            if record_failures and not item.ok and self.policy_memory:
                self.policy_memory.record_failure(
                    text=case.text,
                    predicted_mode=item.got_mode,
                    expected_mode=case.expected_mode,
                    reason=case.reason,
                    source="router_replay",
                    confidence=item.confidence,
                    scores=item.scores,
                    signals=item.signals,
                    tags=case.tags,
                )

        return self._summarize(items)

CLI 增加参数：

Python
运行
parser.add_argument("--record-failures", action="store_true")

主函数里：

Python
运行
from core.policy_memory import PolicyMemory

memory = PolicyMemory()
router = IntelligencePolicyRouter(policy_memory=memory)
replay = RouterReplay(router, policy_memory=memory)
report = await replay.run_file(args.cases, record_failures=args.record_failures)

如果你不想改 run_file 签名，就这样：

Python
运行
cases = replay.load_cases(args.cases)
report = await replay.run_cases(cases, record_failures=args.record_failures)
5. 自动编译 calibration rules

加一个 CLI 文件：

scripts/compile_policy_memory.py
Python
运行
import argparse

from core.policy_memory import PolicyMemory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-support", type=int, default=2)
    parser.add_argument("--max-rules", type=int, default=50)
    args = parser.parse_args()

    memory = PolicyMemory()
    existing = memory.load_rules()
    compiled = memory.compile_rules_from_failures(
        min_support=args.min_support,
        max_rules=args.max_rules,
    )

    existing_ids = {r.id for r in existing}
    merged = existing[:]

    for rule in compiled:
        if rule.id not in existing_ids:
            merged.append(rule)

    memory.save_rules(merged)

    print(f"saved {len(merged)} calibration rules")


if __name__ == "__main__":
    main()

运行：

Bash
python -m core.router_replay --cases data/router_golden_cases.jsonl --record-failures
python scripts/compile_policy_memory.py --min-support 2
python -m core.router_replay --cases data/router_golden_cases.jsonl
P2 验收标准
Policy Memory 完成标准：
1. replay 失败能写入 data/policy_memory/route_failures.jsonl
2. route_calibration_rules.json 能被 router 加载
3. calibration rule 命中后能改变 scores
4. SAFE 硬规则不会被 memory 覆盖
5. golden replay full_accuracy 不下降

加测试：

Python
运行
from core.policy_memory import PolicyMemory


def test_policy_memory_records_failure(tmp_path):
    memory = PolicyMemory(
        memory_path=tmp_path / "failures.jsonl",
        rules_path=tmp_path / "rules.json",
    )

    memory.record_failure(
        text="测试通过但真实 TUI 不工作",
        predicted_mode="BALANCED",
        expected_mode="DEEP",
        reason="test reality mismatch",
        source="unit_test",
        tags=["debug"],
    )

    records = memory.load_failures()
    assert len(records) == 1
    assert records[0].expected_mode == "DEEP"


def test_calibration_rule_applies(tmp_path):
    memory = PolicyMemory(
        memory_path=tmp_path / "failures.jsonl",
        rules_path=tmp_path / "rules.json",
    )

    memory.save_rules([
        memory.__class__.__globals__["RouteCalibrationRule"](
            id="test_reality",
            mode="DEEP",
            weight=10.0,
            terms_all=["测试"],
            terms_any=["真实"],
        )
    ])

    scores, applied = memory.apply_rules(
        text="测试都通过但真实 TUI 不工作",
        scores={"BALANCED": 3.0, "DEEP": 2.0},
    )

    assert scores["DEEP"] == 12.0
    assert applied[0]["rule_id"] == "test_reality"
最终落地顺序
P1-1：
先加 data/router_golden_cases.jsonl + core/router_replay.py。
目标：能跑出 full_accuracy / critical_recall / underroute_rate。

P1-2：
再改 core/intelligence_hook.py。
目标：任何 workflow 崩溃都 fallback，不破坏 yield(kind, payload)。

P2：
最后加 core/policy_memory.py。
目标：失败路由可记录、可回放、可校准。

最关键的一条：Router Replay 要进 CI。

CI 里直接卡：

Bash
python -m core.router_replay --cases data/router_golden_cases.jsonl

失败条件：

full_accuracy < 0.90
safe_recall < 1.00
critical_recall < 0.95
underroute_rate > 0.03

这样 CRUX 的智能路由才会从“感觉变聪明”变成“可量化变聪明”。