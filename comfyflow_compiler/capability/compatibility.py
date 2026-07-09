"""BlueprintCompatibilityMatcher — 蓝图-环境兼容性匹配器

判断蓝图能否在当前 ComfyUI 环境运行，并提供替代方案。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .snapshot import CapabilitySnapshot
from .node_index import NodeIndex
from .model_index import ModelIndex
from .errors import MissingNodeError, MissingModelError


@dataclass
class CompatibilityScore:
    """单个蓝图的兼容性评分"""
    blueprint_id: str
    task_type: str
    display_name: str = ""

    # 评分 (0-1)
    node_score: float = 0.0
    model_score: float = 0.0
    vram_score: float = 1.0
    overall: float = 0.0

    # 详情
    missing_nodes: list[str] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)
    vram_issue: str = ""

    # 替代建议
    available_alternatives: list[str] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return self.overall >= 0.5 and len(self.missing_nodes) == 0 and len(self.missing_models) == 0

    @property
    def summary(self) -> str:
        parts = [f"{'✅' if self.compatible else '⚠️'} {self.display_name or self.blueprint_id} (score={self.overall:.2f})"]
        if self.missing_nodes:
            parts.append(f"   缺失节点: {', '.join(self.missing_nodes)}")
        if self.missing_models:
            parts.append(f"   缺失模型: {', '.join(self.missing_models)}")
        if self.vram_issue:
            parts.append(f"   {self.vram_issue}")
        if self.available_alternatives:
            parts.append(f"   可替代: {', '.join(self.available_alternatives)}")
        return "\n".join(parts)


# 已知节点互替关系
NODE_FALLBACKS: dict[str, list[str]] = {
    "KSampler": ["SamplerCustomAdvanced", "KSamplerAdvanced"],
    "SamplerCustomAdvanced": ["KSampler", "KSamplerAdvanced"],
    "CheckpointLoaderSimple": ["UNETLoader", "DualCLIPLoader"],
    "UNETLoader": ["CheckpointLoaderSimple"],
    "DualCLIPLoader": ["CLIPLoader"],
    "LTXVideoSampler": ["SamplerCustomAdvanced"],
    "VHS_VideoCombine": ["VideoCombine"],
}

# 已知模型互替关系
MODEL_FALLBACKS: dict[str, list[tuple[str, str]]] = {
    "ltx-video-2b-v0.9.safetensors": [("ltx-video-2b-v0.9.safetensors", "checkpoints")],
    "sd_xl_base_1.0.safetensors": [("sd_xl_base_1.0.safetensors", "checkpoints")],
}


class BlueprintCompatibilityMatcher:
    """蓝图兼容性匹配器 — 在能力快照中找到最兼容的蓝图"""

    def __init__(self, snapshot: CapabilitySnapshot | None = None):
        self.snapshot = snapshot or CapabilitySnapshot()

    def set_snapshot(self, snapshot: CapabilitySnapshot):
        self.snapshot = snapshot

    def score(self, blueprint: dict | Any) -> CompatibilityScore:
        """评估单个蓝图与当前环境的兼容性"""
        # 支持新旧两种蓝图格式
        if isinstance(blueprint, dict):
            bid = blueprint.get("id", "unknown")
            task = blueprint.get("capability", {}).get("task_type", "")
            name = blueprint.get("name", bid)
            required_nodes = [r["class_type"] for r in blueprint.get("requirements", {}).get("required_nodes", [])]
            models = blueprint.get("capability", {}).get("models", [])
            req_vram = blueprint.get("validation", {}).get("required_vram_gb", 0)
        else:
            bid = blueprint.name
            task = blueprint.task_type
            name = blueprint.display_name
            required_nodes = blueprint.required_nodes
            models = [{"name": m, "type": 0} for m in blueprint.required_models]
            req_vram = blueprint.min_vram_gb

        score = CompatibilityScore(blueprint_id=bid, task_type=task, display_name=name)

        # 节点兼容性
        present_nodes = 0
        missing_nodes = []
        for ct in required_nodes:
            if self.snapshot.has_node(ct):
                present_nodes += 1
            else:
                missing_nodes.append(ct)
                # 查找替代
                alt = self._find_node_alternative(ct)
                if alt:
                    score.available_alternatives.append(alt)

        score.node_score = present_nodes / max(len(required_nodes), 1)
        score.missing_nodes = missing_nodes

        # 模型兼容性
        present_models = 0
        missing_models = []
        for m in models:
            mname = m["name"] if isinstance(m, dict) else m
            if self.snapshot.has_model(mname):
                present_models += 1
            else:
                missing_models.append(mname)

        score.model_score = present_models / max(len(models), 1)
        score.missing_models = missing_models

        # VRAM 兼容性
        if req_vram > 0 and self.snapshot.system:
            vram = self.snapshot.system.get("device", {}).get("vram_total_gb", 0)
            if vram and req_vram > vram:
                score.vram_score = vram / req_vram
                score.vram_issue = f"需要 {req_vram}GB VRAM，当前 {vram}GB"

        # 综合评分
        score.overall = (
            score.node_score * 0.5 +
            score.model_score * 0.3 +
            score.vram_score * 0.2
        )

        return score

    def rank(self, blueprints: list[dict | Any]) -> list[CompatibilityScore]:
        """对多个蓝图排序，返回兼容性从高到低"""
        scored = [self.score(bp) for bp in blueprints]
        scored.sort(key=lambda s: (-s.overall, -s.node_score, -s.model_score))
        return scored

    def best(self, blueprints: list[dict | Any]) -> tuple[Optional[CompatibilityScore], int]:
        """返回最佳兼容蓝图及其索引"""
        if not blueprints:
            return None, -1
        scored = self.rank(blueprints)
        if scored and scored[0].compatible:
            for i, bp in enumerate(blueprints):
                bid = bp["id"] if isinstance(bp, dict) else bp.name
                if bid == scored[0].blueprint_id:
                    return scored[0], i
        return scored[0] if scored else None, 0

    def find_fallback(self, blueprint: dict | Any,
                      candidates: list[dict | Any]) -> Optional[CompatibilityScore]:
        """为不可用的蓝图找可用替代"""
        score = self.score(blueprint)
        if score.compatible:
            return score

        ranked = self.rank(candidates)
        compatible = [s for s in ranked if s.compatible and s.blueprint_id != score.blueprint_id]
        return compatible[0] if compatible else None

    def _find_node_alternative(self, class_type: str) -> str:
        """查找缺失节点的可用替代"""
        fallbacks = NODE_FALLBACKS.get(class_type, [])
        for alt in fallbacks:
            if self.snapshot.has_node(alt):
                # 检查替代节点是否在已知节点中
                return alt
        return ""
