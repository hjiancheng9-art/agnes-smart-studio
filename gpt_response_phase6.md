你的 Intelligence Pipeline 现在已经进入：

L4：可观测、自评估、可学习的智能流水线

但还没到：

L5：生产级自治执行系统

原因很明确：你现在已经解决了 “想得对不对、证据够不够、能不能从失败中学习”，但还没有完全解决 “长时间运行会不会卡死、工具会不会失控、写文件能不能回滚、并发任务会不会互相踩、学习补丁会不会污染系统”。

所以当前成熟度我给：

Intelligence Pipeline 成熟度：8.2 / 10

已经具备：
- 路由
- 规划
- 审查
- 修复
- 验证
- 追踪
- 评测
- 学习

尚缺：
- 资源预算
- 取消机制
- 回滚机制
- 工具事务
- 并发隔离
- 学习补丁灰度发布
- 运行时健康检查
Phase 6 三个方向
方向 A：Production Reliability OS

这是我最推荐的 Phase 6。

目标是把 CRUX 从：

聪明但可能失控

升级成：

聪明、可控、可取消、可回滚、可恢复

你现在有 execute_plan、multi_agent、agent_swarm、CDP 浏览器、文件写入、代码执行、PolicyAdapter 自动调参，这些都需要运行时治理。

Phase 6-A 要新增这些模块：

core/runtime_guard.py
core/resource_budget.py
core/cancellation.py
core/transaction_manager.py
core/rollback_manager.py
core/tool_sandbox.py
core/healthcheck.py
core/learning_canary.py

核心能力：

1. 每个 Intelligence Run 有预算
2. 用户可取消长任务
3. 写文件前自动 snapshot
4. 工具调用支持事务记录
5. 失败后自动 rollback
6. CDP / shell / write_file 受沙箱限制
7. 自动学习补丁先 canary，不直接污染主策略

关键代码骨架：

Python
运行
# core/resource_budget.py

from dataclasses import dataclass
import time


@dataclass
class ResourceBudget:
    max_tool_calls: int = 40
    max_runtime_sec: float = 300
    max_web_calls: int = 8
    max_repair_rounds: int = 3
    max_agent_tasks: int = 12

    started_at: float = time.time()
    tool_calls: int = 0
    web_calls: int = 0
    repair_rounds: int = 0
    agent_tasks: int = 0

    def check(self) -> None:
        if time.time() - self.started_at > self.max_runtime_sec:
            raise RuntimeError("runtime budget exceeded")

        if self.tool_calls > self.max_tool_calls:
            raise RuntimeError("tool call budget exceeded")

        if self.web_calls > self.max_web_calls:
            raise RuntimeError("web call budget exceeded")

        if self.repair_rounds > self.max_repair_rounds:
            raise RuntimeError("repair round budget exceeded")

        if self.agent_tasks > self.max_agent_tasks:
            raise RuntimeError("agent task budget exceeded")

    def count_tool(self, tool_name: str) -> None:
        self.tool_calls += 1

        if tool_name in {"web_search", "web_fetch", "pw_navigate"}:
            self.web_calls += 1

        self.check()
Python
运行
# core/cancellation.py

import asyncio
from dataclasses import dataclass


@dataclass
class CancellationToken:
    cancelled: bool = False
    reason: str | None = None

    def cancel(self, reason: str = "cancelled by user") -> None:
        self.cancelled = True
        self.reason = reason

    def throw_if_cancelled(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError(self.reason or "cancelled")
Python
运行
# core/transaction_manager.py

from dataclasses import dataclass, field
from typing import Any
import time
import uuid


@dataclass
class ToolTransaction:
    id: str
    tool_name: str
    payload: dict[str, Any]
    started_at: float
    ended_at: float | None = None
    status: str = "running"
    result: dict[str, Any] | None = None
    rollback_info: dict[str, Any] = field(default_factory=dict)


class ToolTransactionManager:
    def __init__(self):
        self.transactions: list[ToolTransaction] = []

    def begin(self, tool_name: str, payload: dict[str, Any]) -> ToolTransaction:
        tx = ToolTransaction(
            id=f"tx_{uuid.uuid4().hex[:12]}",
            tool_name=tool_name,
            payload=payload,
            started_at=time.time(),
        )
        self.transactions.append(tx)
        return tx

    def finish(self, tx: ToolTransaction, result: dict[str, Any]) -> None:
        tx.status = "success"
        tx.result = result
        tx.ended_at = time.time()

    def fail(self, tx: ToolTransaction, error: Exception) -> None:
        tx.status = "failed"
        tx.result = {"error": repr(error)}
        tx.ended_at = time.time()

然后在 execute_plan 或 ToolBus 外面包一层：

Python
运行
async def guarded_tool_call(self, tool_name: str, payload: dict):
    self.cancellation.throw_if_cancelled()
    self.budget.count_tool(tool_name)

    tx = self.tx_manager.begin(tool_name, payload)

    try:
        result = await self.toolbus.call(tool_name, payload)
        self.tx_manager.finish(tx, result)
        return result
    except Exception as exc:
        self.tx_manager.fail(tx, exc)
        raise

这个方向的收益最大，因为它直接补上 CRUX 进入长期可用系统前最危险的短板。

方向 B：Capability Runtime / 能力运行时拆分

目标是把当前统一的 DeliberateWorkflow 拆成多个专业 Runtime：

CodingRuntime
DebugRuntime
ResearchRuntime
CreativeRuntime
SecurityRuntime
RefactorRuntime

现在你的链路已经很完整，但继续堆逻辑会让 DeliberateWorkflow 变成巨型中枢。Phase 6-B 可以把不同任务的最佳实践固化成独立 Runtime。

新增目录：

core/runtime/
  base_runtime.py
  coding_runtime.py
  debug_runtime.py
  research_runtime.py
  creative_runtime.py
  security_runtime.py
  runtime_router.py

骨架：

Python
运行
# core/runtime/base_runtime.py

from abc import ABC, abstractmethod
from typing import Any


class BaseRuntime(ABC):
    name = "base"

    def __init__(self, toolbus, trace_store, evidence_gate, critic_agent):
        self.toolbus = toolbus
        self.trace_store = trace_store
        self.evidence_gate = evidence_gate
        self.critic_agent = critic_agent

    @abstractmethod
    async def run(
        self,
        request: str,
        goal: dict[str, Any],
        policy: Any,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError
Python
运行
# core/runtime/debug_runtime.py

from core.runtime.base_runtime import BaseRuntime


class DebugRuntime(BaseRuntime):
    name = "debug"

    async def run(self, request, goal, policy, context):
        context_pack = await self.toolbus.call("trm_route", {
            "intent": "search",
            "scope": "local_repo",
            "request": request,
            "focus": [
                "error logs",
                "call chain",
                "reproduction path",
                "test gaps",
                "recent changes",
            ],
        })

        plan = await self.toolbus.call("execute_plan", {
            "mode": "plan_only",
            "goal": goal,
            "context_pack": context_pack,
            "require_repro": True,
            "require_tests": True,
        })

        critique = await self.critic_agent.review(
            goal=goal,
            plan=plan,
            context_pack=context_pack,
            policy=policy.to_dict(),
        )

        result = await self.toolbus.call("execute_plan", {
            "mode": "execute",
            "goal": goal,
            "plan": plan,
            "critique": critique,
            "require_tests": True,
            "require_repro": True,
        })

        evidence = self.evidence_gate.evaluate(
            goal=goal,
            result=result,
            policy=policy.to_dict(),
            critique_report=critique,
        )

        result.setdefault("metadata", {})
        result["metadata"]["runtime"] = self.name
        result["metadata"]["evidence_gate"] = evidence.to_dict()

        return result

这个方向的收益是架构整洁、可扩展。缺点是它是中大型重构，最好等 Production Reliability OS 完成后再做。

方向 C：Benchmark Arena / 能力竞技场

目标是让 CRUX 可以持续比较：

不同路由策略
不同 signal 权重
不同 prompt 模板
不同 Critic prompt
不同 repair 策略
不同 skill 组合

你现在有 Replay、Eval、Trace、Learning，但还缺一个“实验平台”。

新增模块：

core/benchmark_arena.py
core/experiment_runner.py
core/variant_registry.py
data/experiments/

核心对象：

Python
运行
from dataclasses import dataclass
from typing import Any


@dataclass
class ExperimentVariant:
    id: str
    name: str
    patch: dict[str, Any]
    description: str


@dataclass
class ExperimentResult:
    variant_id: str
    router_accuracy: float
    eval_pass_rate: float
    avg_score: float
    avg_runtime_sec: float
    regression_count: int

运行逻辑：

Python
运行
class BenchmarkArena:
    def __init__(self, router_replay, intelligence_eval, policy_adapter):
        self.router_replay = router_replay
        self.intelligence_eval = intelligence_eval
        self.policy_adapter = policy_adapter

    async def run_variant(self, variant: ExperimentVariant) -> ExperimentResult:
        snapshot = self.policy_adapter.snapshot()

        try:
            self.policy_adapter.apply_patch(variant.patch)

            router_report = await self.router_replay.run_file(
                "data/router_golden_cases.jsonl"
            )

            eval_report = await self.intelligence_eval.run_file(
                "data/intelligence_eval_cases.jsonl"
            )

            return ExperimentResult(
                variant_id=variant.id,
                router_accuracy=router_report.acceptable_accuracy,
                eval_pass_rate=eval_report.pass_rate,
                avg_score=eval_report.avg_score,
                avg_runtime_sec=getattr(eval_report, "avg_runtime_sec", 0.0),
                regression_count=len(router_report.failures) + len(eval_report.failures),
            )

        finally:
            self.policy_adapter.restore(snapshot)

这个方向会让 PolicyAdapter 更安全，因为任何自动学习补丁都必须先经过 Arena 验证。

我的推荐：Phase 6 做方向 A

明确建议：

Phase 6 = Production Reliability OS

原因：

1. 你已经有自学习了，下一步必须控制自学习风险
2. agent_swarm / execute_plan / CDP / 文件写入都需要预算和回滚
3. 没有取消、预算、事务，复杂任务迟早会卡死或误操作
4. 这是进入 L5 成熟度的关键门槛

推荐 Phase 6 具体拆成 4 个 P0：

P6-1 ResourceBudget
- 限制 tool_calls / web_calls / agent_tasks / runtime / repair_rounds

P6-2 CancellationToken
- 用户中断后所有子任务、agent、browser、execute_plan 都能停

P6-3 ToolTransaction + RollbackManager
- 写文件、执行命令、改配置前自动 snapshot
- 失败后可 rollback

P6-4 Learning Canary
- PolicyAdapter 置信度≥0.7 的自动补丁不能直接全局生效
- 先进入 canary profile
- 通过 RouterReplay + IntelligenceEval 后再 mark_applied

Phase 6 的验收标准：

1. 任意复杂任务都有 ResourceBudget
2. 超预算任务能安全停止
3. 用户取消能中止 workflow / agent_swarm / CDP
4. 文件写入前有 snapshot
5. execute_plan 失败后可以 rollback
6. PolicyAdapter 自动补丁必须先通过 canary eval
7. 现有 107/107 测试不回退
8. 新增 reliability 测试后总测试数达到 125+
最终路线
Phase 6：Production Reliability OS
Phase 7：Benchmark Arena
Phase 8：Capability Runtime 拆分

一句话：

CRUX 现在已经会思考、会验证、会学习；Phase 6 要让它学会“安全地行动”。