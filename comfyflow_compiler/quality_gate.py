"""ComfyFlow Compiler — 质量门"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from .models import TaskSpec, Blueprint, QualityReport, EnvironmentProfile, RuntimeBudget


def evaluate_quality(
    workflow: Dict[str, Any],
    task: TaskSpec,
    blueprint: Optional[Blueprint],
    env: EnvironmentProfile,
    budget: RuntimeBudget,
) -> QualityReport:
    """
    多维度质量评估。

    评分维度：
    - topology_score: 拓扑结构是否完整合法
    - task_fit_score: 是否匹配用户任务
    - model_fit_score: 模型是否合适且存在
    - param_quality_score: 参数设置是否合理
    - environment_score: 环境兼容性
    - reproducibility_score: 可复现性
    - ux_score: 用户体验友好度
    """
    report = QualityReport()
    details = {}

    # 1. 拓扑检查
    topology_score = _check_topology(workflow)
    details["topology"] = topology_score

    # 2. 任务匹配度
    task_fit = _check_task_fit(workflow, task)
    details["task_fit"] = task_fit

    # 3. 模型适配
    model_fit = _check_model_fit(workflow, env)
    details["model_fit"] = model_fit

    # 4. 参数质量
    param_quality = _check_param_quality(workflow, task)
    details["param_quality"] = param_quality

    # 5. 环境兼容性
    env_score = _check_environment(workflow, env)
    details["environment"] = env_score

    # 6. 可复现性
    repro_score = _check_reproducibility(workflow)
    details["reproducibility"] = repro_score

    # 7. UX 得分
    ux_score = _check_ux(workflow)
    details["ux"] = ux_score

    # 计算总分
    weights = {
        "topology": 0.20,
        "task_fit": 0.15,
        "model_fit": 0.15,
        "param_quality": 0.15,
        "environment": 0.15,
        "reproducibility": 0.10,
        "ux": 0.10,
    }
    total = sum(details[k] * weights.get(k, 0) for k in details)
    total = min(1.0, max(0.0, total))

    report.overall_score = round(total, 3)
    report.detail = details
    report.passed = total >= 0.5

    # 生成警告和错误
    if total < 0.5:
        report.errors.append("工作流质量评分低于阈值")
    if topology_score < 0.8:
        report.warnings.append("拓扑结构不完整，可能存在缺失连接")
    if model_fit < 0.5:
        report.warnings.append("部分模型在本机不可用，使用了替代方案")
    if param_quality < 0.6:
        report.warnings.append("部分参数使用默认值，未完全优化")

    report.user_friendly_message = _generate_user_summary(report, task)
    return report


def _check_topology(workflow: Dict[str, Any]) -> float:
    """检查工作流拓扑完整性"""
    if not workflow:
        return 0.0

    # 必须有 SaveImage 输出节点
    has_output = any(n["class_type"] == "SaveImage" for n in workflow.values())
    if not has_output:
        return 0.3

    # 必须有采样器
    has_sampler = any("Sampler" in n["class_type"] for n in workflow.values())
    if not has_sampler:
        return 0.2

    # 检查引用链完整性
    all_refs = set()
    defined_ids = set(workflow.keys())
    for node_id, node in workflow.items():
        for key, val in node["inputs"].items():
            if isinstance(val, (list, tuple)) and len(val) == 2:
                all_refs.add(str(val[0]))

    missing_refs = all_refs - defined_ids
    if missing_refs:
        return 0.5

    score = 1.0
    if has_output and has_sampler:
        score = 1.0
    return score


def _check_task_fit(workflow: Dict[str, Any], task: TaskSpec) -> float:
    """检查工作流是否匹配用户任务"""
    score = 0.5  # 基础分

    for node in workflow.values():
        ct = node["class_type"]

    # img2img 需要 LoadImage
    if task.task_type == "img2img":
        has_load = any(n["class_type"] == "LoadImage" for n in workflow.values())
        has_vae_encode = any(n["class_type"] == "VAEEncode" for n in workflow.values())
        if has_load and has_vae_encode:
            score += 0.3
        else:
            score -= 0.2

    # 高清模式需要 upscale
    if task.needs_upscale:
        has_upscale = any(n["class_type"] in ("UpscaleModelLoader", "ImageUpscaleWithModel")
                          for n in workflow.values())
        if has_upscale:
            score += 0.2

    return min(1.0, max(0.0, score))


def _check_model_fit(workflow: Dict[str, Any], env: EnvironmentProfile) -> float:
    """检查模型是否在本机可用"""
    score = 1.0
    for node in workflow.values():
        if node["class_type"] == "CheckpointLoaderSimple":
            ckpt_name = node["inputs"].get("ckpt_name", "")
            if ckpt_name and ckpt_name not in env.checkpoints:
                score -= 0.3
    return max(0.1, score)


def _check_param_quality(workflow: Dict[str, Any], task: TaskSpec) -> float:
    """检查参数质量"""
    score = 1.0
    for node in workflow.values():
        if "Sampler" in node["class_type"]:
            inputs = node["inputs"]
            if inputs.get("steps", 0) < 10:
                score -= 0.3
            if inputs.get("cfg", 0) < 3 or inputs.get("cfg", 0) > 20:
                score -= 0.2
    return max(0.0, score)


def _check_environment(workflow: Dict[str, Any], env: EnvironmentProfile) -> float:
    """检查环境兼容性"""
    score = 1.0
    for node in workflow.values():
        ct = node["class_type"]
        # 检查 ControlNet 相关节点
        if "ControlNet" in ct and not env.controlnet_models:
            score -= 0.2
    return max(0.0, score)


def _check_reproducibility(workflow: Dict[str, Any]) -> float:
    """检查可复现性"""
    has_seed = False
    for node in workflow.values():
        inputs = node.get("inputs", {})
        if "seed" in inputs:
            has_seed = True
            break
    return 1.0 if has_seed else 0.5


def _check_ux(workflow: Dict[str, Any]) -> float:
    """检查 UX 友好度"""
    score = 1.0
    # 检查文件名前缀是否友好
    for node in workflow.values():
        if node["class_type"] == "SaveImage":
            prefix = node["inputs"].get("filename_prefix", "")
            if not prefix or prefix == "":
                score -= 0.2
    return score


def _generate_user_summary(report: QualityReport, task: TaskSpec) -> str:
    """生成用户友好的总结"""
    score_pct = round(report.overall_score * 100)
    if score_pct >= 85:
        return f"✅ 工作流质量优秀 ({score_pct}分)，已准备就绪，拖入 ComfyUI 即可运行！"
    elif score_pct >= 65:
        return f"👍 工作流质量良好 ({score_pct}分)，可以正常使用。"
    elif score_pct >= 50:
        return f"⚠️ 工作流质量一般 ({score_pct}分)，可以运行但建议检查。"
    else:
        return f"❌ 工作流质量不足 ({score_pct}分)，请重试或降低需求级别。"
