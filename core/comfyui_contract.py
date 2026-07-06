"""ComfyUI Tool Contract — CWIM 原则的工具契约层 (A-step)

给每个 ComfyUI 工具增加契约，在工具执行前自动检查 CWIM 原则合规性。

Tool Contract = {pre_conditions, post_conditions, side_effects, failure_policy}

参考: COMFYUI_METHODOLOGY.md 全部 10 条原则
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 契约定义类型
# ═══════════════════════════════════════════════════════════════════

class PrincipleID(Enum):
    """CWIM 原则编号映射。"""
    P1_UNDERSTAND_FIRST = "P1"     # 先理解任务再决定方案
    P2_REUSE_FIRST = "P2"          # 优先复用成熟模板
    P3_IR_NOT_JSON = "P3"          # LLM → TaskSpec → WorkflowIR → Compiler
    P4_VALIDATOR_GATE = "P4"       # 所有 workflow 必须经过 Validator
    P5_FAILURE_LEARN = "P5"        # 失败不是结束而是学习
    P6_PARAM_SEMANTIC = "P6"       # 参数是语义不是数字
    P7_EXPLAINABLE = "P7"          # 所有推荐必须可解释
    P8_LORA_AS_PROJECT = "P8"      # LoRA 是项目不是文件
    P9_WORKFLOW_AS_GRAPH = "P9"    # Workflow 是图不是 JSON
    P10_TASK_NOT_NODE = "P10"      # 用户面对任务不是节点


@dataclass
class PreCondition:
    """前置条件 — 调用前必须满足。"""
    principle: PrincipleID
    check: str                    # 检查逻辑描述
    required: bool = True         # True=硬性, False=建议
    error_message: str = ""       # 不满足时的提示


@dataclass
class PostCondition:
    """后置条件 — 执行后必须满足。"""
    principle: PrincipleID
    check: str
    required: bool = True


@dataclass
class SideEffect:
    """副作用声明。"""
    description: str
    type: str  # write_file / network_call / install / execute / none
    irreversible: bool = False


@dataclass
class FailurePolicy:
    """失败策略。"""
    max_retries: int = 0
    auto_recover: bool = False
    user_message: str = "操作失败，请检查输入后重试"


@dataclass
class ToolContract:
    """完整工具契约。"""
    tool_name: str
    description: str
    principles: list[str]        # 应用的原则列表
    pre_conditions: list[PreCondition] = field(default_factory=list)
    post_conditions: list[PostCondition] = field(default_factory=list)
    side_effects: list[SideEffect] = field(default_factory=list)
    failure_policy: FailurePolicy = field(default_factory=FailurePolicy)
    check_methodology: bool = True  # 是否在工具前检查方法论

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "description": self.description,
            "principles": self.principles,
            "pre_conditions": [
                {"principle": p.principle.value, "check": p.check, "required": p.required}
                for p in self.pre_conditions
            ],
            "post_conditions": [
                {"principle": p.principle.value, "check": p.check, "required": p.required}
                for p in self.post_conditions
            ],
            "side_effects": [
                {"description": s.description, "type": s.type, "irreversible": s.irreversible}
                for s in self.side_effects
            ],
            "failure_policy": {
                "max_retries": self.failure_policy.max_retries,
                "auto_recover": self.failure_policy.auto_recover,
                "user_message": self.failure_policy.user_message,
            },
            "check_methodology": self.check_methodology,
        }


# ═══════════════════════════════════════════════════════════════════
# 契约检查器
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ContractCheckResult:
    """契约检查结果。"""
    passed: bool
    tool_name: str
    pre_ok: list[str] = field(default_factory=list)
    pre_fail: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    message: str = ""


class ContractChecker:
    """工具契约检查器 — 执行前自动检查。"""

    def __init__(self, contracts: dict[str, ToolContract] | None = None):
        self._contracts = contracts or {}

    def register(self, contract: ToolContract):
        self._contracts[contract.tool_name] = contract

    def check(self, tool_name: str, **kwargs) -> ContractCheckResult:
        """执行前检查契约。"""
        contract = self._contracts.get(tool_name)
        if not contract:
            return ContractCheckResult(passed=True, tool_name=tool_name,
                                       message="未找到契约定义")

        pre_ok: list[str] = []
        pre_fail: list[str] = []
        warnings: list[str] = []

        for cond in contract.pre_conditions:
            result = self._evaluate_condition(cond, kwargs)
            if result["ok"]:
                pre_ok.append(cond.check)
            else:
                if cond.required:
                    pre_fail.append(f"[{cond.principle.value}] {cond.error_message or cond.check}")
                else:
                    warnings.append(f"[{cond.principle.value}] 建议: {cond.check}")

        # 原则 4 特殊检查: Validator 门禁
        if contract.check_methodology and not pre_fail:
            principle_check = self._check_principles(contract, kwargs)
            pre_ok.extend(principle_check["ok"])
            warnings.extend(principle_check["warnings"])

        passed = len(pre_fail) == 0
        msg_parts = []
        if pre_ok:
            msg_parts.append(f"✅ {len(pre_ok)} 项前置检查通过")
        if pre_fail:
            msg_parts.append(f"❌ {len(pre_fail)} 项前置检查失败")
        if warnings:
            msg_parts.append(f"⚠️ {len(warnings)} 项建议")

        return ContractCheckResult(
            passed=passed,
            tool_name=tool_name,
            pre_ok=pre_ok,
            pre_fail=pre_fail,
            warnings=warnings,
            message=" | ".join(msg_parts),
        )

    def _evaluate_condition(self, cond: PreCondition, kwargs: dict) -> dict:
        """评估单个前置条件。"""
        check = cond.check
        p = cond.principle

        # P4: 需要 workflow 经过 Validator
        if p == PrincipleID.P4_VALIDATOR_GATE and "validate" in check.lower():
            return {"ok": True}  # 软检查，实际由工具自行保证

        # P1: 先理解任务
        if p == PrincipleID.P1_UNDERSTAND_FIRST and "prompt" in check.lower():
            has_prompt = bool(kwargs.get("prompt") or kwargs.get("intent"))
            return {"ok": has_prompt, "reason": "缺少 prompt/intent"}

        # P10: 用户面对任务
        if p == PrincipleID.P10_TASK_NOT_NODE:
            has_task_level_input = bool(
                kwargs.get("prompt") or kwargs.get("intent") or kwargs.get("task_type")
            )
            has_node_level_input = bool(
                kwargs.get("workflow_json") or kwargs.get("node_id")
            )
            if has_node_level_input and not has_task_level_input:
                return {"ok": False, "reason": "用户不应直接面对节点参数"}
            return {"ok": True}

        # P3: 使用 IR 而非直接 JSON
        if p == PrincipleID.P3_IR_NOT_JSON:
            return {"ok": True}

        # P5: 失败学习 — 检查是否有 validation_report
        if p == PrincipleID.P5_FAILURE_LEARN and "Validator 报告" in check:
            has_report = bool(kwargs.get("validation_report"))
            return {"ok": has_report, "reason": "缺少 validation_report"}

        # 通用参数检查: 检查 check 中提到的参数名是否在 kwargs 中
        # 格式如 "需要 xxx 参数" 或 "workflow_json"
        for kw_key in ["workflow_json", "prompt", "validation_report"]:
            if kw_key in check.lower() or f"需要 {kw_key}" in check:
                has_value = bool(kwargs.get(kw_key))
                if not has_value:
                    return {"ok": False, "reason": f"缺少必需参数: {kw_key}"}
                return {"ok": True}

        # 默认通过
        return {"ok": True}

    def _check_principles(self, contract: ToolContract, kwargs: dict) -> dict:
        """检查方法论原则合规性。"""
        ok: list[str] = []
        warnings: list[str] = []

        # P10: 用户面对任务
        principle_ids = {PrincipleID[p] for p in contract.principles if hasattr(PrincipleID, p)}
        if PrincipleID.P10_TASK_NOT_NODE in principle_ids:
            has_task = bool(kwargs.get("prompt") or kwargs.get("intent"))
            if has_task:
                ok.append("P10: 用户面对任务 ✓")
            else:
                warnings.append("P10: 建议使用任务级参数")

        return {"ok": ok, "warnings": warnings}


# ═══════════════════════════════════════════════════════════════════
# 内置契约定义
# ═══════════════════════════════════════════════════════════════════

def build_contracts() -> dict[str, ToolContract]:
    """构建所有 ComfyUI 工具的契约。"""
    contracts: dict[str, ToolContract] = {}

    # ── compile_and_validate ──
    contracts["comfyui_compile_and_validate"] = ToolContract(
        tool_name="comfyui_compile_and_validate",
        description="CWIM C-step: TaskSpec → Compile → Validate 一条龙",
        principles=["P1", "P3", "P4", "P6", "P7", "P10"],
        pre_conditions=[
            PreCondition(PrincipleID.P1_UNDERSTAND_FIRST, "需要 prompt 或 intent", required=True,
                         error_message="必须先理解任务目标"),
            PreCondition(PrincipleID.P10_TASK_NOT_NODE, "使用任务级输入", required=True,
                         error_message="应使用 prompt/task_type 而非直接传 workflow"),
            PreCondition(PrincipleID.P3_IR_NOT_JSON, "LLM 输出 TaskSpec", required=True,
                         error_message="不应直接生成 ComfyUI JSON"),
        ],
        post_conditions=[
            PostCondition(PrincipleID.P4_VALIDATOR_GATE, "输出必须经过 Validator", required=True),
            PostCondition(PrincipleID.P7_EXPLAINABLE, "必须返回可解释的摘要", required=True),
        ],
        side_effects=[SideEffect("编译工作流内存中", "none")],
        failure_policy=FailurePolicy(max_retries=1, auto_recover=False,
                                     user_message="编译失败，请检查输入参数"),
    )

    # ── validate_workflow ──
    contracts["comfyui_validate_workflow"] = ToolContract(
        tool_name="comfyui_validate_workflow",
        description="CWIM 原则4: 对 workflow 执行 5 层校验",
        principles=["P4", "P9"],
        pre_conditions=[
            PreCondition(PrincipleID.P9_WORKFLOW_AS_GRAPH, "workflow 必须是 dict", required=True,
                         error_message="输入必须是 dict 格式的 workflow"),
        ],
        post_conditions=[
            PostCondition(PrincipleID.P4_VALIDATOR_GATE, "必须返回 L1-L5 各层结果", required=True),
        ],
        side_effects=[SideEffect("只读校验，不修改任何数据", "none")],
        failure_policy=FailurePolicy(max_retries=0, auto_recover=False,
                                     user_message="校验执行异常"),
    )

    # ── recover_workflow ──
    contracts["comfyui_recover_workflow"] = ToolContract(
        tool_name="comfyui_recover_workflow",
        description="CWIM 原则5: 对校验失败的 workflow 执行自动恢复",
        principles=["P5"],
        pre_conditions=[
            PreCondition(PrincipleID.P5_FAILURE_LEARN, "必须有 Validator 报告", required=True,
                         error_message="恢复前必须先执行校验"),
        ],
        post_conditions=[
            PostCondition(PrincipleID.P5_FAILURE_LEARN, "失败必须记录到知识库", required=True),
        ],
        side_effects=[SideEffect("可能修改 workflow 结构", "none")],
        failure_policy=FailurePolicy(max_retries=2, auto_recover=False,
                                     user_message="自动恢复失败，请检查 workflow"),
    )

    # ── build_workflow ──
    contracts["comfyui_build_workflow"] = ToolContract(
        tool_name="comfyui_build_workflow",
        description="构建 ComfyUI 工作流",
        principles=["P1", "P2", "P3", "P10"],
        pre_conditions=[
            PreCondition(PrincipleID.P1_UNDERSTAND_FIRST, "需要 prompt 描述", required=True,
                         error_message="需要提供任务描述"),
            PreCondition(PrincipleID.P10_TASK_NOT_NODE, "使用任务级描述而非节点级", required=False,
                         error_message="建议使用任务描述（如'生成赛博朋克城市'）而非节点名"),
        ],
        post_conditions=[
            PostCondition(PrincipleID.P3_IR_NOT_JSON, "应通过 IR 编译而非直接生成 JSON", required=False),
        ],
        side_effects=[SideEffect("构建工作流到内存", "none")],
    )

    # ── execute_workflow (submit) ──
    contracts["comfyui_submit_workflow"] = ToolContract(
        tool_name="comfyui_submit_workflow",
        description="提交 workflow 到 ComfyUI 执行",
        principles=["P4", "P5"],
        pre_conditions=[
            PreCondition(PrincipleID.P4_VALIDATOR_GATE, "需要 workflow_json 参数", required=True,
                         error_message="必须提供 workflow_json"),
            PreCondition(PrincipleID.P4_VALIDATOR_GATE, "workflow 必须经过 Validator", required=False,
                         error_message="建议先执行 validate_workflow"),
            PreCondition(PrincipleID.P5_FAILURE_LEARN, "失败应进入恢复流程", required=True,
                         error_message="执行失败应调用 recover_workflow"),
        ],
        side_effects=[SideEffect("提交到 ComfyUI 远程服务", "network_call")],
        failure_policy=FailurePolicy(max_retries=2, auto_recover=True,
                                     user_message="执行失败，已尝试自动恢复"),
    )

    # ── error_kb_query ──
    contracts["comfyui_error_kb_query"] = ToolContract(
        tool_name="comfyui_error_kb_query",
        description="查询错误知识库",
        principles=["P5"],
        side_effects=[SideEffect("只读查询", "none")],
    )

    return contracts


# ═══════════════════════════════════════════════════════════════════
# 全局实例
# ═══════════════════════════════════════════════════════════════════

DEFAULT_CONTRACTS = build_contracts()
DEFAULT_CHECKER = ContractChecker(DEFAULT_CONTRACTS)


def check_tool_contract(tool_name: str, **kwargs) -> ContractCheckResult:
    """快捷函数：检查工具契约。"""
    return DEFAULT_CHECKER.check(tool_name, **kwargs)
