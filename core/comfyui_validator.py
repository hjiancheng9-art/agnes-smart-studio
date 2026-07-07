"""ComfyUI Validator — 5 层校验 (CWIM 原则 4 实现)

所有 workflow 必须经过 Validator 才能执行。

层级：
    L1 JSON 结构校验
    L2 ComfyUI 节点 schema 校验
    L3 图拓扑校验
    L4 运行时资源校验
    L5 业务语义校验

参考: COMFYUI_METHODOLOGY.md 原则 4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 校验结果类型
# ═══════════════════════════════════════════════════════════════════


@dataclass
class ValidationIssue:
    level: str  # error / warning / info
    layer: str  # L1 / L2 / L3 / L4 / L5
    message: str
    node_id: str | None = None
    fix_hint: str | None = None


@dataclass
class ValidationResult:
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    patch_suggestions: list[dict] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def add_error(self, layer: str, message: str, node_id: str | None = None, fix_hint: str | None = None):
        self.issues.append(ValidationIssue("error", layer, message, node_id, fix_hint))
        self.is_valid = False

    def add_warning(self, layer: str, message: str, node_id: str | None = None, fix_hint: str | None = None):
        self.issues.append(ValidationIssue("warning", layer, message, node_id, fix_hint))

    def add_info(self, layer: str, message: str, node_id: str | None = None):
        self.issues.append(ValidationIssue("info", layer, message, node_id))


# ═══════════════════════════════════════════════════════════════════
# 5 层 Validator
# ═══════════════════════════════════════════════════════════════════


class ComfyUIValidator:
    """ComfyUI Workflow 5 层校验器。"""

    def __init__(self, node_ontology: dict | None = None, model_inventory: dict | None = None):
        self._ontology = node_ontology or {}
        self._models = model_inventory or {}

    def validate(self, workflow: dict) -> ValidationResult:
        """执行 5 层校验。"""
        result = ValidationResult(is_valid=True)

        self._validate_l1(workflow, result)
        if not result.is_valid:
            return result  # L1 失败不继续

        self._validate_l2(workflow, result)
        if not result.is_valid:
            return result  # L2 失败不继续

        self._validate_l3(workflow, result)
        self._validate_l4(workflow, result)
        self._validate_l5(workflow, result)

        return result

    # ── L1: JSON 结构校验 ──

    def _validate_l1(self, workflow: dict, result: ValidationResult):
        """L1: 检查 ComfyUI workflow 是否是合法 API 格式。"""
        if not isinstance(workflow, dict):
            result.add_error("L1", "Workflow 必须是 dict")
            return
        if not workflow:
            result.add_error("L1", "Workflow 不能为空")
            return

        for node_id, node in workflow.items():
            if not isinstance(node_id, str):
                result.add_error("L1", f"节点 key 必须是字符串: {node_id}")
            if not isinstance(node, dict):
                result.add_error("L1", "节点值必须是 dict", node_id=node_id)
                continue
            if "class_type" not in node:
                result.add_error("L1", "节点缺少 class_type", node_id=node_id)
            if "inputs" not in node:
                result.add_error("L1", "节点缺少 inputs", node_id=node_id)
            if not isinstance(node.get("inputs"), dict):
                result.add_error("L1", "inputs 必须是 dict", node_id=node_id)

        # 检查连接格式
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            for input_name, input_value in inputs.items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    src_id, src_idx = input_value
                    if str(src_id) not in workflow:
                        result.add_error(
                            "L1",
                            f"连接引用了不存在的节点 {src_id}",
                            node_id=node_id,
                            fix_hint=f"检查 {input_name} 连接的源节点",
                        )

    # ── L2: 节点 schema 校验 ──

    def _validate_l2(self, workflow: dict, result: ValidationResult):
        """L2: 检查节点类型是否已知，输入是否匹配 schema。"""
        if not self._ontology:
            result.add_warning("L2", "节点本体未加载，跳过 L2 校验")
            return

        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            if class_type not in self._ontology:
                result.add_warning(
                    "L2", f"节点类型不在本体中: {class_type}", node_id=node_id, fix_hint="安装缺失的自定义节点"
                )

            # 检查必需输入
            node_info = self._ontology.get(class_type, {})
            required_inputs = node_info.get("input", {}).get("required", {})
            actual_inputs = node.get("inputs", {})

            for req_name in required_inputs:
                if req_name not in actual_inputs:
                    result.add_error(
                        "L2",
                        f"缺少必需输入: {req_name}",
                        node_id=node_id,
                        fix_hint=f"为 {class_type} 添加 {req_name} 输入",
                    )

    # ── L3: 图拓扑校验 ──

    def _validate_l3(self, workflow: dict, result: ValidationResult):
        """L3: 检查图的连通性、孤立节点、循环引用。"""
        # 构建入度
        in_degree: dict[str, int] = dict.fromkeys(workflow, 0)
        edges: list[tuple[str, str]] = []

        for node_id, node in workflow.items():
            for _input_name, input_value in node.get("inputs", {}).items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    src_id = str(input_value[0])
                    in_degree[node_id] += 1
                    edges.append((src_id, node_id))

        # 孤立节点检测
        for node_id, _deg in in_degree.items():
            inputs = workflow[node_id].get("inputs", {})
            has_output_connections = any(
                str(input_value[0]) == node_id
                for other in workflow.values()
                for input_value in other.get("inputs", {}).values()
                if isinstance(input_value, list) and len(input_value) == 2
            )
            has_input_connections = any(isinstance(v, list) and len(v) == 2 for v in inputs.values())
            node_type = workflow[node_id].get("class_type", "")
            # 不是 SaveImage/VHS 等输出节点，但没有连接
            is_output_node = node_type in ("SaveImage", "PreviewImage", "VHS_VideoCombine")

            if not has_input_connections and not has_output_connections and not is_output_node:
                result.add_warning(
                    "L3", "孤立节点（无连接）", node_id=node_id, fix_hint=f"连接 {node_id} 到其他节点或删除它"
                )

        # 死端检测
        dead_ends = []
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            has_outgoing = any(
                str(input_value[0]) == node_id
                for other in workflow.values()
                for input_value in other.get("inputs", {}).values()
                if isinstance(input_value, list) and len(input_value) == 2
            )
            node_type = workflow[node_id].get("class_type", "")
            if not has_outgoing and node_type not in ("SaveImage", "PreviewImage", "VHS_VideoCombine"):
                dead_ends.append(node_id)

        if dead_ends:
            for de in dead_ends:
                result.add_warning("L3", "死端节点（有输入无输出）", node_id=de)

    # ── L4: 运行时资源校验 ──

    def _validate_l4(self, workflow: dict, result: ValidationResult):
        """L4: 检查显存、模型可用性等运行时约束。"""
        # 检查引用的模型
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            for input_name, input_value in inputs.items():
                if isinstance(input_value, str) and input_name in (
                    "ckpt_name",
                    "lora_name",
                    "vae_name",
                    "controlnet_name",
                    "upscale_model",
                ) and input_value and input_value not in self._models:
                    result.add_warning("L4", f"引用的模型可能不可用: {input_value}", node_id=node_id)

        # 检查潜在显存问题
        for node_id, node in workflow.items():
            inputs = node.get("inputs", {})
            if "batch_size" in inputs:
                try:
                    bs = int(inputs["batch_size"])
                    if bs > 4:
                        result.add_warning(
                            "L4", f"batch_size={bs} 可能超出显存", node_id=node_id, fix_hint="减小 batch_size 到 1-4"
                        )
                except (ValueError, TypeError):
                    pass

    # ── L5: 业务语义校验 ──

    def _validate_l5(self, workflow: dict, result: ValidationResult):
        """L5: 检查业务语义 — 是否有基本生成链路。"""
        # 检查基本的 encode+sample+decode 链路
        has_checkpoint = any(n.get("class_type", "").startswith("Checkpoint") for n in workflow.values())
        has_sampler = any(n.get("class_type", "") in ("KSampler", "KSamplerAdvanced") for n in workflow.values())
        has_output = any(
            n.get("class_type", "") in ("SaveImage", "PreviewImage", "VHS_VideoCombine") for n in workflow.values()
        )

        if not has_checkpoint and not has_sampler:
            result.add_info("L5", "无模型加载器+采样器 — 可能是非标准 workflow")
        if not has_output:
            result.add_warning("L5", "无输出节点 — 结果不会保存")


# ═══════════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════════


def validate_workflow(
    workflow: dict, node_ontology: dict | None = None, model_inventory: dict | None = None
) -> ValidationResult:
    """验证 ComfyUI workflow 并返回结果。"""
    validator = ComfyUIValidator(node_ontology, model_inventory)
    return validator.validate(workflow)
