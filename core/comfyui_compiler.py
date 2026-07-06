"""ComfyUI Compiler — 工作流编译协议 (CWIM 原则 3 实现)

LLM 不直接生成 ComfyUI JSON。
LLM 生成 TaskSpec / WorkflowIR，GraphCompiler 确定性生成 ComfyUI workflow。

层：
    User Request
        ↓
    TaskSpec             # 用户任务规格（无节点名）
        ↓
    WorkflowIR           # 抽象工作流中间表示
        ↓
    GraphCompiler        # 编译为 ComfyUI API JSON
        ↓
    Validator            # 编译后验证 (comfyui_validator.py)

参考: COMFYUI_METHODOLOGY.md 原则 3
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# TaskSpec — 用户任务规格 (原则 3: LLM 输出)
# ═══════════════════════════════════════════════════════════════════

TaskType = Literal[
    "txt2img",
    "img2img",
    "inpaint",
    "controlnet",
    "ip_adapter",
    "upscale",
    "image_to_video",
    "text_to_video",
    "lora_training",
    "pipeline",
]

QualityTarget = Literal["preview", "balanced", "production"]


@dataclass
class AssetRef:
    """任务输入/输出资产引用。"""
    asset_type: str  # image / video / mask / control_image
    uri: str | None = None  # 文件路径或 URL
    metadata: dict = field(default_factory=dict)  # 尺寸/格式等


@dataclass
class TaskConstraint:
    """硬件/时间约束。"""
    vram_gb: int | None = None
    timeout_seconds: int = 900
    allow_lora: bool = True
    allow_controlnet: bool = True
    allow_upscale: bool = True
    prefer_batch: bool = False
    max_resolution: str = "2048x2048"


@dataclass
class TaskSpec:
    """用户任务的结构化结果 (L1: TaskSpec)。

    LLM 填入此结构，不涉及任何 ComfyUI 节点名。
    """
    task_id: str
    intent: str  # 用户原始意图描述
    task_type: TaskType

    prompt: str | None = None
    negative_prompt: str | None = None

    input_assets: list[AssetRef] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)  # image / video / lora / json
    output_specs: dict = field(default_factory=dict)  # {width, height, format, fps, duration}

    style_tags: list[str] = field(default_factory=list)  # photorealistic / anime / watercolor ...
    quality: QualityTarget = "balanced"

    constraints: TaskConstraint = field(default_factory=TaskConstraint)
    lora_refs: list[str] = field(default_factory=list)  # 需要的 LoRA 名称
    controlnet_refs: list[str] = field(default_factory=list)  # 需要的 ControlNet 名称
    model_preference: str | None = None  # 优先模型

    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "intent": self.intent,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "input_assets": [{"asset_type": a.asset_type, "uri": a.uri, "metadata": a.metadata} for a in self.input_assets],
            "output_types": self.output_types,
            "output_specs": self.output_specs,
            "style_tags": self.style_tags,
            "quality": self.quality,
            "constraints": {
                "vram_gb": self.constraints.vram_gb,
                "timeout_seconds": self.constraints.timeout_seconds,
            },
            "lora_refs": self.lora_refs,
            "controlnet_refs": self.controlnet_refs,
            "model_preference": self.model_preference,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════
# WorkflowIR — 抽象工作流中间表示 (原则 3: 编译中间层)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class IRComponent:
    """WorkflowIR 组件 — 用 role/motif 描述，不直接用 node_id。"""
    id: str
    role: str  # model_loader / text_encoder / sampler / vae_decode / image_output ...
    motif: str | None = None  # checkpoint_loader / clip_text_encode / ksampler ...
    node_class: str | None = None  # 可选覆盖，默认由 motif 解析
    model_family: str | None = None  # sdxl / sd15 / flux ...
    params: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class IRConnection:
    """WorkflowIR 连接 — 抽象边。"""
    from_component: str
    from_port: str
    to_component: str
    to_port: str
    data_type: str = "LATENT"  # MODEL / CLIP / VAE / LATENT / IMAGE / CONDITIONING / VIDEO


@dataclass
class IROutput:
    """WorkflowIR 输出定义。"""
    id: str
    type: str  # image / video / lora
    from_component: str
    from_port: str = "images"


@dataclass
class WorkflowIR:
    """抽象工作流中间表示 (L2: WorkflowIR)。

    仍不直接等于 ComfyUI JSON。使用 component/motif/role。
    """
    ir_id: str
    graph_type: str  # single_workflow / multi_stage_pipeline
    task_type: str

    components: list[IRComponent] = field(default_factory=list)
    connections: list[IRConnection] = field(default_factory=list)
    params: dict = field(default_factory=dict)

    requirements: dict = field(default_factory=dict)  # {models, custom_nodes, lora}
    outputs: list[IROutput] = field(default_factory=list)

    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ir_id": self.ir_id,
            "graph_type": self.graph_type,
            "task_type": self.task_type,
            "components": [
                {
                    "id": c.id, "role": c.role, "motif": c.motif,
                    "node_class": c.node_class, "model_family": c.model_family,
                    "params": c.params, "metadata": c.metadata,
                }
                for c in self.components
            ],
            "connections": [
                {
                    "from_component": c.from_component, "from_port": c.from_port,
                    "to_component": c.to_component, "to_port": c.to_port,
                    "data_type": c.data_type,
                }
                for c in self.connections
            ],
            "params": self.params,
            "requirements": self.requirements,
            "outputs": [
                {"id": o.id, "type": o.type, "from_component": o.from_component, "from_port": o.from_port}
                for o in self.outputs
            ],
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════
# Motif 库 — 可复用工作流子图模式
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MotifDefinition:
    """可复用的工作流子图模式定义。"""
    motif_id: str
    name: str
    description: str
    category: str  # loader / encoder / sampler / decoder / output
    class_type: str  # ComfyUI 节点类名
    inputs: dict = field(default_factory=dict)  # {input_name: data_type}
    outputs: dict = field(default_factory=dict)  # {output_name: data_type}
    default_params: dict = field(default_factory=dict)
    model_family: str | None = None


# 内置 Motif 库
BUILTIN_MOTIFS: dict[str, MotifDefinition] = {
    "checkpoint_loader": MotifDefinition(
        motif_id="checkpoint_loader",
        name="Checkpoint Loader",
        description="加载基础模型",
        category="loader",
        class_type="CheckpointLoaderSimple",
        inputs={},
        outputs={"model": "MODEL", "clip": "CLIP", "vae": "VAE"},
        default_params={"ckpt_name": ""},
    ),
    "clip_text_encode": MotifDefinition(
        motif_id="clip_text_encode",
        name="CLIP Text Encode",
        description="文本编码",
        category="encoder",
        class_type="CLIPTextEncode",
        inputs={"clip": "CLIP"},
        outputs={"conditioning": "CONDITIONING"},
        default_params={"text": ""},
    ),
    "ksampler": MotifDefinition(
        motif_id="ksampler",
        name="KSampler",
        description="采样器",
        category="sampler",
        class_type="KSampler",
        inputs={
            "model": "MODEL",
            "positive": "CONDITIONING",
            "negative": "CONDITIONING",
            "latent_image": "LATENT",
        },
        outputs={"latent": "LATENT"},
        default_params={
            "seed": -1,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
        },
    ),
    "empty_latent": MotifDefinition(
        motif_id="empty_latent",
        name="Empty Latent Image",
        description="空潜空间",
        category="sampler",
        class_type="EmptyLatentImage",
        inputs={},
        outputs={"latent": "LATENT"},
        default_params={"width": 1024, "height": 1024, "batch_size": 1},
    ),
    "vae_decode": MotifDefinition(
        motif_id="vae_decode",
        name="VAE Decode",
        description="VAE 解码",
        category="decoder",
        class_type="VAEDecode",
        inputs={"samples": "LATENT", "vae": "VAE"},
        outputs={"image": "IMAGE"},
        default_params={},
    ),
    "save_image": MotifDefinition(
        motif_id="save_image",
        name="Save Image",
        description="保存图像",
        category="output",
        class_type="SaveImage",
        inputs={"images": "IMAGE"},
        outputs={"images": "IMAGE"},
        default_params={"filename_prefix": "ComfyUI"},
    ),
    "lora_loader": MotifDefinition(
        motif_id="lora_loader",
        name="LoRA Loader",
        description="加载 LoRA 权重",
        category="loader",
        class_type="LoraLoader",
        inputs={"model": "MODEL", "clip": "CLIP"},
        outputs={"model": "MODEL", "clip": "CLIP"},
        default_params={"lora_name": "", "strength_model": 1.0, "strength_clip": 1.0},
    ),
    "upscale": MotifDefinition(
        motif_id="upscale",
        name="Upscale Image",
        description="图像放大",
        category="decoder",
        class_type="UpscaleImage",
        inputs={"image": "IMAGE"},
        outputs={"image": "IMAGE"},
        default_params={"upscale_model": "4x_NMKD-Superscale-SP_178000_G.pth"},
    ),
    "controlnet_loader": MotifDefinition(
        motif_id="controlnet_loader",
        name="ControlNet Loader",
        description="加载 ControlNet",
        category="loader",
        class_type="ControlNetLoader",
        inputs={},
        outputs={"controlnet": "CONTROL_NET"},
        default_params={"controlnet_name": ""},
    ),
}

# ═══════════════════════════════════════════════════════════════════
# GraphCompiler — 确定性编译器
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CompiledWorkflow:
    """编译产物。"""
    workflow: dict  # ComfyUI API 格式 JSON
    ir: WorkflowIR
    node_map: dict  # {component_id: node_id}
    diagnostics: list[str]
    warnings: list[str]
    is_valid: bool = True


class GraphCompiler:
    """WorkflowIR → ComfyUI API JSON 的确定性编译器。

    不"猜"，根据 Motif 库 + 节点本体 + 参数引擎 确定性地编译。
    """

    def __init__(self, motifs: dict[str, MotifDefinition] | None = None):
        self._motifs = motifs or BUILTIN_MOTIFS
        self._node_counter: int = 0

    def compile(self, ir: WorkflowIR, node_ontology: dict | None = None) -> CompiledWorkflow:
        """编译 WorkflowIR 为 ComfyUI API JSON。"""
        workflow: dict = {}
        node_map: dict = {}
        diagnostics: list[str] = []
        warnings: list[str] = []
        self._node_counter = 1

        try:
            # 1. 为每个组件分配 node_id 并实例化
            for component in ir.components:
                motif = self._resolve_motif(component)
                if not motif:
                    warnings.append(f"未知 motif: {component.role}/{component.motif}")
                    motif = self._resolve_motif_by_role(component)
                    if not motif:
                        raise ValueError(f"无法解析组件 {component.id}/{component.role}")

                node_id = str(self._node_counter)
                self._node_counter += 1
                node_map[component.id] = node_id

                node = {
                    "class_type": motif.class_type,
                    "inputs": {**motif.default_params, **component.params},
                }
                workflow[node_id] = node
                diagnostics.append(f"✓ {component.id} → node {node_id} ({motif.class_type})")

            # 2. 建立连接
            for conn in ir.connections:
                from_nid = node_map.get(conn.from_component)
                to_nid = node_map.get(conn.to_component)
                if not from_nid:
                    diagnostics.append(f"✗ 连接源缺失: {conn.from_component}")
                    continue
                if not to_nid:
                    diagnostics.append(f"✗ 连接目标缺失: {conn.to_component}")
                    continue

                # 找到目标节点中输入端口对应的输出源
                workflow[to_nid]["inputs"][conn.to_port] = [from_nid, 0]
                diagnostics.append(f"✓ {conn.from_component}.{conn.from_port} → {conn.to_component}.{conn.to_port}")

            # 3. 自动补全默认连接（如果有 Motif 默认连接）
            # (简化版：仅处理显式连接)

            return CompiledWorkflow(
                workflow=workflow,
                ir=ir,
                node_map=node_map,
                diagnostics=diagnostics,
                warnings=warnings,
                is_valid=True,
            )

        except Exception as e:
            logger.error("编译失败: %s", e)
            return CompiledWorkflow(
                workflow={},
                ir=ir,
                node_map=node_map,
                diagnostics=diagnostics + [f"✗ 编译错误: {e}"],
                warnings=warnings,
                is_valid=False,
            )

    def _resolve_motif(self, component: IRComponent) -> MotifDefinition | None:
        """根据 motif 名解析。"""
        if component.motif and component.motif in self._motifs:
            return self._motifs[component.motif]
        return None

    def _resolve_motif_by_role(self, component: IRComponent) -> MotifDefinition | None:
        """根据 role 名回退解析。"""
        role_to_motif = {
            "model_loader": "checkpoint_loader",
            "text_encoder_pos": "clip_text_encode",
            "text_encoder_neg": "clip_text_encode",
            "sampler": "ksampler",
            "latent_init": "empty_latent",
            "vae_decode": "vae_decode",
            "image_output": "save_image",
            "lora": "lora_loader",
            "upscale": "upscale",
            "controlnet": "controlnet_loader",
        }
        motif_id = role_to_motif.get(component.role)
        if motif_id:
            return self._motifs.get(motif_id)
        return None


# ═══════════════════════════════════════════════════════════════════
# TaskSpec 构建器 — LLM 输出 TaskSpec 的辅助工具
# ═══════════════════════════════════════════════════════════════════

def build_txt2img_spec(intent: str, prompt: str, negative_prompt: str = "",
                       width: int = 1024, height: int = 1024,
                       quality: QualityTarget = "balanced",
                       style_tags: list[str] | None = None,
                       lora_refs: list[str] | None = None,
                       model_preference: str | None = None) -> TaskSpec:
    """快速构建文生图 TaskSpec。"""
    return TaskSpec(
        task_id=f"txt2img_{abs(hash(prompt)) % 100000}",
        intent=intent,
        task_type="txt2img",
        prompt=prompt,
        negative_prompt=negative_prompt or "low quality, blurry, distorted, bad anatomy",
        input_assets=[],
        output_types=["image"],
        output_specs={"width": width, "height": height, "format": "png"},
        style_tags=style_tags or [],
        quality=quality,
        lora_refs=lora_refs or [],
        model_preference=model_preference,
    )


def spec_to_workflow_ir(spec: TaskSpec, ir_id: str | None = None) -> WorkflowIR:
    """将 TaskSpec 转换为基础 WorkflowIR。

    这是 LLM 输出 TaskSpec → WorkflowIR 的标准转换。
    """
    ir = WorkflowIR(
        ir_id=ir_id or f"ir_{spec.task_id}",
        graph_type="single_workflow",
        task_type=spec.task_type,
        params={
            "width": spec.output_specs.get("width", 1024),
            "height": spec.output_specs.get("height", 1024),
            "seed": -1,
        },
    )

    # 添加模型加载
    ir.components.append(IRComponent(
        id="checkpoint",
        role="model_loader",
        motif="checkpoint_loader",
        params={"ckpt_name": spec.model_preference or ""},
        model_family="sdxl",
    ))

    # 添加 LoRA
    for i, lora_name in enumerate(spec.lora_refs):
        ir.components.append(IRComponent(
            id=f"lora_{i}",
            role="lora",
            motif="lora_loader",
            params={"lora_name": lora_name, "strength_model": 1.0, "strength_clip": 1.0},
        ))

    # 添加文本编码
    ir.components.append(IRComponent(
        id="positive",
        role="text_encoder_pos",
        motif="clip_text_encode",
        params={"text": spec.prompt or ""},
    ))
    ir.components.append(IRComponent(
        id="negative",
        role="text_encoder_neg",
        motif="clip_text_encode",
        params={"text": spec.negative_prompt or ""},
    ))

    # 添加潜空间
    ir.components.append(IRComponent(
        id="latent",
        role="latent_init",
        motif="empty_latent",
        params={
            "width": spec.output_specs.get("width", 1024),
            "height": spec.output_specs.get("height", 1024),
            "batch_size": 1,
        },
    ))

    # 添加采样器
    ir.components.append(IRComponent(
        id="sampler",
        role="sampler",
        motif="ksampler",
        params={
            "seed": -1,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
        },
    ))

    # 添加解码器
    ir.components.append(IRComponent(
        id="decode",
        role="vae_decode",
        motif="vae_decode",
    ))

    # 添加输出
    ir.components.append(IRComponent(
        id="save",
        role="image_output",
        motif="save_image",
        params={"filename_prefix": "ComfyUI"},
    ))

    # 建立默认连接
    default_connections = [
        IRConnection("checkpoint", "model", "sampler", "model", "MODEL"),
        IRConnection("checkpoint", "clip", "positive", "clip", "CLIP"),
        IRConnection("checkpoint", "clip", "negative", "clip", "CLIP"),
        IRConnection("checkpoint", "vae", "decode", "vae", "VAE"),
        IRConnection("positive", "conditioning", "sampler", "positive", "CONDITIONING"),
        IRConnection("negative", "conditioning", "sampler", "negative", "CONDITIONING"),
        IRConnection("latent", "latent", "sampler", "latent_image", "LATENT"),
        IRConnection("sampler", "latent", "decode", "samples", "LATENT"),
        IRConnection("decode", "image", "save", "images", "IMAGE"),
    ]
    ir.connections = default_connections

    # 输出定义
    ir.outputs.append(IROutput(
        id="final_image",
        type="image",
        from_component="save",
        from_port="images",
    ))

    return ir


def compile_spec(spec: TaskSpec) -> CompiledWorkflow:
    """一键编译：TaskSpec → WorkflowIR → CompiledWorkflow。"""
    ir = spec_to_workflow_ir(spec)
    compiler = GraphCompiler()
    return compiler.compile(ir)
