"""ComfyFlow Compiler — 核心数据模型"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# =============================================================================
# 用户需求层
# =============================================================================

@dataclass
class TaskSpec:
    """结构化任务规格 — 系统的中间语言"""
    task_type: str                    # txt2img / img2img / video / controlnet / upscale / edit
    subject: str                      # 主体描述
    production_intent: str = ""       # 生产意图
    style: List[str] = field(default_factory=list)  # 风格标签
    mood: str = ""                    # 氛围/情绪
    aspect_ratio: str = "1:1"         # 宽高比
    quality_mode: str = "balanced"    # fast / balanced / high / cinematic
    needs_upscale: bool = False
    needs_controlnet: bool = False
    needs_video: bool = False
    reference_image: Optional[str] = None  # 参考图路径
    negative_prompt: str = "auto"
    extra_notes: str = ""


# =============================================================================
# 硬件与环境层
# =============================================================================

@dataclass
class HardwareProfile:
    """硬件配置档案"""
    gpu_name: Optional[str] = None
    vram_gb: float = 0.0
    ram_gb: float = 0.0
    cuda_available: bool = False
    compute_capability: str = ""
    source: str = "unknown"           # nvidia-smi / pynvml / torch / fallback
    error: Optional[str] = None


@dataclass
class RuntimeBudget:
    """运行时预算 — 基于硬件的生成能力评估"""
    tier: str = "unknown"             # minimal / low / medium / high / ultra
    vram_gb: float = 0.0
    max_resolution: str = "512x512"
    supports_sdxl: bool = False
    supports_flux: bool = False
    supports_flux_gguf: bool = False
    supports_refiner: bool = False
    supports_upscale: bool = False
    supports_controlnet: int = 0      # 最多几个 ControlNet
    supports_video: bool = False
    supports_wan: bool = False
    supports_ltx: bool = False
    max_batch_size: int = 1
    score: float = 0.0                # 0-10 预算分


@dataclass
class EnvironmentProfile:
    """ComfyUI 环境扫描结果"""
    comfyui_path: str = ""
    comfyui_version: str = ""
    custom_nodes: List[str] = field(default_factory=list)
    custom_node_packages: List[Dict[str, str]] = field(default_factory=list)
    checkpoints: List[str] = field(default_factory=list)
    loras: List[str] = field(default_factory=list)
    vaes: List[str] = field(default_factory=list)
    controlnet_models: List[str] = field(default_factory=list)
    upscale_models: List[str] = field(default_factory=list)
    video_models: List[str] = field(default_factory=list)
    unet_models: List[str] = field(default_factory=list)
    clip_models: List[str] = field(default_factory=list)
    has_sdxl: bool = False
    has_sd15: bool = False
    has_flux: bool = False
    has_ltx: bool = False
    has_wan: bool = False
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# 节点能力层
# =============================================================================

@dataclass
class NodeContract:
    """节点能力合同 — 不只是白名单"""
    class_type: str
    category: str                     # sampling / conditioning / latent / image / video / controlnet / upscale / io
    display_name: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    task_fit: List[str] = field(default_factory=list)  # 适合的任务类型
    quality_role: str = ""            # core_sampling / enhancement / control / preprocess / postprocess
    required: bool = False
    risk: str = "low"                 # low / medium / high_if_bad_params
    preferred_params: Dict[str, Any] = field(default_factory=dict)
    vram_cost: str = "low"            # low / medium / high
    depends_on_custom_node: Optional[str] = None


@dataclass
class ModelProfile:
    """模型档案"""
    filename: str
    model_type: str                   # checkpoint / lora / vae / controlnet / upscale / unet / clip
    base: str = ""                    # sd15 / sdxl / flux / sd3
    best_for: List[str] = field(default_factory=list)
    vram_cost: str = "medium"
    preferred_resolution: str = ""
    is_available: bool = True


# =============================================================================
# 蓝图层
# =============================================================================

@dataclass
class Blueprint:
    """蓝图 — 预审的工作流模板"""
    name: str
    display_name: str
    description: str
    task_type: str
    style_tags: List[str] = field(default_factory=list)
    required_nodes: List[str] = field(default_factory=list)
    optional_nodes: List[str] = field(default_factory=list)
    required_models: List[str] = field(default_factory=list)
    min_vram_gb: float = 0.0
    min_budget_score: float = 0.0
    nodes: Dict[str, Any] = field(default_factory=dict)  # 节点模板
    edges: List[tuple] = field(default_factory=list)       # (from_id, from_slot, to_id, to_slot)
    quality_score: float = 0.5
    chain_depth: int = 1              # 在多级降级链中的位置 (0=最高级)


@dataclass
class Recipe:
    """场景配方 — 面向用户的创意方案"""
    name: str
    user_label: str
    description: str = ""
    fits: List[str] = field(default_factory=list)  # 匹配的用户描述关键词
    preferred_blueprints: List[str] = field(default_factory=list)
    default_quality_mode: str = "balanced"
    prompt_enhancer: str = ""
    negative_prompt_policy: str = ""
    fallback_chain: List[str] = field(default_factory=list)


# =============================================================================
# 质量层
# =============================================================================

@dataclass
class QualityReport:
    """质量评估报告"""
    passed: bool = False
    overall_score: float = 0.0
    detail: Dict[str, float] = field(default_factory=dict)  # 各维度评分
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    user_friendly_message: str = ""


@dataclass
class BlueprintRequirement:
    """蓝图对硬件/环境的最低要求"""
    blueprint_name: str
    min_vram_gb: float = 0.0
    min_budget_score: float = 0.0
    requires_cuda: bool = True
    requires_model: List[str] = field(default_factory=list)
    requires_custom_node: List[str] = field(default_factory=list)
    quality_weight: float = 1.0


# =============================================================================
# 编译结果
# =============================================================================

@dataclass
class CompileResult:
    """编译结果 — 最终输出"""
    success: bool = False
    workflow_json: Optional[Dict[str, Any]] = None
    quality_report: Optional[QualityReport] = None
    blueprint_used: str = ""
    hardware_used: str = ""
    estimated_vram: str = ""
    user_summary: str = ""
    user_result: Optional[Any] = None   # UserFacingResult
    error: Optional[str] = None
    fallback_chain_used: List[str] = field(default_factory=list)

    def to_user_facing(self) -> Any:
        """把编译结果转成小白友好的展示层"""
        from .user_facing import build_user_result
        errors = []
        warnings = []
        if self.quality_report:
            warnings = self.quality_report.warnings
            for e in self.quality_report.errors:
                errors.append(e)
        if self.error:
            errors.append(self.error)

        # 从 vram 字符串提取数字
        vram = 0.0
        if self.estimated_vram:
            try:
                vram = float(self.estimated_vram.replace("GB", "").strip())
            except ValueError:
                pass

        return build_user_result(
            success=self.success,
            intent=self.blueprint_used,
            quality_mode="auto",
            blueprint_name=self.blueprint_used,
            gpu_name=self.hardware_used,
            vram_gb=vram,
            workflow_json=self.workflow_json,
            errors=errors if not self.success else None,
            warnings=warnings,
            technical_report={
                "blueprint": self.blueprint_used,
                "hardware": self.hardware_used,
                "vram": self.estimated_vram,
                "quality_report": self.quality_report.detail if self.quality_report else None,
                "fallback_chain": self.fallback_chain_used,
            } if not self.success else None,
        )
