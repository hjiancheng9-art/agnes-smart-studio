"""Blueprint TypedDict / dataclass 类型定义"""

from __future__ import annotations
from typing import TypedDict, Optional, Any
from dataclasses import dataclass, field


# ── Blueprint JSON 结构类型 ──


class BlueprintMeta(TypedDict, total=False):
    """元信息"""
    created_at: str
    updated_at: str
    changelog: list[str]
    total_nodes: int
    total_edges: int


class BlueprintSlot(TypedDict, total=False):
    """蓝图槽位 — 把节点输入参数抽象为可填的孔"""
    node_id: str
    input_name: str
    type: str  # text, image, number, boolean, choice, latent, seed, model, vae, clip, lora
    description: str
    default: Any
    min: float
    max: float
    choices: list[str]
    required: bool
    expose_to_ui: bool
    ui_label: str
    ui_group: str


class BlueprintRequirement(TypedDict, total=False):
    """节点需求"""
    class_type: str
    reason: str
    fallback: str


class BlueprintInputContract(TypedDict, total=False):
    """输入契约"""
    fields: list[dict]
    prompt_template: str


class BlueprintOutputContract(TypedDict, total=False):
    """输出契约"""
    fields: list[dict]


class BlueprintGraphTemplate(TypedDict, total=False):
    """图模板 — 节点+边的骨架"""
    nodes: list[dict]
    edges: list[dict]
    entry_points: list[str]
    exit_points: list[str]


class BlueprintQualityMode(TypedDict, total=False):
    """质量模式 (draft/standard/quality)"""
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    resolution: str


class BlueprintValidation(TypedDict, total=False):
    """验证信息"""
    required_vram_gb: float
    tested_models: list[str]
    known_issues: list[str]
    golden_texts: list[dict]


class ProductionBlueprint(TypedDict, total=False):
    """完整的生产级蓝图"""
    schema_version: str
    id: str
    name: str
    version: str
    status: str  # stable, beta, deprecated
    source: dict
    capability: dict
    requirements: dict
    input_contract: BlueprintInputContract
    output_contract: BlueprintOutputContract
    graph_template: BlueprintGraphTemplate
    slots: dict[str, BlueprintSlot]
    quality_modes: dict[str, BlueprintQualityMode]
    validation: BlueprintValidation
    metadata: BlueprintMeta


# ── 内部数据结构 ──


@dataclass
class NormalizedWorkflow:
    """归一化的 workflow 表示"""
    prompt: dict[str, dict[str, Any]]
    source_format: str  # "api" | "ui"
    workflow_id: str = ""


@dataclass
class ExtractedNode:
    id: str
    class_type: str
    inputs: dict[str, Any]
    role: str = "intermediate"  # "input" | "output" | "intermediate"


@dataclass
class ExtractedEdge:
    from_node: str
    from_slot: int
    to_node: str
    to_slot: int
    type: str = "default"


@dataclass
class ExtractedWorkflow:
    """从 workflow 提取的结构化数据"""
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]
    models: list[dict]
    params: dict[str, Any]
    task_type: str = "unknown"
