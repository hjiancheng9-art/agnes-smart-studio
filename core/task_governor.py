"""
Task Governor — CRUX 治理层
===========================
ChatGPT 评审裁决后的核心修复：为 CRUX 增加统一的任务治理层。

职责：
  - 将用户意图解析为可执行的 TaskPlan
  - 基于任务复杂度选择执行策略（单工具 / 链式 / 多智能体）
  - 编排工具调用链，注入上下文
  - 监督执行过程，失败时自动降级或重试
  - 收集执行反馈，持续优化路由决策

使用方式：
  governor = TaskGovernor()
  plan = governor.plan(intent, context)
  result = governor.execute(plan)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("task_governor")


# ─── 域模型 ─────────────────────────────────────────────────

class TaskComplexity(Enum):
    """任务复杂度等级"""
    TRIVIAL = "trivial"           # 单工具调用，如"生成一张图片"
    SIMPLE = "simple"             # 2-3步链式，如"搜索→总结→保存"
    MODERATE = "moderate"         # 需要分支判断，如"分析代码→找bug→修复→测试"
    COMPLEX = "complex"           # 多智能体协调，如"跨文件重构→多模块测试→生成报告"
    CRITICAL = "critical"         # 需人工确认，如"部署到生产环境"


class ExecutionStrategy(Enum):
    """执行策略"""
    DIRECT = "direct"             # 直接调用一个工具
    CHAIN = "chain"               # 顺序链式调用
    BRANCH = "branch"             # 条件分支
    SWARM = "swarm"               # 多智能体并行
    HUMAN = "human"               # 需人工介入


@dataclass
class ToolContract:
    """工具契约 — 每个工具的声明式接口"""
    name: str
    description: str
    category: str                 # infra / creative / code / web / data
    tier: int                     # 1=核心高频, 2=常用, 3=专用, 4=实验性
    input_schema: dict
    output_schema: dict
    cost_estimate: str            # "low" / "medium" / "high"
    common_scenarios: list[str]   # 典型使用场景
    requirements: list[str]       # 前置条件
    limitations: list[str]        # 已知限制
    fallback_tools: list[str]     # 备选工具
    success_rate: float = 0.0    # 历史成功率（自动更新）


@dataclass
class TaskStep:
    """任务步骤"""
    tool: str
    input: dict
    expected_output: str
    retry_count: int = 0
    max_retries: int = 2
    timeout: int = 60
    fallback: str | None = None
    depends_on: list[int] = field(default_factory=list)


@dataclass
class TaskPlan:
    """任务计划 — 治理层的输出"""
    intent: str
    complexity: TaskComplexity
    strategy: ExecutionStrategy
    steps: list[TaskStep]
    context: dict = field(default_factory=dict)
    requires_approval: bool = False
    estimated_cost: str = "low"


@dataclass
class StepResult:
    """单步执行结果"""
    step_index: int
    tool: str
    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    used_fallback: bool = False


# ─── 复杂度评估器 ─────────────────────────────────────────

class ComplexityAnalyzer:
    """分析任务意图，判断复杂度等级"""

    # 关键指标：工具调用数预估、是否需要分支/并行、是否需要外部数据
    SWARM_TRIGGERS = [
        "重构", "迁移", "审计", "审查", "分析所有",
        "批量", "并行", "同时", "对比", "比较",
        "多模块", "跨文件", "全项目", "架构",
    ]

    HUMAN_TRIGGERS = [
        "部署", "发布", "上线", "删除", "销毁",
        "支付", "收费", "授权", "生产环境",
    ]

    @classmethod
    def analyze(cls, intent: str, context: dict = None) -> tuple[TaskComplexity, ExecutionStrategy]:
        intent_lower = intent.lower()
        intent_len = len(intent)

        # 人工介入
        if any(t in intent_lower for t in cls.HUMAN_TRIGGERS):
            return TaskComplexity.CRITICAL, ExecutionStrategy.HUMAN

        # 多智能体
        swarm_score = sum(1 for t in cls.SWARM_TRIGGERS if t in intent_lower)
        if swarm_score >= 2 or intent_len > 500:
            return TaskComplexity.COMPLEX, ExecutionStrategy.SWARM

        # 链式：涉及多步骤关键词
        chain_triggers = ["然后", "接着", "先", "再", "并", "且", "同时"]
        chain_score = sum(1 for t in chain_triggers if t in intent_lower)
        if chain_score >= 2:
            return TaskComplexity.MODERATE, ExecutionStrategy.CHAIN

        # 单步骤
        if intent_len < 30:
            return TaskComplexity.TRIVIAL, ExecutionStrategy.DIRECT

        return TaskComplexity.SIMPLE, ExecutionStrategy.DIRECT


# ─── 工具契约注册表 ───────────────────────────────────────

# 预置的核心工具契约（按 ChatGPT 建议的四层分组）
BUILTIN_CONTRACTS: dict[str, ToolContract] = {
    # ─── 基础设施层 (Tier 1) ───
    "read_file": ToolContract(
        name="read_file", description="读取文本文件内容",
        category="infra", tier=1,
        input_schema={"path": "string", "offset": "int?", "limit": "int?"},
        output_schema={"content": "string", "line_count": "int"},
        cost_estimate="low",
        common_scenarios=["读取代码", "查看配置", "读取日志"],
        requirements=[], limitations=["不超过500行"],
        fallback_tools=["search_files"],
    ),
    "write_file": ToolContract(
        name="write_file", description="创建或覆写文件",
        category="infra", tier=1,
        input_schema={"path": "string", "content": "string"},
        output_schema={"success": "bool"},
        cost_estimate="low",
        common_scenarios=["创建文件", "修改配置", "写入输出"],
        requirements=["确认路径正确"], limitations=[],
        fallback_tools=["patch_file"],
    ),
    "run_bash": ToolContract(
        name="run_bash", description="执行shell命令",
        category="infra", tier=1,
        input_schema={"command": "string", "description": "string?"},
        output_schema={"stdout": "string", "return_code": "int"},
        cost_estimate="medium",
        common_scenarios=["运行脚本", "编译", "部署"],
        requirements=["命令不可阻塞"], limitations=["30s超时"],
        fallback_tools=["run_python"],
    ),
    "web_search": ToolContract(
        name="web_search", description="互联网搜索",
        category="infra", tier=1,
        input_schema={"query": "string"},
        output_schema={"results": "array"},
        cost_estimate="low",
        common_scenarios=["查资料", "搜文档", "找API"],
        requirements=[], limitations=["仅返回摘要"],
        fallback_tools=["web_fetch"],
    ),

    # ─── 创意工具层 (Tier 1-2) ───
    "generate_image": ToolContract(
        name="generate_image", description="文生图 / 图生图",
        category="creative", tier=1,
        input_schema={"prompt": "string", "size": "string?", "style": "string?"},
        output_schema={"image_url": "string"},
        cost_estimate="high",
        common_scenarios=["配图生成", "概念设计", "风格迁移"],
        requirements=["需明确风格和尺寸"], limitations=["不支持视频"],
        fallback_tools=["imagegen"],
    ),
    "generate_video": ToolContract(
        name="generate_video", description="文生视频 / 图生视频",
        category="creative", tier=1,
        input_schema={"prompt": "string", "num_frames": "int?", "mode": "string?"},
        output_schema={"video_url": "string"},
        cost_estimate="high",
        common_scenarios=["动画生成", "视频制作"],
        requirements=[],
        limitations=["最长18s", "需GPU"],
        fallback_tools=[],
    ),

    # ─── 代码工具层 (Tier 1-2) ───
    "git_add_commit": ToolContract(
        name="git_add_commit", description="暂存并提交代码",
        category="code", tier=1,
        input_schema={"message": "string"},
        output_schema={"success": "bool", "commit_hash": "string"},
        cost_estimate="low",
        common_scenarios=["代码提交", "版本管理"],
        requirements=["需有变更文件"], limitations=[],
        fallback_tools=[],
    ),
    "run_test": ToolContract(
        name="run_test", description="运行测试",
        category="code", tier=1,
        input_schema={"path": "string?"},
        output_schema={"passed": "bool", "output": "string"},
        cost_estimate="medium",
        common_scenarios=["测试代码", "验证修改"],
        requirements=["需配置pytest"], limitations=["可能耗时"],
        fallback_tools=["run_bash"],
    ),
    "code_review": ToolContract(
        name="code_review", description="审查代码质量",
        category="code", tier=2,
        input_schema={"files": "array", "mode": "string?"},
        output_schema={"issues": "array"},
        cost_estimate="medium",
        common_scenarios=["代码审查", "安全检查"],
        requirements=["需git跟踪"], limitations=[],
        fallback_tools=["tdd_run_tests"],
    ),

    # ─── Web工具层 (Tier 2) ───
    "web_fetch": ToolContract(
        name="web_fetch", description="获取网页文本",
        category="web", tier=2,
        input_schema={"url": "string"},
        output_schema={"content": "string"},
        cost_estimate="low",
        common_scenarios=["爬取内容", "API调试"],
        requirements=["URL可达"], limitations=["最多5000字"],
        fallback_tools=["browser_screenshot"],
    ),
    "github_search": ToolContract(
        name="github_search", description="搜索GitHub",
        category="web", tier=2,
        input_schema={"query": "string", "search_type": "string?"},
        output_schema={"results": "array"},
        cost_estimate="low",
        common_scenarios=["找开源项目", "搜代码"],
        requirements=[], limitations=[],
        fallback_tools=["web_search"],
    ),

    # ─── 实验性工具 (Tier 4) ───
    "comfyui_submit_workflow": ToolContract(
        name="comfyui_submit_workflow", description="提交ComfyUI工作流",
        category="creative", tier=3,
        input_schema={"workflow_json": "string", "wait": "bool?"},
        output_schema={"result": "any"},
        cost_estimate="high",
        common_scenarios=["ComfyUI图片生成"],
        requirements=["ComfyUI需运行"], limitations=["仅限高级用户"],
        fallback_tools=[],
    ),
}


class ContractRegistry:
    """工具契约注册表 — 管理所有工具的契约声明"""

    def __init__(self):
        self._contracts: dict[str, ToolContract] = {}
        self._by_category: dict[str, list[ToolContract]] = {}
        self._load_builtins()

    def _load_builtins(self):
        for name, contract in BUILTIN_CONTRACTS.items():
            self.register(contract)

    def register(self, contract: ToolContract):
        self._contracts[contract.name] = contract
        if contract.category not in self._by_category:
            self._by_category[contract.category] = []
        self._by_category[contract.category].append(contract)

    def get(self, name: str) -> ToolContract | None:
        return self._contracts.get(name)

    def list_by_tier(self, tier: int) -> list[ToolContract]:
        return [c for c in self._contracts.values() if c.tier == tier]

    def list_by_category(self, category: str) -> list[ToolContract]:
        return self._by_category.get(category, [])

    def suggest_fallback(self, tool_name: str) -> str | None:
        contract = self.get(tool_name)
        if contract and contract.fallback_tools:
            return contract.fallback_tools[0]
        return None


# ─── 任务规划器 ─────────────────────────────────────────────

class TaskPlanner:
    """将意图解析为可执行的任务计划"""

    def __init__(self, contract_registry: ContractRegistry):
        self.contracts = contract_registry

    def plan(self, intent: str, context: dict = None) -> TaskPlan:
        context = context or {}

        # 1. 分析复杂度
        complexity, strategy = ComplexityAnalyzer.analyze(intent, context)

        # 2. 提取步骤
        steps = self._extract_steps(intent, strategy)

        return TaskPlan(
            intent=intent,
            complexity=complexity,
            strategy=strategy,
            steps=steps,
            context=context,
            requires_approval=(complexity == TaskComplexity.CRITICAL),
            estimated_cost=self._estimate_cost(strategy, steps),
        )

    def _extract_steps(self, intent: str, strategy: ExecutionStrategy) -> list[TaskStep]:
        """从意图中提取执行步骤（基于关键词启发式匹配）"""
        if strategy == ExecutionStrategy.DIRECT:
            return [self._intent_to_step(intent)]

        if strategy == ExecutionStrategy.CHAIN:
            return self._decompose_chain(intent)

        if strategy == ExecutionStrategy.SWARM:
            return [TaskStep(
                tool="agent_swarm",
                input={"template": intent, "items": ["auto"]},
                expected_output="multi-agent result",
                timeout=300,
            )]

        return [self._intent_to_step(intent)]

    def _intent_to_step(self, intent: str) -> TaskStep:
        """启发式：从意图匹配最佳工具"""
        intent_lower = intent.lower()

        # 创意类
        if any(k in intent_lower for k in ["生成图片", "画一张", "create image", "generate image"]):
            return TaskStep(tool="generate_image", input={"prompt": intent}, expected_output="image", timeout=120)
        if any(k in intent_lower for k in ["生成视频", "create video", "generate video"]):
            return TaskStep(tool="generate_video", input={"prompt": intent}, expected_output="video", timeout=300)

        # 代码类
        if any(k in intent_lower for k in ["搜索代码", "找代码", "search code"]):
            return TaskStep(tool="search_files", input={"pattern": intent}, expected_output="code matches")
        if any(k in intent_lower for k in ["提交", "commit", "git add"]):
            return TaskStep(tool="git_add_commit", input={"message": intent}, expected_output="commit")
        if any(k in intent_lower for k in ["运行测试", "测试", "run test"]):
            return TaskStep(tool="run_test", input={}, expected_output="test results", timeout=120)

        # 数据类
        if any(k in intent_lower for k in ["查询数据库", "sql", "query db"]):
            return TaskStep(tool="db_query", input={"query": intent}, expected_output="query results")

        # Web类
        if any(k in intent_lower for k in ["搜索", "查资料", "search", "查找"]):
            return TaskStep(tool="web_search", input={"query": intent}, expected_output="search results")
        if any(k in intent_lower for k in ["打开网页", "fetch", "抓取"]):
            return TaskStep(tool="web_fetch", input={"url": intent}, expected_output="page content")

        # 文件操作
        if any(k in intent_lower for k in ["读取文件", "读文件", "read file", "打开文件"]):
            return TaskStep(tool="read_file", input={"path": intent}, expected_output="file content")
        if any(k in intent_lower for k in ["写文件", "创建文件", "write file"]):
            return TaskStep(tool="write_file", input={"path": "output", "content": intent}, expected_output="file written")

        # 默认：使用通用工具
        return TaskStep(tool="trm_route", input={"intent": "think", "prompt": intent}, expected_output="analysis", timeout=60)

    def _decompose_chain(self, intent: str) -> list[TaskStep]:
        """将链式意图分解为有序步骤"""
        # 简单启发式分解
        parts = [p.strip() for p in intent.replace("然后", "||").replace("接着", "||").replace("先", "||").replace("再", "||").split("||") if p.strip()]
        steps = []
        for part in parts:
            steps.append(self._intent_to_step(part))
        return steps

    def _estimate_cost(self, strategy: ExecutionStrategy, steps: list[TaskStep]) -> str:
        high_cost_tools = {"generate_image", "generate_video", "comfyui_submit_workflow",
                          "agent_swarm", "multi_agent"}
        has_high = any(s.tool in high_cost_tools for s in steps)
        if strategy == ExecutionStrategy.SWARM:
            return "high"
        if has_high:
            return "medium"
        return "low"


# ─── 执行引擎 ───────────────────────────────────────────────

class TaskExecutor:
    """执行 TaskPlan，包含失败降级与重试"""

    def __init__(self, contract_registry: ContractRegistry):
        self.contracts = contract_registry
        self.history: list[StepResult] = []

    def execute(self, plan: TaskPlan, tool_executor: callable) -> dict:
        """执行任务计划"""
        results = []
        total_start = time.time()

        for i, step in enumerate(plan.steps):
            step_result = self._execute_step(step, i, tool_executor)
            results.append(step_result)

            if not step_result.success and not step_result.used_fallback:
                logger.warning(f"Step {i} ({step.tool}) failed, attempting fallback...")
                fallback = self.contracts.suggest_fallback(step.tool)
                if fallback:
                    fallback_step = TaskStep(tool=fallback, input=step.input,
                                             expected_output=step.expected_output,
                                             max_retries=1)
                    fallback_result = self._execute_step(fallback_step, i, tool_executor)
                    fallback_result.used_fallback = True
                    results[-1] = fallback_result

        total_duration = int((time.time() - total_start) * 1000)

        # 统计
        success_count = sum(1 for r in results if r.success)
        self.history.extend(results)

        return {
            "plan": plan,
            "results": results,
            "success": all(r.success for r in results),
            "success_rate": success_count / len(results) if results else 1.0,
            "total_duration_ms": total_duration,
        }

    def _execute_step(self, step: TaskStep, index: int, executor: callable) -> StepResult:
        """执行单个步骤，含重试"""
        last_error = None
        for attempt in range(step.max_retries + 1):
            start = time.time()
            try:
                output = executor(step.tool, step.input)
                duration = int((time.time() - start) * 1000)
                return StepResult(
                    step_index=index, tool=step.tool, success=True,
                    output=output, duration_ms=duration,
                )
            except Exception as e:
                last_error = str(e)
                duration = int((time.time() - start) * 1000)
                if attempt < step.max_retries:
                    logger.info(f"Retry {attempt+1}/{step.max_retries} for {step.tool}")
                    time.sleep(1)

        return StepResult(
            step_index=index, tool=step.tool, success=False,
            error=last_error, duration_ms=0,
        )


# ─── 主入口 ─────────────────────────────────────────────────

class TaskGovernor:
    """
    Task Governor — CRUX 治理层

    使用示例：
        governor = TaskGovernor()
        plan = governor.plan("搜索Python异步框架并总结")
        result = governor.execute(plan, my_tool_executor)
    """

    def __init__(self):
        self.contracts = ContractRegistry()
        self.planner = TaskPlanner(self.contracts)
        self.executor = TaskExecutor(self.contracts)

    def plan(self, intent: str, context: dict = None) -> TaskPlan:
        """解析意图为任务计划"""
        return self.planner.plan(intent, context)

    def execute(self, plan: TaskPlan, tool_executor: callable) -> dict:
        """执行任务计划"""
        return self.executor.execute(plan, tool_executor)

    def get_stats(self) -> dict:
        """获取治理层统计"""
        history = self.executor.history
        total = len(history)
        if total == 0:
            return {"total_steps": 0}
        success = sum(1 for r in history if r.success)
        return {
            "total_steps": total,
            "success_rate": round(success / total * 100, 1),
            "fallback_used": sum(1 for r in history if r.used_fallback),
            "avg_duration_ms": sum(r.duration_ms for r in history) / total if total else 0,
        }

    def summarize_execution(self, result: dict) -> str:
        """生成执行摘要"""
        plan = result["plan"]
        success = result["success"]
        rate = result["success_rate"]
        duration = result["total_duration_ms"]

        lines = [
            f"🎯 执行策略: {plan.strategy.value} | 复杂度: {plan.complexity.value}",
            f"{'✅' if success else '⚠️'} 成功率: {rate:.0%} | 耗时: {duration}ms",
            f"📋 步骤: {len(plan.steps)} 步 | 预估成本: {plan.estimated_cost}",
        ]
        return "\n".join(lines)
