"""Motif Schema v1 — CWIM 原则 9 的 Motif 数据模型与注册表 (B1)

根据 GPT 的 B1 方案：
- Motif 是工作流子图模式，不是模板
- 每个 Motif 有 canonical_hash 用于去重
- source_templates 记录来源
- param_ranges 约束可调参数范围
- quality_score / pass_rate 用于准入

参考: COMFYUI_METHODOLOGY.md 原则 9 (Workflow 是图不是 JSON)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Motif Schema v1
# ═══════════════════════════════════════════════════════════════════

ParamRange = dict[str, Any]  # {"min": X, "max": Y, "default": Z, "type": "int|float|choice"}


@dataclass
class MotifPort:
    """Motif 端口。"""

    name: str
    data_type: str  # MODEL / CLIP / VAE / LATENT / IMAGE / CONDITIONING / VIDEO
    direction: str  # "input" | "output"
    description: str = ""


@dataclass
class MotifNode:
    """Motif 中的节点模板。"""

    role: str  # 语义角色
    class_type: str  # ComfyUI 节点类名
    params: dict = field(default_factory=dict)  # 固定参数
    param_ranges: dict[str, ParamRange] = field(default_factory=dict)  # 可调参数范围
    optional: bool = False  # 是否可选
    model_family: str | None = None  # 模型族


@dataclass
class MotifEdge:
    """Motif 中的连接模板。"""

    from_node: str
    from_port: str
    to_node: str
    to_port: str
    data_type: str = "LATENT"


@dataclass
class MotifDefinition:
    """Motif Schema v1 — 工作流子图模式定义。

    关键区别 vs 旧 BUILTIN_MOTIFS：
    - canonical_hash: 内容去重
    - source_templates: 来源追踪
    - param_ranges: 参数范围约束
    - quality_score: 质量控制
    - edges: 明确图结构而非隐式连接
    """

    motif_id: str
    name: str
    description: str
    category: str  # loader / encoder / sampler / decoder / output / pipeline
    task_types: list[str]  # 适用任务类型: txt2img / img2img / video ...

    nodes: list[MotifNode] = field(default_factory=list)
    edges: list[MotifEdge] = field(default_factory=list)
    ports: list[MotifPort] = field(default_factory=list)

    # 质量控制
    canonical_hash: str = ""
    source_templates: list[str] = field(default_factory=list)
    quality_score: float = 0.8  # 0-1 质量评分
    pass_rate: float = 1.0  # 回放通过率

    # 约束
    compatible_models: list[str] = field(default_factory=list)
    incompatible_nodes: list[str] = field(default_factory=list)
    min_vram_gb: int = 8

    # 参数范围
    param_ranges: dict[str, ParamRange] = field(default_factory=dict)

    version: str = "1.0.0"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.canonical_hash:
            self.canonical_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """根据内容计算去重 hash。"""
        content = json.dumps(
            {
                "nodes": [{"role": n.role, "class_type": n.class_type} for n in self.nodes],
                "edges": [{"from": e.from_node, "to": e.to_node} for e in self.edges],
                "category": self.category,
                "task_types": sorted(self.task_types),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "motif_id": self.motif_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "task_types": self.task_types,
            "nodes": [
                {
                    "role": n.role,
                    "class_type": n.class_type,
                    "param_ranges": {k: v for k, v in n.param_ranges.items()},
                    "optional": n.optional,
                }
                for n in self.nodes
            ],
            "edges": [{"from": f"{e.from_node}.{e.from_port}", "to": f"{e.to_node}.{e.to_port}"} for e in self.edges],
            "canonical_hash": self.canonical_hash,
            "quality_score": self.quality_score,
            "pass_rate": self.pass_rate,
            "source_templates": self.source_templates,
            "compatible_models": self.compatible_models,
            "min_vram_gb": self.min_vram_gb,
            "version": self.version,
        }


# ═══════════════════════════════════════════════════════════════════
# MotifRegistry — Motif 注册表
# ═══════════════════════════════════════════════════════════════════


class MotifRegistry:
    """Motif 注册表 — 管理、查询、去重、准入门禁。"""

    def __init__(self):
        self._motifs: dict[str, MotifDefinition] = {}
        self._hashes: dict[str, str] = {}  # canonical_hash → motif_id

    def register(self, motif: MotifDefinition, source: str = "manual") -> bool:
        """注册 Motif，自动去重。"""
        # 去重检查
        existing = self._hashes.get(motif.canonical_hash)
        if existing:
            logger.info(f"Motif {motif.motif_id} 与已有 {existing} 重复，跳过")
            return False

        # 准入检查
        if motif.quality_score < 0.5:
            logger.warning(f"Motif {motif.motif_id} 质量评分 {motif.quality_score} 低于准入线 0.5")
            return False

        self._motifs[motif.motif_id] = motif
        self._hashes[motif.canonical_hash] = motif.motif_id
        logger.info(f"注册 Motif: {motif.motif_id} ({motif.name}) [{motif.category}] hash={motif.canonical_hash}")
        return True

    def register_many(self, motifs: list[MotifDefinition]) -> tuple[int, int]:
        """批量注册，返回 (成功数, 总数)。"""
        ok = 0
        for m in motifs:
            if self.register(m):
                ok += 1
        return ok, len(motifs)

    def get(self, motif_id: str) -> MotifDefinition | None:
        return self._motifs.get(motif_id)

    def find_by_hash(self, hash_str: str) -> MotifDefinition | None:
        mid = self._hashes.get(hash_str)
        return self._motifs.get(mid) if mid else None

    def find_by_category(self, category: str) -> list[MotifDefinition]:
        return [m for m in self._motifs.values() if m.category == category]

    def find_by_task(self, task_type: str) -> list[MotifDefinition]:
        """按任务类型查找。"""
        return [m for m in self._motifs.values() if task_type in m.task_types]

    def find_compatible(
        self, task_type: str, model: str | None = None, vram_gb: int | None = None
    ) -> list[MotifDefinition]:
        """查找兼容的 Motif。"""
        results = []
        for m in self._motifs.values():
            if task_type not in m.task_types:
                continue
            if model and m.compatible_models and model not in m.compatible_models:
                continue
            if vram_gb and m.min_vram_gb > vram_gb:
                continue
            results.append(m)
        return results

    def get_stats(self) -> dict:
        """注册表统计。"""
        by_category = {}
        for m in self._motifs.values():
            by_category[m.category] = by_category.get(m.category, 0) + 1
        return {
            "total": len(self._motifs),
            "unique": len(set(m.canonical_hash for m in self._motifs.values())),
            "by_category": by_category,
        }

    def list_all(self) -> list[MotifDefinition]:
        return list(self._motifs.values())

    def remove(self, motif_id: str) -> bool:
        motif = self._motifs.pop(motif_id, None)
        if motif:
            self._hashes.pop(motif.canonical_hash, None)
            return True
        return False


# ═══════════════════════════════════════════════════════════════════
# 从旧的 BUILTIN_MOTIFS 迁移
# ═══════════════════════════════════════════════════════════════════


def migrate_from_old(registry: MotifRegistry) -> int:
    """将旧的 BUILTIN_MOTIFS 迁移到新的 MotifRegistry。"""
    from core.comfyui_compiler import BUILTIN_MOTIFS as old_motifs

    count = 0
    for mid, old in old_motifs.items():
        motif = MotifDefinition(
            motif_id=mid,
            name=old.name,
            description=old.description,
            category=old.category,
            task_types=["txt2img"],
            nodes=[
                MotifNode(
                    role=mid,
                    class_type=old.class_type,
                    params=dict(old.default_params),
                )
            ],
            ports=[
                MotifPort(name=out_name, data_type=out_type, direction="output")
                for out_name, out_type in old.outputs.items()
            ],
            quality_score=0.9,
            version="1.0.0",
        )
        if registry.register(motif, source="migration"):
            count += 1
    return count


# ═══════════════════════════════════════════════════════════════════
# 内置 Motif 库（新格式）
# ═══════════════════════════════════════════════════════════════════


def build_default_motifs() -> list[MotifDefinition]:
    """构建默认 Motif 库。"""
    return [
        MotifDefinition(
            motif_id="txt2img_basic",
            name="Basic Text-to-Image",
            description="标准文生图管线：Checkpoint → CLIP Encode → KSampler → VAE Decode → Save",
            category="pipeline",
            task_types=["txt2img"],
            nodes=[
                MotifNode(role="model_loader", class_type="CheckpointLoaderSimple", params={"ckpt_name": ""}),
                MotifNode(role="text_encoder_pos", class_type="CLIPTextEncode", params={"text": ""}),
                MotifNode(role="text_encoder_neg", class_type="CLIPTextEncode", params={"text": ""}),
                MotifNode(
                    role="latent_init",
                    class_type="EmptyLatentImage",
                    params={"width": 1024, "height": 1024, "batch_size": 1},
                    param_ranges={
                        "width": {"type": "int", "min": 64, "max": 2048, "default": 1024, "step": 64},
                        "height": {"type": "int", "min": 64, "max": 2048, "default": 1024, "step": 64},
                    },
                ),
                MotifNode(
                    role="sampler",
                    class_type="KSampler",
                    params={"seed": -1, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal"},
                    param_ranges={
                        "steps": {"type": "int", "min": 1, "max": 80, "default": 20},
                        "cfg": {"type": "float", "min": 1.0, "max": 30.0, "default": 7.0},
                    },
                ),
                MotifNode(role="vae_decode", class_type="VAEDecode"),
                MotifNode(role="image_output", class_type="SaveImage"),
            ],
            edges=[
                MotifEdge("model_loader", "model", "sampler", "model", "MODEL"),
                MotifEdge("model_loader", "clip", "text_encoder_pos", "clip", "CLIP"),
                MotifEdge("model_loader", "clip", "text_encoder_neg", "clip", "CLIP"),
                MotifEdge("model_loader", "vae", "vae_decode", "vae", "VAE"),
                MotifEdge("text_encoder_pos", "conditioning", "sampler", "positive", "CONDITIONING"),
                MotifEdge("text_encoder_neg", "conditioning", "sampler", "negative", "CONDITIONING"),
                MotifEdge("latent_init", "latent", "sampler", "latent_image", "LATENT"),
                MotifEdge("sampler", "latent", "vae_decode", "samples", "LATENT"),
                MotifEdge("vae_decode", "image", "image_output", "images", "IMAGE"),
            ],
            quality_score=1.0,
            version="1.0.0",
        ),
        MotifDefinition(
            motif_id="lora_enhanced",
            name="LoRA Enhanced Text-to-Image",
            description="文生图 + LoRA 加载：Checkpoint → LoRA → CLIP Encode → KSampler → VAE Decode",
            category="pipeline",
            task_types=["txt2img", "img2img"],
            nodes=[
                MotifNode(role="model_loader", class_type="CheckpointLoaderSimple"),
                MotifNode(
                    role="lora_loader",
                    class_type="LoraLoader",
                    params={"strength_model": 1.0, "strength_clip": 1.0},
                    param_ranges={
                        "strength_model": {"type": "float", "min": 0.0, "max": 2.0, "default": 1.0},
                        "strength_clip": {"type": "float", "min": 0.0, "max": 2.0, "default": 1.0},
                    },
                ),
                MotifNode(role="text_encoder_pos", class_type="CLIPTextEncode"),
                MotifNode(role="text_encoder_neg", class_type="CLIPTextEncode"),
                MotifNode(role="latent_init", class_type="EmptyLatentImage"),
                MotifNode(role="sampler", class_type="KSampler"),
                MotifNode(role="vae_decode", class_type="VAEDecode"),
                MotifNode(role="image_output", class_type="SaveImage"),
            ],
            edges=[
                MotifEdge("model_loader", "model", "lora_loader", "model", "MODEL"),
                MotifEdge("model_loader", "clip", "lora_loader", "clip", "CLIP"),
                MotifEdge("lora_loader", "model", "sampler", "model", "MODEL"),
                MotifEdge("lora_loader", "clip", "text_encoder_pos", "clip", "CLIP"),
                MotifEdge("lora_loader", "clip", "text_encoder_neg", "clip", "CLIP"),
                MotifEdge("model_loader", "vae", "vae_decode", "vae", "VAE"),
                MotifEdge("text_encoder_pos", "conditioning", "sampler", "positive", "CONDITIONING"),
                MotifEdge("text_encoder_neg", "conditioning", "sampler", "negative", "CONDITIONING"),
                MotifEdge("latent_init", "latent", "sampler", "latent_image", "LATENT"),
                MotifEdge("sampler", "latent", "vae_decode", "samples", "LATENT"),
                MotifEdge("vae_decode", "image", "image_output", "images", "IMAGE"),
            ],
            compatible_models=["sd_xl_base_1.0.safetensors", "sd_xl_refiner_1.0.safetensors"],
            quality_score=0.95,
            version="1.0.0",
        ),
        MotifDefinition(
            motif_id="img2img_basic",
            name="Basic Image-to-Image",
            description="图生图管线：加载图像 → VAE Encode → KSampler(img2img) → VAE Decode",
            category="pipeline",
            task_types=["img2img"],
            nodes=[
                MotifNode(role="model_loader", class_type="CheckpointLoaderSimple"),
                MotifNode(role="text_encoder_pos", class_type="CLIPTextEncode"),
                MotifNode(role="text_encoder_neg", class_type="CLIPTextEncode"),
                MotifNode(role="image_loader", class_type="LoadImage"),
                MotifNode(role="vae_encode", class_type="VAEEncode"),
                MotifNode(
                    role="sampler",
                    class_type="KSampler",
                    params={"denoise": 0.7},
                    param_ranges={"denoise": {"type": "float", "min": 0.0, "max": 1.0, "default": 0.7}},
                ),
                MotifNode(role="vae_decode", class_type="VAEDecode"),
                MotifNode(role="image_output", class_type="SaveImage"),
            ],
            edges=[
                MotifEdge("model_loader", "model", "sampler", "model", "MODEL"),
                MotifEdge("model_loader", "clip", "text_encoder_pos", "clip", "CLIP"),
                MotifEdge("model_loader", "clip", "text_encoder_neg", "clip", "CLIP"),
                MotifEdge("image_loader", "image", "vae_encode", "pixels", "IMAGE"),
                MotifEdge("model_loader", "vae", "vae_encode", "vae", "VAE"),
                MotifEdge("model_loader", "vae", "vae_decode", "vae", "VAE"),
                MotifEdge("text_encoder_pos", "conditioning", "sampler", "positive", "CONDITIONING"),
                MotifEdge("text_encoder_neg", "conditioning", "sampler", "negative", "CONDITIONING"),
                MotifEdge("vae_encode", "latent", "sampler", "latent_image", "LATENT"),
                MotifEdge("sampler", "latent", "vae_decode", "samples", "LATENT"),
                MotifEdge("vae_decode", "image", "image_output", "images", "IMAGE"),
            ],
            quality_score=0.9,
            version="1.0.0",
        ),
    ]


# ═══════════════════════════════════════════════════════════════════
# 全局实例
# ═══════════════════════════════════════════════════════════════════

_default_registry: MotifRegistry | None = None


def get_registry() -> MotifRegistry:
    """获取全局 MotifRegistry（懒加载）。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = MotifRegistry()
        # 注册默认 Motif
        for motif in build_default_motifs():
            _default_registry.register(motif, source="builtin")
        # 迁移旧的
        migrate_from_old(_default_registry)
    return _default_registry


def reset_registry() -> MotifRegistry:
    """重置注册表（测试用）。"""
    global _default_registry
    _default_registry = MotifRegistry()
    return _default_registry
